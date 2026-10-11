"""Audio: voice + synthesized SFX (+ music bed, ducked under the voice) -> mix.wav; then mux + loudnorm."""

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfilt

SR = 48000
rng = np.random.default_rng(7)


def _place(buf, at, sig, gain):
    i = int(at * SR)
    if i < 0 or i >= len(buf):
        return
    n = min(len(sig), len(buf) - i)
    buf[i:i + n] += sig[:n] * gain


def _boom(L=2.0):
    t = np.arange(int(L * SR)) / SR
    f = 34 + 85 * np.exp(-t * 6)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.4)
    nz = sosfilt(butter(2, 900, "low", fs=SR, output="sos"), rng.standard_normal(len(t))) * np.exp(-t * 14) * .6
    return s + nz


def _whoosh(dur=.8, lo=300, hi=3500):
    L = int(dur * SR); t = np.arange(L) / SR; nz = rng.standard_normal(L); out = np.zeros(L)
    for j, fc in enumerate(np.linspace(lo, hi, 12)):
        a, b = j * L // 12, (j + 1) * L // 12
        out[a:b] = sosfilt(butter(2, [fc * .6, fc * 1.4], "band", fs=SR, output="sos"), nz[a:b])
    return out * np.sin(np.pi * t / dur) ** 2


def _tick(f=1800):
    t = np.arange(int(.06 * SR)) / SR
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 90)


def _hit():
    t = np.arange(int(.5 * SR)) / SR
    body = np.sin(2 * np.pi * np.cumsum(60 + 140 * np.exp(-t * 40)) / SR) * np.exp(-t * 12)
    snap = sosfilt(butter(2, 2500, "high", fs=SR, output="sos"), rng.standard_normal(len(t))) * np.exp(-t * 60) * .5
    return body + snap


def _riser(dur=1.4):
    L = int(dur * SR); t = np.arange(L) / SR
    f = 200 + 1400 * (t / dur) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * .25
    nz = sosfilt(butter(2, 3000, "high", fs=SR, output="sos"), rng.standard_normal(L)) * .3
    return (tone + nz) * (t / dur) ** 2


def _scan():
    t = np.arange(int(.7 * SR)) / SR
    return np.sin(2 * np.pi * (900 + 600 * np.sin(t * 30)) * t) * np.exp(-t * 4) * .35


def _music(T):
    """Placeholder bed (until royalty-free tracks land in 0004/music/): bright major pad + plucks."""
    N = int((T + 1) * SR); t = np.arange(N) / SR; music = np.zeros(N)
    mtof = lambda m: 440 * 2 ** ((m - 69) / 12)
    prog = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]  # C G Am F
    bars = 4.0
    for ci in range(int(T / bars) + 2):
        ch = prog[ci % 4]; a, b = ci * bars, (ci + 1) * bars
        ia, ib = int(max(0, a - 1) * SR), min(N, int((b + 1) * SR))
        if ia >= N:
            break
        tt = t[ia:ib]; env = np.clip((tt - (a - 1)) / 1, 0, 1) * np.clip(((b + 1) - tt) / 1, 0, 1)
        seg = sum(np.sin(2 * np.pi * mtof(m) * (1 + d) * tt) for m in ch for d in (-.002, 0, .002))
        music[ia:ib] += seg * env * .035
    step = 60 / 112 / 2; pt = np.arange(int(.4 * SR)) / SR
    for k in range(int(T / step)):
        ch = prog[int(k * step / bars) % 4]; f = mtof(ch[[0, 1, 2, 1][k % 4]] + 12)
        _place(music, k * step, np.sin(2 * np.pi * f * pt) * np.exp(-pt * 9), .03)
    return sosfilt(butter(2, 3200, "low", fs=SR, output="sos"), music)


def _load_music(N: int, music_dir) -> np.ndarray:
    """Loop a royalty-free track from music_dir (picked deterministically) under the whole video."""
    tracks = sorted(p for p in Path(music_dir).glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac"))
    if not tracks:
        return np.zeros(N)
    import subprocess as sp
    raw = sp.run(["ffmpeg", "-v", "error", "-i", str(tracks[N % len(tracks)]), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
    m = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    if not len(m):
        return np.zeros(N)
    m = np.tile(m, N // len(m) + 1)[:N]
    return m / max(np.max(np.abs(m)), 1e-6) * .25


def mix(tl: dict, voice_wav: Path, out: Path, music_gain=0.75, music_dir=None):
    T = tl["total"]; N = int((T + 1) * SR)
    v, vsr = sf.read(voice_wav, dtype="float32")
    if vsr != SR:
        v = resample_poly(v, SR, vsr).astype(np.float32)
    voice = np.zeros(N); voice[:min(N, len(v))] = v[:N]
    sfx = np.zeros(N)
    for e in tl["sfx"]:
        k, at = e["k"], e["t"]
        if k == "boom": _place(sfx, at, _boom(), .8)
        elif k == "whoosh": _place(sfx, at - .45, _whoosh(), .32)
        elif k == "swish": _place(sfx, at - .2, _whoosh(.45, 1500, 6000), .14)
        elif k == "thump": _place(sfx, at, _hit(), .10)
        elif k == "hit": _place(sfx, at, _hit(), .18)
        elif k == "riser": _place(sfx, at, _riser(), .35)
        elif k == "scan": _place(sfx, at, _scan(), .25)
        elif k == "react": _place(sfx, at - .25, _whoosh(.35, 800, 5000), .3); _place(sfx, at, _hit(), .35)
        elif k == "ticks":
            for i in range(10): _place(sfx, at + i * .1, _tick(1400 + i * 50), .16)
    music = _load_music(N, music_dir) * music_gain if music_dir else np.zeros(N)
    env = np.convolve(np.abs(voice), np.ones(int(.25 * SR)) / int(.25 * SR), mode="same")
    music *= 1 - .6 * np.clip(env / .02, 0, 1)
    music *= np.clip(np.arange(N) / SR / 2, 0, 1) * np.clip((T + .5 - np.arange(N) / SR) / 2, 0, 1)
    m = voice + music + sfx * .6
    m /= max(np.max(np.abs(m)) * 1.05, 1e-6)
    sf.write(out, m.astype(np.float32), SR)
    return out


def mux(video: Path, audio: Path, out: Path):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio), "-c:v", "copy",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", str(out)], check=True)
    return out

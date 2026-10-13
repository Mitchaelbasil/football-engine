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


# ---------- library (Drive 0004/sfx + 0004/music, synced to <assets>/sfx, <assets>/music by assets.py) ----------
CAP = {"impact": 1.6, "whoosh": 1.1, "title": 3.0, "overload": 1.6, "scouter": 2.0, "charge": 2.6, "aura": 3.0,
       "countdown": 1.6, "photo": 0.8, "shatter": 1.6, "money": 1.1, "notify": 1.1, "typing": 1.6, "list": 0.7,
       "censor": 1.0, "reaction": 2.0}
GAIN_DB = {"impact": -1, "title": -3, "aura": -4, "charge": -6, "scouter": -7, "overload": -5, "whoosh": -8,
           "photo": -8, "list": -11, "money": -5, "reaction": -3, "notify": -8, "typing": -10, "countdown": -4,
           "shatter": -4, "censor": -4}
MUSIC_GAP_DB, DUCK_DB, AMBIENCE_DB = -12.0, -6.0, -3.0   # bed vs speech level; extra dip while anyone talks
FALLBACK = {"impact": "hit", "whoosh": "whoosh", "charge": "riser", "scouter": "scan"}
_cache = {}


def _read(path: Path) -> np.ndarray:
    if path not in _cache:
        a, sr = sf.read(str(path), dtype="float32", always_2d=True)
        a = a.mean(1).astype(np.float64)
        if sr != SR:
            from math import gcd
            g = gcd(SR, sr); a = resample_poly(a, SR // g, sr // g)
        _cache[path] = a
    return _cache[path]


def _family(group: str) -> str:
    return "reaction" if group.startswith("reaction_") else group


class Library:
    def __init__(self, assets, seed: str = "", off=()):
        self.files = {}
        self.seed, self.last = seed, {}
        root = Path(assets) if assets else None
        if root and (root / "sfx").exists():
            for f in sorted((root / "sfx").rglob("*.wav")):
                if any(f"_{t}_" in f.name for t in off):
                    continue
                self.files.setdefault("sfx", []).append(f)
        if root and (root / "music").exists():
            self.files["music"] = sorted(p for p in (root / "music").rglob("*") if p.suffix.lower() in (".wav", ".mp3", ".flac", ".ogg"))

    def pick(self, kind: str, prefix: str, i: int):
        pool = [f for f in self.files.get(kind, []) if f.name.startswith(prefix)]
        if not pool:
            return None
        import random
        r = random.Random(f"{self.seed}|{prefix}|{i}")
        choice = r.choice(pool)
        if len(pool) > 1 and choice == self.last.get(prefix):
            choice = pool[(pool.index(choice) + 1) % len(pool)]
        self.last[prefix] = choice
        return choice


def _rms50_max(a: np.ndarray) -> float:
    w = int(.05 * SR)
    if len(a) < w:
        return float(np.sqrt(np.mean(a ** 2)) + 1e-9)
    c = np.concatenate([[0.0], np.cumsum(a ** 2)])
    return float(np.sqrt(np.max(c[w:] - c[:-w]) / w) + 1e-9)


def _clip(a: np.ndarray, cap: float) -> np.ndarray:
    n = min(len(a), int(cap * SR))
    out = a[:n].copy()
    f = min(n, int(.25 * SR))
    if len(a) > n and f:
        out[-f:] *= np.linspace(1, 0, f) ** 1.5
    return out


def _speech_level(voice: np.ndarray) -> float:
    act = voice[np.abs(voice) > 0.01]
    return float(np.sqrt(np.mean(act ** 2))) if len(act) else 0.05


def _place_lib(buf, e, a, level):
    """Line the clip up on the cue (attack / peak / onset), cap its length, level it, place it."""
    fam = _family(e["g"])
    pk = np.abs(a).max() + 1e-9
    if e.get("align") == "peak":
        anchor = int(np.argmax(np.abs(a[: int(6 * SR)])))
        if e.get("until") is not None:  # riser that must peak on a later moment
            dur = max(.3, e["until"] - e["t"])
            start_in = max(0, anchor - int(dur * SR))
            a = a[start_in:]; anchor -= start_in
            at = e["until"]
        else:
            at = e["t"]
        seg = a[: anchor + int(.6 * SR)] if fam in ("charge",) else a
        seg = _clip(seg, CAP.get(fam, 2.0) + anchor / SR)
        t0 = at - anchor / SR
    else:
        win = np.abs(a[: int((CAP.get(fam, 2.0) + 1.0) * SR)])  # judge the attack inside the part we keep
        on = np.flatnonzero(win > win.max() * (0.5 if e.get("align", "attack") == "attack" else 0.1))
        lead = on[0] if len(on) else 0
        seg = _clip(a[max(0, lead - int(.01 * SR)):], CAP.get(fam, 2.0))
        t0 = e["t"] - .01
    seg = seg * (level * 10 ** (GAIN_DB.get(fam, -6) / 20) / _rms50_max(seg))
    _place(buf, t0, seg, 1.0)


def _bed(N: int, beds: list, lib: Library, level: float, voice_env: np.ndarray) -> np.ndarray:
    """Music (or ambience) per segment: picked by mood prefix, looped with a crossfade, faded in/out, ducked under speech."""
    out = np.zeros(N)
    for i, b in enumerate(beds):
        amb = b["mood"] == "ambience"
        f = lib.pick("sfx", "ambience_", i) if amb else lib.pick("music", f"music_{b['mood']}_", i)
        if not f:
            print(f"  bed: no track for '{b['mood']}' - skipped")
            continue
        a = _read(f)
        if len(a) < SR:
            continue
        i0, i1 = int(b["t0"] * SR), min(N, int((b["t1"] + 1.0) * SR))
        L = i1 - i0
        xf = int(min(2.0, len(a) / SR / 4) * SR)
        seg = a.copy()
        while len(seg) < L:  # loop with crossfade
            ramp = np.linspace(0, 1, xf)
            seg = np.concatenate([seg[:-xf], seg[-xf:] * (1 - ramp) + a[:xf] * ramp, a[xf:]])
        seg = seg[:L]
        act = seg[np.abs(seg) > 1e-4]
        rms = float(np.sqrt(np.mean(act ** 2))) if len(act) else 1.0
        seg = seg * (level * 10 ** ((MUSIC_GAP_DB + (AMBIENCE_DB if amb else 0)) / 20) / rms)
        fi, fo = min(L, int(1.5 * SR)), min(L, int(2.0 * SR))
        seg[:fi] *= np.linspace(0, 1, fi); seg[-fo:] *= np.linspace(1, 0, fo)
        out[i0:i0 + L] += seg
        print(f"  bed {b['t0']:.1f}-{b['t1']:.1f}s: {f.name}")
    return out * (1 - (1 - 10 ** (DUCK_DB / 20)) * voice_env)


def mix(tl: dict, voice_wav: Path, out: Path, assets=None, off=()):
    T = tl["total"]; N = int((T + 1) * SR)
    v, vsr = sf.read(voice_wav, dtype="float32")
    if vsr != SR:
        v = resample_poly(v, SR, vsr).astype(np.float32)
    voice = np.zeros(N); voice[:min(N, len(v))] = v[:N]
    level = _speech_level(voice)
    lib = Library(assets, tl.get("seed", ""), off)
    sfx, used, n, last = np.zeros(N), [], {}, {}
    for e in tl["sfx"]:
        k, at = e.get("k"), e["t"]
        if e.get("g"):
            g = e["g"]; n[g] = n.get(g, 0) + 1
            if at - last.get(_family(g), -9) < 2.0:  # same kind of sound twice in 2 s sounds like a glitch
                continue
            last[_family(g)] = at
            f = lib.pick("sfx", g + "_", n[g])
            if f:
                _place_lib(sfx, e, _read(f), level); used.append(f"{at:7.2f}  {g:<16} {f.name}")
                continue
            k = FALLBACK.get(_family(g))
            if not k:
                continue
        if k == "boom": _place(sfx, at, _boom(), .8)
        elif k == "whoosh": _place(sfx, at - .45, _whoosh(), .32)
        elif k == "swish": _place(sfx, at - .2, _whoosh(.45, 1500, 6000), .14)
        elif k == "thump": _place(sfx, at, _hit(), .10)
        elif k == "hit": _place(sfx, at, _hit(), .18)
        elif k == "riser": _place(sfx, at, _riser(), .35)
        elif k == "scan": _place(sfx, at, _scan(), .25)
        elif k == "react": _place(sfx, at - .25, _whoosh(.35, 800, 5000), .3); _place(sfx, at, _hit(), .35)
        elif k == "ticks":
            for i in range(10): _place(sfx, at + i * .1, _tick(1400 + i * 50), .16 * level / .08)
    w = int(.25 * SR)
    c = np.concatenate([[0.0], np.cumsum(np.abs(voice))])
    idx = np.arange(N)
    lo, hi = np.clip(idx - w // 2, 0, N), np.clip(idx + w // 2, 0, N)
    env = np.clip((c[hi] - c[lo]) / w / (level * .5), 0, 1)  # moving average (cumsum: O(N))
    music = _bed(N, tl.get("beds", []), lib, level, env)
    m = voice + music + sfx
    sf.write(out, m.astype(np.float32), SR, subtype="FLOAT")
    tl["sfx_used"] = used
    return out


def _loudnorm_stats(audio: Path, chain: str, I, TP, LRA) -> dict:
    import json, re
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio), "-af",
                        f"{chain}loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    return json.loads(re.findall(r"\{[^{}]*\}", r.stderr)[-1])


def master(audio: Path, out: Path, I=-14.0, TP=-1.5, LRA=11.0) -> Path:
    """Gain to target, peak-limit, then a linear two-pass loudnorm. (Plain loudnorm undershot to about -15.3 LUFS:
    speech + SFX peaks hit the true-peak ceiling before the gain it needed, so the limiter has to run first.)"""
    raw = _loudnorm_stats(audio, "", I, TP, LRA)
    pre = f"volume={I - float(raw['input_i']):.2f}dB,alimiter=limit=0.75:attack=2:release=60:level=false,"
    m = _loudnorm_stats(audio, pre, I, TP, LRA)
    ln = (f"loudnorm=I={I}:TP={TP}:LRA={LRA}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(audio), "-af", pre + ln, "-ar", "48000", str(out)], check=True)
    return out


def mux(video: Path, audio: Path, out: Path):
    final = Path(audio).with_name(Path(audio).stem + "_master.wav")
    master(audio, final)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(final), "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", str(out)], check=True)
    return out

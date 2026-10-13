"""Voice backends. Each beat's `say` text -> mono float32 audio + word timings (seconds, clip-relative).

Backends:
  fake    - silent audio with estimated timings (local dev, no models)
  kokoro      - Kokoro-82M (kokoro:<voice>, e.g. kokoro:af_bella); word timings from the model
  chatterbox  - Mitchael's cloned voice on Kaggle GPU, Whisper-checked auto-retakes (kaggle_voice.py)

Two hosts: every beat has a speaker. "H" = host/storyteller (the backend above, af_bella),
"P" = pundit who takes over the "why" sections (always Kokoro, am_michael at speed 1.0).
"""

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 24000
_WORD = re.compile(r"[A-Za-z0-9'’\-]+")


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def _syllables(w: str) -> int:
    return max(1, len(re.findall(r"[aeiouy]+", w.lower())))


def _fake(text: str):
    words, t = [], 0.0
    for m in _WORD.finditer(text):
        w = m.group(0)
        d = 0.12 + 0.15 * _syllables(w)
        words.append({"w": w, "s": round(t, 3), "e": round(t + d, 3)})
        t += d + 0.05
        tail = text[m.end():m.end() + 1]
        if tail in ",;:":
            t += 0.22
        elif tail in ".!?":
            t += 0.12
    dur = t + 0.1
    return np.zeros(int(dur * SR), dtype=np.float32), words


_kokoro = {}
HOST_SPEED = 0.95
PUNDIT = ("am_michael", 1.0)   # locked 13 Oct (Mitchael picked Michael over George / Fenrir)


def beat_backend(backend: str, speaker: str, pundit: str = None) -> str:
    """Backend string for one beat. Host beats use the main backend; pundit beats use Kokoro (fake stays fake)."""
    if speaker != "P" or backend == "fake":
        return backend
    return f"kokoro:{pundit or PUNDIT[0]}@{PUNDIT[1]}"


def _kokoro_synth(text: str, voice: str = "bm_george", speed: float = 0.95):
    lang = "b" if voice.startswith("b") else "a"
    if lang not in _kokoro:
        from kokoro import KPipeline
        _kokoro[lang] = KPipeline(lang_code=lang)
    chunks, words, off = [], [], 0.0
    for res in _kokoro[lang](text, voice=voice, speed=speed):
        audio = res.audio.cpu().numpy() if hasattr(res.audio, "cpu") else np.asarray(res.audio)
        for tok in res.tokens or []:
            if tok.start_ts is None or not _WORD.search(tok.text or ""):
                continue
            words.append({"w": tok.text, "s": round(off + tok.start_ts, 3), "e": round(off + (tok.end_ts or tok.start_ts), 3)})
        chunks.append(audio.astype(np.float32))
        off += len(audio) / SR
    audio = np.concatenate(chunks) if chunks else np.zeros(SR // 2, dtype=np.float32)
    # trim leading/trailing silence, keep timings aligned
    nz = np.flatnonzero(np.abs(audio) > 0.004)
    if len(nz):
        a, b = max(0, nz[0] - int(0.03 * SR)), min(len(audio), nz[-1] + int(0.08 * SR))
        audio = audio[a:b]
        sh = a / SR
        words = [{"w": w["w"], "s": round(max(0, w["s"] - sh), 3), "e": round(max(0, w["e"] - sh), 3)} for w in words]
    if not words:
        _, words = _fake(text)
        k = (len(audio) / SR) / max(words[-1]["e"], 0.1)
        words = [{"w": w["w"], "s": round(w["s"] * k, 3), "e": round(w["e"] * k, 3)} for w in words]
    return audio, words


def _parse_kokoro(backend: str):
    """'kokoro' | 'kokoro:af_bella' | 'kokoro:am_michael@1.0' -> (voice, speed)"""
    v = backend.split(":", 1)[1] if ":" in backend else "bm_george"
    if "@" in v:
        v, sp = v.split("@", 1)
        return v, float(sp)
    return v, HOST_SPEED


def _key(backend: str, text: str) -> str:
    tag = backend
    if backend == "chatterbox":
        from kaggle_voice import CFG
        tag += json.dumps(CFG, sort_keys=True)
    return hashlib.sha1(f"{tag}|{text}".encode()).hexdigest()[:16]


def synth_beats(beats: list, backend: str, cache_dir: Path, pundit: str = None) -> list:
    """beats: [{'say': str, 'speaker': 'H'|'P'}] -> [{'wav', 'dur', 'words', 'speaker'}] (cached by text+voice)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    if backend == "chatterbox":  # one Kaggle GPU batch for every host sentence not cached yet
        todo, seen = [], set()
        for b in beats:
            if b.get("speaker", "H") == "P":
                continue
            k = _key(backend, b["say"])
            if k not in seen and not ((cache_dir / f"{k}.wav").exists() and (cache_dir / f"{k}.json").exists()):
                todo.append({"key": k, "text": b["say"]}); seen.add(k)
        if todo:
            from kaggle_voice import run
            run(todo, cache_dir)
    out = []
    for b in beats:
        text, spk = b["say"], b.get("speaker", "H")
        bk = beat_backend(backend, spk, pundit)
        key = _key(bk, text)
        wav, meta = cache_dir / f"{key}.wav", cache_dir / f"{key}.json"
        if not (wav.exists() and meta.exists()):
            if bk == "fake":
                audio, words = _fake(text)
            elif bk.startswith("kokoro"):
                v, sp = _parse_kokoro(bk)
                audio, words = _kokoro_synth(text, v, sp)
            else:
                raise ValueError(f"unknown voice backend {bk}")
            sf.write(wav, audio, SR)
            meta.write_text(json.dumps({"dur": len(audio) / SR, "words": words}))
        m = json.loads(meta.read_text())
        out.append({"wav": str(wav), "dur": m["dur"], "words": m["words"], "speaker": spk})
    return out

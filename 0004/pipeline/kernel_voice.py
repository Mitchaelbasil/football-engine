# Kaggle GPU job (generated per run by kaggle_voice.py): Chatterbox voice in Mitchael's cloned voice,
# one clip per sentence, with automatic retakes checked by Whisper. __JOBS__ / __CFG__ are filled in.
import difflib
import glob
import json
import os
import re
import subprocess
import sys
import time

JOBS = __JOBS__
CFG = __CFG__
OUT = "/kaggle/working/out"
os.makedirs(OUT, exist_ok=True)
t0 = time.time()
import traceback  # noqa: E402


def _fail(msg):
    open(f"{OUT}/error.txt", "w").write(msg)
    print(msg, flush=True)
    sys.exit(1)


r = subprocess.run(f"{sys.executable} -m pip install -q chatterbox-tts faster-whisper num2words 2>&1 | tail -15", shell=True, capture_output=True, text=True)
print("pip:", r.stdout[-1500:], flush=True)
subprocess.run(f"{sys.executable} -m pip uninstall -y -q torchvision", shell=True)  # torch is re-pinned by chatterbox; a stale torchvision breaks transformers imports
try:

    import numpy as np  # noqa: E402
    import soundfile as sf  # noqa: E402
    import torch  # noqa: E402
    import torchaudio  # noqa: E402
    from chatterbox.tts import ChatterboxTTS  # noqa: E402
    from faster_whisper import WhisperModel  # noqa: E402
    from num2words import num2words  # noqa: E402

    refs = glob.glob("/kaggle/input/**/voice_ref.wav", recursive=True)
    REF = refs[0] if refs else None
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print("device", dev, torch.cuda.get_device_name(0) if dev == "cuda" else "", "ref", REF, flush=True)
    tts = ChatterboxTTS.from_pretrained(device=dev)
    try:
        asr = WhisperModel(CFG["whisper"], device=dev, compute_type="float16" if dev == "cuda" else "int8")
    except Exception as e:  # cuDNN mismatch etc. -> CPU whisper is fine for short clips
        print("whisper on cpu:", e, flush=True)
        asr = WhisperModel(CFG["whisper"], device="cpu", compute_type="int8")
    SR = tts.sr


    def toks(s: str) -> list:
        s = s.lower().replace("–", " ").replace("-", " ").replace("’", "'")
        s = re.sub(r"\d+(\.\d+)?", lambda m: " " + num2words(float(m.group(0)) if "." in m.group(0) else int(m.group(0))) + " ", s)
        s = s.replace("-", " ").replace(",", " ")
        return re.findall(r"[a-z']+", s)


    def wer(a: list, b: list) -> float:
        d = list(range(len(b) + 1))
        for i in range(1, len(a) + 1):
            p, d[0] = d[0], i
            for j in range(1, len(b) + 1):
                p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (a[i - 1] != b[j - 1]))
        return d[len(b)] / max(1, len(a))


    def align(text: str, words: list) -> list:
        """Put Whisper's timings onto the SCRIPT's words (so 'Sixty' stays 'Sixty' even if Whisper wrote '60')."""
        sw = text.split()
        s_tok, s_own = [], []
        for i, w in enumerate(sw):
            for t in toks(w):
                s_tok.append(t); s_own.append(i)
        h_tok, h_t = [], []
        for w in words:
            tt = toks(w[0]) or [""]
            span = (w[2] - w[1]) / len(tt)
            for k, t in enumerate(tt):
                h_tok.append(t); h_t.append((w[1] + k * span, w[1] + (k + 1) * span))
        hit = {}
        for a, b, n in difflib.SequenceMatcher(None, s_tok, h_tok, autojunk=False).get_matching_blocks():
            for k in range(n):
                hit.setdefault(s_own[a + k], []).append(h_t[b + k])
        out = []
        for i, w in enumerate(sw):
            clean = re.sub(r"^[^\w']+|[^\w']+$", "", w)
            if not clean:
                continue
            if i in hit:
                out.append({"w": clean, "s": round(min(x[0] for x in hit[i]), 3), "e": round(max(x[1] for x in hit[i]), 3)})
            else:
                out.append({"w": clean, "s": None, "e": None})
        # interpolate unmatched words between known neighbours
        known = [k for k, x in enumerate(out) if x["s"] is not None]
        for k, x in enumerate(out):
            if x["s"] is None:
                prev = max([j for j in known if j < k], default=None)
                nxt = min([j for j in known if j > k], default=None)
                a = out[prev]["e"] if prev is not None else 0.0
                b = out[nxt]["s"] if nxt is not None else a + 0.4
                x["s"], x["e"] = round(a, 3), round(max(a, b), 3)
        return out


    summary = []
    for j in JOBS:
        best = None
        target = toks(j["text"])
        for k in range(CFG["tries"]):
            torch.manual_seed(1000 + k)
            kw = dict(exaggeration=CFG["exaggeration"], cfg_weight=CFG["cfg"], temperature=CFG["temperature"])
            if REF:
                kw["audio_prompt_path"] = REF
            a = tts.generate(j["text"], **kw).squeeze().cpu().numpy().astype(np.float32)
            tmp = f"/tmp/{j['key']}_{k}.wav"
            sf.write(tmp, a, SR)
            a16 = torchaudio.functional.resample(torch.from_numpy(a), SR, 16000).numpy()  # array in: avoids PyAV file decoding
            segs, _ = asr.transcribe(a16, language="en", word_timestamps=True, beam_size=5)
            ws = [(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or [])]
            e = wer(target, toks(" ".join(w[0] for w in ws)))
            dur = len(a) / SR
            tail = dur - (ws[-1][2] if ws else dur)
            score = e + (0.25 if tail > 1.2 else 0)
            if best is None or score < best["score"]:
                best = {"score": score, "wer": e, "a": a, "ws": ws, "try": k + 1}
            if e <= CFG["wer_ok"] and tail <= 1.2:
                break
        a, ws = best["a"], best["ws"]
        if ws:  # trim leading/trailing junk around the spoken words
            s0, s1 = max(0.0, ws[0][1] - 0.08), min(len(a) / SR, ws[-1][2] + 0.25)
            a = a[int(s0 * SR):int(s1 * SR)]
            ws = [(w[0], w[1] - s0, w[2] - s0) for w in ws]
        n = min(len(a), int(0.02 * SR)); a[:n] *= np.linspace(0, 1, n); a[len(a) - n:] *= np.linspace(1, 0, n)
        sf.write(f"{OUT}/{j['key']}.wav", a, SR)
        words = align(j["text"], ws) if ws else []
        json.dump({"dur": len(a) / SR, "words": words, "wer": round(best["wer"], 3), "tries": best["try"]}, open(f"{OUT}/{j['key']}.json", "w"))
        summary.append({"key": j["key"], "wer": round(best["wer"], 3), "tries": best["try"], "text": j["text"][:60]})
        print(f"{len(summary)}/{len(JOBS)} wer={best['wer']:.2f} tries={best['try']} :: {j['text'][:50]}", flush=True)

    json.dump({"items": summary, "seconds": round(time.time() - t0), "device": dev, "ref": bool(REF)}, open(f"{OUT}/summary.json", "w"))
    print("done", round(time.time() - t0), "s", flush=True)
except Exception:
    _fail(traceback.format_exc()[-6000:])

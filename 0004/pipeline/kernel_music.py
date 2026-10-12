# Kaggle GPU job (generated per run by kaggle_music.py): instrumental music with ACE-Step (Apache-2.0).
# __JOBS__ is filled in: [{"name": "music_tension_ace_01", "prompt": "...", "seconds": 90, "seed": 1234}, ...]
# Tries bf16 -> fp16 -> fp32 (+CPU offload) and keeps the first precision that produces sane audio.
import json
import os
import subprocess
import sys
import time
import traceback

JOBS = __JOBS__
OUT = "/kaggle/working/out"
os.makedirs(OUT, exist_ok=True)
t0 = time.time()


def _fail(msg):
    open(f"{OUT}/error.txt", "w").write(msg)
    print(msg, flush=True)
    sys.exit(1)


def pip(args):
    r = subprocess.run(f"{sys.executable} -m pip install -q {args} 2>&1 | tail -8", shell=True, capture_output=True, text=True)
    print("pip", args[:80], "->", r.stdout[-800:], flush=True)


def can_import():
    r = subprocess.run([sys.executable, "-c", "from acestep.pipeline_ace_step import ACEStepPipeline"],
                       capture_output=True, text=True)
    print("import check:", "ok" if r.returncode == 0 else r.stderr[-1200:], flush=True)
    return r.returncode == 0


# ACE-Step's requirements.txt pins old wheels (e.g. spacy==3.8.4) that don't exist for Kaggle's Python 3.13,
# so install the package without deps and add what it imports, unpinned; fall back to its pinned diffusers/transformers.
pip("--no-deps git+https://github.com/ace-step/ACE-Step.git")
pip("loguru pypinyin hangul-romanize py3langid num2words spacy opencc cutlet diffusers accelerate peft librosa soundfile")
if not can_import():
    pip('"diffusers==0.33.1" "transformers==4.50.0"')
    if not can_import():
        _fail("ACE-Step import failed after dependency fallback (see log)")

try:
    import numpy as np
    import soundfile as sf
    import torch

    dev_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    print("device", dev_name, "bf16", torch.cuda.is_available() and torch.cuda.is_bf16_supported(), flush=True)

    def bf16_native():
        if not torch.cuda.is_available():
            return False
        try:
            return torch.cuda.is_bf16_supported(including_emulation=False)
        except TypeError:
            return torch.cuda.get_device_capability(0)[0] >= 8

    attempts = [("bfloat16", False)] if bf16_native() else []
    attempts += [("float16", False), ("float32", True)]

    def sane(path):
        a, sr = sf.read(path, dtype="float32")
        if not np.isfinite(a).all():
            return False, "non-finite samples"
        rms = float(np.sqrt(np.mean(a ** 2)) + 1e-12)
        db = 20 * np.log10(rms)
        return db > -45, f"rms {db:.1f} dBFS, {len(a) / sr:.1f}s"

    from acestep.pipeline_ace_step import ACEStepPipeline

    done, pipe, used, items = set(), None, None, []
    for dtype, offload in attempts:
        os.environ["ACE_PIPELINE_DTYPE"] = dtype
        try:
            pipe = ACEStepPipeline(checkpoint_dir=None, dtype="bfloat16" if dtype == "bfloat16" else "float32",
                                   torch_compile=False, cpu_offload=offload, overlapped_decode=False)
            ok_all = True
            for j in JOBS:
                if j["name"] in done:
                    continue
                path = f"{OUT}/{j['name']}.wav"
                t = time.time()
                pipe(format="wav", audio_duration=float(j["seconds"]), prompt=j["prompt"], lyrics="[inst]",
                     infer_step=60, guidance_scale=15.0, scheduler_type="euler", cfg_type="apg", omega_scale=10.0,
                     manual_seeds=[int(j["seed"])], guidance_interval=0.5, guidance_interval_decay=0.0,
                     min_guidance_scale=3.0, use_erg_tag=True, use_erg_lyric=True, use_erg_diffusion=True,
                     oss_steps="", guidance_scale_text=0.0, guidance_scale_lyric=0.0, save_path=path)
                ok, why = sane(path)
                print(f"{j['name']}: {dtype} offload={offload} {why} ok={ok} in {time.time() - t:.0f}s", flush=True)
                if not ok:
                    ok_all = False
                    os.remove(path)
                    break
                done.add(j["name"])
                items.append({"name": j["name"], "dtype": dtype, "check": why, "seconds": round(time.time() - t)})
            if ok_all:
                used = dtype
                break
        except Exception:
            print(f"--- {dtype} failed ---\n{traceback.format_exc()[-2500:]}", flush=True)
        del pipe
        pipe = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    for p in os.listdir(OUT):  # keep only the wavs + our summary
        if p.endswith("_input_params.json"):
            os.remove(f"{OUT}/{p}")
    json.dump({"device": dev_name, "dtype": used, "items": items, "seconds": round(time.time() - t0)},
              open(f"{OUT}/summary.json", "w"), indent=1)
    if len(done) != len(JOBS):
        _fail(f"generated {len(done)}/{len(JOBS)} tracks on {dev_name}")
    print("done", used, round(time.time() - t0), "s", flush=True)
except SystemExit:
    raise
except Exception:
    _fail(traceback.format_exc()[-4000:])

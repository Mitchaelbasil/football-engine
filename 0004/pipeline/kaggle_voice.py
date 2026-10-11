"""Run the Chatterbox voice job on Kaggle's free GPU and drop the results into the local voice cache.

Needs Kaggle CLI auth in the environment (source 0004/pipeline/kaggle_auth.sh) and the private
dataset <user>/football-engine-voice-ref (made by the 0004-voice-ref workflow).
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = {"exaggeration": 0.7, "cfg": 0.3, "temperature": 0.8, "tries": 4, "wer_ok": 0.12, "whisper": "small.en"}
SLUG = "fe-voice"


def _k(*args, check=True) -> str:
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"kaggle {' '.join(args[:2])} failed: {(r.stderr or r.stdout)[-800:]}")
    return (r.stdout or "") + (r.stderr or "")


def run(jobs: list, cache_dir: Path, timeout_min: int = 80) -> dict:
    """jobs: [{'key': cache key, 'text': sentence}] -> writes <key>.wav/<key>.json into cache_dir."""
    user = os.environ.get("KAGGLE_USER", "mitchaelbasil")
    kid = f"{user}/{SLUG}"
    work = Path(tempfile.mkdtemp(prefix="kv_"))
    code = (HERE / "kernel_voice.py").read_text().replace("__JOBS__", json.dumps(jobs)).replace("__CFG__", json.dumps(CFG))
    (work / "run.py").write_text(code)
    (work / "kernel-metadata.json").write_text(json.dumps({
        "id": kid, "title": SLUG, "code_file": "run.py", "language": "python", "kernel_type": "script",
        "is_private": True, "enable_gpu": True, "enable_tpu": False, "enable_internet": True,
        "dataset_sources": [f"{user}/football-engine-voice-ref"], "competition_sources": [], "kernel_sources": [],
    }))
    print(f"kaggle: pushing voice job ({len(jobs)} sentences)", flush=True)
    print(_k("kernels", "push", "-p", str(work)).strip()[-300:], flush=True)
    t0, status = time.time(), ""
    time.sleep(30)
    while time.time() - t0 < timeout_min * 60:
        status = _k("kernels", "status", kid, check=False).lower()
        if "complete" in status or "error" in status or "cancel" in status:
            break
        time.sleep(30)
    print(f"kaggle: {status.strip()[-120:]} after {time.time() - t0:.0f}s", flush=True)
    out = work / "output"
    out.mkdir()
    dl = _k("kernels", "output", kid, "-p", str(out), check=False)
    if "complete" not in status:
        err = next(out.rglob("error.txt"), None)
        detail = err.read_text()[-3000:] if err else ""
        for lg in out.rglob("*.log"):
            try:
                lines = [x.get("data", "") for x in json.loads(lg.read_text())]
                detail += "\n--- log ---\n" + "".join(lines)[-3000:]
            except Exception:
                detail += "\n--- log ---\n" + lg.read_text()[-3000:]
        if not detail.strip():
            detail = f"(no log; files: {[p.name for p in out.rglob('*')]}; output cmd: {dl.strip()[-400:]})"
        raise RuntimeError(f"Kaggle voice job did not complete ({status.strip()[-80:]}). Detail:\n{detail}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    got = 0
    for j in jobs:
        w, m = next(out.rglob(f"{j['key']}.wav"), None), next(out.rglob(f"{j['key']}.json"), None)
        if w and m:
            shutil.copy(w, cache_dir / f"{j['key']}.wav"); shutil.copy(m, cache_dir / f"{j['key']}.json"); got += 1
    summ = next(out.rglob("summary.json"), None)
    summary = json.loads(summ.read_text()) if summ else {}
    if got != len(jobs):
        raise RuntimeError(f"Kaggle voice job returned {got}/{len(jobs)} clips")
    worst = max((i["wer"] for i in summary.get("items", [])), default=0)
    print(f"kaggle: {got} clips in {summary.get('seconds')}s on {summary.get('device')}, worst WER {worst}", flush=True)
    return summary

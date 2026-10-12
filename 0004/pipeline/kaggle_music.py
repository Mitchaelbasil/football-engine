"""Generate instrumental mood music with ACE-Step (Apache-2.0) on Kaggle's free GPU.

  source 0004/pipeline/kaggle_auth.sh
  python 0004/pipeline/kaggle_music.py --moods tension,sad --takes 2 --seconds 120 --out /tmp/music

Writes <out>/music_<mood>_ace_<NN>.wav (raw 48 kHz from the model). The workflow then fades, levels and
uploads them to Drive football-engine/0004/music/, where the mixer picks a track by its music_<mood>_ prefix.
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SLUG = "fe-music"

# Beds sit under narration: steady, no lead vocals, no busy solo melody.
MOODS = {
    "tension": "cinematic dark tension underscore, low pulsing synth bass, staccato string ostinato, deep taiko drums, "
               "slow suspenseful build, documentary score, 90 bpm, instrumental",
    "sad": "emotional cinematic piano, soft sustained strings, melancholic and reflective, gentle, documentary "
           "underscore, 70 bpm, instrumental",
    "triumph": "epic orchestral triumph, heroic brass fanfare, big drums, soaring strings, victorious anthem, "
               "cinematic sports score, 120 bpm, instrumental",
    "hype": "energetic anime opening style rock, driving drums, distorted electric guitar riffs, synth lead, "
            "high energy, 150 bpm, instrumental",
    "mystery": "mysterious investigative underscore, pizzicato strings, ticking clock percussion, soft synth pads, "
               "curious and suspenseful, 100 bpm, instrumental",
    "epic": "epic anime final battle orchestral score, fast strings, heavy percussion, brass hits, intense and "
            "dramatic, 140 bpm, instrumental",
    "chill": "lo-fi chill hip hop beat, mellow electric piano, soft drums, warm bass, relaxed, 85 bpm, instrumental",
}


def _k(*args, check=True) -> str:
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"kaggle {' '.join(args[:2])} failed: {(r.stderr or r.stdout)[-800:]}")
    return (r.stdout or "") + (r.stderr or "")


def run(jobs: list, out_dir: Path, timeout_min: int = 170) -> dict:
    user = os.environ.get("KAGGLE_USER", "mitchaelbasil")
    kid = f"{user}/{SLUG}"
    work = Path(tempfile.mkdtemp(prefix="km_"))
    (work / "run.py").write_text((HERE / "kernel_music.py").read_text().replace("__JOBS__", json.dumps(jobs)))
    (work / "kernel-metadata.json").write_text(json.dumps({
        "id": kid, "title": SLUG, "code_file": "run.py", "language": "python", "kernel_type": "script",
        "is_private": True, "enable_gpu": True, "enable_tpu": False, "enable_internet": True,
        "dataset_sources": [], "competition_sources": [], "kernel_sources": [],
    }))
    print(f"kaggle: pushing music job ({len(jobs)} tracks)", flush=True)
    print(_k("kernels", "push", "-p", str(work)).strip()[-300:], flush=True)
    t0, status = time.time(), ""
    time.sleep(60)
    while time.time() - t0 < timeout_min * 60:
        status = _k("kernels", "status", kid, check=False).lower()
        if "complete" in status or "error" in status or "cancel" in status:
            break
        time.sleep(30)
    print(f"kaggle: {status.strip()[-120:]} after {time.time() - t0:.0f}s", flush=True)
    out = work / "output"
    out.mkdir()
    dl = _k("kernels", "output", kid, "-p", str(out), check=False)
    logs = ""
    for lg in out.rglob("*.log"):
        try:
            logs += "".join(x.get("data", "") for x in json.loads(lg.read_text()))
        except Exception:
            logs += lg.read_text()
    tracks = [ln for ln in logs.splitlines() if " ok=" in ln or ln.startswith(("device", "done", "---"))]
    for ln in tracks[-20:]:
        print("kaggle-log:", ln.strip()[:300], flush=True)
    if "complete" not in status:
        err = next(out.rglob("error.txt"), None)
        detail = (err.read_text()[-3000:] if err else "") + "\n--- log ---\n" + logs[-3000:]
        if not detail.strip():
            detail = f"(no log; files: {[p.name for p in out.rglob('*')]}; output cmd: {dl.strip()[-400:]})"
        raise RuntimeError(f"Kaggle music job did not complete ({status.strip()[-80:]}). Detail:\n{detail}")
    out_dir.mkdir(parents=True, exist_ok=True)
    got = 0
    for j in jobs:
        w = next(out.rglob(f"{j['name']}.wav"), None)
        if w:
            shutil.copy(w, out_dir / f"{j['name']}.wav")
            got += 1
    summ = next(out.rglob("summary.json"), None)
    summary = json.loads(summ.read_text()) if summ else {}
    if got != len(jobs):
        raise RuntimeError(f"Kaggle music job returned {got}/{len(jobs)} tracks")
    print(f"kaggle: {got} tracks in {summary.get('seconds')}s on {summary.get('device')} ({summary.get('dtype')})",
          flush=True)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moods", default="tension")
    ap.add_argument("--takes", type=int, default=2)
    ap.add_argument("--seconds", type=int, default=120)
    ap.add_argument("--start", type=int, default=1, help="first take number (to add to an existing set)")
    ap.add_argument("--out", type=Path, default=Path("/tmp/music"))
    a = ap.parse_args()
    jobs = []
    for mood in [m.strip() for m in a.moods.split(",") if m.strip()]:
        if mood not in MOODS:
            raise SystemExit(f"unknown mood {mood!r}; known: {', '.join(MOODS)}")
        for n in range(a.start, a.start + a.takes):
            jobs.append({"name": f"music_{mood}_ace_{n:02d}", "prompt": MOODS[mood], "seconds": a.seconds,
                         "seed": random.randint(1, 2**31 - 1)})
    run(jobs, a.out)


if __name__ == "__main__":
    main()

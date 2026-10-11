"""Build one 0004 video folder: scenes.json -> voice -> motion plan -> render -> mix -> final.mp4.

  python 0004/pipeline/build.py 0004/videos/<id> --voice fake --stills auto      # quick visual check
  python 0004/pipeline/build.py 0004/videos/<id> --voice kokoro --video          # full render
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ENGINE = HERE.parent / "engine"

import mix as mixer  # noqa: E402
import plan  # noqa: E402
import render  # noqa: E402
from voice import synth_beats  # noqa: E402


def stage_engine(build: Path):
    for f in ("engine.html", "engine.js", "templates.js"):
        shutil.copy(ENGINE / f, build / f)
    if not (build / "fonts").exists():
        shutil.copytree(ENGINE / "fonts", build / "fonts")


def auto_times(tl) -> list:
    ts = []
    for s in tl["scenes"]:
        evs = sorted(e["t"] for e in s["ev"])
        ts += [min(s["start"] + 0.9, s["end"] - 0.1)] + [min(t + 1.0, s["end"] - 0.1) for t in evs[-2:]]
    ts += [o["t"] + 0.6 for o in tl["overlays"]]
    return sorted({round(t, 2) for t in ts})


def contact_sheet(video: Path, out: Path, every: float = 2.0):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", f"fps=1/{every},scale=384:-1,tile=6x6:padding=4",
                    "-frames:v", "1", str(out)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video_dir", type=Path)
    ap.add_argument("--voice", default="fake")
    ap.add_argument("--stills", default="")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--allow-invalid", action="store_true")
    a = ap.parse_args()

    vd = a.video_dir.resolve()
    build = vd / "build"; build.mkdir(parents=True, exist_ok=True)
    doc = json.loads((vd / "scenes.json").read_text())
    beats = [b for s in doc["scenes"] for b in s["beats"]]
    voice = synth_beats(beats, a.voice, build / f"voice_{a.voice.replace(':', '_')}")
    tl = plan.build_timeline(doc, voice)
    plan.write(tl, build)
    rep = tl["report"]
    print(f"plan: {tl['total']:.1f}s, {rep['changes']} visual changes, avg gap {rep['avg_gap']}s, max gap {rep['max_gap']}s, "
          f"robotic runs {len(rep['robotic_at'])}, micro {len(tl['micro'])}, ok={rep['ok']}")
    for w in rep["warnings"]:
        print("  warn:", w)
    if not rep["ok"] and not a.allow_invalid:
        sys.exit(f"motion plan failed validation: {rep}")
    stage_engine(build)

    if a.stills:
        times = auto_times(tl) if a.stills == "auto" else [float(x) for x in a.stills.split(",")]
        paths = render.stills(build, times, tl["w"], tl["h"], build / "stills")
        print(f"stills: {len(paths)} -> {build / 'stills'}")

    if a.video:
        out = vd / "out"; out.mkdir(exist_ok=True)
        plan.assemble_voice(tl, build / "voice.wav")
        silent = render.video(build, tl["total"], tl["fps"], tl["w"], tl["h"], build / "video.mp4")
        mixer.mix(tl, build / "voice.wav", build / "mix.wav")
        final = mixer.mux(silent, build / "mix.wav", out / "final.mp4")
        contact_sheet(final, out / "contact.jpg")
        print(f"done: {final}")


if __name__ == "__main__":
    main()

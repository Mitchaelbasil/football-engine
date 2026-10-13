"""Build one 0004 video folder: scenes.json -> voice -> motion plan -> render -> mix -> outputs.

  python 0004/pipeline/build.py 0004/videos/<id> --voice fake --stills auto           # quick visual check (16:9)
  python 0004/pipeline/build.py 0004/videos/<id> --voice fake --stills auto --portrait  # same, 9:16
  python 0004/pipeline/build.py 0004/videos/<id> --voice kokoro --video --shorts --thumbs
Outputs land in <id>/out/: final.mp4, short_<name>.mp4, thumb_<A|B|C>[_base].png + thumb_instructions.txt
"""

import argparse
import copy
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
import thumb  # noqa: E402
from voice import synth_beats  # noqa: E402

LAND, PORT = (1920, 1080), (1080, 1920)


def stage_engine(build: Path):
    build.mkdir(parents=True, exist_ok=True)
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


def contact_sheet(video: Path, out: Path, every: float = 2.0, cols: int = 6):
    w = 384 if cols == 6 else 216
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", f"fps=1/{every},scale={w}:-1,tile={cols}x6:padding=4",
                    "-frames:v", "1", str(out)], check=True)


def make(doc: dict, voice_backend: str, build: Path, size, allow_invalid=False):
    beats = plan.doc_beats(doc)
    pundit = (doc.get("meta", {}).get("hosts") or {}).get("P", {}).get("voice")
    voice = synth_beats(beats, voice_backend, build.parent / f"voice_{voice_backend.replace(':', '_')}", pundit)
    tl = plan.build_timeline(doc, voice, w=size[0], h=size[1])
    stage_engine(build)
    plan.write(tl, build)
    rep = tl["report"]
    air = {}
    for bt in tl["beats"]:
        air[bt["speaker"]] = air.get(bt["speaker"], 0) + bt["end"] - bt["t"]
    talk = sum(air.values()) or 1
    hosts = " ".join(f"{k}={v / talk:.0%}" for k, v in sorted(air.items()))
    print(f"plan[{build.name}]: {tl['total']:.1f}s, {rep['changes']} visual changes, avg gap {rep['avg_gap']}s, max gap {rep['max_gap']}s, "
          f"robotic runs {len(rep['robotic_at'])}, micro {len(tl['micro'])}, airtime {hosts}, ok={rep['ok']}")
    for w in rep["warnings"]:
        print("  warn:", w)
    if not rep["ok"] and not allow_invalid:
        sys.exit(f"motion plan failed validation: {rep}")
    return tl


ASSETS, SFX_OFF = None, ()


def render_full(tl, build: Path, out_mp4: Path):
    plan.assemble_voice(tl, build / "voice.wav")
    if len(tl.get("voice_gains", {})) > 1:
        print(f"voice levels[{build.name}]: " + ", ".join(f"{k} x{g:.2f}" for k, g in tl["voice_gains"].items()))
    silent = render.video(build, tl["total"], tl["fps"], tl["w"], tl["h"], build / "video.mp4")
    mixer.mix(tl, build / "voice.wav", build / "mix.wav", ASSETS, SFX_OFF)
    if tl.get("sfx_used"):
        (build / "sfx_used.txt").write_text("\n".join(tl["sfx_used"]))
        print(f"sfx[{build.name}]: {len(tl['sfx_used'])} library sounds, beds {[b['mood'] for b in tl.get('beds', [])]}")
    return mixer.mux(silent, build / "mix.wav", out_mp4)


def short_docs(doc: dict) -> list:
    """Each Short = a run of scenes from the long video + an end card pointing to the full story."""
    by_id = {s.get("id"): s for s in doc["scenes"]}
    specs = doc.get("shorts") or [{"name": "hook", "scenes": [s["id"] for s in doc["scenes"][:3]]}]
    title = doc.get("meta", {}).get("short_title") or doc.get("meta", {}).get("title", "")
    out = []
    for sp in specs:
        scenes = [copy.deepcopy(by_id[i]) for i in sp["scenes"]]
        if sp.get("hook"):  # Shorts must open on a hook: one spoken line over a word slam
            h = sp["hook"]
            scenes.insert(0, {"id": "hook", "type": "slam", "palette": h.get("palette", scenes[0].get("palette", "gold")), "hud": False,
                              "data": {"word": h["word"], "pre": h.get("pre", "")},
                              "beats": [{"say": h["say"], "speaker": h.get("speaker", "H"), "emph": [h["at"]] if h.get("at") else [],
                                         "do": ["pre", {"a": "slam", "at": h["at"]} if h.get("at") else "slam"]}]})
        scenes.append({"id": "end", "type": "endcard", "palette": "violet", "hud": False, "dur": 2.6,
                       "data": {"line": "FULL STORY ON THE CHANNEL", "title": sp.get("title", title)}})
        out.append((sp["name"], {"meta": doc.get("meta", {}), "scenes": scenes}))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video_dir", type=Path)
    ap.add_argument("--voice", default="fake")
    ap.add_argument("--stills", default="")
    ap.add_argument("--portrait", action="store_true", help="stills/video in 9:16 (preview only)")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--shorts", action="store_true")
    ap.add_argument("--thumbs", action="store_true")
    ap.add_argument("--allow-invalid", action="store_true")
    ap.add_argument("--assets", type=Path, help="synced Drive assets (sfx/, music/) - see assets.py")
    ap.add_argument("--sfx-off", default="", help="drop library files by source tag, e.g. op,dbz (if claims land)")
    a = ap.parse_args()
    global ASSETS, SFX_OFF
    ASSETS = a.assets

    vd = a.video_dir.resolve()
    doc = json.loads((vd / "scenes.json").read_text())
    SFX_OFF = tuple(x for x in (a.sfx_off.split(",") + doc.get("meta", {}).get("sfx_off", [])) if x)
    if a.voice == "chatterbox":  # voice every sentence (main + Shorts hooks) in ONE Kaggle job; fall back to Kokoro if it fails
        allb = plan.doc_beats(doc)
        if a.shorts:
            allb += [b for _, d in short_docs(doc) for b in plan.doc_beats(d)]
        try:
            synth_beats(allb, "chatterbox", vd / "build" / "voice_chatterbox")
        except Exception as e:
            print(f"VOICE FALLBACK: chatterbox failed ({str(e)[:1500]}) -> using kokoro:bm_george", flush=True)
            a.voice = "kokoro:bm_george"
    out = vd / "out"; out.mkdir(parents=True, exist_ok=True)
    size = PORT if a.portrait else LAND
    main_build = vd / "build" / ("main_9x16" if a.portrait else "main")
    tl = make(doc, a.voice, main_build, size, a.allow_invalid)

    if a.stills:
        times = auto_times(tl) if a.stills == "auto" else [float(x) for x in a.stills.split(",")]
        paths = render.stills(main_build, times, tl["w"], tl["h"], main_build / "stills")
        print(f"stills: {len(paths)} -> {main_build / 'stills'}")

    if a.video:
        final = render_full(tl, main_build, out / "final.mp4")
        cues = ["SFX PLAYED (time, group, file from Drive 0004/sfx)", ""] + [
            f"{int(float(u.split()[0]) // 60)}:{float(u.split()[0]) % 60:05.2f}  " + " ".join(u.split()[1:]) for u in tl.get("sfx_used", [])]
        (out / "sfx_cues.txt").write_text("\n".join(cues))
        contact_sheet(final, out / "contact.jpg")
        print(f"done: {final}")

    if a.shorts:
        for name, sdoc in short_docs(doc):
            sb = vd / "build" / f"short_{name}"
            stl = make(sdoc, a.voice, sb, PORT, a.allow_invalid)
            if stl["total"] > 60:
                print(f"  warn: short '{name}' is {stl['total']:.0f}s (target 20-45s)")
            mp4 = render_full(stl, sb, out / f"short_{name}.mp4")
            contact_sheet(mp4, out / f"contact_short_{name}.jpg", 1.5, cols=10)
            print(f"short: {mp4}")

    if a.thumbs:
        files = thumb.render_all(doc, vd / "build" / "thumbs", out)
        print(f"thumbs: {[f.name for f in files]}")


if __name__ == "__main__":
    main()

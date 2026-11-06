"""0004 preflight (growth plan Phase 6): packaging + script checks before a render.

    python 0004/pipeline/preflight.py 0004/videos/<folder>

Checks scenes.json against 0004/rules/packaging-and-script.md and prints warnings.
It never blocks a render: GitHub notice annotations go into the run summary instead.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "0006"))

WORDS_PER_SEC = 2.6  # Kokoro at speed 0.95, measured on the checkpoint


def beats(scene: dict) -> list:
    return scene.get("beats", []) or []


def check(folder: Path) -> list:
    data = json.loads((folder / "scenes.json").read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    idea = meta.get("idea") or {}
    warn = []
    if not idea:
        return ["meta.idea is missing: every video needs an approved idea card (0006 Ideas tab, PASS)"]

    import library as lib
    formats = {f["id"]: f for f in lib.load_formats()}
    ideas = {}
    ideas_file = ROOT / "0006" / "ideas.json"
    if ideas_file.exists():
        ideas = {i["id"]: i for i in json.loads(ideas_file.read_text(encoding="utf-8")).get("ideas", [])}
    if idea.get("id") not in ideas:
        warn.append(f"idea '{idea.get('id')}' is not in 0006/ideas.json, so the gate never checked it")
    fmt = formats.get(idea.get("format"))
    if not fmt:
        warn.append(f"format '{idea.get('format')}' is not in 0006/formats.json")
    title = idea.get("title", "")
    tc = lib.title_check(title, fmt["rx"] if fmt else None)
    if tc != "ok":
        warn.append(f"title '{title}': {tc}")
    thumb = idea.get("thumb_text", "")
    if len(thumb.split()) > 3:
        warn.append(f"thumbnail text '{thumb}' has more than 3 words")
    if thumb and thumb.lower() in title.lower():
        warn.append("thumbnail text repeats the title; make it complementary")
    faces = (meta.get("thumb") or {}).get("faces") or []
    if not faces:
        warn.append("meta.thumb.faces is empty: a recognisable player face is mandatory")

    # Promise-Proof-Plan inside the first ~45 s of speech
    said, secs = [], 0.0
    for sc in data.get("scenes", []):
        for b in beats(sc):
            words = len(re.findall(r"\w+", b.get("say", "")))
            if secs > 45:
                break
            said.append(b.get("say", ""))
            secs += words / WORDS_PER_SEC
    opening = " ".join(said).lower()
    for key in ("promise", "proof", "plan"):
        line = (idea.get(key) or "").strip()
        if not line:
            warn.append(f"meta.idea.{key} is empty")
        elif line.lower()[:40] not in opening:
            warn.append(f"the {key} line isn't spoken in the first ~45 s")
    first = said[0] if said else ""
    title_words = {w for w in re.findall(r"[a-z]{4,}", title.lower())}
    if title_words and not title_words & set(re.findall(r"[a-z]{4,}", first.lower())):
        warn.append("the first sentence shares no key word with the title: restate the promise first")
    return warn


def main() -> None:
    folder = Path(sys.argv[1])
    warns = check(folder)
    for w in warns:
        print(f"::notice title=preflight::{w}")
    print(f"preflight: {len(warns)} warning(s) for {folder.name}")


if __name__ == "__main__":
    main()

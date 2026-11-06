"""YouTube title + description for a rendered 0004 video.

  python 0004/pipeline/describe.py 0004/videos/<id>   -> <id>/out/description.txt

- First line: the idea's promise (the first thing a viewer reads under the video).
- Chapters from the timeline's arc cards (YouTube needs 0:00 first and 3+ chapters of 10 s or more).
- Sources from meta.sources, then photo credits from meta.photo_credits.
"""

import json
import sys
from pathlib import Path


def mmss(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def name_case(x: str) -> str:
    """Title case that keeps name particles low: Robin van Persie, Kevin De Bruyne stays as data gives it."""
    return " ".join(w.lower() if i and w.lower() in ("van", "von", "der", "den", "da", "di", "dos", "del") else w
                    for i, w in enumerate(x.title().split()))


def chapters(tl: dict, doc: dict) -> list:
    """Arc cards, plus 'NUMBER N' slams for countdown entries that have no arc card of their own."""
    import re
    by_id = {s["id"]: s for s in doc.get("scenes", [])}
    num = lambda x: (re.match(r"NUMBER (\d+)", str(x or "").upper()) or [None, None])[1]
    arc_nums = {num(s.get("data", {}).get("kicker")) for s in doc.get("scenes", []) if s.get("type") == "arc"}
    out = [(0.0, "Intro")]
    for s in tl.get("scenes", []):
        src = by_id.get(s["id"], {})
        d = src.get("data", {})
        if src.get("type") == "arc":
            title = " ".join(d.get("title", [])) if isinstance(d.get("title"), list) else str(d.get("title", ""))
            name = name_case((d.get("sub") or "").split("·")[0].strip())
            label = f"{d.get('kicker', '').title()}: {name}" if name else title.title()
        elif src.get("type") == "slam" and num(d.get("pre")) and num(d.get("pre")) not in arc_nums and d.get("sub"):
            label = f"{d['pre'].title()}: {str(d.get('word', '')).title()}"
        else:
            continue
        if s["start"] - out[-1][0] >= 10:
            out.append((s["start"], label.replace("Number ", "#")))
    return out if len(out) >= 3 else []


def main() -> None:
    vd = Path(sys.argv[1])
    doc = json.loads((vd / "scenes.json").read_text(encoding="utf-8"))
    tl_path = vd / "build" / "main" / "timeline.json"
    tl = json.loads(tl_path.read_text()) if tl_path.exists() else {"scenes": []}
    meta = doc.get("meta", {})
    idea = meta.get("idea", {})
    lines = [idea.get("title") or meta.get("title", ""), "", "--- DESCRIPTION ---"]
    if idea.get("promise"):
        lines += [idea["promise"], ""]
    ch = chapters(tl, doc)
    if ch:
        lines += [f"{mmss(t)} {name}" for t, name in ch] + [""]
    if meta.get("sources"):
        lines += ["Sources:"] + [f"- {s}" for s in meta["sources"]] + [""]
    if meta.get("photo_credits"):
        lines += ["Photos:"] + [f"- {c}" for c in meta["photo_credits"]] + [""]
    lines += ["Narrated by Bella (story) and Michael (breakdown). If Football was Anime."]
    out = vd / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "description.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"description: {len(ch)} chapters")


if __name__ == "__main__":
    main()

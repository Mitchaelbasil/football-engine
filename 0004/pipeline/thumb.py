"""Thumbnail templates: 3 variants (A number+face, B face+arrow, C versus), each as
   thumb_X.png       guide with labelled face spaces (what to put where)
   thumb_X_base.png  finished background + text, face space left clean for Mitchael's cut-out
plus thumb_instructions.txt. Data: scenes.json meta.thumb = {big, top, kicker, vs:[a,b], palette, faces:[{who,mood}]}"""

import json
import shutil
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine"
FONTS = "Promise.all(['100px Anton','900 30px Inter','800 30px Inter'].map(f=>document.fonts.load(f))).then(()=>document.fonts.ready)"

TIPS = {
    "A": "Big number/word on the left, ONE face on the right. Face slightly overlapping the text edge reads as confident.",
    "B": "Face on the left looking toward the text; the red arrow points at the face. Strongest emotion goes here.",
    "C": "Versus: one face each side, the contradiction in the middle. Both faces should look at the centre.",
}


def render_all(doc: dict, build: Path, out: Path) -> list:
    from playwright.sync_api import sync_playwright
    build.mkdir(parents=True, exist_ok=True)
    shutil.copy(ENGINE / "thumb.html", build / "thumb.html")
    if not (build / "fonts").exists():
        shutil.copytree(ENGINE / "fonts", build / "fonts")
    meta = doc.get("meta", {})
    t = meta.get("thumb") or {"big": meta.get("title", "")[:12], "faces": [{"who": "Main player", "mood": "strong emotion"}]}
    files = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--force-color-profile=srgb"])
        pg = b.new_page(viewport={"width": 1280, "height": 720})
        pg.goto((build / "thumb.html").resolve().as_uri())
        pg.wait_for_function("window.READY===true")
        pg.evaluate(FONTS)
        for v in "ABC":
            if v == "C" and not t.get("vs"):
                continue
            for guide in (True, False):
                pg.evaluate(f"draw({json.dumps({**t, 'variant': v, 'guide': guide})})")
                f = out / f"thumb_{v}{'' if guide else '_base'}.png"
                pg.screenshot(path=str(f))
                files.append(f)
        b.close()
    faces = t.get("faces") or []
    lines = ["THUMBNAIL INSTRUCTIONS", f"Title: {meta.get('title', '')}", ""]
    for v in "ABC":
        if v == "C" and not t.get("vs"):
            continue
        lines += [f"Variant {v}: thumb_{v}_base.png  (guide: thumb_{v}.png)", f"  {TIPS[v]}"]
        need = faces[:2] if v == "C" else faces[:1]
        for i, fc in enumerate(need, 1):
            lines.append(f"  Face {i}: {fc.get('who', '')} - {fc.get('mood', '')}")
        lines.append("")
    lines += ["How: open the _base.png in your editor, drop a background-removed face where the guide shows,",
              "make the head fill that space, eyes on the top third. Don't cover the big number.",
              "Upload 3 variants to YouTube Studio Test & Compare and let the data pick."]
    txt = out / "thumb_instructions.txt"
    txt.write_text("\n".join(lines))
    return files + [txt]

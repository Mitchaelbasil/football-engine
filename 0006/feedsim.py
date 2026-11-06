"""0006 Phase 4: feed simulator.

Puts our title + thumbnail into a mock YouTube feed next to real competitor videos
on the same subject (pulled from the Demand Map DB), and screenshots it at phone
and desktop size, so packaging is judged where it will actually compete.

Request (0006/requests/feedsim.json):
  {"name": "pilot", "terms": ["ronaldo"], "channel": "If Football was Anime",
   "variants": [{"title": "...", "thumb": "<youtube id> | https://... | repo/path.png"}]}
Output: Drive football-engine/0006/feedsim/<name>/feed_<n>_{mobile,desktop}.png + Telegram.
"""

import argparse
import base64
import html
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import demand_map as dm  # noqa: E402


def thumb_src(thumb: str) -> str:
    if thumb.startswith("http"):
        return thumb
    p = ROOT / thumb
    if p.exists():
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()
    return f"https://i.ytimg.com/vi/{thumb}/hqdefault.jpg"


def fmt_views(n: int) -> str:
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            v = n / div
            return f"{v:.1f}".rstrip("0").rstrip(".") + f"{suf} views"
    return f"{n} views"


def competitors(db, terms: list, k: int, seed: str) -> list:
    rows = []
    for r in db.execute(
            "SELECT v.id, v.title, v.views, v.published, v.duration, c.title AS ctitle FROM videos v "
            "JOIN channels c ON c.id=v.channel WHERE v.niche='football' AND c.sample <= ? "
            "AND v.views >= 20000 ORDER BY v.views DESC", (dm.HIGH_VOLUME,)):
        t = r["title"].lower()
        if any(term.lower() in t for term in terms) and dm.replicable(r["title"]):
            rows.append(dict(r))
    pool = rows[:40]
    random.Random(seed).shuffle(pool)
    return pool[:k]


def age(published: str, today) -> str:
    days = (today - dm.parse_ts(published)).days
    if days < 7:
        return f"{max(days, 1)} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    if days < 365:
        return f"{days // 30} months ago"
    return f"{days // 365} year{'s' if days >= 730 else ''} ago"


def card(title, channel, meta, src, duration, us=False) -> str:
    initial = html.escape((channel or "?")[0].upper())
    hue = (sum(map(ord, channel or "x")) * 37) % 360
    return f"""
<div class="card{' us' if us else ''}">
  <div class="thumb"><img src="{src}"><span class="dur">{duration}</span></div>
  <div class="info">
    <div class="av" style="background:hsl({hue},45%,45%)">{initial}</div>
    <div><div class="title">{html.escape(title)}</div>
    <div class="meta">{html.escape(channel)} · {html.escape(meta)}</div></div>
  </div>
</div>"""


def page(cards: list, mode: str) -> str:
    dark = mode == "mobile"
    bg, fg, sub = ("#0f0f0f", "#f1f1f1", "#aaa") if dark else ("#fff", "#0f0f0f", "#606060")
    cols = "1fr" if mode == "mobile" else "repeat(3, 1fr)"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:{bg};color:{fg};font-family:Roboto,Arial,sans-serif}}
.grid{{display:grid;grid-template-columns:{cols};gap:{'18px' if mode == 'mobile' else '40px 16px'};
padding:{'0' if mode == 'mobile' else '24px'}}}
.thumb{{position:relative;aspect-ratio:16/9;overflow:hidden;border-radius:{'0' if mode == 'mobile' else '12px'};background:#333}}
.thumb img{{width:100%;height:100%;object-fit:cover}}
.dur{{position:absolute;right:8px;bottom:8px;background:rgba(0,0,0,.8);color:#fff;font-size:12px;
font-weight:500;padding:1px 4px;border-radius:4px}}
.info{{display:flex;gap:12px;padding:{'12px' if mode == 'mobile' else '12px 0 0'}}}
.av{{flex:0 0 36px;height:36px;border-radius:50%;color:#fff;display:flex;align-items:center;
justify-content:center;font-weight:600}}
.title{{font-size:{'15px' if mode == 'mobile' else '16px'};font-weight:600;line-height:1.35;
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.meta{{font-size:13px;color:{sub};margin-top:4px}}
</style></head><body><div class="grid">{''.join(cards)}</div></body></html>"""


def render(html_doc: str, out: Path, mode: str, full: bool = False) -> None:
    from playwright.sync_api import sync_playwright
    w, h = (390, 1500) if mode == "mobile" else (1366, 1100)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2 if mode == "mobile" else 1)
        pg.set_content(html_doc, wait_until="networkidle")
        pg.screenshot(path=str(out), full_page=full)
        b.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", type=Path, default=HERE / "requests" / "feedsim.json")
    ap.add_argument("--out", type=Path, default=ROOT / ".feedsim")
    ap.add_argument("--db", type=Path, default=HERE / dm.DB_NAME)
    args = ap.parse_args()
    req = json.loads(args.request.read_text(encoding="utf-8"))
    name = req.get("name", "test")
    args.out.mkdir(parents=True, exist_ok=True)
    today = dm.now_utc()

    from shared.google_client import build_service
    drive = build_service("drive", "v3")
    root = dm.find_or_create(drive, dm.DRIVE_ROOT, dm.FOLDER_MIME, "root")
    folder = dm.find_or_create(drive, dm.DRIVE_SUB, dm.FOLDER_MIME, root)
    if not dm.pull_db(drive, folder, args.db):
        raise SystemExit("No Demand Map DB on Drive yet")
    db = dm.open_db(args.db)
    comps = competitors(db, req.get("terms", []), 8, name)
    print(f"Competitors found: {len(comps)}")

    comp_cards = [card(c["title"], c["ctitle"], f"{fmt_views(c['views'])} · {age(c['published'], today)}",
                       f"https://i.ytimg.com/vi/{c['id']}/hqdefault.jpg",
                       f"{c['duration'] // 60}:{c['duration'] % 60:02d}") for c in comps]
    feedsim_dir = dm.find_or_create(drive, "feedsim", dm.FOLDER_MIME, folder)
    target = dm.find_or_create(drive, name, dm.FOLDER_MIME, feedsim_dir)
    links = []
    for i, v in enumerate(req.get("variants", []), 1):
        ours = card(v["title"], req.get("channel", "If Football was Anime"),
                    v.get("meta", "1.2K views · 2 days ago"), thumb_src(v["thumb"]),
                    v.get("duration", "9:41"), us=True)
        for mode, pos in (("mobile", 2), ("desktop", 4)):
            cards = comp_cards[:]
            cards.insert(min(pos, len(cards)), ours)
            out = args.out / f"feed_{i}_{mode}.png"
            render(page(cards, mode), out, mode)
            from shared.drive import upload
            links.append(upload(drive, out, target).get("webViewLink", ""))
            print(f"Rendered variant {i} {mode}")
    try:
        from shared.telegram import send_message
        send_message(f"<b>👀 Feed test: {html.escape(name)}</b>\n{len(req.get('variants', []))} variant(s) "
                     f"vs {len(comps)} real competitors.\n" + "\n".join(
                         f'<a href="{u}">{i + 1}</a>' for i, u in enumerate(links) if u))
    except Exception as exc:
        print(f"Telegram failed: {type(exc).__name__}")


if __name__ == "__main__" and "--gallery" not in sys.argv:
    main()


# ---------- thumbnail gallery (Phase 2: thumbnail patterns per title format) ----------

def gallery_main(req_path: Path, out_dir: Path, db_path: Path) -> None:
    import library as lib
    req = json.loads(req_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    from shared.google_client import build_service
    from shared.drive import upload
    drive = build_service("drive", "v3")
    root = dm.find_or_create(drive, dm.DRIVE_ROOT, dm.FOLDER_MIME, "root")
    folder = dm.find_or_create(drive, dm.DRIVE_SUB, dm.FOLDER_MIME, root)
    if not dm.pull_db(drive, folder, db_path):
        raise SystemExit("No Demand Map DB on Drive yet")
    db = dm.open_db(db_path)
    formats = {f["id"]: f for f in lib.load_formats()}
    pool = lib.creator_pool(db, dm.OUTLIER, dm.MIN_OUTLIER_VIEWS, dm.HIGH_VOLUME, dm.replicable)
    gal = dm.find_or_create(drive, "gallery", dm.FOLDER_MIME, folder)
    per = int(req.get("per", 12))
    for fid in req.get("formats", []):
        f = formats.get(fid)
        if not f:
            continue
        wins = sorted([r for r in pool if r["win"] and f["rx"].search(lib.LEAD_RE.sub("", r["title"]))],
                      key=lambda r: r["score"], reverse=True)
        seen, picks = set(), []
        for r in wins:  # at most 2 per channel, so one channel's style doesn't dominate
            if sum(1 for p in picks if p["channel"] == r["channel"]) >= 2:
                continue
            picks.append(r)
            if len(picks) >= per:
                break
        cards = [card(r["title"], r["ctitle"], f"{r['score']:g}x · {fmt_views(r['views'])}",
                      f"https://i.ytimg.com/vi/{r['id']}/hqdefault.jpg",
                      f"{r['duration'] // 60}:{r['duration'] % 60:02d}") for r in picks]
        out = out_dir / f"gallery_{fid}.png"
        render(page(cards, "desktop"), out, "desktop", full=True)
        upload(drive, out, gal)
        print(f"Gallery {fid}: {len(picks)} thumbnails")


if __name__ == "__main__" and "--gallery" in sys.argv:
    gallery_main(HERE / "requests" / "gallery.json", ROOT / ".feedsim", HERE / dm.DB_NAME)

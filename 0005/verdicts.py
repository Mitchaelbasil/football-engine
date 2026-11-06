"""0005 v3 (growth-plan Phases 7-8): first-48h/7d/28d windows, bottleneck diagnosis,
a weekly verdict per long-form video, and the double-down queue.

Bottleneck logic (growth plan):
  low impressions              -> subject/demand (or channel authority)
  impressions ok, low CTR      -> packaging      -> REPACKAGE (title/thumbnail in Studio)
  CTR ok, low average view %   -> hook broke its promise -> FIX HOOK (next scripts)
  watch ok, low subs per 1k    -> off-viewer topic or no next step
  own outlier score >= 3x      -> DOUBLE DOWN (keep the reason, new expression)
"""

import datetime as dt
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "0006"))

WINDOWS = (2, 7, 28)
MIN_AGE_FOR_VERDICT = 7
CTR_BAD, CTR_GOOD = 0.02, 0.045
AVP_BAD, AVP_GOOD = 30.0, 45.0
IMPRESSIONS_LOW = 1000          # in the first 7 days
SUBS_PER_1K_LOW = 1.0
DOUBLE_DOWN = 3.0


def window_views(yta, rows: list, today: dt.date) -> dict:
    """{video_id: {2: views, 7: views, 28: views}} for long-form videos (per-video date windows)."""
    out = {}
    for r in rows:
        if r["format"] != "Long" or r["privacy"] != "public":
            continue
        res = {}
        for n in WINDOWS:
            end = r["published"] + dt.timedelta(days=n - 1)
            if end > today:
                res[n] = None
                continue
            resp = yta.reports().query(
                ids="channel==MINE", startDate=r["published"].isoformat(), endDate=end.isoformat(),
                metrics="views", filters=f"video=={r['id']}").execute()
            vals = resp.get("rows") or [[0]]
            res[n] = int(vals[0][0] or 0)
        out[r["id"]] = res
    return out


def classify_formats(title: str) -> str:
    try:
        import library
        return ", ".join(library.classify(title, library.load_formats())) or "-"
    except Exception:
        return "?"


def own_scores(rows: list) -> dict:
    """Views / median of the channel's OTHER long-form videos (needs 3+ others)."""
    longs = [r for r in rows if r["format"] == "Long" and r["privacy"] == "public"]
    out = {}
    for r in longs:
        others = [o["views"] for o in longs if o["id"] != r["id"]]
        out[r["id"]] = round(r["views"] / max(statistics.median(others), 1), 2) if len(others) >= 3 else None
    return out


def verdict(r: dict, reach: dict, own: float) -> tuple:
    """(bottleneck, verdict, next action)"""
    if r["age"] < MIN_AGE_FOR_VERDICT:
        return "too early", "WAIT", f"Verdict after day {MIN_AGE_FOR_VERDICT}"
    imp, ctr = (reach or {}).get("impressions"), (reach or {}).get("ctr")
    avp, spk = r["avg_view_pct"], r["subs_per_1k"]
    if own is not None and own >= DOUBLE_DOWN:
        return "none: outlier on our channel", "DOUBLE DOWN", \
            "Same subject in a new format, or same format on a new subject (see queue)"
    if imp is None:
        if avp < AVP_BAD:
            return "retention (reach data pending)", "FIX HOOK", \
                "Rework the first 60 s rules; check the retention graph for the drop"
        return "unknown (reach data pending)", "KEEP", "Re-check when impressions arrive"
    if imp < IMPRESSIONS_LOW and r["age"] >= 7:
        return "reach: YouTube barely showed it", "KILL TOPIC", \
            "Subject lacked demand or authority; pick from Ideas tab (gate PASS only)"
    if ctr < CTR_BAD:
        return f"packaging: CTR {ctr:.1%}", "REPACKAGE", \
            "New title + thumbnail in Studio (run the feed simulator first)"
    if avp < AVP_BAD:
        return f"hook: avg view {avp:.0f}%", "FIX HOOK", \
            "Promise-Proof-Plan in the first 30-45 s; match the title's promise"
    if spk < SUBS_PER_1K_LOW:
        return "conversion: few subs per view", "KEEP", \
            "Add a next-video end screen; check the topic fits the channel's viewer"
    if ctr >= CTR_GOOD and avp >= AVP_GOOD:
        return "none", "DOUBLE DOWN", "Strong click + watch: make the next one in this lane"
    return "none clear", "KEEP", "Healthy; keep the lane"


def queue_suggestions(sheets, drive, find_sheet) -> list:
    """Top fitting formats and subjects from the 0006 Demand Map, for double-down picks."""
    try:
        sid = find_sheet(drive, "0006 Demand Map")
        if not sid:
            return []
        vals = sheets.spreadsheets().values()
        fmts = vals.get(spreadsheetId=sid, range="Formats!A2:F40").execute().get("values", [])
        tops = vals.get(spreadsheetId=sid, range="Topics!A2:E40").execute().get("values", [])
        f_ok = [f for f in fmts if len(f) >= 6 and f[1] == "yes" and str(f[2]).isdigit()
                and int(f[2]) >= 15]
        f_ok.sort(key=lambda f: float(f[5] or 0), reverse=True)
        t_ok = [t for t in tops if len(t) >= 5]
        t_ok.sort(key=lambda t: float(t[4] or 0), reverse=True)
        return [f"Formats with the best lift: " + "; ".join(f"{f[0]} ({f[5]}x)" for f in f_ok[:5]),
                "Subjects with the best hit rate: " + "; ".join(f"{t[0]} ({float(t[4]):.0%})" for t in t_ok[:6])]
    except Exception as exc:
        return [f"(0006 Demand Map not readable: {type(exc).__name__})"]

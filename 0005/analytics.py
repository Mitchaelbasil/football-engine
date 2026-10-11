"""0005 — weekly channel analytics.

Pulls every upload on the channel, joins YouTube Analytics metrics, tags each
video with its pipeline (a 0001-0009 tag in the description, else "original"),
and writes to Drive folder football-engine/0005:
  * Google Sheet "0005 Channel Analytics"  (tabs: Videos, Pipelines, History)
  * Google Doc   "0005 Weekly - YYYY-MM-DD" (summary for review)
then pings Telegram with both links.

The repo is public, so Actions logs are public: log counts only, never stats.
"""

import datetime as dt
import html
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from googleapiclient.http import MediaInMemoryUpload  # noqa: E402

from shared.google_client import build_service  # noqa: E402
from shared.telegram import send_message  # noqa: E402

DRIVE_ROOT = "football-engine"
DRIVE_SUB = "0005"
SHEET_NAME = "0005 Channel Analytics"
SHORT_MAX_SECONDS = 180  # Shorts can run up to 3 min
TAG_RE = re.compile(r"(?<!\d)(000[1-9])(?!\d)")
DUR_RE = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
LIFETIME_METRICS = [
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "comments",
    "shares",
    "subscribersGained",
    "subscribersLost",
]
WEEK_METRICS = ["views", "subscribersGained", "subscribersLost"]
FOLDER_MIME = "application/vnd.google-apps.folder"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
DOC_MIME = "application/vnd.google-apps.document"

VIDEO_HEADERS = [
    "Published", "Title", "Pipeline", "Format", "Privacy", "Duration (s)", "Age (d)",
    "Views", "Views 7d", "Views/day", "Avg view %", "Avg view dur (s)", "Watch min",
    "Likes", "Comments", "Shares", "Like rate %", "Subs gained", "Subs lost",
    "Net subs", "Net subs 7d", "Subs per 1k views", "Video ID",
]
PIPE_HEADERS = [
    "Pipeline", "Format", "Videos", "Total views", "Median views", "Median views/day",
    "Avg view % (mean)", "Net subs", "Subs per 1k views", "Best video", "Best views",
]
HISTORY_HEADERS = ["Snapshot", "Video ID", "Pipeline", "Format", "Views", "Watch min", "Net subs"]


# ---------- parsing ----------

def parse_duration(iso: str) -> int:
    m = DUR_RE.match(iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def pipeline_tag(description: str) -> str:
    m = TAG_RE.search(description or "")
    return m.group(1) if m else "original"


# ---------- YouTube ----------

def fetch_channel(yt) -> dict:
    items = yt.channels().list(part="snippet,contentDetails", mine=True).execute().get("items", [])
    if not items:
        raise RuntimeError("No channel found for this Google account")
    ch = items[0]
    return {
        "id": ch["id"],
        "title": ch["snippet"]["title"],
        "published": ch["snippet"]["publishedAt"][:10],
        "uploads": ch["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def fetch_video_ids(yt, playlist_id: str) -> list:
    ids, token = [], None
    while True:
        resp = yt.playlistItems().list(
            part="contentDetails", playlistId=playlist_id, maxResults=50, pageToken=token
        ).execute()
        ids += [it["contentDetails"]["videoId"] for it in resp.get("items", [])]
        token = resp.get("nextPageToken")
        if not token:
            return ids


def fetch_videos(yt, ids: list) -> list:
    out = []
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(
            part="snippet,contentDetails,status", id=",".join(ids[i:i + 50]), maxResults=50
        ).execute()
        for v in resp.get("items", []):
            sn = v["snippet"]
            out.append({
                "id": v["id"],
                "title": sn.get("title", ""),
                "published": dt.date.fromisoformat(sn["publishedAt"][:10]),
                "pipeline": pipeline_tag(sn.get("description", "")),
                "duration": parse_duration(v.get("contentDetails", {}).get("duration", "")),
                "privacy": v.get("status", {}).get("privacyStatus", ""),
            })
    return out


def fetch_analytics(yta, ids: list, start: str, end: str, metrics: list) -> dict:
    out = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        resp = yta.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics=",".join(metrics),
            dimensions="video",
            filters="video==" + ",".join(chunk),
            sort="-views",
            maxResults=len(chunk),
        ).execute()
        cols = [h["name"] for h in resp.get("columnHeaders", [])]
        for row in resp.get("rows") or []:
            rec = dict(zip(cols, row))
            out[rec["video"]] = rec
    return out


# ---------- shaping ----------

def build_rows(videos: list, life: dict, week: dict, today: dt.date) -> list:
    rows = []
    for v in videos:
        a, w = life.get(v["id"], {}), week.get(v["id"], {})
        views = int(a.get("views", 0) or 0)
        age = max((today - v["published"]).days, 1)
        likes = int(a.get("likes", 0) or 0)
        gained, lost = int(a.get("subscribersGained", 0) or 0), int(a.get("subscribersLost", 0) or 0)
        net = gained - lost
        rows.append({
            **v,
            "format": "Short" if 0 < v["duration"] <= SHORT_MAX_SECONDS else "Long",
            "age": age,
            "views": views,
            "views_7d": int(w.get("views", 0) or 0),
            "views_per_day": round(views / age, 1),
            "avg_view_pct": round(float(a.get("averageViewPercentage", 0) or 0), 1),
            "avg_view_dur": int(a.get("averageViewDuration", 0) or 0),
            "watch_min": int(a.get("estimatedMinutesWatched", 0) or 0),
            "likes": likes,
            "comments": int(a.get("comments", 0) or 0),
            "shares": int(a.get("shares", 0) or 0),
            "like_rate": round(likes / views * 100, 2) if views else 0,
            "subs_gained": gained,
            "subs_lost": lost,
            "net_subs": net,
            "net_subs_7d": int(w.get("subscribersGained", 0) or 0) - int(w.get("subscribersLost", 0) or 0),
            "subs_per_1k": round(net / views * 1000, 2) if views else 0,
        })
    rows.sort(key=lambda r: r["published"], reverse=True)
    return rows


def summarise(rows: list) -> list:
    groups = {}
    for r in rows:
        if r["privacy"] == "public":
            groups.setdefault((r["pipeline"], r["format"]), []).append(r)
    out = []
    for (pipe, fmt), rs in sorted(groups.items()):
        total = sum(r["views"] for r in rs)
        net = sum(r["net_subs"] for r in rs)
        pcts = [r["avg_view_pct"] for r in rs if r["views"]]
        best = max(rs, key=lambda r: r["views"])
        out.append({
            "pipeline": pipe,
            "format": fmt,
            "videos": len(rs),
            "total_views": total,
            "median_views": int(statistics.median(r["views"] for r in rs)),
            "median_vpd": round(statistics.median(r["views_per_day"] for r in rs), 1),
            "avg_view_pct": round(statistics.mean(pcts), 1) if pcts else 0,
            "net_subs": net,
            "subs_per_1k": round(net / total * 1000, 2) if total else 0,
            "best_title": best["title"],
            "best_id": best["id"],
            "best_views": best["views"],
        })
    return out


# ---------- Drive / Sheets ----------

def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def find_or_create(drive, name: str, mime: str, parent: str) -> str:
    q = f"name = '{_q(name)}' and mimeType = '{mime}' and '{parent}' in parents and trashed = false"
    files = drive.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
    if files:
        return files[0]["id"]
    return drive.files().create(
        body={"name": name, "mimeType": mime, "parents": [parent]}, fields="id"
    ).execute()["id"]


def link(url: str, text: str) -> str:
    return f'=HYPERLINK("{url}","{text.replace(chr(34), chr(34) * 2)}")'


def yt_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def ensure_tabs(sheets, sid: str) -> dict:
    meta = sheets.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties").execute()
    tabs = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    reqs = []
    wanted = ["Videos", "Pipelines", "History"]
    if not any(t in tabs for t in wanted) and "Sheet1" in tabs:
        reqs.append({"updateSheetProperties": {
            "properties": {"sheetId": tabs["Sheet1"], "title": "Videos"}, "fields": "title"}})
        tabs["Videos"] = tabs.pop("Sheet1")
    reqs += [{"addSheet": {"properties": {"title": t}}} for t in wanted if t not in tabs]
    if reqs:
        sheets.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": reqs}).execute()
        meta = sheets.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties").execute()
        tabs = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    return tabs


def write_sheet(sheets, sid: str, rows: list, pipes: list, today: dt.date) -> None:
    tabs = ensure_tabs(sheets, sid)
    vals = sheets.spreadsheets().values()

    video_rows = [VIDEO_HEADERS] + [[
        r["published"].isoformat(), link(yt_url(r["id"]), r["title"]), "'" + r["pipeline"],
        r["format"], r["privacy"], r["duration"], r["age"], r["views"], r["views_7d"],
        r["views_per_day"], r["avg_view_pct"], r["avg_view_dur"], r["watch_min"], r["likes"],
        r["comments"], r["shares"], r["like_rate"], r["subs_gained"], r["subs_lost"],
        r["net_subs"], r["net_subs_7d"], r["subs_per_1k"], "'" + r["id"],
    ] for r in rows]
    pipe_rows = [PIPE_HEADERS] + [[
        "'" + p["pipeline"], p["format"], p["videos"], p["total_views"], p["median_views"],
        p["median_vpd"], p["avg_view_pct"], p["net_subs"], p["subs_per_1k"],
        link(yt_url(p["best_id"]), p["best_title"]), p["best_views"],
    ] for p in pipes]

    for tab, data in (("Videos", video_rows), ("Pipelines", pipe_rows)):
        vals.clear(spreadsheetId=sid, range=tab).execute()
        vals.update(spreadsheetId=sid, range=f"{tab}!A1", valueInputOption="USER_ENTERED",
                    body={"values": data}).execute()

    head = vals.get(spreadsheetId=sid, range="History!A1:A1").execute().get("values")
    hist = [] if head else [HISTORY_HEADERS]
    hist += [[today.isoformat(), "'" + r["id"], "'" + r["pipeline"], r["format"], r["views"],
              r["watch_min"], r["net_subs"]] for r in rows]
    vals.append(spreadsheetId=sid, range="History!A1", valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS", body={"values": hist}).execute()

    fmt = []
    for t in ("Videos", "Pipelines", "History"):
        fmt += [
            {"updateSheetProperties": {"properties": {"sheetId": tabs[t],
             "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},
            {"repeatCell": {"range": {"sheetId": tabs[t], "startRowIndex": 0, "endRowIndex": 1},
             "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
             "fields": "userEnteredFormat.textFormat.bold"}},
        ]
    sheets.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": fmt}).execute()


# ---------- summary doc ----------

def _table(headers: list, body: list) -> str:
    th = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in body)
    return f'<table border="1" cellpadding="4" style="border-collapse:collapse">' \
           f"<tr>{th}</tr>{trs}</table>"


def _a(r: dict) -> str:
    return f'<a href="{yt_url(r["id"])}">{html.escape(r["title"])}</a>'


def render_summary(channel: dict, rows: list, pipes: list, today: dt.date) -> str:
    pub = [r for r in rows if r["privacy"] == "public"]
    new = [r for r in pub if (today - r["published"]).days <= 7]
    views_7d = sum(r["views_7d"] for r in pub)
    subs_7d = sum(r["net_subs_7d"] for r in pub)
    top_week = sorted(pub, key=lambda r: r["views_7d"], reverse=True)[:10]
    recent = [r for r in pub if (today - r["published"]).days <= 30]
    recent_top = sorted(recent, key=lambda r: r["views_per_day"], reverse=True)[:5]
    recent_bottom = sorted(recent, key=lambda r: r["views_per_day"])[:5]

    def vrow(r):
        return [r["published"].isoformat(), _a(r), r["pipeline"], r["format"], f'{r["views"]:,}',
                f'{r["views_7d"]:,}', r["views_per_day"], r["avg_view_pct"], r["subs_per_1k"]]

    vhead = ["Published", "Video", "Pipeline", "Format", "Views", "Views 7d", "Views/day",
             "Avg view %", "Subs/1k"]
    parts = [
        f"<h1>0005 Weekly - {today.isoformat()}</h1>",
        f"<p>Channel: {html.escape(channel['title'])} | Public videos: {len(pub)} | "
        f"Lifetime views: {sum(r['views'] for r in pub):,} | Views last 7d: {views_7d:,} | "
        f"Net subs last 7d: {subs_7d:+,}</p>",
        "<p><i>Analytics lag ~2 days, so the newest uploads look small. "
        "Shorts = duration up to 3 min.</i></p>",
        "<h2>By pipeline</h2>",
        _table(["Pipeline", "Format", "Videos", "Total views", "Median views", "Median views/day",
                "Avg view %", "Net subs", "Subs/1k", "Best video"],
               [[p["pipeline"], p["format"], p["videos"], f'{p["total_views"]:,}',
                 f'{p["median_views"]:,}', p["median_vpd"], p["avg_view_pct"], p["net_subs"],
                 p["subs_per_1k"], _a({"id": p["best_id"], "title": p["best_title"]})]
                for p in pipes]),
        f"<h2>Uploaded in the last 7 days ({len(new)})</h2>",
        _table(vhead, [vrow(r) for r in new]) if new else "<p>None.</p>",
        "<h2>Most views in the last 7 days (any upload date)</h2>",
        _table(vhead, [vrow(r) for r in top_week]),
        "<h2>Last 30 days: best 5 by views/day</h2>",
        _table(vhead, [vrow(r) for r in recent_top]) if recent else "<p>No uploads.</p>",
        "<h2>Last 30 days: worst 5 by views/day</h2>",
        _table(vhead, [vrow(r) for r in recent_bottom]) if recent else "<p>No uploads.</p>",
    ]
    return "<html><body>" + "".join(parts) + "</body></html>"


def write_doc(drive, folder: str, title: str, body_html: str) -> str:
    media = MediaInMemoryUpload(body_html.encode("utf-8"), mimetype="text/html", resumable=False)
    f = drive.files().create(
        body={"name": title, "mimeType": DOC_MIME, "parents": [folder]},
        media_body=media, fields="id,webViewLink",
    ).execute()
    return f["webViewLink"]


# ---------- main ----------

def main() -> None:
    today = dt.datetime.now(dt.timezone.utc).date()
    yt = build_service("youtube", "v3")
    yta = build_service("youtubeAnalytics", "v2")
    drive = build_service("drive", "v3")
    sheets = build_service("sheets", "v4")

    channel = fetch_channel(yt)
    ids = fetch_video_ids(yt, channel["uploads"])
    videos = fetch_videos(yt, ids)
    print(f"Fetched {len(videos)} videos")

    life = fetch_analytics(yta, ids, channel["published"], today.isoformat(), LIFETIME_METRICS)
    week = fetch_analytics(yta, ids, (today - dt.timedelta(days=7)).isoformat(),
                           today.isoformat(), WEEK_METRICS)
    print(f"Analytics rows: lifetime={len(life)} week={len(week)}")

    rows = build_rows(videos, life, week, today)
    pipes = summarise(rows)

    root = find_or_create(drive, DRIVE_ROOT, FOLDER_MIME, "root")
    folder = find_or_create(drive, DRIVE_SUB, FOLDER_MIME, root)
    sid = find_or_create(drive, SHEET_NAME, SHEET_MIME, folder)
    write_sheet(sheets, sid, rows, pipes, today)
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sid}"
    doc_url = write_doc(drive, folder, f"0005 Weekly - {today.isoformat()}",
                        render_summary(channel, rows, pipes, today))
    print("Sheet and summary doc written")

    pub = [r for r in rows if r["privacy"] == "public"]
    best = max(pub, key=lambda r: r["views_7d"], default=None)
    lines = [
        "<b>📊 0005 weekly report</b>",
        f"{len(pub)} public videos · {sum(r['views_7d'] for r in pub):,} views last 7d · "
        f"{sum(r['net_subs_7d'] for r in pub):+,} subs",
    ]
    if best and best["views_7d"]:
        lines.append(f"Top this week: {html.escape(best['title'])} ({best['views_7d']:,})")
    lines += ["", f'<a href="{sheet_url}">Sheet</a> · <a href="{doc_url}">Summary</a>']
    send_message("\n".join(lines))
    print("Telegram sent")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            send_message(f"❌ 0005 failed: {html.escape(type(exc).__name__)}. Check GitHub Actions.")
        except Exception:
            pass
        raise

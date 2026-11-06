"""0006 — Demand Map crawler.

Depth-first crawl of football YouTube to find long-form videos that beat their own
channel's median (outliers). Spec: Project doc claude/0006-START-HERE.md.

  seed search -> channels of the hits -> each channel's last 12 months of long-form
  uploads (scored) -> featured channels of channels that have outliers -> backtrack.
  Phrases repeated across outlier titles from 2+ channels become new seeds.

State lives in a SQLite file on Drive (football-engine/0006/demand.sqlite) so the
crawl resumes across daily runs; the Google Sheet "0006 Demand Map" is the view.
YouTube data older than 30 days is refreshed or deleted (API data-retention rule).

The repo is public, so Actions logs are public: log counts only.
"""

import argparse
import datetime as dt
import html
import io
import json
import re
import sqlite3
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HERE = Path(__file__).resolve().parent
SEEDS_FILE = HERE / "seeds.json"

DRIVE_ROOT = "football-engine"
DRIVE_SUB = "0006"
DB_NAME = "demand.sqlite"
SHEET_NAME = "0006 Demand Map"
FOLDER_MIME = "application/vnd.google-apps.folder"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"

WINDOW_DAYS = 365          # channel window for the median and for scoring
SEARCH_WINDOW_DAYS = 730   # search only surfaces videos from the last 24 months
MIN_AGE_DAYS = 14          # too-young videos are stored but not scored
SHORT_MAX_SECONDS = 180    # Shorts can run up to 3 min
MIN_SAMPLE = 5             # long-form videos needed for a valid channel median
OUTLIER = 3.0
STRONG = 5.0
MIN_OUTLIER_VIEWS = 10_000 # an outlier must also prove absolute demand
HIGH_VOLUME = 150          # >150 long-form uploads a year = broadcaster/news/podcast feed
DB_VERSION = 2             # bump to start a fresh DB when scoring or filters change
MAX_DEPTH = 2              # 0 seed search, 1 channel from a search, 2 featured channel
CHANNELS_PER_SEARCH = 25
MAX_UPLOADS = 300          # playlist items read per channel
REFRESH_DAYS = 25          # re-crawl channels with outliers before their data expires
EXPIRE_DAYS = 30           # delete YouTube data not refreshed within this
NEW_SEEDS_PER_RUN = 5
SHEET_OUTLIER_ROWS = 2000
COST = {"search": 100}     # every other call we make costs 1 unit

DUR_RE = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
FOOTBALL_TOPIC = "Association_football"
OTHER_SPORT_TOPICS = {
    "American_football", "Rugby_football", "Rugby_union", "Rugby_league", "Basketball",
    "Baseball", "Tennis", "Cricket", "Boxing", "Mixed_martial_arts", "Golf", "Motorsport",
    "Ice_hockey", "Volleyball", "Athletics_(sport)", "Professional_wrestling",
}
NOT_SOCCER_RE = re.compile(
    r"\b(nfl|ncaa|college football|super bowl|fantasy football|quarterback|touchdowns?|"
    r"rugby|cfb|gridiron|packers|cowboys|patriots|giants|steelers|chiefs)\b", re.I)
NOT_REPLICABLE_RE = re.compile(
    r"\b(highlights|full match|full game|live|livestream|watchalong|post[- ]match|"
    r"press conference|presser|matchday|line ?ups?)\b", re.I)
FOOTBALL_RE = re.compile(
    r"\b(soccer|futbol|fútbol|futebol|calcio|fc|premier league|la ?liga|serie a|"
    r"bundesliga|ligue 1|champions league|ucl|epl|world cup|ballon d.or|messi|ronaldo|cr7|"
    r"haaland|mbapp[eé]|neymar|yamal|bellingham|real madrid|barcelona|man(chester)? (united|city)|"
    r"arsenal|liverpool|chelsea|tottenham|juventus|bayern|psg|ac milan|inter milan)\b",
    re.I,
)
STOP = set("""a an and are as at be been before being but by can could did do does doing
for from had has have he her here him his how i if in into is it its just me more most my
no not now of off on once only or our out over own same she so some such than that the
their them then there these they this those through to too under until up very was we were
what when where which while who whom why will with would you your vs v ever every all after
again against any because both down during each few further let lets nobody own s t don
should shouldn isn wasn aren didn doesn won wouldn couldn got get gets went new top best one
two 1 2 3 4 5 6 7 8 9 10 football soccer video full part official highlights""".split())

TOKEN_RE = re.compile(r"[a-z0-9à-ÿ']+")


class QuotaExhausted(Exception):
    pass


# ---------- helpers ----------

def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)


def parse_duration(s: str) -> int:
    m = DUR_RE.match(s or "")
    if not m:
        return 0
    d, h, mi, sec = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + sec


def is_football(ch: dict) -> bool:
    """Soccer-only channels. Multi-sport broadcasters and American football are out."""
    topics = {t.rsplit("/", 1)[-1] for t in ch.get("topics") or []}
    if FOOTBALL_TOPIC in topics:
        return not (topics & OTHER_SPORT_TOPICS)
    text = f"{ch.get('title', '')} {ch.get('description', '')}"
    if topics & OTHER_SPORT_TOPICS or NOT_SOCCER_RE.search(text):
        return False
    return bool(FOOTBALL_RE.search(text))


def is_outlier(score, views) -> bool:
    return score is not None and score >= OUTLIER and (views or 0) >= MIN_OUTLIER_VIEWS


def replicable(title: str) -> bool:
    """Match footage, live streams and pressers can't be remade by a faceless channel."""
    return not NOT_REPLICABLE_RE.search(title or "")


def score_videos(videos: list, today: dt.datetime) -> tuple:
    """Leave-one-out outlier score for a channel's long-form videos in the window.

    videos: dicts with views, published (datetime), duration. Returns
    (median, sample, {video_id: score}); score is None when the sample is too thin
    or the video is too young.
    """
    since = today - dt.timedelta(days=WINDOW_DAYS)
    young = today - dt.timedelta(days=MIN_AGE_DAYS)
    eligible = [v for v in videos if v["duration"] > SHORT_MAX_SECONDS
                and since <= v["published"] <= young]
    scores = {v["id"]: None for v in videos}
    if len(eligible) < MIN_SAMPLE:
        return None, len(eligible), scores
    views = [v["views"] for v in eligible]
    med = statistics.median(views)
    for i, v in enumerate(eligible):
        others = views[:i] + views[i + 1:]
        scores[v["id"]] = round(v["views"] / max(statistics.median(others), 1), 2)
    return med, len(eligible), scores


def phrases(title: str) -> set:
    toks = [t.strip("'") for t in TOKEN_RE.findall(title.lower())]
    toks = [t for t in toks if t]
    out = set()
    for n in (2, 3):
        for i in range(len(toks) - n + 1):
            g = toks[i:i + n]
            if g[0] in STOP or g[-1] in STOP or any(t.isdigit() for t in g):
                continue
            if len(set(g)) < n:
                continue
            out.add(" ".join(g))
    return out


# ---------- YouTube client with a quota meter ----------

class YT:
    def __init__(self, service, limit: int):
        self.s = service
        self.limit = limit
        self.used = 0
        self.calls = 0

    def run(self, req, cost: int = 1, allow_404: bool = False):
        if self.used + cost > self.limit:
            raise QuotaExhausted("budget")
        self.used += cost
        self.calls += 1
        from googleapiclient.errors import HttpError
        for attempt in range(3):
            try:
                return req.execute()
            except HttpError as e:
                status = getattr(e.resp, "status", 0)
                text = str(e)
                if status == 403 and ("quotaExceeded" in text or "dailyLimitExceeded" in text
                                      or "rateLimitExceeded" in text):
                    raise QuotaExhausted("api") from None
                if status == 403 and ("accessNotConfigured" in text
                                      or "insufficientPermissions" in text):
                    raise
                if status == 404 and allow_404:
                    return None
                if status in (403, 404):
                    return None  # disabled playlists/sections, hidden channels: skip the node
                if status >= 500 and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise

    def videos(self, ids: list) -> list:
        out = []
        for i in range(0, len(ids), 50):
            resp = self.run(self.s.videos().list(
                part="snippet,contentDetails,statistics", id=",".join(ids[i:i + 50]),
                maxResults=50))
            for v in (resp or {}).get("items", []):
                sn, st = v["snippet"], v.get("statistics", {})
                out.append({
                    "id": v["id"],
                    "channel": sn["channelId"],
                    "title": sn.get("title", ""),
                    "published": parse_ts(sn["publishedAt"]),
                    "duration": parse_duration(v.get("contentDetails", {}).get("duration", "")),
                    "views": int(st.get("viewCount", 0) or 0),
                    "likes": int(st.get("likeCount", 0) or 0),
                    "comments": int(st.get("commentCount", 0) or 0),
                })
        return out

    def channels(self, ids: list) -> dict:
        out = {}
        for i in range(0, len(ids), 50):
            resp = self.run(self.s.channels().list(
                part="snippet,statistics,topicDetails,contentDetails",
                id=",".join(ids[i:i + 50]), maxResults=50))
            for c in (resp or {}).get("items", []):
                st = c.get("statistics", {})
                vids = int(st.get("videoCount", 0) or 0)
                out[c["id"]] = {
                    "id": c["id"],
                    "title": c["snippet"].get("title", ""),
                    "description": c["snippet"].get("description", "")[:2000],
                    "subs": int(st.get("subscriberCount", 0) or 0),
                    "avg_views": int(st.get("viewCount", 0) or 0) / max(vids, 1),
                    "topics": c.get("topicDetails", {}).get("topicCategories", []),
                    "uploads": c.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", ""),
                }
        return out

    def recent_uploads(self, channel_id: str, uploads: str, since: dt.datetime) -> list:
        """Video ids from the last WINDOW_DAYS, long-form playlist first (UULF), else all uploads."""
        for pid in ("UULF" + channel_id[2:], uploads):
            if not pid:
                continue
            ids, token, ok = [], None, False
            while len(ids) < MAX_UPLOADS:
                resp = self.run(self.s.playlistItems().list(
                    part="contentDetails", playlistId=pid, maxResults=50, pageToken=token),
                    allow_404=True)
                if resp is None:
                    break
                ok = True
                stop = False
                for it in resp.get("items", []):
                    cd = it.get("contentDetails", {})
                    pub = cd.get("videoPublishedAt")
                    if pub and parse_ts(pub) < since:
                        stop = True
                        break
                    ids.append(cd["videoId"])
                token = resp.get("nextPageToken")
                if stop or not token:
                    break
            if ok:
                return ids
        return []

    def featured(self, channel_id: str) -> list:
        resp = self.run(self.s.channelSections().list(part="contentDetails", channelId=channel_id))
        out = []
        for sec in (resp or {}).get("items", []):
            out += sec.get("contentDetails", {}).get("channels", []) or []
        return [c for c in dict.fromkeys(out) if c != channel_id]

    def search(self, term: str, after: dt.datetime, region: str = None) -> list:
        kw = {"regionCode": region} if region else {}
        resp = self.run(self.s.search().list(
            part="snippet", q=term, type="video", maxResults=50, order="relevance",
            publishedAfter=iso(after), relevanceLanguage="en", **kw), cost=COST["search"])
        return [it["id"]["videoId"] for it in (resp or {}).get("items", [])
                if it.get("id", {}).get("videoId")]


# ---------- database ----------

SCHEMA = """
CREATE TABLE IF NOT EXISTS seeds(term TEXT PRIMARY KEY, niche TEXT, source TEXT,
  status TEXT DEFAULT 'pending', ord INTEGER, added TEXT, searched TEXT);
CREATE TABLE IF NOT EXISTS channels(id TEXT PRIMARY KEY, title TEXT, subs INTEGER,
  niche TEXT, football INTEGER, median REAL, sample INTEGER, scored INTEGER,
  outliers INTEGER, best REAL, depth INTEGER, found_via TEXT, status TEXT, crawled TEXT);
CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY, channel TEXT, title TEXT,
  published TEXT, duration INTEGER, views INTEGER, likes INTEGER, comments INTEGER,
  score REAL, niche TEXT, found_via TEXT, fetched TEXT);
CREATE TABLE IF NOT EXISTS stack(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, ref TEXT,
  depth INTEGER, niche TEXT, via TEXT, UNIQUE(kind, ref));
CREATE TABLE IF NOT EXISTS runs(started TEXT, units INTEGER, searches INTEGER,
  channels INTEGER, scored INTEGER, new_outliers INTEGER, stack INTEGER, seeds_left INTEGER,
  stop TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS videos_channel ON videos(channel);
CREATE INDEX IF NOT EXISTS videos_score ON videos(score);
"""


def open_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    row = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()
    has_data = db.execute("SELECT COUNT(*) FROM seeds").fetchone()[0]
    if has_data and (not row or int(row[0]) != DB_VERSION):
        db.close()
        path.unlink()
        print(f"DB version changed: starting fresh (v{DB_VERSION})")
        return open_db(path)
    db.execute("INSERT OR REPLACE INTO meta VALUES('version', ?)", (str(DB_VERSION),))
    db.commit()
    return db


def load_seeds(db: sqlite3.Connection, today: dt.datetime) -> None:
    data = json.loads(SEEDS_FILE.read_text(encoding="utf-8"))
    nxt = (db.execute("SELECT COALESCE(MAX(ord), 0) FROM seeds").fetchone()[0] or 0) + 1
    for niche in ("football", "adjacent"):
        for term in data.get(niche, []):
            t = term.strip().lower()
            if not t:
                continue
            cur = db.execute(
                "INSERT OR IGNORE INTO seeds(term, niche, source, ord, added) VALUES(?,?,?,?,?)",
                (t, niche, "seed", nxt, iso(today)))
            nxt += cur.rowcount
    db.commit()


def expire_old(db: sqlite3.Connection, today: dt.datetime) -> int:
    cutoff = iso(today - dt.timedelta(days=EXPIRE_DAYS))
    n = db.execute("DELETE FROM videos WHERE fetched < ?", (cutoff,)).rowcount
    db.execute("UPDATE channels SET status='expired', median=NULL, scored=0, outliers=0, best=NULL "
               "WHERE crawled < ? AND status IN ('done','thin')", (cutoff,))
    db.commit()
    return n


def push(db: sqlite3.Connection, kind: str, ref: str, depth: int, niche: str, via: str) -> None:
    db.execute("INSERT OR IGNORE INTO stack(kind, ref, depth, niche, via) VALUES(?,?,?,?,?)",
               (kind, ref, depth, niche, via))


def channel_fresh(db: sqlite3.Connection, cid: str, today: dt.datetime) -> bool:
    row = db.execute("SELECT status, crawled FROM channels WHERE id=?", (cid,)).fetchone()
    if not row or not row["crawled"]:
        return False
    if row["status"] in ("done", "thin", "off-topic"):
        return parse_ts(row["crawled"]) > today - dt.timedelta(days=REFRESH_DAYS)
    return False


def next_node(db: sqlite3.Connection, today: dt.datetime):
    row = db.execute("SELECT * FROM stack ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        db.execute("DELETE FROM stack WHERE id=?", (row["id"],))
        return dict(row)
    cutoff = iso(today - dt.timedelta(days=REFRESH_DAYS))
    stale = db.execute("SELECT id, depth, niche, found_via FROM channels WHERE outliers > 0 "
                       "AND status IN ('done','expired') AND crawled < ? ORDER BY best DESC LIMIT 1",
                       (cutoff,)).fetchone()
    if stale:
        return {"kind": "refresh", "ref": stale["id"], "depth": stale["depth"] or 1,
                "niche": stale["niche"], "via": stale["found_via"]}
    seed = db.execute("SELECT term, niche FROM seeds WHERE status='pending' "
                      "ORDER BY ord LIMIT 1").fetchone()
    if seed:
        return {"kind": "search", "ref": seed["term"], "depth": 0, "niche": seed["niche"],
                "via": seed["term"]}
    return None


# ---------- nodes ----------

def do_search(db, yt: YT, node: dict, today: dt.datetime, stats: dict) -> None:
    term, niche = node["ref"], node["niche"]
    # GB region so "football" means soccer, not the NFL
    ids = yt.search(term, today - dt.timedelta(days=SEARCH_WINDOW_DAYS),
                    "GB" if niche == "football" else None)
    stats["searches"] += 1
    db.execute("UPDATE seeds SET status='done', searched=? WHERE term=?", (iso(today), term))
    hits = [v for v in yt.videos(ids) if v["duration"] > SHORT_MAX_SECONDS]
    ch_ids = list(dict.fromkeys(v["channel"] for v in hits))
    if not ch_ids:
        db.commit()
        return
    info = yt.channels(ch_ids)
    ranked = []
    for v in hits:
        ch = info.get(v["channel"])
        if not ch or v["channel"] in [r[1] for r in ranked]:
            continue
        if niche == "football" and not is_football(ch):
            continue
        ranked.append((v["views"] / max(ch["avg_views"], 1), v["channel"]))
    ranked.sort(reverse=True)
    picks = [cid for _, cid in ranked if not channel_fresh(db, cid, today)][:CHANNELS_PER_SEARCH]
    for cid in reversed(picks):  # best candidate ends on top of the LIFO stack
        upsert_channel(db, info[cid], niche, 1, term, status="queued")
        push(db, "channel", cid, 1, niche, term)
    db.commit()


def upsert_channel(db, ch: dict, niche: str, depth: int, via: str, status: str) -> None:
    db.execute(
        "INSERT INTO channels(id, title, subs, niche, football, depth, found_via, status) "
        "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title, "
        "subs=excluded.subs, football=excluded.football, "
        "status=CASE WHEN channels.status IN ('done','thin','off-topic') THEN channels.status "
        "ELSE excluded.status END",
        (ch["id"], ch["title"], ch["subs"], niche, int(is_football(ch)), depth, via, status))


def do_channel(db, yt: YT, node: dict, today: dt.datetime, stats: dict) -> None:
    cid, depth, niche, via = node["ref"], node["depth"], node["niche"], node["via"]
    expand = node["kind"] == "channel"
    if node["kind"] == "channel" and channel_fresh(db, cid, today):
        return
    ch = yt.channels([cid]).get(cid)
    if not ch:
        db.execute("UPDATE channels SET status='gone', crawled=? WHERE id=?", (iso(today), cid))
        db.commit()
        return
    upsert_channel(db, ch, niche, depth, via, status="crawling")
    if niche == "football" and not is_football(ch):
        db.execute("UPDATE channels SET status='off-topic', crawled=? WHERE id=?", (iso(today), cid))
        db.commit()
        return

    ids = yt.recent_uploads(cid, ch["uploads"], today - dt.timedelta(days=WINDOW_DAYS))
    vids = [v for v in yt.videos(ids) if v["duration"] > SHORT_MAX_SECONDS]
    med, sample, scores = score_videos(vids, today)
    stats["channels"] += 1

    before = {r["id"] for r in db.execute(
        "SELECT id FROM videos WHERE channel=? AND score >= ? AND views >= ?",
        (cid, OUTLIER, MIN_OUTLIER_VIEWS))}
    views = {v["id"]: v["views"] for v in vids}
    for v in vids:
        s = scores.get(v["id"])
        db.execute(
            "INSERT INTO videos(id, channel, title, published, duration, views, likes, comments, "
            "score, niche, found_via, fetched) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, views=excluded.views, "
            "likes=excluded.likes, comments=excluded.comments, score=excluded.score, "
            "fetched=excluded.fetched",
            (v["id"], cid, v["title"], iso(v["published"]), v["duration"], v["views"],
             v["likes"], v["comments"], s, niche, via, iso(today)))
    scored = [s for s in scores.values() if s is not None]
    outliers = [vid for vid, s in scores.items() if is_outlier(s, views.get(vid))]
    stats["scored"] += len(scored)
    stats["new_outliers"] += len(set(outliers) - before)
    db.execute(
        "UPDATE channels SET median=?, sample=?, scored=?, outliers=?, best=?, status=?, crawled=? "
        "WHERE id=?",
        (med, sample, len(scored), len(outliers), max(scored) if scored else None,
         "done" if med is not None else "thin", iso(today), cid))
    db.commit()

    if expand and niche == "football" and outliers and depth < MAX_DEPTH \
            and sample <= HIGH_VOLUME:
        for fid in reversed(yt.featured(cid)):
            if not channel_fresh(db, fid, today):
                push(db, "channel", fid, depth + 1, niche, via)
        db.commit()


def expand_seeds(db, today: dt.datetime) -> int:
    rows = db.execute("SELECT v.title, v.channel FROM videos v JOIN channels c ON c.id=v.channel "
                      "WHERE v.score >= ? AND v.views >= ? AND v.niche='football' "
                      "AND c.sample <= ?", (OUTLIER, MIN_OUTLIER_VIEWS, HIGH_VOLUME)).fetchall()
    chans = {}
    for r in rows:
        if not replicable(r["title"]):
            continue
        for p in phrases(r["title"]):
            chans.setdefault(p, set()).add(r["channel"])
    existing = [r["term"] for r in db.execute("SELECT term FROM seeds")]
    cands = sorted(((len(c), p) for p, c in chans.items() if len(c) >= 2), reverse=True)
    nxt = (db.execute("SELECT COALESCE(MAX(ord), 0) FROM seeds").fetchone()[0] or 0) + 1
    added = 0
    for _, p in cands:
        if added >= NEW_SEEDS_PER_RUN:
            break
        if any(p in t or t in p for t in existing):
            continue
        db.execute("INSERT OR IGNORE INTO seeds(term, niche, source, ord, added) "
                   "VALUES(?,?,?,?,?)", (p, "football", "expanded", nxt, iso(today)))
        existing.append(p)
        nxt += 1
        added += 1
    db.commit()
    return added


def crawl(db, yt: YT, today: dt.datetime, stats: dict) -> str:
    errors = 0
    while True:
        node = next_node(db, today)
        if node is None:
            return "frontier empty"
        try:
            if node["kind"] == "search":
                do_search(db, yt, node, today, stats)
            else:
                do_channel(db, yt, node, today, stats)
        except QuotaExhausted as e:
            # put the node back so tomorrow resumes exactly here
            if node["kind"] == "search":
                db.execute("UPDATE seeds SET status='pending' WHERE term=?", (node["ref"],))
            else:
                push(db, node["kind"], node["ref"], node["depth"], node["niche"], node["via"])
            db.commit()
            return "quota budget used" if str(e) == "budget" else "YouTube daily quota hit"
        except Exception as e:  # one bad node must not kill the run; it is dropped, not retried
            errors += 1
            db.rollback()
            print(f"Node failed ({node['kind']}): {type(e).__name__}")
            if errors >= 10:
                raise


# ---------- Drive + Sheet ----------

def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def find(drive, name: str, parent: str, mime: str = None):
    q = f"name = '{_q(name)}' and '{parent}' in parents and trashed = false"
    if mime:
        q += f" and mimeType = '{mime}'"
    hit = drive.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
    return hit[0]["id"] if hit else None


def find_or_create(drive, name: str, mime: str, parent: str) -> str:
    fid = find(drive, name, parent, mime)
    if fid:
        return fid
    return drive.files().create(body={"name": name, "mimeType": mime, "parents": [parent]},
                                fields="id").execute()["id"]


def pull_db(drive, folder: str, local: Path) -> bool:
    from googleapiclient.http import MediaIoBaseDownload
    fid = find(drive, DB_NAME, folder)
    if not fid:
        return False
    buf = io.FileIO(str(local), "wb")
    dl = MediaIoBaseDownload(buf, drive.files().get_media(fileId=fid))
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.close()
    return True


def push_db(drive, folder: str, local: Path) -> None:
    from googleapiclient.http import MediaFileUpload
    fid = find(drive, DB_NAME, folder)
    media = MediaFileUpload(str(local), mimetype="application/octet-stream", resumable=True)
    if fid:
        drive.files().update(fileId=fid, media_body=media).execute()
    else:
        drive.files().create(body={"name": DB_NAME, "parents": [folder]}, media_body=media,
                             fields="id").execute()


def txt(s) -> str:
    s = "" if s is None else str(s)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def link(url: str, text: str) -> str:
    return f'=HYPERLINK("{url}","{str(text).replace(chr(34), chr(34) * 2)[:250]}")'


def outlier_rows(db, niche: str, limit: int) -> list:
    rows = [["Thumb", "Score", "Title", "Channel", "Views", "Channel median", "Length (min)",
             "Published", "Subs", "Found via"]]
    for r in db.execute(
            "SELECT v.*, c.title AS ctitle, c.median, c.subs FROM videos v "
            "JOIN channels c ON c.id=v.channel WHERE v.niche=? AND v.score >= ? AND v.views >= ? "
            "AND c.sample <= ? ORDER BY v.score DESC",
            (niche, OUTLIER, MIN_OUTLIER_VIEWS, HIGH_VOLUME)):
        if not replicable(r["title"]):
            continue
        if len(rows) > limit:
            break
        rows.append([
            f'=IMAGE("https://i.ytimg.com/vi/{r["id"]}/mqdefault.jpg")', r["score"],
            link(f"https://www.youtube.com/watch?v={r['id']}", r["title"]),
            link(f"https://www.youtube.com/channel/{r['channel']}", r["ctitle"]),
            r["views"], round(r["median"] or 0), round(r["duration"] / 60, 1), r["published"][:10],
            r["subs"], txt(r["found_via"]),
        ])
    return rows


def sheet_data(db, runs: list) -> dict:
    out_rows = outlier_rows(db, "football", SHEET_OUTLIER_ROWS)
    adj_rows = outlier_rows(db, "adjacent", 300)

    ch_rows = [["Channel", "Niche", "Subs", "Long-form (12m)", "Median views", "Outliers (3x+)",
                "Hit rate", "Best score", "Depth", "Found via", "Status", "Crawled", "Type"]]
    for r in db.execute("SELECT * FROM channels WHERE status IN ('done','thin') "
                        "ORDER BY (COALESCE(sample, 0) > ?), niche != 'football', outliers DESC, "
                        "best DESC", (HIGH_VOLUME,)):
        hit = round(r["outliers"] / r["scored"], 3) if r["scored"] else ""
        ch_rows.append([
            link(f"https://www.youtube.com/channel/{r['id']}", r["title"]), r["niche"], r["subs"],
            r["sample"], round(r["median"] or 0), r["outliers"], hit, r["best"], r["depth"],
            txt(r["found_via"]), r["status"], (r["crawled"] or "")[:10],
            "high-volume feed" if (r["sample"] or 0) > HIGH_VOLUME else "creator",
        ])

    # Topics: phrase hit rates over every scored football video, not just winners.
    total, wins, best = {}, {}, {}
    for r in db.execute("SELECT v.id, v.title, v.channel, v.score, v.views FROM videos v "
                        "JOIN channels c ON c.id=v.channel WHERE v.niche='football' "
                        "AND v.score IS NOT NULL AND c.sample <= ?", (HIGH_VOLUME,)):
        if not replicable(r["title"]):
            continue
        for p in phrases(r["title"]):
            total[p] = total.get(p, 0) + 1
            if is_outlier(r["score"], r["views"]):
                wins.setdefault(p, []).append((r["score"], r["channel"], r["id"], r["title"]))
    top_rows = [["Phrase", "Outlier channels", "Outliers", "Videos using it", "Hit rate",
                 "Median outlier score", "Best example"]]
    topics = []
    for p, w in wins.items():
        n_ch = len({c for _, c, _, _ in w})
        if n_ch < 2:
            continue
        b = max(w)
        topics.append((n_ch, len(w), p, total[p], statistics.median(s for s, *_ in w), b))
    topics.sort(key=lambda t: (t[0], t[1]), reverse=True)
    # drop "fifa world" when "fifa world cup" carries (almost) the same videos
    by_wins = {}
    for t in topics:
        by_wins.setdefault(t[1], []).append(t)
    topics = [t for t in topics if not any(
        o[2] != t[2] and f" {t[2]} " in f" {o[2]} " and o[3] >= 0.9 * t[3]
        for o in by_wins[t[1]])]
    for n_ch, n_w, p, tot, med, b in topics[:500]:
        top_rows.append([txt(p), n_ch, n_w, tot, round(n_w / tot, 3), round(med, 2),
                         link(f"https://www.youtube.com/watch?v={b[2]}", b[3])])

    log_rows = [["Run (UTC)", "Units", "Searches", "Channels", "Videos scored", "New outliers",
                 "Stack left", "Seeds left", "Stopped because"]]
    for r in runs:
        log_rows.append([r["started"], r["units"], r["searches"], r["channels"], r["scored"],
                         r["new_outliers"], r["stack"], r["seeds_left"], r["stop"]])
    import library as lib
    formats = lib.load_formats()
    pool = lib.creator_pool(db, OUTLIER, MIN_OUTLIER_VIEWS, HIGH_VOLUME, replicable)
    fmt_rows, fstats, base = lib.format_rows(pool, formats, link)
    return {"Ideas": lib.idea_rows(pool, fstats, base, formats, link), "Formats": fmt_rows,
            "Outliers": out_rows, "Topics": top_rows, "Features": lib.feature_rows(pool),
            "Channels": ch_rows, "Adjacent": adj_rows, "Log": log_rows,
            "_export": lib.export_text(pool)}


def write_export(drive, folder: str, text: str) -> None:
    """Top creator outliers as plain text in Drive (refreshed every run) for Claude's reviews."""
    from googleapiclient.http import MediaInMemoryUpload
    name = "0006 export - top outliers.txt"
    media = MediaInMemoryUpload(text.encode("utf-8"), mimetype="text/plain")
    fid = find(drive, name, folder)
    if fid:
        drive.files().update(fileId=fid, media_body=media).execute()
    else:
        drive.files().create(body={"name": name, "parents": [folder]}, media_body=media,
                             fields="id").execute()


def write_sheet(drive, sheets, folder: str, data: dict) -> str:
    export = data.pop("_export", None)
    if export:
        write_export(drive, folder, export)
    sid = find_or_create(drive, SHEET_NAME, SHEET_MIME, folder)
    meta = sheets.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties").execute()
    tabs = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    reqs = []
    if "Outliers" not in tabs and "Sheet1" in tabs:
        reqs.append({"updateSheetProperties": {"properties": {"sheetId": tabs["Sheet1"],
                     "title": "Outliers"}, "fields": "title"}})
        tabs["Outliers"] = tabs.pop("Sheet1")
    reqs += [{"addSheet": {"properties": {"title": t}}} for t in data if t not in tabs]
    if reqs:
        sheets.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": reqs}).execute()
        meta = sheets.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties").execute()
        tabs = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}

    sheets.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [
        {"updateCells": {"range": {"sheetId": tabs[t]}, "fields": "userEnteredFormat"}}
        for t in data]}).execute()
    vals = sheets.spreadsheets().values()
    for tab, rows in data.items():
        vals.clear(spreadsheetId=sid, range=tab).execute()
        vals.update(spreadsheetId=sid, range=f"{tab}!A1", valueInputOption="USER_ENTERED",
                    body={"values": rows}).execute()

    fmt = []
    for t in data:
        fmt += [
            {"updateSheetProperties": {"properties": {"sheetId": tabs[t],
             "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},
            {"repeatCell": {"range": {"sheetId": tabs[t], "startRowIndex": 0, "endRowIndex": 1},
             "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
             "fields": "userEnteredFormat.textFormat.bold"}},
        ]
    for tab in ("Outliers", "Adjacent"):
        fmt += image_layout(tabs[tab], len(data[tab]))
    sheets.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": fmt}).execute()
    return f"https://docs.google.com/spreadsheets/d/{sid}"


def image_layout(sheet_id: int, n: int) -> list:
    fmt = [
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS",
         "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 128}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS",
         "startIndex": 2, "endIndex": 3}, "properties": {"pixelSize": 420}, "fields": "pixelSize"}},
    ]
    if n > 1:
        fmt.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id,
                    "dimension": "ROWS", "startIndex": 1, "endIndex": n},
                    "properties": {"pixelSize": 72}, "fields": "pixelSize"}})
    return fmt


# ---------- main ----------

def counts(db) -> dict:
    one = lambda q, *a: db.execute(q, a).fetchone()[0]  # noqa: E731
    return {
        "videos": one("SELECT COUNT(*) FROM videos WHERE score IS NOT NULL"),
        "outliers": one("SELECT COUNT(*) FROM videos WHERE score >= ? AND views >= ?",
                        OUTLIER, MIN_OUTLIER_VIEWS),
        "strong": one("SELECT COUNT(*) FROM videos WHERE score >= ? AND views >= ?",
                      STRONG, MIN_OUTLIER_VIEWS),
        "channels": one("SELECT COUNT(*) FROM channels WHERE status IN ('done','thin') "
                        "AND niche='football'"),
        "stack": one("SELECT COUNT(*) FROM stack"),
        "seeds_left": one("SELECT COUNT(*) FROM seeds WHERE status='pending'"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-units", type=int, default=9000)
    ap.add_argument("--db", type=Path, default=HERE / DB_NAME)
    ap.add_argument("--offline", action="store_true", help="local DB only: no Drive, Sheet, Telegram")
    ap.add_argument("--sheet-only", action="store_true", help="rebuild the sheet from the DB; no crawl")
    args = ap.parse_args()
    budget = max(200, min(args.max_units, 9500))
    today = now_utc()

    from shared.google_client import build_service
    drive = sheets = folder = None
    if not args.offline:
        drive = build_service("drive", "v3")
        sheets = build_service("sheets", "v4")
        root = find_or_create(drive, DRIVE_ROOT, FOLDER_MIME, "root")
        folder = find_or_create(drive, DRIVE_SUB, FOLDER_MIME, root)
        print("Resumed DB from Drive" if pull_db(drive, folder, args.db) else "Starting new DB")

    db = open_db(args.db)
    if args.sheet_only:
        runs = [dict(r) for r in db.execute("SELECT * FROM runs ORDER BY started DESC LIMIT 200")]
        data = sheet_data(db, runs)
        db.close()
        write_sheet(drive, sheets, folder, data)
        print("Sheet rebuilt (no crawl)")
        return
    load_seeds(db, today)
    print(f"Expired {expire_old(db, today)} videos older than {EXPIRE_DAYS} days")

    yt = YT(build_service("youtube", "v3"), budget)
    stats = {"searches": 0, "channels": 0, "scored": 0, "new_outliers": 0}
    stop = "error"
    try:
        stop = crawl(db, yt, today, stats)
    finally:
        added = expand_seeds(db, today)
        c = counts(db)
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)",
                   (iso(today)[:16].replace("T", " "), yt.used, stats["searches"],
                    stats["channels"], stats["scored"], stats["new_outliers"], c["stack"],
                    c["seeds_left"], stop))
        db.commit()
        runs = [dict(r) for r in db.execute("SELECT * FROM runs ORDER BY started DESC LIMIT 200")]
        data = sheet_data(db, runs)
        db.close()
        if not args.offline:
            push_db(drive, folder, args.db)
            print("DB saved to Drive")
    print(f"Stop: {stop} | units {yt.used}/{budget} | searches {stats['searches']} | "
          f"channels {stats['channels']} | scored {stats['scored']} | "
          f"new outliers {stats['new_outliers']} | new seeds {added}")
    print(f"Totals: {c['videos']} scored videos, {c['channels']} football channels, "
          f"{c['outliers']} outliers ({c['strong']} at {STRONG:g}x+), stack {c['stack']}, "
          f"seeds left {c['seeds_left']}")
    if args.offline:
        return

    url = write_sheet(drive, sheets, folder, data)
    print("Sheet written")
    send_message_safe("\n".join([
        "<b>🗺 0006 Demand Map</b>",
        f"+{stats['new_outliers']} outliers · {stats['channels']} channels · "
        f"{stats['searches']} searches · {yt.used:,} units",
        f"Totals: {c['outliers']:,} outliers ({c['strong']:,} at 5x+) from "
        f"{c['videos']:,} scored videos · {c['channels']} channels",
        f"Stack {c['stack']} · seeds left {c['seeds_left']} · {html.escape(stop)}",
        "", f'<a href="{url}">Open the sheet</a>',
    ]))


def send_message_safe(text: str) -> None:
    try:
        from shared.telegram import send_message
        send_message(text)
        print("Telegram sent")
    except Exception as exc:  # the sheet is the deliverable; a failed ping must not fail the run
        print(f"Telegram failed: {type(exc).__name__}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        send_message_safe(f"❌ 0006 failed: {html.escape(type(exc).__name__)}. Check GitHub Actions.")
        raise

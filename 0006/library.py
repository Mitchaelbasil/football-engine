"""0006 Phase 2-3: Format Library, title/length features and the Idea Gate.

Everything here reads the Demand Map DB; it never calls YouTube.

* Formats: each title is matched against formats.json (multi-label). For every
  format we count ALL creator videos that use it, not just winners, so the hit rate
  and lift carry the negative evidence too.
* Features: hit rate by title traits and by video length.
* Ideas: idea cards in ideas.json are checked against the evidence (Idea Gate).
"""

import json
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORMATS_FILE = HERE / "formats.json"
IDEAS_FILE = HERE / "ideas.json"

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
CAPS_RE = re.compile(r"\b[A-Z]{4,}\b")
NUM_RE = re.compile(r"\d")

GATE_MIN_OUTLIERS = 3
GATE_MIN_CHANNELS = 2
GATE_MIN_FORMAT_SAMPLE = 15


def load_formats() -> list:
    data = json.loads(FORMATS_FILE.read_text(encoding="utf-8"))
    for f in data["formats"]:
        f["rx"] = re.compile(f["re"], re.I)
    return data["formats"]


LEAD_RE = re.compile(r"^[^\w]+")


def classify(title: str, formats: list) -> list:
    t = LEAD_RE.sub("", title or "")  # leading emoji, flags, zero-width spaces, quotes
    return [f["id"] for f in formats if f["rx"].search(t)]


def creator_pool(db, outlier, min_views, high_volume, replicable) -> list:
    """Scored football videos from creator channels with replicable titles."""
    rows = []
    for r in db.execute(
            "SELECT v.id, v.title, v.channel, v.score, v.views, v.duration, v.published, "
            "c.title AS ctitle FROM videos v JOIN channels c ON c.id=v.channel "
            "WHERE v.niche='football' AND v.score IS NOT NULL AND c.sample <= ?", (high_volume,)):
        if not replicable(r["title"]):
            continue
        d = dict(r)
        d["win"] = d["score"] >= outlier and (d["views"] or 0) >= min_views
        rows.append(d)
    return rows


def _rate(rows: list) -> tuple:
    n = len(rows)
    w = [r for r in rows if r["win"]]
    return n, len(w), (len(w) / n if n else 0.0), w


def _examples(wins: list, link, k: int = 3) -> str:
    top = sorted(wins, key=lambda r: r["score"], reverse=True)[:k]
    return " | ".join(f"{r['title'][:70]} ({r['score']:g}x)" for r in top)


def format_rows(pool: list, formats: list, link) -> tuple:
    base_n, base_w, base_rate, _ = _rate(pool)
    for r in pool:
        r["formats"] = classify(r["title"], formats)
    out = [["Format", "Fits us", "Videos", "Outliers", "Hit rate", "Lift vs baseline",
            "Outlier channels", "Median outlier score", "Median outlier views", "Why it works",
            "Best examples"]]
    stats = {}
    for f in formats:
        rows = [r for r in pool if f["id"] in r["formats"]]
        n, w, rate, wins = _rate(rows)
        lift = rate / base_rate if base_rate else 0
        stats[f["id"]] = {"n": n, "w": w, "rate": rate, "lift": lift}
        out.append([
            f["name"], "yes" if f["fits_us"] else "no", n, w, round(rate, 3),
            round(lift, 2) if n else "", len({r["channel"] for r in wins}),
            round(statistics.median(r["score"] for r in wins), 2) if wins else "",
            round(statistics.median(r["views"] for r in wins)) if wins else "",
            f["why"], _examples(wins, link),
        ])
    none = [r for r in pool if not r["formats"]]
    n, w, rate, wins = _rate(none)
    out.append(["(no known format)", "", n, w, round(rate, 3),
                round(rate / base_rate, 2) if base_rate else "", len({r["channel"] for r in wins}),
                "", "", "Titles none of the formats match: mine these for new formats.",
                _examples(wins, link)])
    out.append(["BASELINE (all creator videos)", "", base_n, base_w, round(base_rate, 3), 1.0,
                "", "", "", "Hit rate of every replicable video from creator channels.", ""])
    head, body = out[0], out[1:-2]
    body.sort(key=lambda row: (row[1] == "yes", row[2] >= GATE_MIN_FORMAT_SAMPLE,
                               row[5] if row[5] != "" else 0), reverse=True)
    return [head] + body + out[-2:], stats, base_rate


def feature_rows(pool: list) -> list:
    base_n, base_w, base_rate, _ = _rate(pool)
    groups = [
        ("Title has a number", lambda r: bool(NUM_RE.search(r["title"]))),
        ("Title is a question (?)", lambda r: "?" in r["title"]),
        ("Title has an ALL-CAPS word", lambda r: bool(CAPS_RE.search(r["title"]))),
        ("Title has an emoji", lambda r: bool(EMOJI_RE.search(r["title"]))),
        ("Title has '!'", lambda r: "!" in r["title"]),
        ("Title has '|' (keyword stuffing)", lambda r: "|" in r["title"]),
        ("Title under 40 chars", lambda r: len(r["title"]) < 40),
        ("Title 40-60 chars", lambda r: 40 <= len(r["title"]) <= 60),
        ("Title 61-80 chars", lambda r: 60 < len(r["title"]) <= 80),
        ("Title over 80 chars", lambda r: len(r["title"]) > 80),
        ("Length 3-8 min", lambda r: 180 < r["duration"] <= 480),
        ("Length 8-12 min", lambda r: 480 < r["duration"] <= 720),
        ("Length 12-20 min", lambda r: 720 < r["duration"] <= 1200),
        ("Length 20-40 min", lambda r: 1200 < r["duration"] <= 2400),
        ("Length 40+ min", lambda r: r["duration"] > 2400),
    ]
    out = [["Trait", "Videos", "Outliers", "Hit rate", "Lift vs baseline"]]
    for name, fn in groups:
        n, w, rate, _ = _rate([r for r in pool if fn(r)])
        out.append([name, n, w, round(rate, 3), round(rate / base_rate, 2) if base_rate and n else ""])
    out.append(["BASELINE", base_n, base_w, round(base_rate, 3), 1.0])
    return out


def idea_rows(pool: list, stats: dict, base_rate: float, formats: list, link) -> list:
    """Idea Gate: every idea needs subject demand AND a format that beats the baseline."""
    if not IDEAS_FILE.exists():
        return [["No ideas.json yet"]]
    ideas = json.loads(IDEAS_FILE.read_text(encoding="utf-8")).get("ideas", [])
    names = {f["id"]: f["name"] for f in formats}
    out = [["Gate", "Idea", "Subject terms", "Format", "Subject outliers", "Subject channels",
            "Subject hit rate", "Format hit rate", "Format lift", "Why it fails", "Title options",
            "Thumbnail", "Angle (mechanism -> outcome)", "Evidence"]]
    for idea in ideas:
        terms = [t.lower() for t in idea.get("subject_terms", [])]
        rows = [r for r in pool if any(t in r["title"].lower() for t in terms)]
        n, w, rate, wins = _rate(rows)
        chans = len({r["channel"] for r in wins})
        fs = stats.get(idea.get("format"), {"n": 0, "rate": 0, "lift": 0})
        fails = []
        if w < GATE_MIN_OUTLIERS:
            fails.append(f"subject has {w} outliers (<{GATE_MIN_OUTLIERS})")
        if chans < GATE_MIN_CHANNELS:
            fails.append(f"outliers from {chans} channel(s) (<{GATE_MIN_CHANNELS})")
        if fs["n"] < GATE_MIN_FORMAT_SAMPLE:
            fails.append(f"format sample {fs['n']} (<{GATE_MIN_FORMAT_SAMPLE})")
        elif fs["lift"] < 1.0:
            fails.append(f"format lift {fs['lift']:.2f} (<1.0)")
        out.append([
            "PASS" if not fails else "FAIL", idea.get("idea", ""), ", ".join(terms),
            names.get(idea.get("format"), idea.get("format", "?")), w, chans,
            round(rate, 3) if n else "", round(fs["rate"], 3), round(fs["lift"], 2),
            "; ".join(fails), " || ".join(idea.get("titles", [])), idea.get("thumbnail", ""),
            idea.get("angle", ""), _examples(wins, link),
        ])
    return out


def export_text(pool: list, limit: int = 400) -> str:
    """Plain-text dump of the strongest creator outliers, for Claude's format/idea review."""
    wins = sorted([r for r in pool if r["win"]], key=lambda r: r["score"], reverse=True)[:limit]
    lines = ["score\tviews\tmin\tformats\tchannel\ttitle"]
    for r in wins:
        lines.append(f"{r['score']:g}\t{r['views']}\t{r['duration'] // 60}\t"
                     f"{','.join(r.get('formats', [])) or '-'}\t{r['ctitle']}\t{r['title']}")
    return "\n".join(lines)

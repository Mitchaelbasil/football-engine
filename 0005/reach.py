"""Impressions + thumbnail CTR per video from the YouTube Reporting API.

The Analytics API has no impressions/CTR, so 0005 keeps a Reporting API job for
`channel_reach_basic_a1` (date, video_id, video_thumbnail_impressions,
video_thumbnail_impressions_ctr). YouTube writes one report per day once the job
exists (first files ~48 h after the job is created) and keeps them ~60 days, so
0005 stores every daily row it sees in the sheet's "Reach daily" tab.
"""

import csv
import io

REPORT_TYPE = "channel_reach_basic_a1"


def ensure_job(rep) -> tuple:
    """Return (job, created_now)."""
    jobs, token = [], None
    while True:
        resp = rep.jobs().list(pageToken=token).execute() if token else rep.jobs().list().execute()
        jobs += resp.get("jobs", [])
        token = resp.get("nextPageToken")
        if not token:
            break
    for j in jobs:
        if j.get("reportTypeId") == REPORT_TYPE:
            return j, False
    job = rep.jobs().create(body={"reportTypeId": REPORT_TYPE, "name": "0005 reach"}).execute()
    return job, True


def _download(rep, url: str) -> str:
    from googleapiclient.http import MediaIoBaseDownload
    req = rep.media().download_media(resourceName=" ")
    req.uri = url
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req, chunksize=-1)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue().decode("utf-8")


def fetch(rep, known_dates: set) -> tuple:
    """Daily rows [(date, video_id, impressions, ctr)] for report days not seen before.

    Returns (rows, status_text).
    """
    try:
        job, created = ensure_job(rep)
    except Exception as exc:  # API disabled in the Cloud project, or no permission
        text = str(exc)
        if "accessNotConfigured" in text or "has not been used" in text or "disabled" in text:
            return [], "YouTube Reporting API is not enabled in the Google Cloud project"
        return [], f"Reporting API error: {type(exc).__name__}"
    if created:
        return [], "Reach job created today; first data arrives in about 48 hours"
    reports, token = [], None
    while True:
        kw = {"jobId": job["id"]}
        if token:
            kw["pageToken"] = token
        resp = rep.jobs().reports().list(**kw).execute()
        reports += resp.get("reports", [])
        token = resp.get("nextPageToken")
        if not token:
            break
    rows = []
    fetched = 0
    for r in sorted(reports, key=lambda r: r.get("startTime", "")):
        day = r.get("startTime", "")[:10]
        if not day or day in known_dates:
            continue
        fetched += 1
        for rec in csv.DictReader(io.StringIO(_download(rep, r["downloadUrl"]))):
            vid = rec.get("video_id")
            if not vid:
                continue
            imp = int(float(rec.get("video_thumbnail_impressions") or 0))
            ctr = float(rec.get("video_thumbnail_impressions_ctr") or 0)
            if ctr > 1:  # percent, not a ratio
                ctr /= 100
            rows.append((day, vid, imp, ctr))  # report day (CSV dates are YYYYMMDD)
    status = f"{len(reports)} daily reports available, {fetched} new"
    if not reports:
        status = "Reach job exists; no reports yet (they start ~48 hours after the job was created)"
    return rows, status


def totals(daily: list) -> dict:
    """{video_id: {"impressions": n, "ctr": weighted ratio, "first": date, "days": n}}"""
    out = {}
    for day, vid, imp, ctr in daily:
        t = out.setdefault(vid, {"impressions": 0, "clicks": 0.0, "first": day, "days": 0})
        t["impressions"] += imp
        t["clicks"] += imp * ctr
        t["first"] = min(t["first"], day)
        t["days"] += 1
    for t in out.values():
        t["ctr"] = t["clicks"] / t["impressions"] if t["impressions"] else 0.0
    return out

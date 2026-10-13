"""Sync the Drive asset folders a render needs into a local dir (kept between runs by actions/cache).

  python 0004/pipeline/assets.py --doc 0004/videos/<id>/scenes.json --out assets
-> assets/sfx/*.wav (whole library, flat), assets/music/music_<mood>_*.wav (only the moods the script uses),
   assets/arc-intro/*, assets/reactions/*. Files already present with the same size are skipped.
"""

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from googleapiclient.http import MediaIoBaseDownload  # noqa: E402

from shared.drive import FOLDER, drive  # noqa: E402

FOLDERS = {  # Drive football-engine/0004/...
    "sfx": "1XiC92aRWz19oqdxOUg6v1p9cbFbSrW-0",
    "music": "1BgTlOZ3F_PWH2nbJXig0X9BGEck03t2X",
    "arc-intro": "19i4wjSLyr1BREhdokgn3dvK3PWIC20mz",
    "reactions": "1C8JTzr8BvoSFw9Exv1opTquGVlMBLMC-",
}


def listing(dr, fid: str) -> list:
    """All files under a folder (walks subfolders: Mitchael may add some)."""
    out, tok = [], None
    while True:
        r = dr.files().list(q=f"'{fid}' in parents and trashed = false", pageToken=tok, pageSize=200,
                            fields="nextPageToken, files(id, name, mimeType, size)").execute()
        for f in r.get("files", []):
            out += listing(dr, f["id"]) if f["mimeType"] == FOLDER else [f]
        tok = r.get("nextPageToken")
        if not tok:
            return out


def fetch(dr, f: dict, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size == int(f.get("size", -1)):
        return False
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, dr.files().get_media(fileId=f["id"]), chunksize=8 * 1024 * 1024)
    done = False
    while not done:
        _, done = dl.next_chunk()
    dest.write_bytes(buf.getvalue())
    return True


def moods(doc: dict) -> set:
    return {s["bed"] for s in doc.get("scenes", []) if s.get("bed") and s["bed"] not in ("none", "ambience")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", type=Path, action="append", default=[])
    ap.add_argument("--out", type=Path, default=Path("assets"))
    a = ap.parse_args()
    want = set()
    for d in a.doc:
        want |= moods(json.loads(d.read_text()))
    dr = drive()
    for kind, fid in FOLDERS.items():
        dest = a.out / kind
        dest.mkdir(parents=True, exist_ok=True)
        files = listing(dr, fid)
        if kind == "music":
            files = [f for f in files if any(f["name"].startswith(f"music_{m}_") for m in want)]
        new = sum(fetch(dr, f, dest / f["name"]) for f in files if not f["name"].startswith("."))
        print(f"assets: {kind}: {len(files)} files ({new} downloaded)")


if __name__ == "__main__":
    main()

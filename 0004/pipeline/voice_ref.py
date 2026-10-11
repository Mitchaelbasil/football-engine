"""Fetch the newest audio recording Mitchael dropped into Drive football-engine/0004/voice/ (skips our own voice_ref.wav).

  python 0004/pipeline/voice_ref.py fetch /tmp/raw
"""

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from googleapiclient.http import MediaIoBaseDownload  # noqa: E402

from shared.drive import drive, folder_path  # noqa: E402


def fetch(dest: Path):
    dr = drive()
    fid = folder_path(dr, "football-engine/0004/voice")
    q = f"'{fid}' in parents and trashed = false and (mimeType contains 'audio/' or mimeType contains 'video/')"
    files = dr.files().list(q=q, orderBy="createdTime desc", fields="files(id,name,mimeType,createdTime)", pageSize=20).execute()["files"]
    files = [f for f in files if f["name"] != "voice_ref.wav"]
    if not files:
        sys.exit("No recording found in Drive football-engine/0004/voice/ - upload one first.")
    f = files[0]
    buf = io.FileIO(dest, "wb")
    dl = MediaIoBaseDownload(buf, dr.files().get_media(fileId=f["id"]))
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.close()
    print(f"::notice title=recording::{f['name']} ({f['mimeType']}, {dest.stat().st_size} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "fetch":
        sys.exit(__doc__)
    fetch(Path(sys.argv[2]))

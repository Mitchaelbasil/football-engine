"""Upload build outputs to Drive and ping Telegram.

  python 0004/pipeline/deliver.py --drive-path football-engine/0004/tests/<name> --note "..." file1 file2 ...
Text files (.log/.txt/.json) are uploaded as Google Docs so they can be read from Drive.
"""

import argparse
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.drive import drive, folder_path, upload  # noqa: E402
from shared.telegram import send_message  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--drive-path", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--no-telegram", action="store_true")
    a = ap.parse_args()
    dr = drive()
    fid = folder_path(dr, a.drive_path)
    for f in a.files:
        if f.exists():
            upload(dr, f, fid, as_doc=f.suffix in (".log", ".txt", ".json"))
            print(f"uploaded {f.name}")
    link = f"https://drive.google.com/drive/folders/{fid}"
    if not a.no_telegram:
        send_message(f"{html.escape(a.note)}\n<a href=\"{link}\">Open in Drive</a>")
    print(link)


if __name__ == "__main__":
    main()

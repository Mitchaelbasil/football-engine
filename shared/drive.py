"""Google Drive helpers: nested folders + file upload. Uses shared.google_client credentials."""

from pathlib import Path

from googleapiclient.http import MediaFileUpload

from shared.google_client import build_service

FOLDER = "application/vnd.google-apps.folder"


def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def drive():
    return build_service("drive", "v3")


def folder(dr, name: str, parent: str = "root") -> str:
    q = f"name = '{_q(name)}' and mimeType = '{FOLDER}' and '{parent}' in parents and trashed = false"
    hit = dr.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
    if hit:
        return hit[0]["id"]
    return dr.files().create(body={"name": name, "mimeType": FOLDER, "parents": [parent]}, fields="id").execute()["id"]


def folder_path(dr, path: str) -> str:
    """'football-engine/0004/tests/x' -> folder id (created as needed)."""
    pid = "root"
    for part in [p for p in path.split("/") if p]:
        pid = folder(dr, part, pid)
    return pid


def upload(dr, local: Path, parent: str, name: str = None, as_doc: bool = False) -> dict:
    """Upload (or replace by name) a file. as_doc converts text to a Google Doc."""
    name = name or local.name
    q = f"name = '{_q(name)}' and '{parent}' in parents and trashed = false"
    hit = dr.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
    media = MediaFileUpload(str(local), resumable=local.stat().st_size > 5_000_000,
                            mimetype="text/plain" if as_doc else None)
    if hit:
        return dr.files().update(fileId=hit[0]["id"], media_body=media, fields="id,webViewLink").execute()
    body = {"name": name, "parents": [parent]}
    if as_doc:
        body["mimeType"] = "application/vnd.google-apps.document"
    return dr.files().create(body=body, media_body=media, fields="id,webViewLink").execute()

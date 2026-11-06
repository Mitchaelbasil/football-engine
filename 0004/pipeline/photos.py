"""0004 steps 3c/3d: photo slots in Drive, render scheduling, and putting filled photos into the script.

  python 0004/pipeline/photos.py intake <video> [at]       # Drive slots folder + SLOTS list + Telegram + status
  python 0004/pipeline/photos.py due                       # print the first video whose render time has come
  python 0004/pipeline/photos.py pull <video>              # download filled slots, write their src into scenes.json
  python 0004/pipeline/photos.py done <video> ok|fail [link]  # mark rendered (or retry later)

Drive layout: football-engine/0004/videos/<video>/
  photos/      Mitchael drops files named slot_02.jpg (or "slot 2 lewandowski.png" - only the number matters)
  SLOTS        a doc listing every slot: what photo, which scene, the line it sits under
  status.json  {"state": "waiting" | "rendering" | "rendered", "render_after": ISO-UTC, "created": ISO-UTC, "link"}
Render time: intake before 15:00 Lagos -> 21:00 Lagos that day; later -> intake + 6 h (the impromptu rule).
Photos Mitchael skips fall back to the engine's location card, so a render never waits on him.
"""

import datetime as dt
import html
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

VIDEOS = ROOT / "0004" / "videos"
LAGOS = dt.timezone(dt.timedelta(hours=1))
SLOT_RE = re.compile(r"slot[\s_-]*0*(\d+)", re.I)
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def slots(doc: dict) -> list:
    """[(slot, desc, cap, scene id, first line)] for photo and aura scenes that name a slot."""
    out, seen = [], set()
    for s in doc.get("scenes", []):
        d = s.get("data", {})
        if s.get("type") in ("photo", "aura") and d.get("slot") and d["slot"] not in seen:
            seen.add(d["slot"])
            line = (s.get("beats") or [{}])[0].get("say", "")
            out.append((int(d["slot"]), d.get("desc", ""), d.get("cap", ""), s.get("id", ""), line))
    return sorted(out)


FACE_RE = re.compile(r"face[\s_-]*0*(\d+)", re.I)


def face_slots(doc: dict) -> list:
    """[(n, who, mood)] for the thumbnail's face boxes: variant D's row if set, else meta.thumb.faces."""
    t = doc.get("meta", {}).get("thumb") or {}
    return [(i, f.get("who", ""), f.get("mood", "")) for i, f in enumerate(t.get("row") or t.get("faces") or [], 1)]


def cut_out(src: Path, dest: Path) -> Path:
    """Background removal for a face photo (skipped when the file already has transparency), cropped to the subject."""
    from PIL import Image
    im = Image.open(src)
    if im.mode in ("RGBA", "LA") and im.getextrema()[-1][0] < 250:
        out = im.convert("RGBA")
    else:
        from rembg import new_session, remove
        out = remove(im.convert("RGB"), session=new_session("u2net_human_seg")).convert("RGBA")
    box = out.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
    if box:
        out = out.crop(box)
    out.save(dest)
    return dest


def render_after(created: dt.datetime) -> dt.datetime:
    local = created.astimezone(LAGOS)
    if local.hour < 15:
        return local.replace(hour=21, minute=0, second=0).astimezone(dt.timezone.utc)
    return created + dt.timedelta(hours=6)


# ---------- Drive ----------

def _drive():
    from shared.drive import drive
    return drive()


def video_folder(dr, video: str) -> str:
    from shared.drive import folder_path
    return folder_path(dr, f"football-engine/0004/videos/{video}")


def _find(dr, name: str, parent: str):
    q = f"name = '{name}' and '{parent}' in parents and trashed = false"
    hit = dr.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
    return hit[0]["id"] if hit else None


def read_status(dr, folder: str) -> dict:
    from googleapiclient.http import MediaIoBaseDownload
    fid = _find(dr, "status.json", folder)
    if not fid:
        return {}
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, dr.files().get_media(fileId=fid))
    done = False
    while not done:
        _, done = dl.next_chunk()
    return json.loads(buf.getvalue().decode("utf-8") or "{}")


def write_status(dr, folder: str, st: dict) -> None:
    from googleapiclient.http import MediaInMemoryUpload
    media = MediaInMemoryUpload(json.dumps(st, indent=1).encode(), mimetype="application/json")
    fid = _find(dr, "status.json", folder)
    if fid:
        dr.files().update(fileId=fid, media_body=media).execute()
    else:
        dr.files().create(body={"name": "status.json", "parents": [folder]}, media_body=media).execute()


# ---------- commands ----------

def intake(video: str, at: str = "") -> None:
    """at: optional render time override (ISO with offset, e.g. 2026-11-07T21:00+01:00)."""
    from googleapiclient.http import MediaInMemoryUpload
    from shared.drive import folder
    from shared.telegram import send_message
    doc = json.loads((VIDEOS / video / "scenes.json").read_text(encoding="utf-8"))
    dr = _drive()
    vf = video_folder(dr, video)
    pf = folder(dr, "photos", vf)
    sl = slots(doc)
    lines = [f"PHOTO SLOTS - {doc.get('meta', {}).get('title', video)}", "",
             "Drop each photo into the 'photos' folder named slot_NN (e.g. slot_02.jpg). Landscape, the subject in the middle.",
             "Skipped slots fall back to a clean location card.", ""]
    for n, desc, cap, sid, line in sl:
        lines += [f"slot_{n:02d}  {desc}", f"         caption: {cap} | scene '{sid}' | line: \"{line}\"", ""]
    fs = face_slots(doc)
    if fs:
        lines += ["THUMBNAIL FACES - name them face_1, face_2 ... Head-and-shoulders photo, face clearly visible.",
                  "The background is removed automatically (or drop a cut-out PNG). These go straight into the thumbnail.", ""]
        lines += [f"face_{n}  {who} - {mood}" for n, who, mood in fs] + [""]
    media = MediaInMemoryUpload("\n".join(lines).encode("utf-8"), mimetype="text/plain")
    sid = _find(dr, "SLOTS", vf)
    if sid:
        dr.files().update(fileId=sid, media_body=media).execute()
    else:
        dr.files().create(body={"name": "SLOTS", "parents": [vf], "mimeType": "application/vnd.google-apps.document"},
                          media_body=media).execute()
    st = read_status(dr, vf)
    srev = _rev([sl, face_slots(doc)])
    new_script = not st or (st.get("state") == "rendered" and st.get("rev") != _rev(doc.get("scenes", [])))
    if new_script:  # first intake, or a new script after a render: start the clock
        created = now()
        st = {"state": "waiting", "created": created.isoformat(), "render_after": render_after(created).isoformat()}
    if at and st.get("state") != "rendering":
        st.update({"state": "waiting", "render_after": dt.datetime.fromisoformat(at).astimezone(dt.timezone.utc).isoformat()})
    changed = new_script or st.get("slots_rev") != srev or bool(at)
    st.update({"rev": _rev(doc.get("scenes", [])), "slots_rev": srev})
    write_status(dr, vf, st)
    when = dt.datetime.fromisoformat(st["render_after"]).astimezone(LAGOS).strftime("%a %H:%M")
    if changed:  # script edits that leave the slot list alone don't ping Telegram again
        msg = [f"<b>📸 Photo slots: {html.escape(doc.get('meta', {}).get('title', video))}</b>",
               f"{len(sl)} slots. Render at {when} (Lagos) with whatever is filled.", ""]
        msg += [f"slot_{n:02d}: {html.escape(desc)}" for n, desc, *_ in sl]
        if face_slots(doc):
            msg += ["", "<b>Thumbnail faces</b> (head and shoulders; background removed for you):"]
            msg += [f"face_{n}: {html.escape(who)} - {html.escape(mood)}" for n, who, mood in face_slots(doc)]
        msg += ["", f'<a href="https://drive.google.com/drive/folders/{pf}">Open the photos folder</a>']
        send_message("\n".join(msg))
    print(f"intake {video}: {len(sl)} slots, state {st['state']}, render_after {st['render_after']}, telegram {changed}")


def _rev(obj) -> str:
    import hashlib
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:10]


STUCK = dt.timedelta(hours=2)  # a "rendering" state older than this means the runner died: render again


def due(force: str = "") -> None:
    """Print the first video due for rendering (or the forced one); empty output = nothing to do."""
    if force:
        print(force)
        return
    dr = _drive()
    root = _find(dr, "football-engine", "root")
    f4 = _find(dr, "0004", root) if root else None
    fv = _find(dr, "videos", f4) if f4 else None
    if not fv:
        return
    for vd in sorted(VIDEOS.iterdir()):
        if not vd.is_dir() or vd.name.startswith("_") or not (vd / "scenes.json").exists():
            continue
        vf = _find(dr, vd.name, fv)
        st = read_status(dr, vf) if vf else {}
        t = now()
        waiting = st.get("state") == "waiting" and t >= dt.datetime.fromisoformat(st["render_after"])
        stuck = st.get("state") == "rendering" and t - dt.datetime.fromisoformat(st.get("started", st["render_after"])) > STUCK
        if waiting or stuck:
            print(vd.name)
            return


def pull(video: str) -> None:
    """Download filled slots and point the script's photo/aura scenes at them (in this runner only)."""
    from googleapiclient.http import MediaIoBaseDownload
    from shared.drive import folder
    dr = _drive()
    vf = video_folder(dr, video)
    pf = folder(dr, "photos", vf)
    st = read_status(dr, vf)
    st.update({"state": "rendering", "started": now().isoformat()})
    write_status(dr, vf, st)
    files = dr.files().list(q=f"'{pf}' in parents and trashed = false", pageSize=200,
                            fields="files(id, name)").execute().get("files", [])
    local = VIDEOS / video / "photos"
    local.mkdir(exist_ok=True)
    got, faces = {}, {}
    for f in files:
        ext = Path(f["name"]).suffix.lower()
        m, fm = SLOT_RE.search(f["name"]), FACE_RE.search(f["name"])
        if ext not in IMG_EXT or not (m or fm):
            continue
        dest = local / (f"slot_{int(m.group(1)):02d}{ext}" if m else f"face_{int(fm.group(1))}_src{ext}")
        with open(dest, "wb") as fh:
            dl = MediaIoBaseDownload(fh, dr.files().get_media(fileId=f["id"]))
            done = False
            while not done:
                _, done = dl.next_chunk()
        if m:
            got[int(m.group(1))] = dest
        else:
            try:
                faces[int(fm.group(1))] = cut_out(dest, local / f"face_{int(fm.group(1))}.png")
            except Exception as e:  # a bad face file must not stop the render
                print(f"face_{fm.group(1)}: cut-out failed ({e}) - box stays empty")
    p = VIDEOS / video / "scenes.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    for s in doc.get("scenes", []):
        d = s.get("data", {})
        if s.get("type") in ("photo", "aura") and d.get("slot") in got:
            d["src"] = got[d["slot"]].resolve().as_uri()
    t = doc.get("meta", {}).get("thumb") or {}
    for i, f in enumerate(t.get("row") or t.get("faces") or [], 1):
        if i in faces:
            f["src"] = faces[i].resolve().as_uri()
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    want = [n for n, *_ in slots(doc)]
    print(f"photos {video}: {len(got)}/{len(want)} slots filled {sorted(got)}; faces {len(faces)}/{len(face_slots(doc))}")


def done(video: str, ok: str = "ok", link: str = "") -> None:
    """ok: rendered. Anything else: back to waiting, retried by the next hourly check (at most 3 tries)."""
    dr = _drive()
    vf = video_folder(dr, video)
    st = read_status(dr, vf)
    if ok == "ok":
        st.update({"state": "rendered", "rendered": now().isoformat(), "link": link})
    else:
        st["tries"] = st.get("tries", 0) + 1
        st["state"] = "waiting" if st["tries"] < 3 else "failed"
    write_status(dr, vf, st)
    print(f"status {video}: {st['state']}")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    {"intake": intake, "due": due, "pull": pull, "done": done}[cmd](*args)

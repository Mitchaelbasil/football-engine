"""Render frames with Playwright (deterministic renderFrame(T)) -> H.264, split across CPU workers."""

import os
import subprocess
import time
from multiprocessing import Pool
from pathlib import Path

FONTS = "Promise.all(['100px Anton','800 30px Inter','600 30px Oswald','900 30px Inter'].map(f=>document.fonts.load(f))).then(()=>document.fonts.ready)"


def _page(p, build: Path, w: int, h: int):
    exe = os.environ.get("CHROMIUM_PATH")
    b = p.chromium.launch(executable_path=exe or None, args=["--force-color-profile=srgb", "--disable-lcd-text", "--allow-file-access-from-files"])
    pg = b.new_page(viewport={"width": w, "height": h})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto((build / "engine.html").resolve().as_uri())
    pg.wait_for_function("window.READY===true", timeout=30000)
    pg.evaluate(FONTS)
    pg.evaluate("renderFrame(0)")
    return b, pg, errs


def stills(build: Path, times: list, w: int, h: int, out_dir: Path) -> list:
    from playwright.sync_api import sync_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        b, pg, errs = _page(p, build, w, h)
        for T in times:
            pg.evaluate(f"renderFrame({T})")
            path = out_dir / f"s_{T:07.2f}.jpg"
            pg.screenshot(path=str(path), type="jpeg", quality=82)
            paths.append(path)
        b.close()
    if errs:
        raise RuntimeError(f"engine errors: {errs[:5]}")
    return paths


def _chunk(args):
    build, f0, f1, fps, w, h, out = args
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, pg, errs = _page(p, Path(build), w, h)
        ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-threads", "1", out],
                              stdin=subprocess.PIPE)
        t0 = time.time()
        for f in range(f0, f1):
            pg.evaluate(f"renderFrame({f / fps})")
            ff.stdin.write(pg.screenshot(type="jpeg", quality=93))
            if (f - f0) % 300 == 0:
                print(f"  chunk {Path(out).name}: {f - f0}/{f1 - f0} ({time.time() - t0:.0f}s)", flush=True)
        ff.stdin.close(); ff.wait(); b.close()
        if errs:
            raise RuntimeError(f"engine errors: {errs[:5]}")
    return out


def video(build: Path, total: float, fps: int, w: int, h: int, out: Path, workers: int = 0) -> Path:
    n = int(round(total * fps))
    workers = workers or max(1, os.cpu_count() or 1)
    step = -(-n // workers)
    jobs = [(str(build), i, min(n, i + step), fps, w, h, str(build / f"part{k:02d}.mp4")) for k, i in enumerate(range(0, n, step))]
    with Pool(len(jobs)) as pool:
        parts = pool.map(_chunk, jobs)
    lst = build / "parts.txt"
    lst.write_text("".join(f"file '{Path(p).name}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], check=True, cwd=build)
    return out

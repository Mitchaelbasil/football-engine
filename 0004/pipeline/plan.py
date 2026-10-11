"""Motion planner: scenes.json + voice timings -> timeline.json (+ voice track).

Enforces the Beastify rules:
  * no visual change gap >= 3.0 s (we target <= MAX_GAP for safety)
  * no robotic rhythm: 3+ consecutive gaps within +-ROBOT_TOL of each other
Visual changes are anchored to narration: emphasised words first, then content words, then beat starts.
Only planner-inserted micro-motions are ever moved, so scripted beats stay exactly where Claude put them.
"""

import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf

from voice import SR, norm

MAX_GAP = 2.7          # hard limit is 3.0; keep headroom
HARD_LIMIT = 3.0
ROBOT_TOL = 0.3
MIN_SPACING = 0.45     # don't cram changes closer than this
MERGE = 0.25           # changes closer than this count as one
BEAT_GAP = 0.16
REACT_DUR = 1.8
TRANSITIONS = ["zoom", "slide", "rise", "flash"]
REACT_POS = ["br", "tl", "tr", "bl"]


def _resolve(beat: dict, bt: float, words: list, spec, warn: list) -> tuple:
    """Return (action, abs_time) for a `do` entry: 'name' or {'a','at','dt'}."""
    if isinstance(spec, str):
        return spec, bt
    a, at, dt = spec["a"], spec.get("at"), spec.get("dt", 0.0)
    if at is None:
        return a, bt + dt
    key = norm(at)
    for w in words:
        if key and norm(w["w"]).startswith(key):
            return a, w["s"] + dt
    warn.append(f"word '{at}' not found in: {beat['say'][:50]}")
    return a, bt + dt


def build_timeline(doc: dict, voice: list, w: int = 1920, h: int = 1080, fps: int = 30):
    warn, scenes, beats_out, words_all, overlays, sfx = [], [], [], [], [], []
    cur, vi, arc_label, react_i = 0.0, 0, None, 0
    for si, sc in enumerate(doc["scenes"]):
        start = cur
        cur += sc.get("pre", 0.35 if si else 0.25)
        evs = []
        for b in sc["beats"]:
            v = voice[vi]; vi += 1
            bt = cur
            words = [{"w": x["w"], "s": bt + x["s"], "e": bt + x["e"], "emph": False} for x in v["words"]]
            emph = {norm(e) for e in b.get("emph", [])}
            for x in words:
                if norm(x["w"]) in emph:
                    x["emph"] = True
            for spec in b.get("do", []):
                a, t = _resolve(b, bt, words, spec, warn)
                evs.append({"a": a, "t": round(t, 3)})
            end = bt + v["dur"]
            if b.get("react"):
                r = b["react"] if isinstance(b["react"], dict) else {"emo": b["react"]}
                rt = end + 0.35
                if r.get("at"):
                    _, rt = _resolve(b, bt, words, {"a": "r", "at": r["at"]}, warn)
                overlays.append({"t": round(rt, 3), "d": r.get("d", REACT_DUR), "emo": r["emo"], "text": r.get("text"),
                                 "cap": r.get("cap"), "clip": r.get("clip"), "pos": r.get("pos", REACT_POS[react_i % 4])})
                react_i += 1
            beats_out.append({"t": round(bt, 3), "end": round(end, 3), "say": b["say"], "wav": v["wav"], "scene": si})
            words_all += [{**x, "s": round(x["s"], 3), "e": round(x["e"], 3)} for x in words]
            cur = end + b.get("hold", 0.0) + BEAT_GAP
            if b.get("react"):  # narration pauses for the reaction; it never spills into the next scene
                o = overlays[-1]
                cur = max(cur, o["t"] + o["d"] + 0.2)
        end = cur + sc.get("post", 0.25)
        if sc["type"] == "arc":
            d = sc.get("data", {})
            arc_label = f"{d.get('kicker', '')} · {' '.join(d.get('title', []))}".strip(" ·")
        scenes.append({"id": sc.get("id", f"s{si}"), "type": sc["type"], "palette": sc.get("palette", "madrid"),
                       "start": round(start, 3), "end": round(end, 3), "data": sc.get("data", {}), "ev": evs,
                       "tr": sc.get("tr") or TRANSITIONS[si % len(TRANSITIONS)] if si else "zoom",
                       "arcLabel": sc.get("arcLabel", arc_label), "hud": sc.get("hud", True)})
        cur = end
    total = round(cur + 0.4, 3)
    tl = {"w": w, "h": h, "fps": fps, "total": total, "scenes": scenes, "overlays": overlays,
          "beats": beats_out, "words": words_all, "micro": [], "sfx": sfx}
    _plan_motion(tl)
    _plan_sfx(tl)
    tl["report"] = validate(tl)
    tl["report"]["warnings"] = warn
    return tl


# ---------- change bookkeeping ----------

def fixed_changes(tl) -> list:
    ch = [s["start"] for s in tl["scenes"]] + [e["t"] for s in tl["scenes"] for e in s["ev"]]
    for o in tl["overlays"]:
        ch += [o["t"], o["t"] + o["d"]]
    return ch


def merged(times: list) -> list:
    out = []
    for t in sorted(times):
        if not out or t - out[-1] >= MERGE:
            out.append(t)
    return out


def all_changes(tl) -> list:
    return merged(fixed_changes(tl) + [m["t"] for m in tl["micro"]])


def gaps(ch: list) -> list:
    return [b - a for a, b in zip(ch, ch[1:])]


def robotic_runs(ch: list) -> list:
    g = gaps(ch)
    return [i for i in range(len(g) - 2) if max(g[i:i + 3]) - min(g[i:i + 3]) <= ROBOT_TOL]


def validate(tl) -> dict:
    ch = all_changes(tl) + [tl["total"]]
    g = gaps(ch)
    worst = max(g) if g else 0
    rob = robotic_runs(ch)
    return {"changes": len(ch) - 1, "avg_gap": round(sum(g) / len(g), 2) if g else 0, "max_gap": round(worst, 2),
            "over_limit": [round(ch[i], 2) for i, x in enumerate(g) if x >= HARD_LIMIT],
            "robotic_at": [round(ch[i], 2) for i in rob], "ok": worst < HARD_LIMIT and not rob}


# ---------- motion planning ----------

def _candidates(tl) -> list:
    """Word starts with a preference weight (emph 3, numbers/names 2, long words 1, short 0)."""
    c = []
    for wd in tl["words"]:
        raw = wd["w"]
        wt = 3 if wd["emph"] else 2 if (re.search(r"\d", raw) or raw[:1].isupper()) else 1 if len(raw) > 4 else 0
        c.append((wd["s"], wt))
    return c


def _scene_at(tl, t):
    for s in tl["scenes"]:
        if s["start"] <= t < s["end"]:
            return s
    return tl["scenes"][-1]


def _in_speech(tl, t):
    return any(b["t"] <= t <= b["end"] for b in tl["beats"])


class _Kinds:
    def __init__(self):
        self.prev, self.n, self.zoom, self.dir = None, 0, {}, 1

    def pick(self, scene_id, emph, silent):
        z = self.zoom.get(scene_id, 0)
        if emph:
            pool = ["punch", "glow"] if z < 2 else ["glow", "pull"]
        elif silent:
            pool = ["drift", "tilt", "sweep"]
        else:
            pool = ["drift", "punch", "tilt", "glow", "pull", "sweep"] if z < 2 else ["pull", "drift", "tilt", "glow"]
        k = next((p for p in pool[self.n % len(pool):] + pool if p != self.prev), pool[0])
        self.n += 1
        self.prev = k
        if k == "punch":
            self.zoom[scene_id] = z + 1
        elif k == "pull":
            self.zoom[scene_id] = z - 1
        self.dir = -self.dir
        return {"k": k, "dir": self.dir}


def _add_micro(tl, kinds, t):
    sc = _scene_at(tl, t)
    emph = any(abs(w["s"] - t) < 0.02 and w["emph"] for w in tl["words"])
    tl["micro"].append({"t": round(t, 3), **kinds.pick(sc["id"], emph, not _in_speech(tl, t)), "auto": True})


def _choose(cands, a, b, bias):
    """Pick a word start inside (a,b) leaving MIN_SPACING both sides; prefer weight, then a point near a+bias*(b-a)."""
    inside = [(t, w) for t, w in cands if a + MIN_SPACING <= t <= b - MIN_SPACING]
    if not inside:
        return None
    target = a + bias * (b - a)
    return max(inside, key=lambda x: (x[1], -abs(x[0] - target)))[0]


def _plan_motion(tl):
    kinds, cands, bias_i = _Kinds(), _candidates(tl), 0
    biases = [0.42, 0.61, 0.5, 0.36, 0.67]
    # 1) break every long gap
    for _ in range(500):
        ch = all_changes(tl) + [tl["total"]]
        long = [(a, b) for a, b in zip(ch, ch[1:]) if b - a > MAX_GAP]
        if not long:
            break
        a, b = long[0]
        bias = biases[bias_i % len(biases)]; bias_i += 1
        t = _choose(cands, a, b, bias)
        if t is None:
            n = int((b - a) // MAX_GAP) + 1
            t = a + (b - a) * (bias if n <= 2 else 1 / n)
        _add_micro(tl, kinds, t)
    # 2) de-robot: move or add auto micro events
    for _ in range(300):
        ch = all_changes(tl) + [tl["total"]]
        rob = robotic_runs(ch)
        if not rob:
            break
        i = rob[0]
        before = len(rob)
        fixed = False
        autos = {m["t"]: m for m in tl["micro"] if m.get("auto")}
        for j in (i + 1, i + 2):
            ev = autos.get(ch[j])
            if not ev:
                continue
            lo, hi = ch[j - 1], ch[j + 1]
            for t, _w in sorted(cands, key=lambda x: -x[1]):
                if not (lo + MIN_SPACING <= t <= hi - MIN_SPACING) or abs(t - ev["t"]) < 0.2:
                    continue
                old = ev["t"]; ev["t"] = round(t, 3)
                ch2 = all_changes(tl) + [tl["total"]]
                if len(robotic_runs(ch2)) < before and max(gaps(ch2)) <= MAX_GAP + 0.05:
                    fixed = True
                    break
                ev["t"] = old
            if fixed:
                break
        if not fixed:
            g = gaps(ch)
            k = max(range(i, i + 3), key=lambda x: g[x])
            a, b = ch[k], ch[k + 1]
            t = _choose(cands, a, b, 0.33) or (a + (b - a) * 0.37 if b - a >= 2 * MIN_SPACING else None)
            if t is None:
                break
            _add_micro(tl, kinds, t)
    tl["micro"].sort(key=lambda m: m["t"])


def _plan_sfx(tl):
    s = tl["sfx"]
    for i, sc in enumerate(tl["scenes"]):
        if i:
            s.append({"t": sc["start"], "k": "whoosh"})
        for e in sc["ev"]:
            if e["a"] in ("slam", "burst"):
                s.append({"t": e["t"], "k": "boom"})
            elif e["a"] in ("count", "read", "rread"):
                s.append({"t": e["t"], "k": "ticks"})
            elif e["a"].startswith("item") or e["a"] in ("title", "open"):
                s.append({"t": e["t"], "k": "hit"})
            elif e["a"] == "charge":
                s.append({"t": e["t"], "k": "riser"})
            elif e["a"] in ("lock", "rival"):
                s.append({"t": e["t"], "k": "scan"})
    for o in tl["overlays"]:
        s.append({"t": o["t"], "k": "react"})
    for m in tl["micro"]:
        if m["k"] in ("punch", "sweep"):
            s.append({"t": m["t"], "k": "swish" if m["k"] == "sweep" else "thump"})
    s.sort(key=lambda x: x["t"])


def assemble_voice(tl, out: Path):
    track = np.zeros(int((tl["total"] + 1) * SR), dtype=np.float32)
    for b in tl["beats"]:
        a, _ = sf.read(b["wav"], dtype="float32")
        i = int(b["t"] * SR)
        track[i:i + len(a)] += a[: max(0, len(track) - i)]
    sf.write(out, track, SR)


def write(tl, build: Path):
    build.mkdir(parents=True, exist_ok=True)
    (build / "timeline.json").write_text(json.dumps(tl, indent=1))
    eng = {k: tl[k] for k in ("w", "h", "fps", "total", "scenes", "overlays", "micro")}
    (build / "timeline.js").write_text("window.TL=" + json.dumps(eng) + ";")

"""Motion planner: scenes.json + voice timings -> timeline.json (+ voice track).

Enforces the Beastify rules:
  * no visual change gap >= 3.0 s (we target <= MAX_GAP for safety)
  * no robotic rhythm: 3+ consecutive gaps within +-ROBOT_TOL of each other
Visual changes are anchored to narration: emphasised words first, then content words, then beat starts.
Only planner-inserted micro-motions are ever moved, so scripted beats stay exactly where Claude put them.

Two hosts: beats carry speaker "H" (Bella, story) or "P" (Michael, the breakdown); a scene-level "speaker"
sets the default for its beats. A speaker switch gets a natural pause (HANDOFF) and counts as a visible
change (the name tag swaps). tl["speakers"] lists the contiguous runs for the engine's name tag.
"""

import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf

from voice import SR, norm

MAX_GAP = 2.4          # hard limit is 3.0; changes must be clearly felt, so keep real headroom
HARD_LIMIT = 3.0
ROBOT_TOL = 0.3
MIN_SPACING = 0.45     # don't cram changes closer than this
MERGE = 0.25           # changes closer than this count as one
BEAT_GAP = 0.16
REACT_DUR = 1.8
TRANSITIONS = ["zoom", "slide", "rise", "flash"]
REACT_POS = ["br", "tl", "tr", "bl"]
HANDOFF = 0.55         # min silence between the last word of one host and the first of the other
TAG_IN = 0.25          # name tag starts entering this long before the new speaker's first word


def speaker_of(scene: dict, beat: dict) -> str:
    return beat.get("speaker") or scene.get("speaker") or "H"


def doc_beats(doc: dict) -> list:
    """Every spoken beat in order, with its speaker resolved (input for voice.synth_beats)."""
    return [{**b, "speaker": speaker_of(s, b)} for s in doc["scenes"] for b in s.get("beats", [])]


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
    last_spk, last_end = None, -1e9
    for si, sc in enumerate(doc["scenes"]):
        start = cur
        cur += sc.get("pre", 0.35 if si else 0.25)
        evs = []
        if not sc.get("beats"):  # silent scene (e.g. Shorts end card)
            cur += sc.get("dur", 2.5)
        for b in sc.get("beats", []):
            v = voice[vi]; vi += 1
            spk = speaker_of(sc, b)
            if last_spk and spk != last_spk:
                cur = max(cur, last_end + HANDOFF)
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
            beats_out.append({"t": round(bt, 3), "end": round(end, 3), "say": b["say"], "wav": v["wav"], "scene": si, "speaker": spk})
            last_spk, last_end = spk, end
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
          "beats": beats_out, "words": words_all, "micro": [], "sfx": sfx,
          "speakers": speaker_runs(beats_out), "hosts": hosts_meta(doc)}
    _plan_motion(tl)
    _plan_sfx(tl)
    tl["report"] = validate(tl)
    tl["report"]["warnings"] = warn
    return tl


def speaker_runs(beats: list) -> list:
    """Contiguous runs of one speaker: [{'who', 't', 'end', 'talk': [[t, end], ...]}]."""
    runs = []
    for b in beats:
        if runs and runs[-1]["who"] == b["speaker"]:
            runs[-1]["end"] = b["end"]; runs[-1]["talk"].append([b["t"], b["end"]])
        else:
            runs.append({"who": b["speaker"], "t": b["t"], "end": b["end"], "talk": [[b["t"], b["end"]]]})
    return runs


def hosts_meta(doc: dict) -> dict:
    h = {"H": {"name": "BELLA", "role": "THE STORY"}, "P": {"name": "MICHAEL", "role": "THE BREAKDOWN"}}
    for k, v in (doc.get("meta", {}).get("hosts") or {}).items():
        h[k] = {**h.get(k, {}), **v}
    return h


# ---------- change bookkeeping ----------

def fixed_changes(tl) -> list:
    ch = [s["start"] for s in tl["scenes"]] + [e["t"] for s in tl["scenes"] for e in s["ev"]]
    if len({r["who"] for r in tl.get("speakers", [])}) > 1:  # name tag swap on every handoff
        ch += [r["t"] - TAG_IN for r in tl["speakers"][1:]]
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
    """Visible changes only: content accents (template-specific), strong zoom punches/pulls, light sweeps."""
    def __init__(self):
        self.prev, self.n, self.zoom, self.dir = None, 0, {}, 1

    def pick(self, scene_id, emph, silent):
        z = self.zoom.get(scene_id, 0)
        if emph:
            pool = ["punch", "accent"] if z < 1 else ["accent", "pull"]
        elif silent:
            pool = ["accent", "sweep"]
        else:
            pool = ["accent", "punch", "accent", "sweep"] if z < 1 else ["accent", "pull", "accent", "sweep"]
        k = next((p for p in pool[self.n % len(pool):] + pool if p != self.prev or p == "accent"), pool[0])
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
    """Built-in SFX ONLY on mundane moments (number ticks, list-item hits). Anime-worthy moments get NO built-in
    sound: they are listed as cues (tl['cues']) for Mitchael's anime SFX / reaction clips, tested by hand first."""
    s, cues = tl["sfx"], tl.setdefault("cues", [])
    last_whoosh = -1e9  # whoosh only on BIG transitions (into an arc card / end card), at most ~1 per 40 s
    for i, sc in enumerate(tl["scenes"]):
        if i and sc["type"] in ("arc", "endcard") and sc["start"] - last_whoosh >= 40:
            s.append({"t": sc["start"], "k": "whoosh"}); last_whoosh = sc["start"]
        for e in sc["ev"]:
            a = e["a"]
            if a in ("count", "read", "rread"):
                s.append({"t": e["t"], "k": "ticks"})
            elif a.startswith("item"):
                s.append({"t": e["t"], "k": "hit"})
            if a in ("slam", "stamp"):
                cues.append({"t": e["t"], "what": "SLAM", "idea": "impact hit / dramatic sting"})
            elif a == "burst":
                cues.append({"t": e["t"], "what": "AURA", "idea": "aura / power-up sound"})
            elif a == "charge":
                cues.append({"t": e["t"], "what": "AURA CHARGE", "idea": "charging / energy build"})
            elif a in ("lock", "rival"):
                cues.append({"t": e["t"], "what": "SCANNER", "idea": "scouter beep"})
            elif a == "title":
                cues.append({"t": e["t"], "what": "ARC TITLE", "idea": "anime title-card sting"})
    for o in tl["overlays"]:
        cues.append({"t": o["t"], "what": f"REACTION ({o['emo']})", "idea": "anime reaction clip / sound"})
    s.sort(key=lambda x: x["t"]); cues.sort(key=lambda x: x["t"])


def _speech_rms(a: np.ndarray) -> float:
    """Rough perceived level: high-passed (drops the male voice's extra low end), speech samples only."""
    from scipy.signal import butter, sosfilt
    y = sosfilt(butter(2, 150, "high", fs=SR, output="sos"), a)
    act = y[np.abs(y) > 0.01]
    return float(np.sqrt(np.mean(act ** 2))) if len(act) else 0.0


def speaker_gains(tl) -> dict:
    """Level every speaker to the host's level with one gain per speaker (keeps each voice's own dynamics)."""
    by = {}
    for b in tl["beats"]:
        a, _ = sf.read(b["wav"], dtype="float32")
        by.setdefault(b.get("speaker", "H"), []).append(a)
    rms = {k: _speech_rms(np.concatenate(v)) for k, v in by.items()}
    ref = rms.get("H") or next(iter(rms.values()), 0)
    return {k: float(np.clip(ref / r, 0.5, 2.5)) if r and ref else 1.0 for k, r in rms.items()}


def voice_track(tl) -> np.ndarray:
    track = np.zeros(int((tl["total"] + 1) * SR), dtype=np.float32)
    gains = tl.get("voice_gains") or speaker_gains(tl)
    tl["voice_gains"] = gains
    for b in tl["beats"]:
        a, _ = sf.read(b["wav"], dtype="float32")
        a = a * gains.get(b.get("speaker", "H"), 1.0)
        i = int(b["t"] * SR)
        track[i:i + len(a)] += a[: max(0, len(track) - i)]
    return track


ENV_RANGE_DB = 26.0   # meter span below the loud end of the speech
ENV_RELEASE = 0.16    # seconds for the glow to fall back (fast attack, slow release, like a VU meter)


def voice_envelope(tl, track: np.ndarray) -> list:
    """Per-frame voice loudness 0-99 for the host mic glow. Fake (silent) voice -> driven by word timings."""
    fps = tl["fps"]; n = int(tl["total"] * fps) + 2
    if float(np.max(np.abs(track))) < 1e-4:
        v = np.zeros(n)
        for w in tl["words"]:
            i0, i1 = int(w["s"] * fps), min(n, int(w["e"] * fps) + 1)
            v[i0:i1] = np.maximum(v[i0:i1], .55 + .45 * np.abs(np.sin(np.arange(i0, i1) * 1.7)))
    else:
        hop, L = SR / fps, int(SR / fps)
        cs = np.concatenate([[0.0], np.cumsum(track.astype(np.float64) ** 2)])
        mid = (np.arange(n) * hop).astype(int)
        lo, hi = np.clip(mid - L // 2, 0, len(track)), np.clip(mid + L // 2, 0, len(track))
        rms = np.sqrt((cs[hi] - cs[lo]) / np.maximum(hi - lo, 1))
        db = 20 * np.log10(rms + 1e-9)
        act = db[db > -60]
        top = float(np.percentile(act, 95)) if len(act) else -14.0
        v = np.clip((db - (top - ENV_RANGE_DB)) / ENV_RANGE_DB, 0, 1)
    rel = float(np.exp(-1 / (fps * ENV_RELEASE)))
    env = np.zeros(n)
    for i in range(n):
        env[i] = max(v[i], env[i - 1] * rel if i else 0)
    return [int(x) for x in np.round(env * 99)]


def assemble_voice(tl, out: Path):
    sf.write(out, voice_track(tl), SR)


def write(tl, build: Path):
    build.mkdir(parents=True, exist_ok=True)
    if len({r["who"] for r in tl.get("speakers", [])}) > 1 and "env" not in tl:
        tl["env"] = voice_envelope(tl, voice_track(tl))
    (build / "timeline.json").write_text(json.dumps({k: v for k, v in tl.items() if k != "env"}, indent=1))
    eng = {k: tl[k] for k in ("w", "h", "fps", "total", "scenes", "overlays", "micro", "speakers", "hosts", "env") if k in tl}
    (build / "timeline.js").write_text("window.TL=" + json.dumps(eng) + ";")

// 0004 engine v2 — core runtime. Deterministic: renderFrame(T) depends only on T + timeline.
// timeline.js defines window.TL (written by pipeline/plan.py).
const W = TL.w || 1920, H = TL.h || 1080, CX = W / 2, CY = H / 2, PORT = H > W;
const TPL = {};

// ---------- math / easing ----------
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const eo = x => 1 - Math.pow(1 - x, 3);
const eio = x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
const eb = x => { const c1 = 1.9, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
const P = (t, a, d = .6, e = eo) => e(clamp((t - a) / d));
const lerp = (a, b, p) => a + (b - a) * p;
const rnd = i => { const x = Math.sin(i * 12.9898 + 78.233) * 43758.5453; return x - Math.floor(x); };
const $ = id => document.getElementById(id);
const fmt = (v, dec = 0) => dec ? v.toFixed(dec) : Math.round(v).toString();
const NEVER = 1e9;

// ---------- element helpers ----------
function E(par, html, o = {}) {
  const d = document.createElement('div'); d.className = 'el ' + (o.c || ''); d.innerHTML = html;
  if (o.fs) d.style.fontSize = o.fs + 'px'; if (o.col) d.style.color = o.col; if (o.st) Object.assign(d.style, o.st);
  d._f = d.style.filter || '';  // keep custom filters (outlines/glows) when S() animates blur
  d._x = o.x ?? CX; d._y = o.y ?? CY; d._a = o.a || 'c'; d._r = o.r || 0; par.appendChild(d); S(d, 0); return d;
}
// shrink an element (uniformly) so its layout width fits maxW; needs fonts loaded (start() awaits them)
function fit(d, maxW = W - 160) { const w = d.offsetWidth; if (w > maxW && w > 0) d._k = maxW / w; return d; }
function S(d, o = 1, dx = 0, dy = 0, s = 1, blur = 0, rot = 0) {
  const ax = d._a === 'l' ? '0%' : d._a === 'r' ? '-100%' : '-50%';
  d.style.transform = `translate(${d._x + dx}px,${d._y + dy}px) translate(${ax},-50%) rotate(${d._r + rot}deg) scale(${s * (d._k || 1)})`;
  d.style.opacity = o; d.style.filter = ((d._f || '') + (blur > .3 ? ` blur(${blur}px)` : '')).trim();
}
function R(d, t, a, b = NEVER, amt = 40, dur = .55) { const pi = P(t, a, dur), po = 1 - P(t, b, .35, eio); S(d, pi * po, 0, (1 - pi) * amt - (1 - po) * 20, 1, (1 - pi) * 8); }
function RX(d, t, a, b = NEVER, amt = -80, dur = .5) { const pi = P(t, a, dur), po = 1 - P(t, b, .35, eio); S(d, pi * po, (1 - pi) * amt, 0, 1, (1 - pi) * 6); }
function POP(d, t, a, b = NEVER, from = .55) { const pi = clamp((t - a) / .45), po = 1 - P(t, b, .35, eio); S(d, clamp(pi * 2.5) * po, 0, 0, lerp(from, 1, eb(pi)), 0); }
function DIM(t, a, to = .25) { return lerp(1, to, P(t, a, .45)); }
function shake(t, a, amp = 14, dur = .45) { const k = clamp(1 - (t - a) / dur); if (t < a || k <= 0) return ''; return ` translate(${Math.sin(t * 90) * amp * k}px,${Math.cos(t * 77) * amp * k}px)`; }
function speedLines(n = 72, r0 = 260, r1 = 1400, cols = ['rgba(20,33,92,.10)', 'rgba(227,22,91,.16)', 'rgba(255,255,255,.55)'], seed = 1) {
  let s = `<svg width="${W}" height="${H}" viewBox="${-CX} ${-CY} ${W} ${H}" style="display:block">`;
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2 + rnd(i + seed) * .05, w = .006 + rnd(i * 3 + seed) * .016, rr = r0 + rnd(i * 7 + seed) * 180;
    const p = [[Math.cos(a - w) * r1, Math.sin(a - w) * r1], [Math.cos(a) * rr, Math.sin(a) * rr], [Math.cos(a + w) * r1, Math.sin(a + w) * r1]];
    s += `<polygon points="${p.map(q => q.join(',')).join(' ')}" fill="${cols[i % cols.length]}"/>`;
  }
  return s + '</svg>';
}

// ---------- theme: Daylight ----------
const THEME = {
  '--text': '#14215c', '--accent': '#e3165b', '--tshadow': '0 6px 30px rgba(255,255,255,.45)',
  '--vig': 'radial-gradient(ellipse at 50% 50%,rgba(255,255,255,0) 50%,rgba(255,255,255,.28) 100%)',
  '--hero': 'linear-gradient(180deg,#ff9a1f 0%,#ff5a3c 55%,#e3165b 100%)', '--heroglow': 'drop-shadow(0 10px 26px rgba(227,22,91,.25))',
  '--rival': 'linear-gradient(180deg,#2f6bff 0%,#3a2bd9 60%,#8a1fd0 100%)', '--rivalglow': 'drop-shadow(0 10px 26px rgba(47,107,255,.25))',
  '--rivaltext': '#3a2bd9', '--card': 'rgba(255,255,255,.62)', '--cardb': 'rgba(255,255,255,.9)', '--cards': '0 24px 60px rgba(30,70,160,.18)',
  '--herobar': 'linear-gradient(90deg,#ffb11f,#ff5a3c)', '--herobarL': 'linear-gradient(270deg,#ffb11f,#ff5a3c)',
  '--rivalbar': 'linear-gradient(90deg,#2f6bff,#8a1fd0)', '--rivalbarL': 'linear-gradient(270deg,#2f6bff,#8a1fd0)',
  '--pilltext': '#ffffff', '--track': 'rgba(20,33,92,.10)', '--stampbg': 'rgba(255,255,255,.75)',
};
for (const k in THEME) document.documentElement.style.setProperty(k, THEME[k]);
const PAL = {
  madrid: { base: ['#7fd4ff', '#b8f5d8'], b: ['#ffe066', '#ff9fb2', '#4fc3ff', '#9ff0c9'] },
  violet: { base: ['#9fc4ff', '#ffc6e0'], b: ['#c9a6ff', '#ffe066', '#6fd6ff', '#ff9fb2'] },
  gold: { base: ['#ffe39a', '#ffc2d4'], b: ['#ffd23f', '#ff9a76', '#ffb3c7', '#8fd8ff'] },
  barca: { base: ['#8ec0ff', '#ffbdd0'], b: ['#5aa0ff', '#ff8fae', '#ffe066', '#7fe3ff'] },
  clasico: { base: ['#a7d8ff', '#ffd0dc'], b: ['#ffd23f', '#5aa0ff', '#ff8fae', '#9ff0c9'] },
  bayern: { base: ['#ffb3b3', '#ffd9a0'], b: ['#ff7a8a', '#ffd23f', '#8ec0ff', '#ffb3c7'] },
  mint: { base: ['#b8f5d8', '#9fdcff'], b: ['#7fe3c4', '#ffe066', '#9fc4ff', '#ffb3c7'] },
  sunset: { base: ['#ffd0a8', '#ffb3d1'], b: ['#ffb84d', '#ff8fae', '#ffe066', '#c9a6ff'] },
};
const hex = h => [1, 3, 5].map(i => parseInt(h.substr(i, 2), 16));
const mixv = (a, b, p) => { const A = hex(a), B = hex(b); return A.map((v, i) => Math.round(lerp(v, B[i], p))).join(','); };
const mix = (a, b, p) => `rgb(${mixv(a, b, p)})`;

// ---------- background ----------
let bgEl, blobs = [];
function initBG() {
  bgEl = $('bg');
  for (let i = 0; i < 4; i++) { const d = document.createElement('div'); d.className = 'blob'; bgEl.appendChild(d); blobs.push(d); }
}
function drawBG(T) {
  const sc = TL.scenes; let i = sc.findIndex(s => T < s.end); if (i < 0) i = sc.length - 1;
  const cur = PAL[sc[i].palette] || PAL.madrid, prev = PAL[(sc[i - 1] || sc[i]).palette] || cur;
  const p = P(T, sc[i].start - .2, 1.2, eio);
  bgEl.style.background = `linear-gradient(135deg,${mix(prev.base[0], cur.base[0], p)} 0%,${mix(prev.base[1], cur.base[1], p)} 100%)`;
  const pos = [[.15, .2], [.85, .75], [.8, .15], [.2, .85]];
  blobs.forEach((d, k) => {
    const c = mixv(prev.b[k], cur.b[k], p);
    d.style.background = `radial-gradient(circle at 50% 50%, rgba(${c},1) 0%, rgba(${c},.53) 22%, rgba(${c},0) 62%)`;
    const x = pos[k][0] * W + Math.sin(T * .11 + k * 1.7) * 260 - 750, y = pos[k][1] * H + Math.cos(T * .09 + k * 2.3) * 180 - 750;
    d.style.transform = `translate(${x}px,${y}px) scale(${1 + .12 * Math.sin(T * .2 + k)})`; d.style.opacity = .8;
  });
}

// ---------- micro-motions (planner-inserted visual changes) ----------
// kinds: punch (zoom in), pull (zoom out), drift (pan), tilt (rotate), glow (bloom pulse), sweep (light band)
function camera(s, t) {
  let z = 1 + .02 * clamp(t / s.D), x = 0, y = 0, r = 0;
  for (const m of s.micro) {
    const p = P(t, m.t, .24, eo);
    if (p <= 0) continue;
    if (m.k === 'punch') z += .12 * p;
    else if (m.k === 'pull') z -= .09 * p;
    else if (m.k === 'accent') z += .025 * p;
  }
  return `translate(${x}px,${y}px) rotate(${r}deg) scale(${Math.max(.8, z)})` + s.micro.filter(m => m.k === 'punch').map(m => shake(t, m.t, 9, .25)).join('');
}
let bloom, sweep;
function initFX() {
  const fx = $('fx');
  bloom = E(fx, '', { st: { width: W * 1.2 + 'px', height: H * 1.2 + 'px', background: 'radial-gradient(ellipse at 50% 50%,rgba(255,250,220,.85) 0%,rgba(255,220,170,.35) 30%,rgba(255,255,255,0) 60%)', mixBlendMode: 'screen' } });
  sweep = E(fx, '', { st: { width: '520px', height: H * 2 + 'px', background: 'linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.7),rgba(255,255,255,0))', mixBlendMode: 'screen' }, r: 18 });
}
function drawFX(T) {
  let b = 0, sw = -1;
  for (const m of TL.micro) {
    if (m.k === 'glow') { const d = T - m.t; if (d >= 0 && d < .9) b = Math.max(b, Math.sin(Math.PI * d / .9) * .55); }
    if (m.k === 'sweep') { const d = T - m.t; if (d >= 0 && d < .55) sw = d / .55; }
  }
  for (const s of TL.scenes) if (s.tr === 'flash') { const d = T - s.start; if (d >= 0 && d < .55) sw = Math.max(sw, d / .55); }
  S(bloom, b, 0, 0, 1);
  sweep._x = lerp(-400, W + 400, eio(clamp(sw))); S(sweep, sw >= 0 ? 1 : 0, 0, 0, 1);
}

// ---------- reaction overlays ----------
const REACT_TEXT = { shock: 'EHHH?!', bored: '...', hype: "LET'S GO!!", sad: 'NOOO...', laugh: 'HAHAHA', aura: 'AURA', what: 'HUH?!' };
const REACT_POS = PORT
  ? { br: [CX + 120, H * .66, -4], tr: [CX + 120, H * .3, 3], bl: [CX - 120, H * .66, 4], tl: [CX - 120, H * .3, -3] }
  : { br: [W - 400, H - 290, -4], tr: [W - 400, 340, 3], bl: [400, H - 290, 4], tl: [400, 340, -3] };
function initOverlays() {
  const ov = $('over');
  for (const o of TL.overlays) {
    const [x, y, rot] = REACT_POS[o.pos || 'br'];
    const txt = o.text || REACT_TEXT[o.emo] || 'EHHH?!';
    o.el = E(ov, `<div style="position:relative;width:620px;height:400px;border-radius:20px;overflow:hidden;border:10px solid #14215c;background:#fff6d6;box-shadow:0 30px 70px rgba(20,33,92,.35)">
        <div class="sl" style="position:absolute;left:${310 - CX}px;top:${200 - CY}px">${speedLines(64, 70, 900, ['rgba(20,33,92,.18)', 'rgba(227,22,91,.22)', 'rgba(255,190,40,.35)'], 7)}</div>
        <div class="A stroke" style="position:absolute;left:0;right:0;top:50%;transform:translateY(-50%) rotate(-6deg);text-align:center;font-size:${txt.length > 6 ? 130 : 170}px;color:#ffd23f">${txt}</div>
      </div>
      ${o.cap ? `<div class="L" style="margin:-24px auto 0;position:relative;width:max-content;padding:14px 28px;border-radius:12px;background:#e3165b;color:#fff;font-size:30px">${o.cap}</div>` : ''}`,
      { x, y, r: rot });
  }
}
function roomShift(T) {
  let k = 0, dx = 0, dy = 0;
  for (const o of TL.overlays) {
    const e = P(T, o.t - .05, .35, eio) * (1 - P(T, o.t + o.d - .2, .4, eio));
    if (e > k) { k = e; dx = o.pos[1] === 'r' ? -1 : 1; dy = o.pos[0] === 'b' ? -1 : 1; }
  }
  if (PORT) return k > 0 ? `translate(0px,${dy * H * .12 * k}px) scale(${1 - .14 * k})` : '';
  return k > 0 ? `translate(${dx * W * .1 * k}px,${dy * H * .035 * k}px) scale(${1 - .16 * k})` : '';
}
function drawOverlays(T) {
  for (const o of TL.overlays) {
    const d = T - o.t;
    if (d < 0 || d > o.d + .35) { o.el.style.opacity = 0; continue; }
    const pi = clamp(d / .4), po = P(T, o.t + o.d - .25, .3, eio);
    const k = clamp(1 - d / .4);
    o.el.style.opacity = clamp(pi * 3) * (1 - po);
    o.el.style.transform = `translate(${o.el._x + Math.sin(d * 80) * 10 * k + po * 700 * (o.pos[1] === 'r' ? 1 : -1)}px,${o.el._y + Math.cos(d * 70) * 8 * k}px) translate(-50%,-50%) rotate(${o.el._r + (1 - eo(pi)) * -10}deg) scale(${lerp(.4, 1, eb(pi))})`;
    const sl = o.el.querySelector('.sl'); if (sl) sl.style.transform = `rotate(${d * 25}deg)`;
  }
}

// ---------- HUD ----------
let hudL, hudR, prog;
function initHUD() {
  const hud = $('hud');
  hudL = PORT ? E(hud, 'IF FOOTBALL WAS ANIME', { c: 'L', fs: 24, x: CX, y: 170 }) : E(hud, 'IF FOOTBALL WAS ANIME', { c: 'L', fs: 20, x: 80, y: 66, a: 'l' });
  hudR = PORT ? E(hud, '', { c: 'L', fs: 22, x: CX, y: 210, col: 'var(--accent)' }) : E(hud, '', { c: 'L', fs: 20, x: W - 80, y: 66, a: 'r', col: 'var(--accent)' });
  prog = E(hud, '', { x: 0, y: H - 4, a: 'l', st: { height: '8px', width: W + 'px', background: 'linear-gradient(90deg,#ffb11f,#e3165b)', transformOrigin: '0 50%' } });
}
function drawHUD(T, cur) {
  const on = cur.hud === false ? 0 : 1, hp = P(T, cur.start + .2, .5) * on + (1 - on) * (1 - P(T, cur.start, .3));
  S(hudL, .85 * hp); hudR.innerHTML = cur.arcLabel || ''; S(hudR, PORT && TWO ? 0 : hp);  // 9:16 two-host: the mic takes the arc label's slot
  S(prog, PORT ? 0 : .9); prog.style.transform += ` scaleX(${T / TL.total})`;
}

// ---------- host mic (two-host videos only) ----------
// One mic per host in the same spot: pink = Bella (H, the story), blue = Michael (P, the breakdown).
// The glow follows the REAL voice loudness (TL.env, 0-99 per frame, VU-style fast attack / slow release),
// so it breathes with every word. On each handoff the mics crossfade and the host's name flashes beside it.
const MIC_COL = { H: { a: '#ff9bd0', b: '#e3165b', g: '255,70,150' }, P: { a: '#8fbcff', b: '#2f4bff', g: '60,120,255' } };
const TAG_IN = .25, TAG_FORCE = 3.5, NAME_FOR = 2.6;
const MIC_POS = PORT ? { x: 64, y: 262, k: .7 } : { x: 118, y: H - 128, k: 1.2 };
let mics = {}, TWO = false;
const envAt = T => { const e = TL.env; if (!e || !e.length) return 0; return e[Math.max(0, Math.min(e.length - 1, Math.round(T * TL.fps)))] / 99; };
function micSVG(c, id) {
  const w = (d, cls) => `<path class="${cls}" d="${d}" fill="none" stroke="${c.b}" stroke-width="6" stroke-linecap="round"/>`;
  return `<svg width="100" height="150" viewBox="0 0 100 150" style="display:block;overflow:visible">
    <defs><linearGradient id="mg${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c.a}"/><stop offset="1" stop-color="${c.b}"/></linearGradient></defs>
    ${w('M90 20 a34 34 0 0 1 0 46', 'w1')}${w('M104 8 a52 52 0 0 1 0 70', 'w2')}${w('M10 20 a34 34 0 0 0 0 46', 'w1')}${w('M-4 8 a52 52 0 0 0 0 70', 'w2')}
    <g class="cap" style="transform-origin:50px 42px">
      <rect x="28" y="4" width="44" height="76" rx="22" fill="url(#mg${id})" stroke="#14215c" stroke-width="5"/>
      <path d="M37 26 h26 M37 38 h26 M37 50 h26" stroke="#fff" stroke-opacity=".8" stroke-width="4" stroke-linecap="round"/>
    </g>
    <path d="M17 50 v7 a33 33 0 0 0 66 0 v-7" fill="none" stroke="#14215c" stroke-width="6" stroke-linecap="round"/>
    <path d="M50 91 v26 M30 120 h40" stroke="#14215c" stroke-width="7" stroke-linecap="round"/>
  </svg>`;
}
function initTags() {
  const runs = TL.speakers || [];
  TWO = new Set(runs.map(r => r.who)).size > 1;
  if (!TWO) return;
  const hud = $('hud'), k = MIC_POS.k;
  for (const who of new Set(runs.map(r => r.who))) {
    const h = (TL.hosts || {})[who] || { name: who }, c = MIC_COL[who] || MIC_COL.H;
    const el = E(hud, `<div style="position:relative;width:100px;height:150px">
        <div class="glow" style="position:absolute;left:-95px;top:-103px;width:290px;height:290px;border-radius:50%;background:radial-gradient(circle,rgba(${c.g},.8) 0%,rgba(${c.g},.3) 36%,rgba(${c.g},0) 68%)"></div>
        <div class="mic" style="position:absolute;left:0;top:0">${micSVG(c, who)}</div></div>`, { x: MIC_POS.x, y: MIC_POS.y });
    el._k = k;
    el._glow = el.querySelector('.glow'); el._mic = el.querySelector('.mic'); el._cap = el.querySelector('.cap');
    el._w1 = [...el.querySelectorAll('.w1')]; el._w2 = [...el.querySelectorAll('.w2')]; el._c = c;
    el._name = E(hud, `<div style="padding:10px 28px;border-radius:999px;background:linear-gradient(90deg,${c.a},${c.b});color:#fff;font-family:Anton;font-size:42px;letter-spacing:.04em;box-shadow:0 12px 30px rgba(${c.g},.35)">${h.name || who}</div>`,
      { x: MIC_POS.x + 78 * k, y: MIC_POS.y - 34 * k, a: 'l' });
    el._name._k = k;
    mics[who] = el;
  }
}
function drawTags(T, cur) {
  if (!TWO) return;
  const runs = TL.speakers, e = envAt(T);
  let ri = -1; for (let i = 0; i < runs.length; i++) if (T >= runs[i].t - TAG_IN) ri = i;
  const ci = TL.scenes.indexOf(cur), prev = TL.scenes[ci - 1];
  const hudV = lerp(prev && prev.hud === false ? 0 : 1, cur.hud === false ? 0 : 1, prev ? P(T, cur.start, .3) : 1);
  let corner = 0;  // a reaction panel in the mic's corner pushes it out
  if (!PORT) for (const o of TL.overlays) if (o.pos === 'bl') corner = Math.max(corner, P(T, o.t - .2, .2) * (1 - P(T, o.t + o.d, .3)));
  for (const who in mics) {
    const el = mics[who];
    let o = 0, sc = 1, nm = 0, ndx = 0, live = 0;
    if (ri >= 0 && runs[ri].who === who) {
      const a = runs[ri].t - TAG_IN, pin = clamp((T - a) / .45);
      const forced = ri > 0 ? clamp((T - a) * 50) * (1 - P(T, a + TAG_FORCE, .3)) : 0;  // handoffs always show
      const vis = Math.max(hudV, forced) * (1 - corner);
      o = clamp(pin * 2.5) * vis; sc = lerp(.6, 1, eb(pin)); live = 1;
      const pn = P(T, a + .15, .35) * (1 - P(T, a + NAME_FOR, .4, eio));
      nm = pn * vis; ndx = (1 - eo(P(T, a + .15, .35))) * -40;
    } else if (ri > 0 && runs[ri - 1].who === who) {  // the other host just took over: crossfade out
      const po = P(T, runs[ri].t - TAG_IN, .3, eio);
      o = (1 - po) * hudV * (1 - corner); sc = lerp(1, .85, po);
    }
    S(el, o, 0, 0, sc);
    S(el._name, nm, ndx, 0, 1);
    const g = live ? e : 0;
    el._glow.style.opacity = .16 + .84 * g;
    el._glow.style.transform = `scale(${.7 + .6 * g})`;
    el._mic.style.filter = `drop-shadow(0 0 ${3 + 26 * g}px rgba(${el._c.g},${.45 + .55 * g})) drop-shadow(0 0 ${2 + 8 * g}px rgba(${el._c.g},${.5 + .5 * g}))`;
    el._cap.style.transform = `scale(${1 + .08 * g})`;
    el._w1.forEach(p => p.style.opacity = clamp(g * 1.7 - .2));
    el._w2.forEach(p => p.style.opacity = clamp(g * 1.7 - .75));
  }
}

// ---------- scenes ----------
function initScenes() {
  const layersEl = $('layers');
  TL.scenes.forEach((s, i) => {
    const L = document.createElement('div'); L.className = 'layer'; layersEl.appendChild(L); s.L = L; s.i = i;
    s.D = s.end - s.start;
    const ev = {}; for (const e of s.ev) (ev[e.a] = ev[e.a] || []).push(e.t - s.start);
    for (const k in ev) ev[k].sort((a, b) => a - b);
    s.A = (name, j = 0, dflt = NEVER) => (ev[name] && ev[name][j] !== undefined) ? ev[name][j] : dflt;
    s.micro = TL.micro.filter(m => m.t >= s.start - .01 && m.t < s.end).map(m => ({ ...m, t: m.t - s.start }));
    s.accT = s.micro.filter(m => m.k === 'accent').map(m => m.t);
    s.acc = t => { let i = -1; for (let j = 0; j < s.accT.length; j++) if (s.accT[j] <= t) i = j; return { i, k: i < 0 ? 0 : eo(clamp(1 - (t - s.accT[i]) / .6)) }; };
    const tpl = TPL[s.type]; if (!tpl) throw new Error('Unknown template: ' + s.type);
    s.r = tpl.build(L, s.data || {}, s);
  });
}
function transitionIn(s, T) {
  if (s.i === 0) return { o: P(T, 0, .3), tf: '' };
  const p = P(T, s.start, .42, eo);
  switch (s.tr) {
    case 'slide': return { o: clamp(p * 1.6), tf: `translateX(${(1 - p) * W * .22}px)` };
    case 'rise': return { o: clamp(p * 1.6), tf: `translateY(${(1 - p) * 140}px)` };
    case 'flash': return { o: clamp(p * 2), tf: `scale(${lerp(1.06, 1, p)})` };
    default: return { o: clamp(p * 1.6), tf: `scale(${lerp(1.18, 1, p)})` };
  }
}

async function start() {
  const st = $('stage'); st.style.width = W + 'px'; st.style.height = H + 'px';
  document.body.style.width = W + 'px'; document.body.style.height = H + 'px';
  await Promise.all(['100px Anton', '800 30px Inter', '900 30px Inter', '600 30px Oswald'].map(f => document.fonts.load(f)));
  await document.fonts.ready;
  initBG(); initScenes(); initFX(); initOverlays(); initHUD(); initTags();
  window.READY = true;
}

window.renderFrame = function (T) {
  drawBG(T);
  const last = TL.scenes.length - 1;
  let cur = TL.scenes[last];
  for (const s of TL.scenes) {
    if (T >= s.start && T < s.end) cur = s;
    const t = T - s.start, outD = .32;
    if (T < s.start - .01 || (s.i < last && T > s.end + outD)) { s.L.style.display = 'none'; continue; }
    s.L.style.display = 'block';
    const tin = transitionIn(s, T), po = s.i < last ? P(T, s.end, outD, eio) : 0;
    s.L.style.opacity = tin.o * (1 - po);
    let extra = TPL[s.type].update(t, s.A, s.r, s.L, s) || '';
    if (s.accT.length && TPL[s.type].accent) { const ac = s.acc(t); if (ac.i >= 0) extra += TPL[s.type].accent(s.r, ac, t, s) || ''; }
    s.L.style.transform = `${tin.tf} scale(${lerp(1, .94, po)}) ${camera(s, t)}${extra}`;
  }
  $('layers').style.transform = roomShift(T);
  drawFX(T); drawOverlays(T); drawHUD(T, cur); drawTags(T, cur);
};

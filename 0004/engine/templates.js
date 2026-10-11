// 0004 engine v2 — scene templates. Each: build(L, data, scene) -> refs; update(t, A, refs, L, scene) -> extra transform.
// A(action, i=0, default) returns the scene-relative time of the i-th event named `action` (from scenes.json "do").

// Big number that counts up. data: value, label, sub, dec, prefix, suffix. actions: count, sub
TPL.counter = {
  build(L, d) {
    const r = { d };
    r.num = E(L, '0', { c: 'A gold', fs: d.fs || 420, y: CY - 70 });
    r.lab = E(L, d.label || '', { c: 'L', fs: 48, y: CY + 190, col: 'var(--accent)' });
    r.sub = E(L, d.sub || '', { c: 'L', fs: 34, y: CY + 262 });
    return r;
  },
  update(t, A, r) {
    const a = A('count', 0, .1), n = P(t, a, 1.1, eio);
    r.num.innerHTML = (r.d.prefix || '') + fmt((r.d.value || 0) * n, r.d.dec) + (r.d.suffix || '');
    POP(r.num, t, a - .05, NEVER, .6); R(r.lab, t, a + .35, NEVER, 24); R(r.sub, t, A('sub'), NEVER, 24);
    return shake(t, a + 1.05, 8, .3);
  }
};

// Ticked list. data: items[]. actions: item0..itemN
TPL.checklist = {
  build(L, d) {
    const n = d.items.length, gap = Math.min(175, 560 / Math.max(n - 1, 1)), y0 = CY - gap * (n - 1) / 2 + 20;
    return { items: d.items.map((s, i) => E(L, `<span class="ck">✓</span><span style="vertical-align:middle">${s}</span>`, { c: 'A', fs: d.fs || 104, x: W * .2, y: y0 + i * gap, a: 'l' })) };
  },
  update(t, A, r) {
    let ex = '';
    r.items.forEach((d, i) => {
      const a = A('item' + i, 0, .1 + i * .5), pi = P(t, a, .45);
      S(d, pi, (1 - pi) * -90, 0, 1, (1 - pi) * 6);
      d.firstChild.style.transform = `scale(${eb(clamp((t - a - .12) / .4))})`;
      ex += shake(t, a + .12, 5, .2);
    });
    return ex;
  }
};

// Word slam. data: pre, word, sub, fs. actions: pre, slam, sub
TPL.slam = {
  build(L, d) {
    const r = {};
    r.pre = E(L, d.pre || '', { c: 'L', fs: 46, y: CY - 270, col: 'var(--accent)' });
    r.ring = E(L, '', { y: CY + 30, st: { width: '220px', height: '220px', borderRadius: '50%', border: '16px solid #ffb11f' } });
    r.word = E(L, d.word || '', { c: 'A gold', fs: d.fs || 560, y: CY + 30 });
    r.sub = E(L, d.sub || '', { c: 'L', fs: 34, y: CY + 330 });
    return r;
  },
  update(t, A, r) {
    const a = A('slam', 0, .2);
    R(r.pre, t, A('pre', 0, .05), NEVER, 24);
    POP(r.word, t, a, NEVER, 1.7);
    const pr = clamp((t - a) / .65); S(r.ring, t >= a ? (1 - pr) : 0, 0, 0, lerp(.6, 8, eo(pr)));
    R(r.sub, t, A('sub'), NEVER, 20);
    return shake(t, a + .05, 20);
  }
};

// Anime arc title card. data: kicker, title:[line1,line2], sub. actions: open, title, sub
TPL.arc = {
  build(L, d) {
    const r = {};
    r.lines = E(L, speedLines(90, 330, 1500, ['rgba(20,33,92,.09)', 'rgba(227,22,91,.14)', 'rgba(255,255,255,.6)'], 3), {});
    r.kick = E(L, d.kicker || 'ARC 01', { c: 'pill pg', y: CY - 250, st: { fontSize: '34px' } });
    r.brush = E(L, '', { y: CY + 30, st: { width: '1500px', height: '300px', background: 'linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.92) 12%,rgba(255,255,255,.92) 88%,rgba(255,255,255,0))', transformOrigin: '0 50%' } });
    const [l1, l2] = d.title || ['', ''];
    r.t1 = E(L, l1, { c: 'A', fs: d.fs1 || 140, y: CY - 50 });
    r.t2 = E(L, l2, { c: 'A gold', fs: d.fs2 || 190, y: CY + 115 });
    r.sub = E(L, d.sub || '', { c: 'L', fs: 30, y: CY + 300 });
    return r;
  },
  update(t, A, r) {
    const o = A('open', 0, .05), ti = A('title', 0, o + .5);
    const pl = P(t, o, .6);
    S(r.lines, pl, 0, 0, lerp(1.6, 1, eo(pl)), 0, t * 6);
    POP(r.kick, t, o + .1, NEVER, .4);
    const pb = P(t, ti, .45, eio); S(r.brush, pb * .95, 0, 0, 1, 0, -2); r.brush.style.transform += ` scaleX(${Math.max(pb, .001)})`;
    RX(r.t1, t, ti, NEVER, -160); RX(r.t2, t, ti + .18, NEVER, 160);
    R(r.sub, t, A('sub', 0, ti + .7), NEVER, 20);
    return shake(t, ti + .2, 12, .35);
  }
};

// Power-level scanner. data: name, initials, value, max, label, rival:{name,initials,value}. actions: lock, read, rival, rread
TPL.scan = {
  build(L, d) {
    const r = { d }, rx = W * .29, ry = CY + 30; r.rx = rx; r.ry = ry;
    const ticks = [...Array(72)].map((_, i) => { const a = i / 72 * Math.PI * 2, r0 = i % 6 ? 282 : 262; return `<line x1="${Math.cos(a) * r0}" y1="${Math.sin(a) * r0}" x2="${Math.cos(a) * 300}" y2="${Math.sin(a) * 300}" stroke="#14215c" stroke-width="${i % 6 ? 3 : 6}" stroke-opacity=".55"/>`; }).join('');
    r.ring1 = E(L, `<svg width="640" height="640" viewBox="-320 -320 640 640">${ticks}<circle r="310" fill="none" stroke="#e3165b" stroke-width="4" stroke-dasharray="40 22"/></svg>`, { x: rx, y: ry });
    r.ring2 = E(L, `<svg width="480" height="480" viewBox="-240 -240 480 480"><path d="M -220 0 A 220 220 0 0 1 0 -220" fill="none" stroke="#ffb11f" stroke-width="16" stroke-linecap="round"/><path d="M 220 0 A 220 220 0 0 1 0 220" fill="none" stroke="#ffb11f" stroke-width="16" stroke-linecap="round"/><circle r="200" fill="none" stroke="#14215c" stroke-opacity=".2" stroke-width="2"/></svg>`, { x: rx, y: ry });
    const core = (ini, bg) => `<div style="width:340px;height:340px;border-radius:50%;background:${bg};display:flex;align-items:center;justify-content:center;box-shadow:0 20px 60px rgba(20,33,92,.25)"><span class="A" style="font-size:150px;color:#fff;text-shadow:none">${ini}</span></div>`;
    r.core1 = E(L, core(d.initials || 'CR', 'var(--herobar)'), { x: rx, y: ry });
    r.cross = E(L, `<svg width="760" height="760" viewBox="-380 -380 760 760"><g stroke="#14215c" stroke-width="4" stroke-opacity=".5"><line x1="-380" y1="0" x2="-330" y2="0"/><line x1="330" y1="0" x2="380" y2="0"/><line x1="0" y1="-380" x2="0" y2="-330"/><line x1="0" y1="330" x2="0" y2="380"/></g></svg>`, { x: rx, y: ry });
    r.scanline = E(L, '', { x: rx, y: ry, st: { width: '640px', height: '10px', borderRadius: '5px', background: 'linear-gradient(90deg,rgba(227,22,91,0),#e3165b,rgba(227,22,91,0))', boxShadow: '0 0 30px #e3165b' } });
    const X = W * .58;
    r.tgt = E(L, 'TARGET', { c: 'L', fs: 26, x: X, y: CY - 250, a: 'l', col: 'var(--accent)' });
    r.name1 = E(L, d.name || '', { c: 'A', fs: 92, x: X, y: CY - 175, a: 'l' });
    r.pl = E(L, d.label || 'POWER LEVEL', { c: 'L', fs: 30, x: X, y: CY - 85, a: 'l' });
    r.num1 = E(L, '00', { c: 'A gold', fs: 300, x: X - 10, y: CY + 90, a: 'l' });
    r.segs = [...Array(20)].map((_, i) => E(L, '', { x: X + i * 34, y: CY + 290, a: 'l', st: { width: '28px', height: '58px', borderRadius: '6px', background: 'var(--track)' } }));
    r.stat = E(L, '', { c: 'L', fs: 26, x: X, y: CY + 370, a: 'l' });
    if (d.rival) {
      r.core2 = E(L, core(d.rival.initials || 'LM', 'var(--rivalbar)'), { x: rx, y: ry });
      r.name2 = E(L, d.rival.name, { c: 'A', fs: 92, x: X, y: CY - 175, a: 'l', col: 'var(--rivaltext)' });
      r.num2 = E(L, '00', { c: 'A blue', fs: 300, x: X - 10, y: CY + 90, a: 'l' });
      r.warn = E(L, 'LIMIT EXCEEDED', { c: 'A', fs: 64, x: X + 470, y: CY + 60, r: -8, st: { padding: '6px 24px', border: '6px solid #e3165b', color: '#e3165b', borderRadius: '12px', background: 'rgba(255,255,255,.8)', textShadow: 'none' } });
    }
    return r;
  },
  update(t, A, r) {
    const d = r.d, lock = A('lock', 0, .05), read = A('read', 0, lock + 1.2);
    const riv = d.rival ? A('rival', 0, NEVER) : NEVER, rread = d.rival ? A('rread', 0, riv + .8) : NEVER;
    const max = d.max || 100;
    const pin = P(t, lock, .55);
    S(r.ring1, pin, 0, 0, lerp(1.5, 1, eo(pin)), 0, t * 22);
    S(r.ring2, pin, 0, 0, lerp(.6, 1, eo(pin)), 0, -t * 48);
    S(r.cross, pin, 0, 0, lerp(1.3, 1, eo(pin)));
    const sw = (t >= lock && t < read) || (t >= riv && t < rread);
    S(r.scanline, sw ? .95 : 0, 0, Math.sin(t * 5.5) * 240);
    [r.tgt, r.pl].forEach((e, i) => R(e, t, lock + .15 + i * .12, NEVER, 16));
    const swap = P(t, riv, .3);
    const c1 = POPv(t, lock + .1); S(r.core1, c1 * (1 - swap), 0, 0, lerp(.5, 1, eb(clamp((t - lock - .1) / .45))) * (1 - .3 * swap));
    S(r.name1, P(t, lock + .25, .4) * (1 - swap), (1 - P(t, lock + .25, .4)) * 40);
    const scr = i => String(10 + Math.floor(rnd(Math.floor(t / .055) + i) * 89));
    const n1 = P(t, read, .9, eio);
    r.num1.innerHTML = t < read ? scr(1) : fmt(d.value * n1);
    S(r.num1, P(t, lock + .4, .3) * (1 - swap), 0, 0, t >= read ? lerp(1.12, 1, P(t, read, .3)) : 1);
    let fill = t >= read ? Math.round(20 * Math.min(d.value / max, 1) * n1) : 0, over = false;
    if (d.rival) {
      S(r.core2, swap, 0, 0, lerp(.6, 1, eb(clamp((t - riv) / .45))));
      S(r.name2, swap, (1 - swap) * 40);
      const n2 = P(t, rread, .9, eio);
      r.num2.innerHTML = t < rread ? scr(7) : fmt(d.rival.value * n2);
      S(r.num2, swap, 0, 0, t >= rread ? lerp(1.15, 1, P(t, rread, .3)) : 1);
      if (t >= riv) { fill = t >= rread ? Math.round(20 * Math.min(d.rival.value / max, 1) * n2) : 0; over = t >= rread + .9 && d.rival.value > max; }
      POP(r.warn, t, over ? rread + .9 : NEVER, NEVER, 1.6);
    }
    r.segs.forEach((s, i) => {
      S(s, P(t, lock + .3 + i * .015, .3));
      const on = i < fill, blink = over && Math.floor(t * 8) % 2;
      s.style.background = over ? (blink ? '#e3165b' : '#ff8fae') : on ? (t >= riv ? 'var(--rivalbar)' : 'var(--herobar)') : 'var(--track)';
    });
    const st = over ? 'WARNING · OVER THE LIMIT' : (t >= rread || (t >= read && t < riv)) ? 'LOCKED' : t >= lock ? 'SCANNING…' : '';
    r.stat.innerHTML = st; S(r.stat, t >= lock + .3 ? 1 : 0); r.stat.style.color = over ? '#e3165b' : 'var(--text)';
    return shake(t, read + .9, 10, .3) + shake(t, rread + .9, 18, .5);
  }
};
function POPv(t, a) { return clamp((t - a) / .45 * 2.5); }

// Head to head bars. data: left:{name}, right:{name}, rows:[[label,a,b,dec]]. actions: left, right
TPL.h2h = {
  build(L, d) {
    const r = { rows: [] }, gap = 170, mw = 560, top = CY - 150, step = Math.min(140, 520 / Math.max(d.rows.length - 1, 1));
    r.hl = E(L, d.left.name, { c: 'A gold', fs: 110, x: CX - 420, y: CY - 300 });
    r.hr = E(L, d.right.name, { c: 'A blue', fs: 110, x: CX + 420, y: CY - 300 });
    r.vs = E(L, 'VS', { c: 'pill pg', y: CY - 300, st: { fontSize: '30px' } });
    d.rows.forEach(([lab, a, b, dec], i) => {
      const y = top + i * step, mx = Math.max(a, b), o = { a, b, dec: dec || 0 };
      o.lab = E(L, lab, { c: 'L', fs: 22, y, st: { opacity: .85 } });
      o.bl = E(L, '', { x: CX - gap, y, a: 'r', c: 'bar', st: { width: (mw * a / mx) + 'px', height: '74px', background: 'var(--herobarL)', transformOrigin: '100% 50%' } });
      o.br = E(L, '', { x: CX + gap, y, a: 'l', c: 'bar', st: { width: (mw * b / mx) + 'px', height: '74px', background: 'var(--rivalbar)' } });
      o.vl = E(L, '', { c: 'A', fs: 66, x: CX - gap - mw * a / mx - 24, y, a: 'r' });
      o.vr = E(L, '', { c: 'A', fs: 66, x: CX + gap + mw * b / mx + 24, y, a: 'l' });
      r.rows.push(o);
    });
    return r;
  },
  update(t, A, r) {
    const l = A('left', 0, .2), rt = A('right', 0, l + 1);
    RX(r.hl, t, l - .1, NEVER, -120); RX(r.hr, t, rt - .1, NEVER, 120); POP(r.vs, t, l, NEVER, .3);
    r.rows.forEach((o, i) => {
      const pa = P(t, l + i * .14, .9, eio), pb = P(t, rt + i * .14, .9, eio);
      S(o.lab, P(t, l - .1 + i * .08, .4));
      S(o.bl, pa > 0 ? 1 : 0); o.bl.style.transform += ` scaleX(${Math.max(.001, pa)})`;
      S(o.br, pb > 0 ? 1 : 0); o.br.style.transform += ` scaleX(${Math.max(.001, pb)})`;
      o.vl.innerHTML = fmt(o.a * pa, o.dec); S(o.vl, P(t, l + i * .14 + .2, .4));
      o.vr.innerHTML = fmt(o.b * pb, o.dec); S(o.vr, P(t, rt + i * .14 + .2, .4));
    });
    return '';
  }
};

// Photo slot with multi-crop pans. data: slot, desc, src, cap, crops:[[cx,cy,zoom],...]. actions: crop1, crop2..., cap
function photoInner(d, w, h) {
  if (d.src) return `<img src="${d.src}" style="width:${w}px;height:${h}px;object-fit:cover;display:block">`;
  return `<div style="width:${w}px;height:${h}px;background:repeating-linear-gradient(135deg,rgba(255,255,255,.75) 0 40px,rgba(214,236,255,.75) 40px 80px);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px">
    <div class="A" style="font-size:120px">PHOTO SLOT ${d.slot || ''}</div><div class="L" style="font-size:28px;max-width:${w - 200}px;white-space:normal;text-align:center;line-height:1.5">${d.desc || ''}</div></div>`;
}
TPL.photo = {
  build(L, d) {
    const r = { d }, w = d.w || 1500, h = d.h || 840; r.w = w; r.h = h;
    r.crops = d.crops || [[.5, .5, 1.08], [.36, .42, 1.38], [.64, .56, 1.26]];
    r.card = E(L, `<div style="width:${w}px;height:${h}px;overflow:hidden;border-radius:26px;border:10px solid #fff;box-shadow:0 30px 80px rgba(20,33,92,.28);background:#fff"><div class="pin" style="transform-origin:50% 50%">${photoInner(d, w, h)}</div></div>`, { y: CY + 15 });
    r.pin = r.card.querySelector('.pin');
    r.cap = E(L, d.cap || '', { c: 'pill pg', x: CX - w / 2 + 40, y: CY + 15 + h / 2 - 10, a: 'l', st: { fontSize: '26px' } });
    return r;
  },
  update(t, A, r) {
    S(r.card, P(t, 0, .4), 0, 0, 1);
    let [cx, cy, z] = r.crops[0];
    for (let i = 1; i < r.crops.length; i++) {
      const p = P(t, A('crop' + i), .9, eio); if (p <= 0) break;
      cx = lerp(cx, r.crops[i][0], p); cy = lerp(cy, r.crops[i][1], p); z = lerp(z, r.crops[i][2], p);
    }
    z += .025 * t / 6;
    r.pin.style.transform = `scale(${z}) translate(${(.5 - cx) * r.w}px,${(.5 - cy) * r.h}px)`;
    R(r.cap, t, A('cap', 0, .6), NEVER, 20);
    return '';
  }
};

// Aura moment. data: slot, desc, src, word, sub. actions: charge, burst, sub
TPL.aura = {
  build(L, d) {
    const r = { d }, w = 1080, h = 680;
    r.rays = E(L, '', { st: { width: '2600px', height: '2600px', borderRadius: '50%', background: 'repeating-conic-gradient(from 0deg,rgba(255,214,90,.55) 0deg 6deg,rgba(255,255,255,0) 6deg 15deg)', maskImage: 'radial-gradient(circle,#000 20%,transparent 62%)', WebkitMaskImage: 'radial-gradient(circle,#000 20%,transparent 62%)' } });
    r.glow = E(L, '', { st: { width: '1500px', height: '1100px', borderRadius: '50%', background: 'radial-gradient(ellipse,rgba(255,200,60,.9) 0%,rgba(255,120,150,.45) 40%,rgba(255,255,255,0) 70%)' } });
    r.card = E(L, `<div style="width:${w}px;height:${h}px;overflow:hidden;border-radius:26px;border:10px solid #fff;box-shadow:0 0 90px rgba(255,170,40,.65)">${photoInner(d, w, h)}</div>`, { y: CY });
    r.parts = [...Array(46)].map((_, i) => E(L, '', { st: { width: (6 + rnd(i * 9) * 12) + 'px', height: (6 + rnd(i * 9) * 12) + 'px', borderRadius: '50%', background: i % 3 ? '#ffd23f' : '#ff7aa8', boxShadow: '0 0 16px #ffd23f' } }));
    r.word = E(L, d.word || 'AURA', { c: 'A gold stroke', fs: d.fs || 330, y: CY + 20, st: { WebkitTextStroke: '0px', filter: 'drop-shadow(0 0 30px rgba(255,255,255,.9)) drop-shadow(0 10px 40px rgba(227,22,91,.5))' } });
    r.sub = E(L, d.sub || '', { c: 'L', fs: 34, y: CY + 300 });
    return r;
  },
  update(t, A, r) {
    const c = A('charge', 0, .05), b = A('burst', 0, c + 1.6);
    const pc = P(t, c, 1.2), pb = P(t, b, .35);
    S(r.rays, pc * .9, 0, 0, lerp(.7, 1.05, pc) + pb * .15, 0, t * (12 + 40 * pb));
    S(r.glow, pc * (.55 + .35 * Math.sin(t * 7) * .5 + .4 * pb), 0, 0, 1 + .06 * Math.sin(t * 5));
    S(r.card, P(t, 0, .35), 0, 0, lerp(.96, 1.07, P(t, c, 2.4, eio)) - .05 * pb * (1 - P(t, b + .2, .4)));
    r.card.style.filter = pb > 0 ? `brightness(${1 - .25 * pb}) saturate(${1 + .3 * pb})` : '';
    r.parts.forEach((p, i) => {
      const sp = 70 + rnd(i * 3) * 160, ph = rnd(i * 5) * 900;
      const yy = CY + 460 - ((Math.max(0, t - c) * sp * (1 + 1.8 * pb) + ph) % 960), xx = CX + (rnd(i) - .5) * 1500 + Math.sin(t * 1.5 + i) * 30;
      p._x = xx; p._y = yy; S(p, pc * (.4 + .6 * rnd(i * 11)));
    });
    POP(r.word, t, b, NEVER, 2.2);
    R(r.sub, t, A('sub', 0, b + .6), NEVER, 20);
    return shake(t, b + .03, 22, .5);
  }
};

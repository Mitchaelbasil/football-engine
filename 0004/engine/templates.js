// 0004 engine v2 — scene templates. Each: build(L, data, scene) -> refs; update(t, A, refs, L, scene) -> extra transform.
// A(action, i=0, default) returns the scene-relative time of the i-th event named `action` (from scenes.json "do").
// Every template has a landscape (16:9) and portrait (9:16, PORT) layout. fit() keeps text inside the frame.
const M = PORT ? 70 : 160;            // side margin
const FW = W - 2 * M;                 // usable width

// Big number that counts up. data: value, label, sub, dec, prefix, suffix. actions: count, sub
TPL.counter = {
  build(L, d) {
    const r = { d };
    r.num = fit(E(L, (d.prefix || '') + fmt(d.value || 0, d.dec) + (d.suffix || ''), { c: 'A gold', fs: d.fs || 420, y: CY - 70 }), FW);
    r.lab = fit(E(L, d.label || '', { c: 'L', fs: 48, y: CY + 190, col: 'var(--accent)' }), FW);
    r.sub = fit(E(L, d.sub || '', { c: 'L', fs: 34, y: CY + 262 }), FW);
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
    const n = d.items.length, gap = Math.min(PORT ? 150 : 175, (PORT ? 760 : 560) / Math.max(n - 1, 1)), y0 = CY - gap * (n - 1) / 2 + 20;
    const x = PORT ? M : W * .2;
    return { items: d.items.map((s, i) => fit(E(L, `<span class="ck">✓</span><span style="vertical-align:middle">${s}</span>`, { c: 'A', fs: d.fs || (PORT ? 84 : 104), x, y: y0 + i * gap, a: 'l' }), W - x - 40)) };
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
    r.pre = fit(E(L, d.pre || '', { c: 'L', fs: 46, y: CY - (PORT ? 330 : 270), col: 'var(--accent)' }), FW);
    r.ring = E(L, '', { y: CY + 30, st: { width: '220px', height: '220px', borderRadius: '50%', border: '16px solid #ffb11f' } });
    r.word = fit(E(L, d.word || '', { c: 'A gold', fs: d.fs || 560, y: CY + 30 }), FW);
    r.sub = fit(E(L, d.sub || '', { c: 'L', fs: 34, y: CY + (PORT ? 400 : 330) }), FW);
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
    r.kick = E(L, d.kicker || 'ARC 01', { c: 'pill pg', y: CY - (PORT ? 330 : 250), st: { fontSize: '34px' } });
    r.brush = E(L, '', { y: CY + 30, st: { width: Math.min(1500, W - 20) + 'px', height: (PORT ? 420 : 300) + 'px', background: 'linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.92) 12%,rgba(255,255,255,.92) 88%,rgba(255,255,255,0))', transformOrigin: '0 50%' } });
    const [l1, l2] = d.title || ['', ''];
    r.t1 = fit(E(L, l1, { c: 'A', fs: d.fs1 || 140, y: CY - (PORT ? 70 : 50) }), FW);
    r.t2 = fit(E(L, l2, { c: 'A gold', fs: d.fs2 || 190, y: CY + (PORT ? 110 : 115) }), FW);
    r.sub = fit(E(L, d.sub || '', { c: 'L', fs: 30, y: CY + (PORT ? 330 : 300) }), FW);
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
    const r = { d }, rx = PORT ? CX : W * .29, ry = PORT ? CY - 430 : CY + 30, k = PORT ? .82 : 1;
    const ticks = [...Array(72)].map((_, i) => { const a = i / 72 * Math.PI * 2, r0 = i % 6 ? 282 : 262; return `<line x1="${Math.cos(a) * r0}" y1="${Math.sin(a) * r0}" x2="${Math.cos(a) * 300}" y2="${Math.sin(a) * 300}" stroke="#14215c" stroke-width="${i % 6 ? 3 : 6}" stroke-opacity=".55"/>`; }).join('');
    r.ring1 = E(L, `<svg width="640" height="640" viewBox="-320 -320 640 640">${ticks}<circle r="310" fill="none" stroke="#e3165b" stroke-width="4" stroke-dasharray="40 22"/></svg>`, { x: rx, y: ry });
    r.ring2 = E(L, `<svg width="480" height="480" viewBox="-240 -240 480 480"><path d="M -220 0 A 220 220 0 0 1 0 -220" fill="none" stroke="#ffb11f" stroke-width="16" stroke-linecap="round"/><path d="M 220 0 A 220 220 0 0 1 0 220" fill="none" stroke="#ffb11f" stroke-width="16" stroke-linecap="round"/><circle r="200" fill="none" stroke="#14215c" stroke-opacity=".2" stroke-width="2"/></svg>`, { x: rx, y: ry });
    const core = (ini, bg) => `<div style="width:340px;height:340px;border-radius:50%;background:${bg};display:flex;align-items:center;justify-content:center;box-shadow:0 20px 60px rgba(20,33,92,.25)"><span class="A" style="font-size:150px;color:#fff;text-shadow:none">${ini}</span></div>`;
    r.core1 = E(L, core(d.initials || 'CR', 'var(--herobar)'), { x: rx, y: ry });
    r.cross = E(L, `<svg width="760" height="760" viewBox="-380 -380 760 760"><g stroke="#14215c" stroke-width="4" stroke-opacity=".5"><line x1="-380" y1="0" x2="-330" y2="0"/><line x1="330" y1="0" x2="380" y2="0"/><line x1="0" y1="-380" x2="0" y2="-330"/><line x1="0" y1="330" x2="0" y2="380"/></g></svg>`, { x: rx, y: ry });
    r.scanline = E(L, '', { x: rx, y: ry, st: { width: '640px', height: '10px', borderRadius: '5px', background: 'linear-gradient(90deg,rgba(227,22,91,0),#e3165b,rgba(227,22,91,0))', boxShadow: '0 0 30px #e3165b' } });
    [r.ring1, r.ring2, r.core1, r.cross, r.scanline].forEach(e => e._k = k);
    const X = PORT ? M + 20 : W * .58, Y = PORT ? CY + 260 : CY;
    r.tgt = E(L, 'TARGET', { c: 'L', fs: 26, x: X, y: Y - 250, a: 'l', col: 'var(--accent)' });
    r.name1 = fit(E(L, d.name || '', { c: 'A', fs: 92, x: X, y: Y - 175, a: 'l' }), W - X - 40);
    r.pl = E(L, d.label || 'POWER LEVEL', { c: 'L', fs: 30, x: X, y: Y - 85, a: 'l' });
    r.num1 = E(L, '00', { c: 'A gold', fs: 300, x: X - 10, y: Y + 90, a: 'l' });
    r.segs = [...Array(20)].map((_, i) => E(L, '', { x: X + i * 34, y: Y + 290, a: 'l', st: { width: '28px', height: '58px', borderRadius: '6px', background: 'var(--track)' } }));
    r.stat = E(L, '', { c: 'L', fs: 26, x: X, y: Y + 370, a: 'l' });
    if (d.rival) {
      r.core2 = E(L, core(d.rival.initials || 'LM', 'var(--rivalbar)'), { x: rx, y: ry }); r.core2._k = k;
      r.name2 = fit(E(L, d.rival.name, { c: 'A', fs: 92, x: X, y: Y - 175, a: 'l', col: 'var(--rivaltext)' }), W - X - 40);
      r.num2 = E(L, '00', { c: 'A blue', fs: 300, x: X - 10, y: Y + 90, a: 'l' });
      r.warn = E(L, 'LIMIT EXCEEDED', { c: 'A', fs: 64, x: PORT ? X + 560 : X + 470, y: Y + 60, r: -8, st: { padding: '6px 24px', border: '6px solid #e3165b', color: '#e3165b', borderRadius: '12px', background: 'rgba(255,255,255,.8)', textShadow: 'none' } });
      if (PORT) r.warn._k = .8;
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
    S(r.scanline, sw ? .95 : 0, 0, Math.sin(t * 5.5) * 240 * (PORT ? .82 : 1));
    [r.tgt, r.pl].forEach((e, i) => R(e, t, lock + .15 + i * .12, NEVER, 16));
    const swap = P(t, riv, .3);
    const c1 = clamp((t - lock - .1) / .45 * 2.5); S(r.core1, c1 * (1 - swap), 0, 0, lerp(.5, 1, eb(clamp((t - lock - .1) / .45))) * (1 - .3 * swap));
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

// Head to head bars. data: left:{name}, right:{name}, rows:[[label,a,b,dec]]. actions: left, right
TPL.h2h = {
  build(L, d) {
    const r = { rows: [] }, gap = PORT ? 22 : 170, mw = PORT ? 330 : 560, bh = PORT ? 64 : 74;
    const n = d.rows.length, step = PORT ? Math.min(190, 900 / Math.max(n - 1, 1)) : Math.min(140, 520 / Math.max(n - 1, 1));
    const top = PORT ? CY - 300 : CY - 150, nameY = PORT ? CY - 560 : CY - 300;
    r.hl = fit(E(L, d.left.name, { c: 'A gold', fs: PORT ? 96 : 110, x: PORT ? CX - 250 : CX - 420, y: nameY }), PORT ? 440 : 700);
    r.hr = fit(E(L, d.right.name, { c: 'A blue', fs: PORT ? 96 : 110, x: PORT ? CX + 250 : CX + 420, y: nameY }), PORT ? 440 : 700);
    r.vs = E(L, 'VS', { c: 'pill pg', y: nameY, st: { fontSize: '30px' } });
    d.rows.forEach(([lab, a, b, dec], i) => {
      const y = top + i * step, mx = Math.max(a, b), o = { a, b, dec: dec || 0 };
      o.lab = E(L, lab, { c: 'L', fs: 22, y: PORT ? y - 62 : y, st: { opacity: .85 } });
      o.bl = E(L, '', { x: CX - gap, y, a: 'r', c: 'bar', st: { width: (mw * a / mx) + 'px', height: bh + 'px', background: 'var(--herobarL)', transformOrigin: '100% 50%' } });
      o.br = E(L, '', { x: CX + gap, y, a: 'l', c: 'bar', st: { width: (mw * b / mx) + 'px', height: bh + 'px', background: 'var(--rivalbar)' } });
      o.vl = E(L, '', { c: 'A', fs: PORT ? 54 : 66, x: CX - gap - mw * a / mx - 18, y, a: 'r' });
      o.vr = E(L, '', { c: 'A', fs: PORT ? 54 : 66, x: CX + gap + mw * b / mx + 18, y, a: 'l' });
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
  if (d.preview) return `<div style="width:${w}px;height:${h}px;background:repeating-linear-gradient(135deg,rgba(255,255,255,.75) 0 40px,rgba(214,236,255,.75) 40px 80px);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px">
    <div class="A" style="font-size:${Math.min(120, w / 8)}px">PHOTO SLOT ${d.slot || ''}</div><div class="L" style="font-size:28px;max-width:${w - 120}px;white-space:normal;text-align:center;line-height:1.5">${d.desc || ''}</div></div>`;
  // skipped slot: a clean location/date card instead of a photo
  const [a, b] = (d.cap || '').split('·').map(x => x.trim());
  return `<div style="position:relative;width:${w}px;height:${h}px;overflow:hidden;background:linear-gradient(135deg,#ffe9a8,#ffc2d4 55%,#b9dcff)">
    <div style="position:absolute;left:${w / 2 - CX}px;top:${h / 2 - CY}px">${speedLines(70, 120, 1400, ['rgba(20,33,92,.07)', 'rgba(227,22,91,.10)', 'rgba(255,255,255,.55)'], 5)}</div>
    <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;text-align:center;padding:0 60px">
      <div class="A" style="font-size:${Math.min(150, w / 7)}px;color:#14215c;white-space:normal;line-height:.95">${a || ''}</div>
      ${b ? `<div class="L" style="font-size:34px;color:#e3165b">${b}</div>` : ''}</div></div>`;
}
TPL.photo = {
  build(L, d) {
    const r = { d }, w = d.w || (PORT ? W - 100 : 1500), h = d.h || (PORT ? Math.round((W - 100) * 1.3) : 840); r.w = w; r.h = h;
    r.crops = d.crops || [[.5, .5, 1.08], [.36, .42, 1.38], [.64, .56, 1.26]];
    r.card = E(L, `<div style="width:${w}px;height:${h}px;overflow:hidden;border-radius:26px;border:10px solid #fff;box-shadow:0 30px 80px rgba(20,33,92,.28);background:#fff"><div class="pin" style="transform-origin:50% 50%">${photoInner(d, w, h)}</div></div>`, { y: CY + 15 });
    r.pin = r.card.querySelector('.pin');
    r.cap = fit(E(L, d.cap || '', { c: 'pill pg', x: CX - w / 2 + 40, y: CY + 15 + h / 2 - 10, a: 'l', st: { fontSize: '26px' } }), w - 80);
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
    const r = { d }, w = PORT ? W - 140 : 1080, h = PORT ? 1100 : 680;
    r.rays = E(L, '', { st: { width: '2600px', height: '2600px', borderRadius: '50%', background: 'repeating-conic-gradient(from 0deg,rgba(255,214,90,.55) 0deg 6deg,rgba(255,255,255,0) 6deg 15deg)', maskImage: 'radial-gradient(circle,#000 20%,transparent 62%)', WebkitMaskImage: 'radial-gradient(circle,#000 20%,transparent 62%)' } });
    r.glow = E(L, '', { st: { width: '1500px', height: '1100px', borderRadius: '50%', background: 'radial-gradient(ellipse,rgba(255,200,60,.9) 0%,rgba(255,120,150,.45) 40%,rgba(255,255,255,0) 70%)' } });
    r.card = (d.src || d.preview) ? E(L, `<div style="width:${w}px;height:${h}px;overflow:hidden;border-radius:26px;border:10px solid #fff;box-shadow:0 0 90px rgba(255,170,40,.65)">${photoInner(d, w, h)}</div>`, { y: CY }) : null;
    r.parts = [...Array(46)].map((_, i) => E(L, '', { st: { width: (6 + rnd(i * 9) * 12) + 'px', height: (6 + rnd(i * 9) * 12) + 'px', borderRadius: '50%', background: i % 3 ? '#ffd23f' : '#ff7aa8', boxShadow: '0 0 16px #ffd23f' } }));
    r.word = fit(E(L, d.word || 'AURA', { c: 'A gold', fs: d.fs || 330, y: CY + 20 }), W - 80);  // layered after the photo card = always on top
    r.sub = fit(E(L, d.sub || '', { c: 'L', fs: 34, y: CY + (PORT ? 620 : 300) }), FW);
    return r;
  },
  update(t, A, r) {
    const c = A('charge', 0, .05), b = A('burst', 0, c + 1.6);
    const pc = P(t, c, 1.2), pb = P(t, b, .35);
    S(r.rays, pc * .9, 0, 0, lerp(.7, 1.05, pc) + pb * .15, 0, t * (12 + 40 * pb));
    S(r.glow, pc * (.55 + .35 * Math.sin(t * 7) * .5 + .4 * pb), 0, 0, 1 + .06 * Math.sin(t * 5));
    if (r.card) {
      S(r.card, P(t, 0, .35), 0, 0, lerp(.96, 1.07, P(t, c, 2.4, eio)) - .05 * pb * (1 - P(t, b + .2, .4)));
      r.card.style.filter = pb > 0 ? `brightness(${1 - .25 * pb}) saturate(${1 + .3 * pb})` : '';
    }
    r.parts.forEach((p, i) => {
      const sp = 70 + rnd(i * 3) * 160, ph = rnd(i * 5) * 900, span = PORT ? 1700 : 960;
      const yy = CY + span / 2 - ((Math.max(0, t - c) * sp * (1 + 1.8 * pb) + ph) % span), xx = CX + (rnd(i) - .5) * (PORT ? 950 : 1500) + Math.sin(t * 1.5 + i) * 30;
      p._x = xx; p._y = yy; S(p, pc * (.4 + .6 * rnd(i * 11)));
    });
    POP(r.word, t, b, NEVER, 2.2);
    R(r.sub, t, A('sub', 0, b + .6), NEVER, 20);
    return shake(t, b + .03, 22, .5);
  }
};

// Match timeline. data: header, home, away, hero ('h'|'a' = our side, accent colour), events:[[minute,name,'h'|'a']], max (90). actions: open, ev0..evN, final
TPL.timeline = {
  build(L, d) {
    const r = { d }, X0 = PORT ? 110 : 260, X1 = W - X0, ty = PORT ? CY + 60 : CY + 100, mx = d.max || 90;
    r.X0 = X0; r.X1 = X1; r.mx = mx;
    r.hdr = fit(E(L, d.header || '', { c: 'L', fs: 24, y: PORT ? CY - 520 : CY - 330, col: 'var(--accent)' }), FW);
    if (PORT) {
      r.home = fit(E(L, d.home, { c: 'A', fs: 96, y: CY - 430 }), FW);
      r.away = fit(E(L, d.away, { c: 'A', fs: 96, y: CY - 170 }), FW);
      r.score = E(L, '0–0', { c: 'A card', fs: 120, y: CY - 300, st: { padding: '6px 32px', borderRadius: '22px' } });
    } else {
      r.home = fit(E(L, d.home, { c: 'A', fs: 110, x: CX - 260, y: CY - 210, a: 'r' }), 640);
      r.away = fit(E(L, d.away, { c: 'A', fs: 110, x: CX + 260, y: CY - 210, a: 'l' }), 640);
      r.score = E(L, '0–0', { c: 'A card', fs: 130, y: CY - 210, st: { padding: '10px 36px', borderRadius: '22px' } });
    }
    r.track = E(L, '', { x: X0, y: ty, a: 'l', st: { width: (X1 - X0) + 'px', height: '10px', borderRadius: '5px', background: 'var(--track)' } });
    r.fill = E(L, '', { x: X0, y: ty, a: 'l', st: { width: (X1 - X0) + 'px', height: '10px', borderRadius: '5px', background: 'var(--herobar)', transformOrigin: '0 50%' } });
    r.ticks = [0, 15, 30, 45, 60, 75, 90].filter(m => m <= mx).map(m => E(L, m + "'", { c: 'L', fs: 20, x: X0 + (X1 - X0) * m / mx, y: ty + 50, st: { opacity: .6 } }));
    r.head = E(L, '', { x: X0, y: ty, st: { width: '30px', height: '30px', borderRadius: '50%', background: '#fff', boxShadow: '0 0 24px #fff' } });
    let sh = 0, sa = 0;
    r.ev = (d.events || []).map(([m, name, side], i) => {
      side === 'h' ? sh++ : sa++;
      const x = X0 + (X1 - X0) * m / mx, up = i % 2 === 0, col = side === (d.hero || 'h') ? 'var(--accent)' : 'var(--rivaltext)';
      return {
        m, score: `${sh}–${sa}`,
        lab: E(L, `<div class="A" style="font-size:${PORT ? 56 : 64}px">${m}'</div><div class="L" style="font-size:${PORT ? 20 : 24}px;margin-top:6px">${name}</div>`, { x: clamp(x, X0 + 60, X1 - 60), y: up ? ty - 130 : ty + 150, st: { textAlign: 'center', color: col } }),
        dot: E(L, '', { x, y: ty, st: { width: '40px', height: '40px', borderRadius: '50%', background: col, border: '4px solid #fff' } })
      };
    });
    return r;
  },
  update(t, A, r) {
    const o = A('open', 0, .05);
    [r.hdr, r.home, r.away].forEach((e, i) => R(e, t, o + i * .1, NEVER, 30));
    R(r.score, t, o + .25, NEVER, 20);
    let m = 0;
    r.ev.forEach((e, i) => { const a = A('ev' + i, 0, NEVER); if (t >= a - .9) m = lerp(m, e.m, P(t, a - .9, .9, eio)); });
    const end = A('final', 0, NEVER); if (t >= end - 1) m = lerp(m, r.mx, P(t, end - 1, 1, eio));
    S(r.track, P(t, o + .2, .5)); S(r.fill, P(t, o + .2, .5)); r.fill.style.transform += ` scaleX(${Math.max(.001, m / r.mx)})`;
    r.ticks.forEach((d, i) => S(d, .6 * P(t, o + .3 + i * .05, .4)));
    r.head._x = lerp(r.X0, r.X1, m / r.mx); S(r.head, P(t, o + .3, .4));
    let score = '0–0', last = -1;
    r.ev.forEach((e, i) => { const a = A('ev' + i, 0, NEVER); if (t >= a) { score = e.score; last = a; } POP(e.lab, t, a, NEVER, .5); POP(e.dot, t, a, NEVER, .2); });
    r.score.innerHTML = score;
    S(r.score, P(t, o + .3, .5), 0, 0, last >= 0 ? lerp(1.25, 1, P(t, last, .4)) : 1);
    return last >= 0 ? shake(t, last, 10, .3) : '';
  }
};

// League table. data: title, cols:[...], rows:[[pos,name,[vals],hl]], short:[col indices for 9:16]. actions: rows, hl, badge
TPL.table = {
  build(L, d) {
    const r = { rows: [] }, idx = PORT ? (d.short || [d.cols.length - 1]) : d.cols.map((_, i) => i);
    const cw = PORT ? 150 : 130, nw = PORT ? 520 : 620, x0 = PORT ? M - 20 : (W - (70 + nw + cw * idx.length)) / 2;
    const cell = (v, i, big) => `<span style="display:inline-block;width:${cw}px;text-align:center;${big ? 'font-size:1.2em;' : ''}">${v}</span>`;
    const line = (p, n, vals) => `<span style="display:inline-block;width:70px">${p}</span><span style="display:inline-block;width:${nw}px;overflow:hidden">${n}</span>` + idx.map((i, k) => cell(vals[i], i, k === idx.length - 1)).join('');
    r.title = fit(E(L, d.title || '', { c: 'L', fs: 26, x: x0 + 20, y: CY - (PORT ? 420 : 300), a: 'l', col: 'var(--accent)' }), FW);
    r.head = E(L, line('', '', d.cols), { c: 'L', fs: 22, x: x0 + 20, y: CY - (PORT ? 350 : 220), a: 'l', st: { opacity: .7 } });
    const step = PORT ? 120 : 112;
    d.rows.forEach(([p, n, vals, hl], i) => {
      const e = E(L, line(p, n, vals), { c: 'A card', fs: PORT ? 56 : 60, x: x0, y: CY - (PORT ? 250 : 120) + i * step, a: 'l', st: { padding: '14px 20px', ...(hl ? { background: 'linear-gradient(90deg,rgba(255,201,74,.95),rgba(255,120,80,.85))', color: '#fff' } : {}) } });
      e._hl = !!hl; r.rows.push(fit(e, W - x0 - 20));
    });
    r.badge = d.badge ? E(L, d.badge, { c: 'pill pg', x: PORT ? CX : W - 260, y: CY - (PORT ? 250 : 120) + d.rows.length * step + 30, st: { fontSize: '34px' } }) : null;
    return r;
  },
  update(t, A, r) {
    const a = A('rows', 0, .1), h = A('hl', 0, NEVER);
    R(r.title, t, a - .1, NEVER, 20); R(r.head, t, a, NEVER, 20);
    r.rows.forEach((e, i) => { const pi = P(t, a + .15 + i * .12, .45); S(e, pi, (1 - pi) * 60, 0, e._hl && t >= h ? lerp(1.06, 1.02, P(t, h, .4)) : 1); });
    if (r.badge) POP(r.badge, t, A('badge', 0, NEVER), NEVER, .4);
    return shake(t, h, 8, .3);
  }
};

// Grid of tiles that light up (e.g. every opponent scored against). data: title, items[], count (label). actions: show, light, stamp
TPL.grid = {
  build(L, d) {
    const r = { d }, n = d.items.length, cols = PORT ? 3 : (d.cols || 5), tw = PORT ? 300 : 300, th = PORT ? 100 : 112, gx = PORT ? 20 : 24, gy = PORT ? 22 : 32;
    const rows = Math.ceil(n / cols), y0 = CY - (rows - 1) * (th + gy) / 2 + (PORT ? 40 : 30);
    r.title = fit(E(L, d.title || '', { c: 'L', fs: 26, y: y0 - th - (PORT ? 60 : 40), col: 'var(--accent)' }), FW);
    r.tiles = d.items.map((s, i) => {
      const row = Math.floor(i / cols), col = i % cols, inRow = Math.min(cols, n - row * cols);
      const x = CX + (col - (inRow - 1) / 2) * (tw + gx), y = y0 + row * (th + gy);
      return fit(E(L, `<span class="tk" style="display:inline-block;width:0;overflow:hidden;vertical-align:middle">✓&nbsp;</span>${s}`, { c: 'O card', fs: PORT ? 28 : 32, x, y, st: { width: tw + 'px', height: th + 'px', lineHeight: th + 'px', textAlign: 'center', borderRadius: '18px', overflow: 'hidden' } }), tw + 10);
    });
    r.count = E(L, '', { c: 'L', fs: 30, y: y0 + rows * (th + gy) + 20, col: 'var(--accent)' });
    r.stamp = d.stamp ? fit(E(L, d.stamp, { c: 'A', fs: 100, y: CY, r: -5, st: { padding: '14px 40px', border: '8px solid #e3165b', color: '#e3165b', borderRadius: '18px', background: 'rgba(255,255,255,.85)', textShadow: 'none' } }), FW) : null;
    return r;
  },
  update(t, A, r) {
    const s = A('show', 0, .05), l = A('light', 0, NEVER), st = A('stamp', 0, NEVER);
    R(r.title, t, s, NEVER, 20);
    let lit = 0; const dim = r.stamp ? DIM(t, st, .45) : 1;
    r.tiles.forEach((d, i) => {
      const p = P(t, s + i * .03, .4), la = l + .1 + i * .09, on = t >= la; if (on) lit++;
      S(d, p * dim, 0, (1 - p) * 30, on ? lerp(1.12, 1, P(t, la, .25)) : 1);
      d.style.background = on ? 'var(--herobar)' : ''; d.style.color = on ? '#fff' : 'var(--text)';
      d.querySelector('.tk').style.width = on ? 'auto' : '0';
    });
    r.count.innerHTML = `${r.d.count || ''} <span style="font-size:44px">${lit}</span> / ${r.tiles.length}`;
    S(r.count, P(t, l, .4) * dim);
    if (r.stamp) POP(r.stamp, t, st, NEVER, 1.6);
    return shake(t, st + .05, 14);
  }
};

// Penalty shootout. data: teams:[A,B], kicks:[[0|1 team, scored bool, name]], result. actions: show, run (auto-plays kicks .32s apart), k0..kN override, result
TPL.shootout = {
  build(L, d) {
    const r = { d }, step = PORT ? 175 : 230, sz = PORT ? 110 : 120, x0 = PORT ? CX - 2 * step : 680;
    const ys = PORT ? [CY - 260, CY + 160] : [CY - 120, CY + 100];
    r.names = d.teams.map((n, i) => fit(E(L, n, { c: 'A', fs: PORT ? 72 : 84, x: PORT ? CX : 520, y: PORT ? ys[i] - 130 : ys[i], a: PORT ? 'c' : 'r' }), PORT ? FW : 480));
    r.slots = [0, 1].flatMap(tm => [...Array(5)].map((_, i) => E(L, '', { x: x0 + i * step, y: ys[tm], st: { width: sz + 'px', height: sz + 'px', borderRadius: '50%', border: '4px solid rgba(20,33,92,.15)' } })));
    const cnt = [0, 0];
    r.k = d.kicks.map(([tm, ok, nm]) => {
      const i = cnt[tm]++, x = x0 + i * step, y = ys[tm];
      return {
        c: E(L, ok ? '✓' : '✕', { x, y, st: { width: sz + 'px', height: sz + 'px', lineHeight: sz + 'px', textAlign: 'center', borderRadius: '50%', fontSize: '60px', fontWeight: '900', background: ok ? 'linear-gradient(135deg,#4be08a,#14a35a)' : 'linear-gradient(135deg,#ff5c6c,#c3134f)', color: '#fff' } }),
        n: fit(E(L, nm, { c: 'L', fs: 17, x, y: y + sz / 2 + 26, st: { opacity: .85 } }), step - 10)
      };
    });
    r.res = d.result ? fit(E(L, d.result, { c: 'A', fs: PORT ? 64 : 76, y: PORT ? CY + 480 : CY + 330 }), FW) : null;
    return r;
  },
  update(t, A, r) {
    const s = A('show', 0, .05), run = A('run', 0, s + .6);
    r.names.forEach((e, i) => R(e, t, s + i * .1, NEVER, 20));
    r.slots.forEach(e => S(e, P(t, s + .1, .4)));
    let last = -1;
    r.k.forEach((k, i) => { const a = A('k' + i, 0, run + i * .32); if (t >= a) last = a; POP(k.c, t, a); R(k.n, t, a + .1, NEVER, 10); });
    if (r.res) R(r.res, t, A('result', 0, NEVER), NEVER, 20);
    return last >= 0 ? shake(t, last, 6, .2) : '';
  }
};

// End card for Shorts. data: line, title. actions: none (auto)
TPL.endcard = {
  build(L, d) {
    const r = {};
    r.lines = E(L, speedLines(80, 300, 1600, ['rgba(20,33,92,.08)', 'rgba(227,22,91,.12)', 'rgba(255,255,255,.6)'], 9), {});
    r.l1 = fit(E(L, d.line || 'FULL STORY ON THE CHANNEL', { c: 'A', fs: PORT ? 110 : 120, y: CY - 80 }), FW);
    r.t = fit(E(L, d.title || '', { c: 'A gold', fs: PORT ? 84 : 96, y: CY + 70 }), FW);
    r.arrow = E(L, '↓', { c: 'A', fs: 160, y: CY + (PORT ? 300 : 260), col: 'var(--accent)' });
    return r;
  },
  update(t, A, r) {
    S(r.lines, P(t, 0, .5), 0, 0, 1, 0, t * 8); R(r.l1, t, .05, NEVER, 40); R(r.t, t, .3, NEVER, 40);
    S(r.arrow, P(t, .5, .3), 0, Math.sin(t * 7) * 18);
    return '';
  }
};

// ---------- accents: planner-inserted visible changes, specific to each scene type ----------
const PULSE = (el, k, amt) => { if (el && k > 0) el.style.transform += ` scale(${1 + amt * k})`; };
TPL.counter.accent = (r, ac) => { PULSE(r.num, ac.k, .14); if (ac.k > 0) r.num.style.filter = `brightness(${1 + .3 * ac.k}) drop-shadow(0 0 ${30 * ac.k}px rgba(255,180,60,.9))`; };
TPL.checklist.accent = (r, ac) => { const it = r.items[ac.i % r.items.length]; PULSE(it, ac.k, .09); if (it) it.firstChild.style.transform += ` rotate(${360 * (1 - ac.k)}deg)`; };
TPL.slam.accent = (r, ac) => { if (ac.k > 0) S(r.ring, ac.k, 0, 0, lerp(.6, 7, 1 - ac.k)); PULSE(r.word, ac.k, .07); return shake(0, 0, 0); };
TPL.arc.accent = (r, ac) => { PULSE(r.lines, ac.k, .3); PULSE(r.t2, ac.k, .07); };
TPL.scan.accent = (r, ac) => { PULSE(r.ring1, ac.k, .22); PULSE(r.ring2, ac.k, -.18); [r.num1, r.num2].forEach(e => PULSE(e, ac.k, .1)); };
TPL.h2h.accent = (r, ac) => {
  r.rows.forEach(x => x.lab.style.color = '');
  const o = r.rows[ac.i % r.rows.length]; if (!o || ac.k <= 0) return;
  [o.bl, o.br].forEach(b => { b.style.transform += ` scaleY(${1 + .45 * ac.k})`; b.style.filter = `brightness(${1 + .35 * ac.k}) drop-shadow(0 0 ${24 * ac.k}px rgba(255,255,255,.95))`; });
  [o.vl, o.vr].forEach(v => PULSE(v, ac.k, .4)); PULSE(o.lab, ac.k, .06); o.lab.style.color = 'var(--accent)';
};
TPL.photo.accent = (r, ac, t, s) => {  // each accent re-frames the photo: alternate push-in / pull-back
  let z = 0; s.accT.forEach((a, j) => { z += (j % 2 ? -.08 : .11) * eo(clamp((t - a) / .35)); });
  r.pin.style.transform += ` scale(${1 + z})`;
};
TPL.aura.accent = (r, ac) => { PULSE(r.glow, ac.k, .35); PULSE(r.rays, ac.k, .12); if (r.card) PULSE(r.card, ac.k, .04); };
TPL.timeline.accent = (r, ac) => { PULSE(r.score, ac.k, .22); r.ev.forEach(e => PULSE(e.dot, ac.k, .6)); };
TPL.table.accent = (r, ac) => { PULSE(r.rows[ac.i % r.rows.length], ac.k, .06); };
TPL.grid.accent = (r, ac, t) => { if (ac.k <= 0) return; const n = r.tiles.length; r.tiles.forEach((d, i) => { const w = Math.max(0, 1 - Math.abs(i / n - (1 - ac.k)) * 4); PULSE(d, w, .14); }); };
TPL.shootout.accent = (r, ac) => { r.k.forEach(k => PULSE(k.c, ac.k, .18)); };
TPL.endcard.accent = (r, ac) => { PULSE(r.t, ac.k, .08); };

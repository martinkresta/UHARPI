/* UHA schematic pages (SCADA style): inline SVG drawn from a data description, refreshed with the live values.
 * A page calls UHA.scheme(def). The topology lives only in def (one place to correct it); this file only draws.
 *
 * def = {
 *   title, sub: text keys; head: [[href, text key], ...] (page head buttons)
 *   width, height: viewBox (design for a phone in portrait: 600 wide; text 20 units = 11 px at 360 px width)
 *   modes: true          -> Výkon / Proud / Obojí switch (remembered); rows with an `i` key are "flow" rows
 *   areas:  [{x, y, w, h, label}]                       dashed frame with a title (label = text key)
 *   blocks: [{id, x, y, w, h?, label, cls, rows, state}]
 *            label: text key ("mon.…") or a variable name (its short name is shown)
 *            cls:   solar | load | bat | heat | home (colour of the top stripe)
 *            rows:  [{v, i?, l?, o?}]  v = value variable, i = current variable (flow row), l = label (text key or
 *                    variable name, default: the measure part of v's name), o = U.parts options
 *                    or {fn: U => [label, value text, cls]} for a computed row
 *            state: state variable (enum / bool) shown as the first row
 *            href:  the block is a link (e.g. to its control section), " ›" after the title
 *   links:  [{from, to, v, i?, cls, pts?, min?, imin?, invert?}]  power line between blocks; arrow in the flow
 *            direction when |value| >= min (default 20 W / 0.5 A); v / i may also be functions U => number;
 *            without v: a static line (bus); pts instead of from / to: explicit path
 *   pipes:  [{pts: [[x, y], ...], t, label?: [x, y, anchor]}]     heat pipe coloured by temperature variable t
 *   symbols:[{type: 'pump' | 'valve' | 'fan', x, y, v, dir?, r?, label?: [dx, dy, anchor]}]
 *   texts:  [{x, y, v, l?, anchor?, cls?}]                         loose value, optional label
 *   extra:  U => svg string drawn after the pipes (tank, exchanger, ...)
 * }
 * Invalid / stale values are grey (as on the other pages). Positions are viewBox units.
 */
(function () {
  const ROW_H = 27, HEAD_H = 38, PAD = 10;
  let mode = 'power';
  try { const m = localStorage.getItem('uha.scheme.mode'); if (['power', 'current', 'both'].includes(m)) mode = m; } catch (e) { /* no storage */ }

  const isVar = s => /^[A-Z][A-Z0-9_]*$/.test(s);

  UHA.scheme = function (def) {
    UHA.start(U => render(U, def), {
      after() {
        document.querySelectorAll('.modesw button').forEach(b => {
          b.onclick = () => {
            mode = b.dataset.mode;
            try { localStorage.setItem('uha.scheme.mode', mode); } catch (e) { /* no storage */ }
            UHA.refresh();
          };
        });
      }
    });
  };

  function render(U, def) {
    const label = l => (isVar(l) ? U.vshort(l) : U.t(l));
    const val = v => (typeof v === 'function' ? v(U) : U.num(v));
    const blocks = {};
    def.blocks.forEach(b => {
      const n = (b.rows || []).length + (b.state ? 1 : 0);
      blocks[b.id] = Object.assign({ h: HEAD_H + n * ROW_H + PAD }, b);
    });

    // ---------- rows ----------
    function rowText(r) {
      if (r.fn) return r.fn(U);
      const lbl = r.l ? label(r.l) : U.vmeasure(r.v);
      if (!('i' in r)) return [lbl, U.show(r.v, r.o), U.ageClass(r.v)];
      const p = U.show(r.v, r.o), c = r.i ? U.show(r.i) : '–';
      if (mode === 'power') return [lbl, p, U.ageClass(r.v)];
      if (mode === 'current') return [r.il ? label(r.il) : lbl, c, r.i ? U.ageClass(r.i) : 'bad'];
      return [lbl, `${p} · ${c}`, U.ageClass(r.v)];
    }

    // text squeezed to maxW when its estimated width is larger (long dictionary names on a phone-sized block)
    function fitAttr(str, perChar, maxW) {
      return String(str).length * perChar > maxW && maxW > 30 ? ` textLength="${maxW.toFixed(0)}" lengthAdjust="spacingAndGlyphs"` : '';
    }
    const plain = s => String(s).replace(/<[^>]*>/g, '');

    function block(b) {
      const rows = (b.state ? [{ fn: () => [U.t('mon.scheme.state'), U.show(b.state), U.ageClass(b.state)] }] : []).concat(b.rows || []);
      let s = `<g><rect class="blk" x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="10"/>` +
        `<rect class="stripe ${b.cls || ''}" x="${b.x}" y="${b.y}" width="${b.w}" height="5" rx="2"/>` +
        `<text class="title" x="${b.x + PAD}" y="${b.y + 29}"${fitAttr(label(b.label) + (b.href ? ' ›' : ''), 11.8, b.w - 2 * PAD)}>${U.esc(label(b.label))}${b.href ? ' ›' : ''}</text>`;
      rows.forEach((r, k) => {
        const [l, v, cls] = rowText(r), y = b.y + HEAD_H + 19 + k * ROW_H;
        const room = b.w - 2 * PAD - plain(v).length * 11.2 - 8;
        if (room >= 30) s += `<text class="rl" x="${b.x + PAD}" y="${y}"${fitAttr(l, 10.4, room)}>${U.esc(l)}</text>`;   // no room: value only
        s +=
          `<text class="rv ${cls || ''}" x="${b.x + b.w - PAD}" y="${y}" text-anchor="end">${v}</text>`;
      });
      s += '</g>';
      return b.href ? `<a class="blink" href="${b.href}">${s}</a>` : s;
    }

    // ---------- links (power lines) ----------
    function autoPts(a, b) {
      const ac = [a.x + a.w / 2, a.y + a.h / 2], bc = [b.x + b.w / 2, b.y + b.h / 2];
      const overlapX = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      if (b.y >= a.y + a.h || a.y >= b.y + b.h) {               // one above the other: vertical
        const down = b.y >= a.y + a.h;
        const x1 = overlapX > 20 ? (Math.max(a.x, b.x) + Math.min(a.x + a.w, b.x + b.w)) / 2 : ac[0];
        const x2 = overlapX > 20 ? x1 : bc[0];
        const y1 = down ? a.y + a.h : a.y, y2 = down ? b.y : b.y + b.h, ym = (y1 + y2) / 2;
        return x1 === x2 ? [[x1, y1], [x2, y2]] : [[x1, y1], [x1, ym], [x2, ym], [x2, y2]];
      }
      const right = b.x >= a.x + a.w;                          // side by side: horizontal
      const x1 = right ? a.x + a.w : a.x, x2 = right ? b.x : b.x + b.w, xm = (x1 + x2) / 2;
      const overlapY = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      const y1 = overlapY > 20 ? (Math.max(a.y, b.y) + Math.min(a.y + a.h, b.y + b.h)) / 2 : ac[1];
      const y2 = overlapY > 20 ? y1 : bc[1];
      return y1 === y2 ? [[x1, y1], [x2, y2]] : [[x1, y1], [xm, y1], [xm, y2], [x2, y2]];
    }
    function arrow(pts, forward, cls) {
      let best = 0, bi = 0;
      for (let k = 0; k < pts.length - 1; k++) {
        const d = Math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]);
        if (d > best) { best = d; bi = k; }
      }
      const [x1, y1] = pts[bi], [x2, y2] = pts[bi + 1];
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      let ang = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;
      if (!forward) ang += 180;
      return `<path class="arrow ${cls}" d="M 9 0 L -7 -8 L -7 8 Z" transform="translate(${mx} ${my}) rotate(${ang.toFixed(1)})"/>`;
    }
    function link(l) {
      const a = blocks[l.from], b = blocks[l.to];
      const pts = l.pts || (a && b ? autoPts(a, b) : null);
      if (!pts) return '';
      if (l.v === undefined) return `<path class="lnk ${l.cls || ''}" d="M ${pts.map(p => p.join(' ')).join(' L ')}"/>`;   // static (bus)
      const cur = mode === 'current' && l.i !== undefined;
      const x = cur ? (l.i ? val(l.i) : null) : val(l.v);
      const min = cur ? (l.imin || 0.5) : (l.min || 20);
      const valid = x !== null && x !== undefined;
      const flowing = valid && Math.abs(x) >= min;
      const cls = !valid ? 'bad' : flowing ? (l.cls || '') : (l.cls || '') + ' idle';
      const d = 'M ' + pts.map(p => p.join(' ')).join(' L ');
      return `<path class="lnk ${cls}" d="${d}"/>` + (flowing ? arrow(pts, (x > 0) !== Boolean(l.invert), l.cls || '') : '');
    }

    // ---------- heat pipes, symbols, loose texts ----------
    function pipe(p) {
      const t = U.num(p.t), cls = U.ageClass(p.t);
      let s = `<path class="pipe" d="M ${p.pts.map(q => q.join(' ')).join(' L ')}" stroke="${U.tempColor(t)}"${cls === 'bad' ? ' stroke-opacity=".35"' : ''}/>`;
      if (p.label) s += `<text class="lv ${cls}" x="${p.label[0]}" y="${p.label[1]}" text-anchor="${p.label[2] || 'middle'}">${U.show(p.t)}</text>`;
      return s;
    }
    function symbol(sy) {
      const r = sy.r || 16;
      let s = '';
      if (sy.type === 'pump') {
        const on = U.bool(sy.v), rot = { right: 0, down: 90, left: 180, up: 270 }[sy.dir || 'right'];
        s = `<circle class="pump${on ? ' on' : ''}${on === null ? ' bad' : ''}" cx="${sy.x}" cy="${sy.y}" r="${r}"/>` +
          `<path class="pumptri" d="M ${r * 0.6} 0 L ${-r * 0.4} ${-r * 0.55} L ${-r * 0.4} ${r * 0.55} Z" transform="translate(${sy.x} ${sy.y}) rotate(${rot})"/>`;
      } else if (sy.type === 'valve') {
        const k = r * 0.9, vert = sy.dir === 'down' || sy.dir === 'up';
        s = vert
          ? `<path class="valve" d="M ${sy.x - k} ${sy.y - k} L ${sy.x + k} ${sy.y - k} L ${sy.x - k} ${sy.y + k} L ${sy.x + k} ${sy.y + k} Z"/>`
          : `<path class="valve" d="M ${sy.x - k} ${sy.y - k} L ${sy.x + k} ${sy.y + k} L ${sy.x + k} ${sy.y - k} L ${sy.x - k} ${sy.y + k} Z"/>`;
      } else if (sy.type === 'fan') {
        const pct = U.num(sy.v), blades = [0, 120, 240].map(a =>
          `<path class="fanblade" d="M 0 0 C ${r * 0.2} ${-r * 0.5}, ${r * 0.7} ${-r * 0.5}, ${r * 0.75} ${-r * 0.1} Z" transform="translate(${sy.x} ${sy.y}) rotate(${a})"/>`).join('');
        s = `<circle class="fan" cx="${sy.x}" cy="${sy.y}" r="${r}"${pct === null ? ' stroke-opacity=".4"' : ''}/>` + blades;
      }
      if (sy.label) {
        const [dx, dy, anchor] = sy.label;
        s += `<text class="lv ${U.ageClass(sy.v)}" x="${sy.x + dx}" y="${sy.y + dy}" text-anchor="${anchor || 'middle'}">${U.show(sy.v)}</text>`;
      }
      return s;
    }
    function text(t) {
      const cls = t.v ? U.ageClass(t.v) : '';
      const v = t.v ? U.show(t.v, t.o) : '';
      const l = t.l ? label(t.l) + (t.v ? ' ' : '') : '';
      return `<text class="${t.cls || 'lv'} ${cls}" x="${t.x}" y="${t.y}" text-anchor="${t.anchor || 'start'}">${U.esc(l)}${v}</text>`;
    }

    const areas = (def.areas || []).map(a => `<rect class="areabox" x="${a.x}" y="${a.y}" width="${a.w}" height="${a.h}" rx="14"/>` +
      `<text class="area" x="${a.x + 14}" y="${a.y + 28}">${U.esc(label(a.label))}</text>`).join('');
    const svg = `<svg class="scheme" viewBox="0 0 ${def.width} ${def.height}" role="img" aria-label="${U.esc(U.t(def.title))}">` +
      areas + (def.pipes || []).map(pipe).join('') + (def.links || []).map(link).join('') +
      (def.extra ? def.extra(U, { mode }) : '') + def.blocks.map(b => block(blocks[b.id])).join('') +
      (def.symbols || []).map(symbol).join('') + (def.texts || []).map(text).join('') + '</svg>';

    const sw = def.modes ? `<div class="modesw">${['power', 'current', 'both'].map(m =>
      `<button data-mode="${m}" class="${m === mode ? 'on' : ''}">${U.t('mon.scheme.mode_' + m)}</button>`).join('')}</div>` : '';
    return U.pageHead(U.t(def.title), U.t(def.sub), (def.head || []).map(([h, k]) => [h, U.t(k)])) +
      `<div class="schemewrap">${sw}${svg}</div>` + (def.note ? `<p class="note">${U.t(def.note)}</p>` : '');
  }
})();

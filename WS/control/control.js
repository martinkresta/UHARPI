// UHA control pages (https://ctrl.uha.mkresta.cz, client certificate required). One script for all pages; the
// page is chosen by <body data-page="..."> (no inline script: the ctrl CSP is default-src 'self').
// Commands from /api/commands (UhaGatePy, from uha_vars.yaml), states from /uha2.json (js/uha-common.js polls it).
// A command is a request: success = the state variable of the target node changed (CMD_spec.md, "Principles").
// Everything is generic from the YAML: commands grouped by `category:`, the widget chosen by type (kind()).
// ?dry=1: commands are only logged in the console, nothing is sent (to check the UI).
"use strict";
(function () {
  const U = window.UHA;
  const DIMMING_ENABLED = false;   // light brightness slider: shown with the state, sends on release once enabled
  const WAIT_MS = 10000;           // no state change within this time -> "stav se nezměnil"
  const DONE_SHOW_MS = 5000;       // "hotovo" disappears after this
  const DEBOUNCE_MS = 1500;        // stepper: the command is sent this long after the last press
  const REPEAT_DELAY_MS = 450, REPEAT_MS = 150;   // stepper long press
  const LOG_ROWS = 50, LOG_MS = 15000;
  const DRY = new URLSearchParams(location.search).has('dry');

  // pages and their sections (= YAML command categories; "loads" = Vytěžování placeholders, "other" = commands
  // without a known category)
  const PAGES = [
    { file: 'index.html', key: 'ctrl.page.light', sections: ['light'] },
    { file: 'heating.html', key: 'ctrl.page.heating', sections: ['heating', 'ventilation'] },
    { file: 'other.html', key: 'ctrl.page.other', sections: ['blind', 'inverter', 'loads', 'other'] },
    { file: 'history.html', key: 'ctrl.page.history', sections: [] }
  ];
  const KNOWN = ['light', 'blind', 'heating', 'inverter', 'ventilation'];
  const SECTION_TITLE = { light: 'ctrl.cat.light', blind: 'ctrl.cat.blind', heating: 'ctrl.cat.heating', inverter: 'ctrl.cat.inverter',
    ventilation: 'ctrl.cat.ventilation', loads: 'ctrl.cat.loads', other: 'ctrl.cat.other' };
  // section -> monitoring page ("Přehled ›")
  const MON = { heating: 'uha-heat.html', ventilation: 'uha-climate.html', inverter: 'uha-loads.html', loads: 'uha-loads.html' };
  // monitoring pages in the menu
  const MON_MENU = [['uha.html', 'mon.nav.home'], ['uha-energy.html', 'mon.nav.energy'], ['uha-battery.html', 'mon.nav.battery'],
    ['uha-loads.html', 'mon.nav.loads'], ['uha-heat.html', 'mon.nav.heat'], ['uha-climate.html', 'mon.nav.climate']];
  // Vytěžování: loads that cannot be commanded yet (no YAML commands); toggle disabled, state live
  const LOADS = [
    { label: 'POW_EVSE_W', state: 'ST_EVSE_RELAY', on: () => U.bool('ST_EVSE_RELAY') },
    { label: 'POW_WS_HEATING_W', state: 'ST_WS_HEATING_RELAY', on: () => U.bool('ST_WS_HEATING_RELAY') },
    { label: 'EL_HEATER_STATUS', state: 'EL_HEATER_STATUS', on: () => { const c = U.num('ST_EL_HEATER_COILS'); return c === null ? null : c > 0; } }
  ];
  // enum buttons: symbol by the YAML item name, in this order first; items in ENUM_SKIP get no button
  const ENUM_SYMBOLS = [['Up', '▲'], ['Stop', '■'], ['Down', '▼']];
  const ENUM_SKIP = ['None'];

  let commands = [];
  let rows = {};                   // command name -> row state
  const app = () => document.getElementById('app');
  const fileName = () => location.pathname.split('/').pop() || 'index.html';
  const page = PAGES.find(p => p.file === fileName()) || PAGES[0];

  /* ---------- small DOM helpers (no innerHTML with styles: CSP) ---------- */
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  const decimals = step => (step && step < 1 ? Math.min(3, (String(step).split('.')[1] || '').length) : 0);
  const clamp = (c, x) => Math.min(c.max, Math.max(c.min, x));
  const section = c => (KNOWN.includes(c.category) ? c.category : 'other');

  /* ---------- widget kind ---------- */
  function kind(c) {
    if ((c.type === 'uint32' || c.type === 'int32') && c.unit === '%' && c.min === 0 && c.max === 100) return 'light';
    if (c.type === 'bool') return 'toggle';
    if (c.type === 'enum' && c.enum) return 'enum';
    if (c.step) return 'stepper';
    return 'generic';
  }
  const known = v => v && v.valid && v.value !== null && v.value !== undefined;
  const fmtVal = (c, x) => U.fmtNum(x, c.type === 'float' ? decimals(c.step) || (c.step ? 0 : 1) : 0) + (c.unit ? ' ' + c.unit : '');

  function stateText(c, k, v) {
    if (!known(v)) return { text: U.t('ctrl.st.unknown'), cls: 'unknown' };
    switch (k) {
      case 'light': return { text: U.fmtNum(v.value, 0) + ' %', cls: v.value > 0 ? 'on' : '' };
      case 'toggle': {
        const e = U.enumText(c.state);                       // inverters: InverterState item
        const txt = e !== null && (v.enum_name !== undefined) ? e : U.t(v.value ? 'ctrl.st.on' : 'ctrl.st.off');
        return { text: txt, cls: v.value ? 'on' : '' };
      }
      case 'enum': return { text: U.enumText(c.state) || String(v.value), cls: '' };
      default: return { text: fmtVal(c, v.value), cls: '' };
    }
  }
  function reached(k, v, expected) {
    if (!known(v)) return false;
    if (k === 'light') return expected > 0 ? v.value > 0 : v.value === 0;
    if (k === 'toggle') return Boolean(v.value) === Boolean(expected);
    if (k === 'stepper' || k === 'generic') return Math.abs(v.value - expected) <= Math.max(1e-6, Math.abs(expected) * 1e-5);  // float32
    return v.value === expected;
  }

  /* ---------- rows ---------- */
  function toggleEl(onChange, disabled) {
    const lab = el('label', 'sw'), inp = el('input'), knob = el('span');
    inp.type = 'checkbox';
    inp.disabled = Boolean(disabled);
    if (onChange) inp.addEventListener('change', () => onChange(inp.checked));
    lab.append(inp, knob);
    return { lab, inp };
  }

  function buildRow(c) {
    const k = kind(c);
    const r = { c, k, pending: null, pend: null, timer: null, msgTimer: null, buttons: [] };
    const row = el('div', 'crow k-' + k);
    const name = el('div', 'cname', U.cname(c.name, c.desc));
    name.title = c.name + ' → ' + c.target;
    const ctl = el('div', 'cctl'), st = el('div', 'cstate'), msg = el('div', 'cmsg');
    r.badge = el('span', 'badge');
    st.appendChild(r.badge);

    if (k === 'light') {
      const t = toggleEl(on => send(r, on ? 100 : 0));
      r.toggle = t.inp;
      r.slider = el('input', 'dim');
      r.slider.type = 'range'; r.slider.min = 0; r.slider.max = 100; r.slider.step = 1;
      r.slider.disabled = !DIMMING_ENABLED;
      r.slider.setAttribute('aria-label', U.t('ctrl.dim'));
      if (DIMMING_ENABLED) r.slider.addEventListener('change', () => send(r, Number(r.slider.value)));
      ctl.append(t.lab, r.slider);
      r.buttons.push(r.toggle);
    } else if (k === 'toggle') {
      const t = toggleEl(on => send(r, on ? 1 : 0));
      r.toggle = t.inp;
      ctl.append(t.lab);
      r.buttons.push(r.toggle);
    } else if (k === 'enum') {
      r.enumBtns = {};
      const items = Object.entries(c.enum).filter(([, n]) => !ENUM_SKIP.includes(n));
      const order = n => { const i = ENUM_SYMBOLS.findIndex(s => s[0] === n); return i < 0 ? 99 : i; };
      items.sort((a, b) => order(a[1]) - order(b[1]) || Number(a[0]) - Number(b[0]));
      for (const [num, yamlName] of items) {
        const sym = (ENUM_SYMBOLS.find(s => s[0] === yamlName) || [])[1];
        const item = U.enumItem(c.enum_name || '', num);
        const label = (item && item.text) || enumLabel(c, num, yamlName);
        const b = el('button', 'ebtn' + (sym ? ' sym' : ''), sym || label);
        b.title = label;
        b.setAttribute('aria-label', label);
        b.addEventListener('click', () => send(r, Number(num)));
        r.enumBtns[num] = b;
        r.buttons.push(b);
        ctl.appendChild(b);
      }
    } else if (k === 'stepper') {
      const minus = el('button', 'stp', '−'), plus = el('button', 'stp', '+');
      minus.setAttribute('aria-label', U.t('ctrl.dec'));
      plus.setAttribute('aria-label', U.t('ctrl.inc'));
      const box = el('div', 'stpval');
      r.val = el('div', 'v');
      r.sub = el('div', 'sub');
      box.append(r.val, r.sub);
      repeatPress(minus, () => press(r, -1));
      repeatPress(plus, () => press(r, +1));
      ctl.append(minus, box, plus);
      st.classList.add('empty');
      r.buttons.push(minus, plus);
    } else {
      const input = el('input', 'num');
      input.type = 'number'; input.min = c.min; input.max = c.max; input.step = c.type === 'float' ? 'any' : 1;
      input.title = U.t('ctrl.range', { min: fmtVal(c, c.min), max: fmtVal(c, c.max) });
      const b = el('button', 'setbtn', U.t('ctrl.set'));
      const go = () => {
        const x = input.value.trim() === '' ? NaN : Number(input.value);
        if (!Number.isFinite(x)) { setMsg(r, U.t('ctrl.msg.number'), 'error'); return; }
        send(r, x);
      };
      b.addEventListener('click', go);
      input.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
      r.input = input;
      ctl.append(input, b);
      r.buttons.push(b);
    }
    row.append(name, ctl, st, msg);
    r.msg = msg;
    rows[c.name] = r;
    return row;
  }

  // enum item text when the variable's enum is not known by name: look it up through the state variable
  function enumLabel(c, num, yamlName) {
    const v = U.get(c.state);
    if (v && String(v.value) === String(num)) return U.enumText(c.state) || yamlName;
    return yamlName;
  }

  function buildLoadRow(l) {
    const row = el('div', 'crow k-toggle placeholder');
    const name = el('div', 'cname', U.vshort(l.label));
    name.appendChild(el('div', 'cnote', U.t('ctrl.notyet')));
    const t = toggleEl(null, true);
    const ctl = el('div', 'cctl'), st = el('div', 'cstate'), badge = el('span', 'badge');
    ctl.appendChild(t.lab);
    st.appendChild(badge);
    row.append(name, ctl, st);
    return { row, upd: () => {
      const on = l.on(), v = U.get(l.state);
      t.inp.checked = Boolean(on);
      if (!known(v)) { badge.textContent = U.t('ctrl.st.unknown'); badge.className = 'badge unknown'; return; }
      const e = U.enumText(l.state);
      badge.textContent = v.enum_name !== undefined && e !== null ? e : U.t(v.value ? 'ctrl.st.on' : 'ctrl.st.off');
      badge.className = 'badge' + (on ? ' on' : '');
    } };
  }

  /* ---------- stepper ---------- */
  function repeatPress(btn, fn) {
    let t1 = null, t2 = null;
    const stop = () => { clearTimeout(t1); clearInterval(t2); t1 = t2 = null; };
    btn.addEventListener('pointerdown', e => {
      e.preventDefault();
      if (btn.disabled) return;
      fn();
      stop();
      t1 = setTimeout(() => { t2 = setInterval(fn, REPEAT_MS); }, REPEAT_DELAY_MS);
    });
    ['pointerup', 'pointerleave', 'pointercancel'].forEach(ev => btn.addEventListener(ev, stop));
    btn.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(); } });
    btn.addEventListener('contextmenu', e => e.preventDefault());
  }
  function press(r, dir) {
    const c = r.c, v = U.get(c.state);
    const base = r.pend !== null ? r.pend : known(v) ? v.value : c.min;
    const d = decimals(c.step);
    r.pend = clamp(c, Number((Math.round((base + dir * c.step) / c.step) * c.step).toFixed(d)));
    r.pending = null;                 // a new value replaces a running wait
    setMsg(r, '');
    clearTimeout(r.timer);
    r.timer = setTimeout(() => { r.timer = null; send(r, r.pend); }, DEBOUNCE_MS);
    updateRow(r);
  }

  /* ---------- send ---------- */
  function setMsg(r, text, cls) {
    clearTimeout(r.msgTimer);
    r.msg.textContent = text;
    r.msg.className = 'cmsg' + (cls ? ' ' + cls : '') + (text ? ' show' : '');
  }

  async function send(r, value) {
    const c = r.c;
    r.buttons.forEach(b => (b.disabled = true));
    setMsg(r, U.t('ctrl.msg.sending'));
    try {
      let resp, answer = {};
      if (DRY) {
        console.log('UHA control dry run, not sent:', c.name, '=', value);
        resp = { ok: true, status: 200 }; answer = { ok: true };
      } else {
        resp = await fetch('/api/cmd', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cmd: c.name, value: value }) });
        try { answer = await resp.json(); } catch (e) { /* not JSON (e.g. an nginx error page) */ }
      }
      if (resp.ok && answer.ok) {
        r.pending = { expected: r.k === 'stepper' || r.k === 'generic' ? clamp(c, value) : value, deadline: Date.now() + WAIT_MS };
        setMsg(r, U.t('ctrl.msg.waiting') + (DRY ? ' (dry)' : ''));
        setTimeout(() => U.refresh && U.refresh(), 800);
      } else {
        r.pend = null;
        if (resp.status === 429) setMsg(r, U.t('ctrl.msg.ratelimit'), 'error');
        else if (resp.status === 503) setMsg(r, U.t('ctrl.msg.nolink') + ' (' + (answer.error || '503') + ')', 'error');
        else setMsg(r, U.t('ctrl.msg.error', { code: resp.status }) + (answer.error ? ': ' + answer.error : ''), 'error');
      }
    } catch (e) {
      r.pend = null;
      setMsg(r, U.t('ctrl.msg.cantsend', { e: e.message }), 'error');
    } finally {
      r.buttons.forEach(b => (b.disabled = false));
      updateRow(r);
    }
  }

  /* ---------- update from uha2.json ---------- */
  function updateRow(r) {
    const c = r.c, v = U.get(c.state), s = stateText(c, r.k, v);
    r.badge.textContent = s.text;
    r.badge.className = 'badge' + (s.cls ? ' ' + s.cls : '');
    if (r.pending) {
      if (reached(r.k, v, r.pending.expected)) {
        r.pending = null; r.pend = null;
        setMsg(r, U.t('ctrl.msg.done'), 'ok');
        r.msgTimer = setTimeout(() => setMsg(r, ''), DONE_SHOW_MS);
      } else if (Date.now() > r.pending.deadline) {
        r.pending = null; r.pend = null;
        setMsg(r, U.t('ctrl.msg.nochange'), 'error');
      }
    }
    if (r.toggle && !r.pending) r.toggle.checked = known(v) && Boolean(v.value);
    if (r.toggle) r.toggle.parentElement.classList.toggle('unknown', !known(v));
    if (r.slider && (!DIMMING_ENABLED || document.activeElement !== r.slider)) r.slider.value = known(v) ? v.value : 0;
    if (r.enumBtns) for (const [num, b] of Object.entries(r.enumBtns)) b.classList.toggle('current', known(v) && v.value === Number(num));
    if (r.val) {
      const shown = r.pend !== null ? r.pend : known(v) ? v.value : null;
      r.val.textContent = shown === null ? '–' : fmtVal(c, shown);
      r.val.classList.toggle('pending', r.pend !== null);
      r.sub.textContent = r.pend !== null && known(v) && Math.abs(v.value - r.pend) > 1e-6 ? U.t('ctrl.now', { x: fmtVal(c, v.value) }) : '';
    }
    if (r.input && known(v) && !r.inputFilled && document.activeElement !== r.input) { r.input.value = v.value; r.inputFilled = true; }
  }

  let loadRows = [];
  function update() {
    Object.values(rows).forEach(updateRow);
    loadRows.forEach(l => l.upd());
  }

  /* ---------- page build ---------- */
  function head(title) {
    const h = el('div', 'phead'), d = el('div');
    d.appendChild(el('h1', 'pagetitle', title));
    h.appendChild(d);
    return h;
  }
  function sectionCard(sec, body) {
    const card = el('section', 'card csec');
    card.id = sec;
    const h2 = el('h2'), t = el('span', '', U.t(SECTION_TITLE[sec]));
    h2.appendChild(t);
    if (MON[sec]) { const a = el('a', 'ctrllink', U.t('ctrl.monlink')); a.href = U.MON_URL + MON[sec]; h2.appendChild(a); }
    card.append(h2, body);
    return card;
  }

  function build() {
    const root = app();
    root.textContent = '';
    rows = {}; loadRows = [];
    root.appendChild(head(U.t(page.key)));
    if (DRY) root.appendChild(el('div', 'banner dry', U.t('ctrl.dry')));
    const grid = el('div', 'cgrid');
    for (const sec of page.sections) {
      const body = el('div', 'crows');
      if (sec === 'loads') {
        LOADS.forEach(l => { const x = buildLoadRow(l); loadRows.push(x); body.appendChild(x.row); });
      } else {
        const list = commands.filter(c => section(c) === sec);
        if (!list.length) continue;
        list.forEach(c => body.appendChild(buildRow(c)));
      }
      grid.appendChild(sectionCard(sec, body));
    }
    root.appendChild(grid);
    const note = el('p', 'note', U.t('ctrl.note'));
    const hist = el('p', 'note'), a = el('a', '', U.t('ctrl.histlink'));
    a.href = 'history.html';
    hist.appendChild(a);
    root.append(note, hist);
  }

  /* ---------- history page ---------- */
  function commandText(row) {
    const c = commands.find(x => x.name === row.cmd);
    if (!c) return String(row.value);
    switch (kind(c)) {
      case 'light': return row.value > 0 ? U.t('ctrl.log.on') + (row.value < 100 ? ' ' + row.value + ' %' : '') : U.t('ctrl.log.off');
      case 'toggle': return U.t(row.value ? 'ctrl.log.on' : 'ctrl.log.off');
      case 'enum': {
        const item = U.enumItem(c.enum_name || '', row.value);
        return (item && item.text) || (c.enum[String(row.value)] !== undefined ? c.enum[String(row.value)] : String(row.value));
      }
    }
    return fmtVal(c, row.value);
  }
  let logBody = null, logInfo = null, logTimer = null;
  function buildHistory() {
    const root = app();
    root.textContent = '';
    root.appendChild(head(U.t(page.key)));
    const table = el('table', 't'), tr = el('tr');
    ['ctrl.log.time', 'ctrl.log.who', 'ctrl.log.func', 'ctrl.log.cmd'].forEach(k => tr.appendChild(el('th', '', U.t(k))));
    logBody = el('tbody');
    table.append(tr, logBody);
    logInfo = el('p', 'note');
    root.append(table, logInfo);
  }
  async function loadLog() {
    clearTimeout(logTimer);
    try {
      const resp = await fetch('/api/log?limit=' + LOG_ROWS, { cache: 'no-store' });
      let data = null;
      try { data = await resp.json(); } catch (e) { /* not JSON */ }
      if (!resp.ok) throw new Error((data && data.error) || 'HTTP ' + resp.status);
      logBody.textContent = '';
      const today = new Date().toDateString();
      for (const r of data) {
        const t = new Date(r.ts * 1000);
        const when = (t.toDateString() === today ? '' : t.toLocaleDateString(U.locale()) + ' ') + t.toLocaleTimeString(U.locale());
        const tr = el('tr');
        tr.append(el('td', 'time', when), el('td', '', r.user), el('td', '', U.cname(r.cmd, r.desc)), el('td', '', commandText(r)));
        logBody.appendChild(tr);
      }
      logInfo.textContent = data.length ? '' : U.t('ctrl.log.empty');
      logInfo.className = 'note';
    } catch (e) {
      logInfo.textContent = U.t('ctrl.log.err', { e: e.message });
      logInfo.className = 'note error';
    }
    logTimer = setTimeout(loadLog, LOG_MS);
  }

  /* ---------- start ---------- */
  async function main() {
    U.setNav({
      items: PAGES.map(p => [p.file, p.key]),
      external: MON_MENU.map(([f, k]) => [U.MON_URL + f, k]).concat([[U.MON_URL + 'grafana/', 'mon.nav.grafana']]),
      home: 'index.html', status: U.MON_URL + 'uha-status.html'
    });
    await U.boot();
    try {
      const resp = await fetch('/api/commands', { cache: 'no-store' });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      commands = await resp.json();
    } catch (e) {
      app().appendChild(el('p', 'note error', U.t('ctrl.err.commands', { e: e.message })));
      return;
    }
    // the enum name of a command is not in /api/commands: take it from its state variable (texts.json var_enums)
    commands.forEach(c => { if (c.type === 'enum') c.enum_name = U.varEnum(c.state) || ''; });
    if (page.file === 'history.html') {
      buildHistory();
      loadLog();
      U.langChanged = () => { buildHistory(); loadLog(); };
      U.poll(() => {});
      return;
    }
    build();
    U.langChanged = () => { build(); update(); };
    let first = true;
    U.poll(() => {
      update();
      if (first && location.hash) { const t = document.getElementById(location.hash.slice(1)); if (t) t.scrollIntoView(); }
      first = false;
    });
  }
  main();
})();

/* UHA monitoring pages - shared helpers.
 * Loads i18n/texts.json once (all user-visible texts, from Martin's dictionary, see i18n/README.md), then
 * uha2.json (+ optionally uha_status.json) every 2 s and calls render(U). If the live file is missing (local PC),
 * falls back to sample/<file>.
 *
 * Texts:   U.t(key, {params})   UI text ("mon.*"), {x} placeholders filled from params
 *          U.vname(NAME)        full variable name ("Baterie – napětí")       - where the context is missing
 *          U.vshort(NAME)       short name ("Baterie", "Kuchyň")              - in a card that names the measure
 *          U.vmeasure(NAME)     the measure part of the full name ("Napětí")  - in a card that names the area
 * A missing key is shown as the key itself and listed once in the console.
 */
(function () {
  const U = (window.UHA = {});
  const INTERVAL_MS = 2000;
  const STALE_AGE_S = 10;      // variable older than this is shown as "old"
  const STALE_FEED_S = 15;     // uha2.json UnixTime did not change for this long

  // PV peak for the Home bargraph (SOLAR_POWER_W = house + workshop): house panels 5600 Wp but the MPPT gives at
  // most 4600 W; workshop 16 x 365 Wp = 5840 W (Martin, 2026-11-21)
  U.PV_HOUSE_MAX_W = 4600;
  U.PV_WORKSHOP_PEAK_W = 16 * 365;
  U.SOLAR_PEAK_W = U.PV_HOUSE_MAX_W + U.PV_WORKSHOP_PEAK_W;
  U.TEMP_COLD_C = 20;          // temperature colour scale (tank, pipes): blue at or below ...
  U.TEMP_HOT_C = 70;           // ... red at or above

  // [href, text key, sub-entry (schematic) of the page above]
  const NAV = [
    ['uha.html', 'mon.nav.home'],
    ['uha-energy.html', 'mon.nav.energy'], ['uha-energy-scheme.html', 'mon.nav.scheme_energy', true],
    ['uha-battery.html', 'mon.nav.battery'], ['uha-loads.html', 'mon.nav.loads'],
    ['uha-heat.html', 'mon.nav.heat'], ['uha-heat-scheme.html', 'mon.nav.scheme_heat', true],
    ['uha-climate.html', 'mon.nav.climate'], ['uha-recu-scheme.html', 'mon.nav.scheme_recu', true],
    ['uha-detail.html', 'mon.nav.detail'], ['uha-status.html', 'mon.nav.status']
  ];
  const EXTERNAL = [['/grafana/', 'mon.nav.grafana'], ['https://ctrl.uha.mkresta.cz/', 'mon.nav.control']];
  // menu of the current site: the control site (ctrl.uha.mkresta.cz) sets its own with U.setNav()
  let nav = { items: NAV, external: EXTERNAL, home: 'uha.html', status: 'uha-status.html' };
  U.setNav = o => { nav = Object.assign({}, nav, o); };

  /* Cross-links monitoring <-> control: control page of each section (one table). Without a client certificate
     the control site answers 400 - accepted, only family devices have one. */
  U.MON_URL = 'https://uha.mkresta.cz/';
  U.CTRL_URL = 'https://ctrl.uha.mkresta.cz/';
  U.CTRL_PAGES = { light: 'index.html', heating: 'heating.html', ventilation: 'heating.html',
    blind: 'other.html', inverter: 'other.html', loads: 'other.html' };
  U.ctrlHref = section => U.CTRL_URL + (U.CTRL_PAGES[section] || '') + '#' + section;

  /* Level 3 grouping (All data page): first matching rule wins. Same split as the level 2 pages. */
  U.GROUPS = [
    ['battery', n => /^BMS\d/.test(n)],
    ['heat', n => /^(EL_HEATER|HEAT_|BOILER|FLOW_|CONS_COLD|CONS_HOT|TEMP_BOILER|TEMP_TANK|TEMP_WALL|TEMP_RAD|TEMP_TECHM|TECHM_|ST_(PUMP|RAD|WALL|BOILER|EL_HEATER|EXHAUST|UP_REQ|DOWN_REQ))/.test(n)],
    ['energy', n => /^(SOLAR_|BAT_|LOAD_|CHARGING_A|CONS_TODAY_WH|MPPT_|SHUNT_|STRG|LLOAD|LPV|AXPERT_|ST_AC_|ST_AKUPACK)/.test(n)],
    ['loads', n => /^(CONS_|POW_|ST_(EVSE|WS_HEATING))/.test(n)],
    ['climate', n => /^(TEMP_|RH_|CO2|DP_|RECU_|METEO_|ST_RECU)/.test(n)],
    ['other', () => true]
  ];
  U.groupOf = name => U.GROUPS.find(g => g[1](name))[0];

  /* ---------- language and texts ---------- */
  let lang = 'cz';
  try { const l = localStorage.getItem('uha.lang'); if (l === 'cz' || l === 'en') lang = l; } catch (e) { /* no storage */ }
  let T = { ui: {}, vars: {}, cmds: {}, enums: {}, var_enums: {} };
  const missing = new Set();
  let missingTimer = null;

  function miss(key) {
    if (missing.has(key)) return;
    missing.add(key);
    clearTimeout(missingTimer);
    missingTimer = setTimeout(() => console.warn(`UHA: ${missing.size} text(s) missing in i18n/texts.json: ${[...missing].join(', ')}`), 2000);
  }
  const fill = (s, p) => p ? s.replace(/\{(\w+)\}/g, (m, k) => (p[k] !== undefined && p[k] !== null ? p[k] : m)) : s;

  U.lang = () => lang;
  U.locale = () => (lang === 'en' ? 'en-GB' : 'cs-CZ');
  U.missingTexts = () => [...missing];
  U.t = function (key, params) {
    const e = T.ui[key];
    if (!e) { miss(key); return fill(key, params); }
    return fill(e[lang] || e.cz || key, params);
  };
  function varEntry(name) {
    if (T.vars[name]) return [T.vars[name], null];
    const m = /^(.*_)(\d+)$/.exec(name);                      // BMS1_CELL_V_5 -> BMS1_CELL_V_{n}
    if (m && T.vars[m[1] + '{n}']) return [T.vars[m[1] + '{n}'], m[2]];
    return [null, null];
  }
  function vtext(name, field, n) {
    const [e, n2] = varEntry(name);
    if (!e) { miss(name); return name; }
    return fill(e[field] || e[lang] || name, { n: n !== undefined ? n : n2 });
  }
  U.vname = (name, n) => vtext(name, lang, n);
  U.vshort = (name, n) => vtext(name, lang + '_short', n);
  U.vmeasure = function (name, n) {
    const full = U.vname(name, n), i = full.lastIndexOf(' – ');
    const part = i < 0 ? full : full.slice(i + 3);
    return part.charAt(0).toUpperCase() + part.slice(1);
  };
  /* command name from the dictionary (sheet "Příkazy YAML"), fallback: the given text, then the command name */
  U.cname = function (name, fallback) {
    const e = T.cmds[name];
    if (!e) { miss(name); return fallback || name; }
    return e[lang] || fallback || name;
  };
  U.varEnum = name => T.var_enums[name] || null;        // enum name of an enum variable (from uha_vars.yaml)
  /* enum item by enum name and number (e.g. the BlindCmd buttons); null when the dictionary has none */
  U.enumItem = (en, value) => { const e = T.enums[en] && T.enums[en][String(value)]; return e ? { name: e.name, text: e[lang] } : null; };
  /* text of an enum variable in the current language (the YAML item name when the dictionary has none) */
  U.enumText = function (name) {
    const v = vars[name];
    if (!v || v.value === null || v.value === undefined) return null;
    const en = T.var_enums[name], item = en && T.enums[en] && T.enums[en][String(v.value)];
    return item ? item[lang] : (v.enum_name || String(v.value));
  };
  U.setLang = function (l) {
    lang = l;
    try { localStorage.setItem('uha.lang', l); } catch (e) { /* no storage */ }
    buildFrame();
    if (U.langChanged) U.langChanged();
    if (U.refresh) U.refresh();
  };

  async function loadTexts() {
    try {
      const r = await fetch('i18n/texts.json', { cache: 'no-cache' });
      if (!r.ok) throw new Error(r.status);
      T = Object.assign(T, await r.json());
    } catch (e) {
      console.warn('UHA: i18n/texts.json not loaded, keys are shown instead of texts', e);
    }
  }

  /* ---------- data access ---------- */
  let vars = {}, status = null, uha = null, usingSample = false, lastUnix = null, lastChange = Date.now();

  U.get = n => vars[n];
  U.num = n => { const v = vars[n]; return v && v.valid && typeof v.value === 'number' ? v.value : null; };
  U.bool = n => { const v = vars[n]; return v && v.valid && v.value !== null && v.value !== undefined ? Boolean(v.value) : null; };
  U.status = () => status;
  U.vars = () => vars;
  U.isSample = () => usingSample;

  U.fmtNum = (x, d) => x.toLocaleString(U.locale(), { minimumFractionDigits: d, maximumFractionDigits: d });
  const defDecimals = unit => (unit === 'kWh' ? 2 : (['W', 'ppm', '%', 'Pa', 'l', 'mV'].includes(unit) ? 0 : 1));
  U.format = function (x, unit, d) {
    if (x === null || x === undefined || Number.isNaN(x)) return '–';
    if (d === undefined) d = defDecimals(unit);
    return U.fmtNum(x, d) + (unit ? ' ' + unit : '');
  };

  /* {text, num, unit} for a variable; Wh -> kWh unless o.kwh === false; invalid -> null unless o.force */
  U.parts = function (n, o) {
    o = o || {};
    const v = vars[n];
    if (!v || v.value === null || v.value === undefined) return null;
    if (v.valid === false && !o.force) return null;
    if (typeof v.value === 'boolean') { const s = U.t(v.value ? 'mon.val.yes' : 'mon.val.no'); return { text: s, num: s, unit: '' }; }
    if (v.enum_name !== undefined || T.var_enums[n]) { const s = U.enumText(n); return { text: s, num: s, unit: '' }; }
    let x = v.value, unit = o.unit !== undefined ? o.unit : v.unit;
    if (unit === 'Wh' && o.kwh !== false) { x /= 1000; unit = 'kWh'; }
    const num = U.fmtNum(x, o.d === undefined ? defDecimals(unit) : o.d);
    return { text: num + (unit ? ' ' + unit : ''), num, unit };
  };
  U.show = (n, o) => { const p = U.parts(n, o); return p ? p.text : '–'; };

  U.ageClass = function (n) {
    const v = vars[n];
    if (!v || v.value === null || v.valid === false) return 'bad';
    if (v.on_change) return '';   // states (send: on_change) come only on change + every 20 s; valid covers the timeout
    return v.age_s !== null && v.age_s > STALE_AGE_S ? 'old' : '';
  };

  /* ---------- html helpers ---------- */
  U.esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  U.tile = function (label, name, o) {
    o = o || {};
    const p = typeof name === 'string' ? U.parts(name, o) : name;      // name may be a prepared {num, unit}
    const cls = typeof name === 'string' ? U.ageClass(name) : (p ? '' : 'bad');
    const num = p ? p.num : '–';
    const unit = p && p.unit ? `<span class="unit">${p.unit}</span>` : '';
    return `<div class="tile ${o.cls || ''} ${cls}"><div class="lbl">${label}</div>` +
      `<div class="num${o.big ? ' big' : ''}${/^[\d\s.,\-–  ]+$/.test(num) ? '' : ' txt'}">${num}${unit}</div>${o.sub ? `<div class="sub">${o.sub}</div>` : ''}</div>`;
  };
  U.row = function (label, name, o) {
    return `<div class="row ${typeof name === 'string' ? U.ageClass(name) : ''}"><span class="l">${label}</span><span class="v">${typeof name === 'string' ? U.show(name, o) : name}</span></div>`;
  };
  /* row labelled with the measure part of the variable name (inside a card that names the area) */
  U.mrow = (name, o) => U.row(U.vmeasure(name), name, o);
  U.rowText = (label, text, cls) => `<div class="row ${cls || ''}"><span class="l">${label}</span><span class="v">${text}</span></div>`;
  /* value computed from several variables: fn(values) or null if one of them is missing / invalid */
  U.calc = (names, fn) => { const v = names.map(U.num); return v.some(x => x === null) ? null : fn(...v); };
  U.calcClass = names => { const c = names.map(U.ageClass); return c.includes('bad') ? 'bad' : c.includes('old') ? 'old' : ''; };
  /* row with a computed value; unit 'Wh' is shown as kWh */
  U.calcRow = function (label, names, fn, unit) {
    let x = U.calc(names, fn);
    if (unit === 'Wh') { unit = 'kWh'; if (x !== null) x /= 1000; }
    return U.rowText(label, U.format(x, unit), U.calcClass(names));
  };
  U.card = function (title, body, o) {
    o = o || {};
    const ctrl = o.ctrl && !o.href ? `<a class="ctrllink" href="${U.ctrlHref(o.ctrl)}">${U.t('mon.ctrl.link')}</a>` : '';
    const head = `<h2><span>${title}</span>${o.href ? '<span class="chev">›</span>' : ctrl}</h2>`;
    return o.href
      ? `<a class="card link ${o.cls || ''}" href="${o.href}">${head}${body}</a>`
      : `<section class="card ${o.cls || ''}">${head}${body}</section>`;
  };
  /* page title + subtitle (+ links on the right, e.g. [['uha-heat-scheme.html', U.t('mon.scheme.link')]]) */
  U.pageHead = function (title, sub, links) {
    const l = (links || []).map(([href, text]) => `<a class="plink" href="${href}">${text}</a>`).join('');
    return `<div class="phead"><div><h1 class="pagetitle">${title}</h1>${sub ? `<p class="pagesub">${sub}</p>` : ''}</div>${l ? `<div class="plinks">${l}</div>` : ''}</div>`;
  };
  U.bar = function (frac, cls) {
    if (frac === null || frac === undefined || Number.isNaN(frac)) frac = 0;
    const f = Math.max(0, Math.min(1, frac));
    return `<div class="bar"><div class="fill ${cls || ''}" style="width:${(f * 100).toFixed(1)}%"></div></div>`;
  };
  U.loadBar = function (w, rating) {           // load colour; amber above 70 %, red above 90 % of the rating
    if (w === null) return U.bar(0);
    const f = w / rating;
    return U.bar(f, f > 0.9 ? 'bad' : f > 0.7 ? 'warn' : 'load');
  };
  U.socClass = soc => (soc === null ? '' : soc < 20 ? 'bad' : soc < 40 ? 'warn' : 'bat');
  U.socBar = soc => U.bar(soc === null ? 0 : soc / 100, U.socClass(soc));

  /* temperature colour: blue (TEMP_COLD_C) -> violet -> red (TEMP_HOT_C), no green */
  const STOPS = [[59, 111, 217], [163, 79, 196], [224, 53, 43]];
  U.tempColor = function (t) {
    if (t === null || t === undefined) return '#56606b';
    const f = Math.max(0, Math.min(1, (t - U.TEMP_COLD_C) / (U.TEMP_HOT_C - U.TEMP_COLD_C))) * (STOPS.length - 1);
    const i = Math.min(STOPS.length - 2, Math.floor(f)), k = f - i;
    const c = STOPS[i].map((a, j) => Math.round(a + (STOPS[i + 1][j] - a) * k));
    return `rgb(${c.join(',')})`;
  };
  /* Accumulation tank as SVG elements at x, y (w x h): rounded body, levels 6 (top) ... 1 (bottom) evenly spaced,
     the temperature written on each level, filled with a vertical gradient between the level colours. */
  let tankSeq = 0;
  U.tankGroup = function (x, y, w, h, o) {
    o = o || {};
    const id = 'tankg' + (++tankSeq), n = 6, pad = h * 0.06, step = (h - 2 * pad) / (n - 1);
    const lv = [];
    for (let i = n; i >= 1; i--) lv.push({ i, t: U.num(`TEMP_TANK_${i}_C`), cls: U.ageClass(`TEMP_TANK_${i}_C`), yy: y + pad + (n - i) * step });
    const stops = lv.filter(l => l.t !== null).map(l => `<stop offset="${((l.yy - y) / h).toFixed(3)}" stop-color="${U.tempColor(l.t)}"/>`).join('');
    const fs = o.fs || 15;
    const texts = lv.map(l => `<text class="lbl" x="${x + 8}" y="${(l.yy + fs * 0.35).toFixed(1)}" style="font-size:${fs * 0.8}px">${l.i}</text>` +
      `<text x="${x + w - 8}" y="${(l.yy + fs * 0.35).toFixed(1)}" text-anchor="end" style="font-size:${fs}px"${l.cls === 'bad' ? ' opacity=".6"' : ''}>` +
      `${l.t === null ? '–' : U.fmtNum(l.t, 1) + ' °C'}</text>`).join('');
    const ticks = lv.map(l => `<line x1="${x}" x2="${x + 5}" y1="${l.yy}" y2="${l.yy}" stroke="rgba(255,255,255,.5)"/>`).join('');
    return `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">${stops || '<stop offset="0" stop-color="#56606b"/>'}</linearGradient></defs>` +
      `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${Math.min(w / 2, 26)}" fill="url(#${id})"/>` +
      `<rect class="outline" x="${x}" y="${y}" width="${w}" height="${h}" rx="${Math.min(w / 2, 26)}" fill="none" stroke="#8b9aab" stroke-width="2"/>` +
      ticks + texts;
  };
  U.tankSvg = (w, h) => `<svg class="tanksvg" viewBox="0 0 ${w} ${h}" role="img" aria-label="${U.t('mon.heat.tank')}">${U.tankGroup(1, 1, w - 2, h - 2)}</svg>`;

  U.sum = names => names.reduce((a, n) => { const x = U.num(n); return x === null ? a : (a === null ? x : a + x); }, null);
  U.fmtDuration = function (s) {
    if (s === null || s === undefined) return '–';
    const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    return (d ? d + ' d ' : '') + h + ' h ' + m + ' min';
  };
  U.clock = unix => (unix ? new Date(unix * 1000).toLocaleTimeString(U.locale()) : '–');

  /* ---------- page frame: top bar + hamburger menu ---------- */
  const page = () => location.pathname.split('/').pop() || nav.home;

  function buildFrame() {
    const active = page();
    const navItem = ([href, key, sub]) =>
      `<a href="${href}" class="${sub ? 'sub' : ''}${href === active ? ' active' : ''}">${U.t(key)}</a>`;
    const menu = nav.items.map(navItem).join('') + '<hr>' + nav.external.map(navItem).join('') +
      `<div class="langsw"><span>${U.t('mon.nav.lang')}</span>` +
      ['cz', 'en'].map(l => `<button data-lang="${l}" class="${l === lang ? 'on' : ''}">${l.toUpperCase()}</button>`).join('') + '</div>';
    const html =
      `<header class="top"><a class="brand" href="${nav.home}">UHA</a><span class="spacer"></span>` +
      `<a class="stlink${active === nav.status ? ' active' : ''}" href="${nav.status}">${U.t('mon.nav.status')}</a>` +
      `<div class="feed" id="feed"><span class="dot"></span><span id="feedtxt">${U.t('mon.feed.connecting')}</span></div>` +
      `<button class="burger" id="burger" aria-label="${U.t('mon.nav.menu')}" aria-expanded="false">☰</button></header>` +
      `<div class="menu" id="menu" hidden><div class="scrim" id="scrim"></div><nav class="drawer">${menu}</nav></div>` +
      `<div id="sample" class="banner" hidden>${U.t('mon.sample.banner')}</div>`;
    const old = document.getElementById('frame');
    if (old) old.innerHTML = html;
    else document.body.insertAdjacentHTML('afterbegin', `<div id="frame">${html}</div><main id="app"></main>`);
    document.documentElement.lang = lang === 'en' ? 'en' : 'cs';
    const item = nav.items.find(n => n[0] === active);
    document.title = 'UHA – ' + (item ? U.t(item[1]) : '');

    const menuEl = document.getElementById('menu'), burger = document.getElementById('burger');
    const open = on => { menuEl.hidden = !on; burger.setAttribute('aria-expanded', on); };
    burger.onclick = () => open(menuEl.hidden);
    document.getElementById('scrim').onclick = () => open(false);
    menuEl.querySelectorAll('button[data-lang]').forEach(b => { b.onclick = () => { open(false); U.setLang(b.dataset.lang); }; });
    setFeed();
  }
  document.addEventListener('keydown', e => {
    const m = document.getElementById('menu');
    if (e.key === 'Escape' && m && !m.hidden) { m.hidden = true; document.getElementById('burger').setAttribute('aria-expanded', false); }
  });

  function setFeed() {
    const el = document.getElementById('feed'), txt = document.getElementById('feedtxt');
    if (!el) return;
    const age = (Date.now() - lastChange) / 1000;
    const bad = !uha || (!usingSample && age > STALE_FEED_S);
    el.className = 'feed ' + (!uha ? 'bad' : usingSample ? 'warn' : bad ? 'bad' : 'ok');
    txt.textContent = !uha ? U.t('mon.feed.nodata') : usingSample ? U.t('mon.feed.sample')
      : bad ? U.t('mon.feed.stale', { n: Math.round(age) }) : U.clock(uha.UnixTime);
    document.getElementById('sample').hidden = !usingSample;
  }

  async function getJson(file) {
    try {
      const r = await fetch(file + '?t=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) throw new Error(r.status);
      return [await r.json(), false];
    } catch (e) {
      const r = await fetch('sample/' + file, { cache: 'no-store' });
      if (!r.ok) throw e;
      return [await r.json(), true];
    }
  }

  /* texts + page frame (top bar, menu); the control site uses this with U.poll() and keeps its own DOM */
  U.boot = async function () {
    await loadTexts();
    buildFrame();
  };

  /* load uha2.json (+ uha_status.json with opts.status) every 2 s and call onData(U); also U.refresh() */
  U.poll = function (onData, opts) {
    opts = opts || {};
    async function tick() {
      try {
        const [u, s] = await Promise.all([getJson('uha2.json'), opts.status ? getJson('uha_status.json') : [null, false]]);
        uha = u[0]; usingSample = u[1]; vars = uha.Vars || {}; status = s[0];
        if (uha.UnixTime !== lastUnix) { lastUnix = uha.UnixTime; lastChange = Date.now(); }
      } catch (e) {
        if (opts.onError && !uha) opts.onError(e);
        setFeed();
        return;
      }
      try { onData(U); } catch (e) { console.error('UHA: render failed', e); }
      setFeed();
    }
    U.refresh = tick;
    tick();
    setInterval(tick, opts.intervalMs || INTERVAL_MS);
    setInterval(setFeed, 1000);
  };

  /* monitoring pages: render(U) returns html for #app (rebuilt every tick); opts.status loads uha_status.json too;
     opts.after(U) runs after each render */
  U.start = async function (render, opts) {
    opts = opts || {};
    await U.boot();
    const app = document.getElementById('app');
    U.poll(() => {
      app.innerHTML = render(U);
      if (opts.after) opts.after(U);
    }, {
      status: opts.status,
      onError: () => { app.innerHTML = `<div class="card"><h2>${U.t('mon.err.nodata')}</h2><p>${U.t('mon.err.load')}</p></div>`; }
    });
  };
})();

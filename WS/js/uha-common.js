/* UHA dashboard - shared helpers.
 * Loads uha2.json (+ optionally uha_status.json) every 2 s and calls render().
 * If the live file is missing (e.g. local PC), falls back to sample/<file>.
 */
(function () {
  const U = (window.UHA = {});
  const INTERVAL_MS = 2000;
  const STALE_AGE_S = 10;      // variable older than this is shown as "old"
  const STALE_FEED_S = 15;     // uha2.json UnixTime did not change for this long

  const NAV = [
    ['uha.html', 'Home'], ['uha-energy.html', 'Energy'], ['uha-battery.html', 'Battery'],
    ['uha-loads.html', 'Loads'], ['uha-heat.html', 'Heat'], ['uha-climate.html', 'Climate'],
    ['uha-detail.html', 'All data'], ['uha-status.html', 'Status']
  ];

  /* Level 3 grouping: first matching rule wins. Same split as the level 2 pages. */
  U.GROUPS = [
    ['battery', 'Battery (BMS)', n => /^BMS\d/.test(n)],
    ['heat', 'Heat & water', n => /^(EL_HEATER|HEAT_|BOILER|FLOW_|CONS_COLD|CONS_HOT|TEMP_BOILER|TEMP_TANK|TEMP_WALL|TEMP_RAD|TEMP_TECHM)/.test(n)],
    ['energy', 'Energy', n => /^(SOLAR_|BAT_|LOAD_|CHARGING_A|CONS_TODAY_WH|MPPT_|SHUNT_|STRG|LLOAD|LPV|AXPERT_)/.test(n)],
    ['loads', 'Loads & inverters', n => /^(CONS_|POW_)/.test(n)],
    ['climate', 'Climate', n => /^(TEMP_|RH_|CO2|DP_|RECU_|METEO_)/.test(n)],
    ['other', 'Other', () => true]
  ];
  U.groupOf = name => U.GROUPS.find(g => g[2](name))[0];

  const ACRONYMS = new Set(['SOC', 'MPPT', 'PV', 'AC', 'DC', 'EVSE', 'RECU', 'TECHM', 'CO2', 'RH', 'DP', 'STRG', 'LLOAD',
    'LPV', 'EL', 'WS', 'IOBOARD', 'ELECON', 'AKUPACK1', 'AC300', 'AC3KW', 'AC5KW', 'PVS1', 'PVS2', 'PCK1', 'PCK2', 'FC', 'FH', 'WH', 'WC']);
  U.label = function (name) {
    const w = name.replace(/_(WH|W|A|V|C|L|LPM)$/, '').split('_').map((t, i) => {
      if (ACRONYMS.has(t) || /^(BMS|STRG|LLOAD|LPV)\d$/.test(t) || /^\d+$/.test(t)) return t;
      t = t.toLowerCase();
      return i === 0 ? t[0].toUpperCase() + t.slice(1) : t;
    });
    return w.join(' ');
  };

  /* ---------- data access ---------- */
  let vars = {}, status = null, uha = null, usingSample = false, lastUnix = null, lastChange = Date.now();

  U.get = n => vars[n];
  U.num = n => { const v = vars[n]; return v && v.valid && typeof v.value === 'number' ? v.value : null; };
  U.status = () => status;
  U.vars = () => vars;
  U.isSample = () => usingSample;

  U.format = function (x, unit, d) {
    if (x === null || x === undefined || Number.isNaN(x)) return '–';
    if (d === undefined) d = (unit === 'kWh' || unit === 'V' && Math.abs(x) < 10) ? 2 : (['W', 'ppm', '%', 'Pa'].includes(unit) ? 0 : 1);
    return x.toLocaleString('en', { minimumFractionDigits: d, maximumFractionDigits: d }) + (unit ? ' ' + unit : '');
  };

  /* {text, num, unit} for a variable; Wh -> kWh unless o.kwh === false; invalid -> null unless o.force */
  U.parts = function (n, o) {
    o = o || {};
    const v = vars[n];
    if (!v || v.value === null || v.value === undefined) return null;
    if (v.valid === false && !o.force) return null;
    if (typeof v.value === 'boolean') return { text: v.value ? 'yes' : 'no', num: '', unit: '' };
    if (v.enum_name) return { text: v.enum_name, num: v.enum_name, unit: '' };
    let x = v.value, unit = o.unit !== undefined ? o.unit : v.unit;
    if (unit === 'Wh' && o.kwh !== false) { x /= 1000; unit = 'kWh'; }
    const d = o.d === undefined ? (unit === 'kWh' ? 2 : (['W', 'ppm', '%', 'Pa'].includes(unit) ? 0 : 1)) : o.d;
    const num = x.toLocaleString('en', { minimumFractionDigits: d, maximumFractionDigits: d });
    return { text: num + (unit ? ' ' + unit : ''), num, unit };
  };
  U.show = (n, o) => { const p = U.parts(n, o); return p ? p.text : '–'; };

  U.ageClass = function (n) {
    const v = vars[n];
    if (!v || v.value === null || v.valid === false) return 'bad';
    return v.age_s !== null && v.age_s > STALE_AGE_S ? 'old' : '';
  };

  /* ---------- html helpers ---------- */
  U.tile = function (label, name, o) {
    o = o || {};
    const p = typeof name === 'string' ? U.parts(name, o) : name;      // name may be a prepared {num, unit}
    const cls = typeof name === 'string' ? U.ageClass(name) : '';
    const num = p ? p.num : '–';
    const unit = p && p.unit ? `<span class="unit">${p.unit}</span>` : '';
    return `<div class="tile ${o.cls || ''} ${cls}"><div class="lbl">${label}</div>` +
      `<div class="num${o.big ? ' big' : ''}${/^[\d.,\-–]+$/.test(num) ? '' : ' txt'}">${num}${unit}</div>${o.sub ? `<div class="sub">${o.sub}</div>` : ''}</div>`;
  };
  U.row = function (label, name, o) {
    return `<div class="row ${typeof name === 'string' ? U.ageClass(name) : ''}"><span class="l">${label}</span><span class="v">${typeof name === 'string' ? U.show(name, o) : name}</span></div>`;
  };
  U.rowText = (label, text, cls) => `<div class="row ${cls || ''}"><span class="l">${label}</span><span class="v">${text}</span></div>`;
  U.card = function (title, body, o) {
    o = o || {};
    const head = `<h2>${title}${o.href ? '<span class="chev">›</span>' : ''}</h2>`;
    return o.href
      ? `<a class="card link ${o.cls || ''}" href="${o.href}">${head}${body}</a>`
      : `<section class="card ${o.cls || ''}">${head}${body}</section>`;
  };
  U.bar = function (frac, cls) {
    if (frac === null || frac === undefined || Number.isNaN(frac)) frac = 0;
    const f = Math.max(0, Math.min(1, frac));
    return `<div class="bar"><div class="fill ${cls || ''}" style="width:${(f * 100).toFixed(1)}%"></div></div>`;
  };
  U.loadBar = function (w, rating) {           // green < 70 %, amber < 90 %, red above
    if (w === null) return U.bar(0);
    const f = w / rating;
    return U.bar(f, f > 0.9 ? 'bad' : f > 0.7 ? 'warn' : 'ok');
  };
  U.socBar = soc => U.bar(soc === null ? 0 : soc / 100, soc === null ? '' : soc < 20 ? 'bad' : soc < 40 ? 'warn' : 'ok');
  U.tempColor = function (t) {                  // 15 C blue ... 65 C red
    const h = 210 - Math.max(0, Math.min(1, (t - 15) / 50)) * 195;   // blue -> orange, no green
    return `hsl(${h.toFixed(0)},65%,48%)`;
  };
  U.sum = names => names.reduce((a, n) => { const x = U.num(n); return x === null ? a : (a === null ? x : a + x); }, null);
  U.fmtDuration = function (s) {
    if (s === null || s === undefined) return '–';
    const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    return (d ? d + 'd ' : '') + h + 'h ' + m + 'm';
  };
  U.clock = unix => unix ? new Date(unix * 1000).toLocaleTimeString('en-GB') : '–';

  /* ---------- page frame ---------- */
  function buildFrame(active) {
    const nav = NAV.map(([href, t]) => `<a href="${href}"${href === active ? ' class="active"' : ''}>${t}</a>`).join('');
    document.body.insertAdjacentHTML('afterbegin',
      `<header class="top"><div class="brand">UHA</div><nav>${nav}</nav>` +
      `<div class="feed" id="feed"><span class="dot"></span><span id="feedtxt">connecting…</span></div></header>` +
      `<div id="sample" class="banner" hidden>Sample data (live uha2.json not found) – values are static.</div>` +
      `<main id="app"></main>`);
  }

  function setFeed() {
    const el = document.getElementById('feed'), txt = document.getElementById('feedtxt');
    if (!el) return;
    const age = (Date.now() - lastChange) / 1000;
    const bad = !uha || (!usingSample && age > STALE_FEED_S);
    el.className = 'feed ' + (!uha ? 'bad' : usingSample ? 'warn' : bad ? 'bad' : 'ok');
    txt.textContent = !uha ? 'no data' : usingSample ? 'sample' : bad ? `no new data for ${Math.round(age)} s` : U.clock(uha.UnixTime);
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

  /* render(U) returns html for #app; opts.status loads uha_status.json too; opts.after(U) runs after each render */
  U.start = function (render, opts) {
    opts = opts || {};
    buildFrame(location.pathname.split('/').pop() || 'uha.html');
    const app = document.getElementById('app');
    async function tick() {
      try {
        const [u, s] = await Promise.all([getJson('uha2.json'), opts.status ? getJson('uha_status.json') : [null, false]]);
        uha = u[0]; usingSample = u[1]; vars = uha.Vars || {}; status = s[0];
        if (uha.UnixTime !== lastUnix) { lastUnix = uha.UnixTime; lastChange = Date.now(); }
        app.innerHTML = render(U);
        if (opts.after) opts.after(U);
      } catch (e) {
        if (!uha) app.innerHTML = '<div class="card"><h2>No data</h2><p>Could not load uha2.json. ' +
          'When testing locally, serve the folder over http (<code>python -m http.server</code>); file:// cannot fetch.</p></div>';
      }
      setFeed();
    }
    U.refresh = tick;
    tick();
    setInterval(tick, INTERVAL_MS);
    setInterval(setFeed, 1000);
  };
})();

// UHA control page (https://ctrl.uha.mkresta.cz, client certificate required).
// Commands from /api/commands (UhaGatePy, from uha_vars.yaml), states from /uha2.json (polled every 3 s).
// A command is a request: success = the state variable of the target node changed (CMD_spec.md, "Principles").
// Everything is generic from the YAML: rows grouped by `category:`, the widget chosen by type (see kind()).
"use strict";

const POLL_MS = 3000;
const POLL_PENDING_MS = 1000;     // faster while waiting for a state change
const WAIT_MS = 10000;            // no change within this time -> "stav se nezměnil"
const STALE_S = 15;               // uha2.json older than this: the gateway does not write it
const LOG_MS = 15000;             // command log refresh (and right after a sent command)
const LOG_ROWS = 30;

// Section order and titles of the YAML key `category:`; commands without a (known) category -> "Ostatní".
const CATEGORIES = [["light", "Světla"], ["blind", "Žaluzie"], ["heating", "Topení"], ["inverter", "Střídače"],
                    ["ventilation", "Rekuperace"]];
const OTHER = "Ostatní";

let commands = [];                // from /api/commands
let vars = {};                    // uha2.json "Vars"
const pending = {};               // command name -> {expected, deadline}
const rows = {};                  // command name -> {state, msg, buttons, enumButtons, input, inputFilled}

// Widget by type: "light" (uint32/int32 in % 0..100: on/off buttons), "bool" (on/off), "enum" (one button per
// item, the current one highlighted), "number" (float and other integers: input + "Nastavit").
function kind(c) {
  if ((c.type === "uint32" || c.type === "int32") && c.unit === "%" && c.min === 0 && c.max === 100) return "light";
  if (c.type === "bool") return "bool";
  if (c.type === "enum" && c.enum) return "enum";
  return "number";
}

function fmt(c, x) {
  if (c.type !== "float") return String(x);
  let decimals = 2;
  if (c.step) decimals = c.step >= 1 ? 0 : Math.min(3, (String(c.step).split(".")[1] || "").length);
  return Number(x).toLocaleString("cs-CZ", { maximumFractionDigits: decimals });
}

function known(v) {
  return v && v.valid && v.value !== null && v.value !== undefined;
}

function stateText(c, v) {
  if (!known(v)) return { text: "neznámý", cls: "unknown" };
  switch (kind(c)) {
    case "light": return v.value > 0 ? { text: "zapnuto" + (v.value < 100 ? " " + v.value + " %" : ""), cls: "on" }
                                     : { text: "vypnuto", cls: "" };
    case "bool": {
      // the state may be an enum (inverters: InverterState, every item except 0 = Off means running): show the item
      const detail = v.enum_name && !/^(on|off)$/i.test(v.enum_name) ? " (" + v.enum_name + ")" : "";
      return v.value ? { text: "zapnuto" + detail, cls: "on" } : { text: "vypnuto" + detail, cls: "" };
    }
    case "enum": return { text: v.enum_name || c.enum[String(v.value)] || String(v.value), cls: "" };
    default: return { text: fmt(c, v.value) + (c.unit ? " " + c.unit : ""), cls: "" };
  }
}

// What the state should become: the node clamps a number to min..max (CMD_spec.md "Principles").
function expectedState(c, value) {
  return kind(c) === "number" ? Math.min(c.max, Math.max(c.min, value)) : value;
}

function reached(c, v, expected) {
  if (!known(v)) return false;
  switch (kind(c)) {
    case "light": return expected > 0 ? v.value > 0 : v.value === 0;
    case "bool": return Boolean(v.value) === Boolean(expected);
    case "number": return Math.abs(v.value - expected) <= Math.max(1e-6, Math.abs(expected) * 1e-5);  // float32
    default: return v.value === expected;
  }
}

function setMsg(name, text, cls) {
  const m = rows[name].msg;
  m.textContent = text;
  m.className = "msg" + (cls ? " " + cls : "");
}

function button(label, value, c, cls) {
  const b = document.createElement("button");
  b.textContent = label;
  if (cls) b.className = cls;
  b.addEventListener("click", () => send(c, value));
  return b;
}

function numberInput(c, actions, buttons) {
  const input = document.createElement("input");
  input.type = "number";
  input.min = c.min;
  input.max = c.max;
  input.step = c.step || (c.type === "float" ? "any" : 1);
  input.title = "rozsah " + fmt(c, c.min) + " až " + fmt(c, c.max) + (c.unit ? " " + c.unit : "");
  const b = document.createElement("button");
  b.textContent = "Nastavit";
  const go = () => {
    const x = input.value.trim() === "" ? NaN : Number(input.value);
    if (!Number.isFinite(x)) { setMsg(c.name, "zadejte číslo", "error"); return; }
    send(c, x);
  };
  b.addEventListener("click", go);
  input.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  actions.appendChild(input);
  if (c.unit) {
    const u = document.createElement("span");
    u.className = "unit";
    u.textContent = c.unit;
    actions.appendChild(u);
  }
  buttons.push(b);
  return input;
}

function buildRow(c) {
  const tr = document.createElement("tr");
  const name = document.createElement("td");
  name.textContent = c.desc || c.name;
  name.title = c.name + " → " + c.target;
  const state = document.createElement("td");
  state.className = "state";
  const msg = document.createElement("td");
  msg.className = "msg";
  const actions = document.createElement("td");
  actions.className = "actions";
  const buttons = [];
  const enumButtons = {};
  let input = null;
  switch (kind(c)) {
    case "light":
      buttons.push(button("Zapnout", 100, c, "on"), button("Vypnout", 0, c));
      break;
    case "bool":
      buttons.push(button("Zapnout", 1, c, "on"), button("Vypnout", 0, c));
      break;
    case "enum":
      for (const [num, label] of Object.entries(c.enum)) {
        const b = button(label, Number(num), c);
        enumButtons[num] = b;
        buttons.push(b);
      }
      break;
    default:
      input = numberInput(c, actions, buttons);
  }
  buttons.forEach(b => actions.appendChild(b));
  tr.append(name, state, msg, actions);
  rows[c.name] = { state, msg, buttons, enumButtons, input, inputFilled: false };
  return tr;
}

function buildTable() {
  const root = document.getElementById("groups");
  root.textContent = "";
  const titles = new Map(CATEGORIES);
  const groups = new Map(CATEGORIES.map(([key]) => [key, []]));
  groups.set("", []);
  for (const c of commands) groups.get(titles.has(c.category) ? c.category : "").push(c);
  for (const [key, list] of groups) {
    if (!list.length) continue;
    const h = document.createElement("h2");
    h.textContent = titles.get(key) || OTHER;
    const table = document.createElement("table");
    table.className = "commands";
    table.innerHTML = "<thead><tr><th>Funkce</th><th>Stav</th><th></th><th></th></tr></thead>";
    const body = document.createElement("tbody");
    list.forEach(c => body.appendChild(buildRow(c)));
    table.appendChild(body);
    root.append(h, table);
  }
  render();
}

function render() {
  for (const c of commands) {
    const r = rows[c.name];
    const v = vars[c.state];
    const s = stateText(c, v);
    r.state.innerHTML = "";
    const badge = document.createElement("span");
    badge.className = "badge" + (s.cls ? " " + s.cls : "");
    badge.textContent = s.text;
    r.state.appendChild(badge);
    for (const [num, b] of Object.entries(r.enumButtons)) {
      b.classList.toggle("current", known(v) && v.value === Number(num));
    }
    if (r.input && known(v) && !r.inputFilled && document.activeElement !== r.input) {
      r.input.value = v.value;           // start from the current setpoint (once, never while the user types)
      r.inputFilled = true;
    }

    const p = pending[c.name];
    if (p) {
      if (reached(c, v, p.expected)) {
        delete pending[c.name];
        setMsg(c.name, "hotovo", "ok");
      } else if (Date.now() > p.deadline) {
        delete pending[c.name];
        setMsg(c.name, "stav se nezměnil", "error");
      }
    }
  }
}

async function send(c, value) {
  const r = rows[c.name];
  r.buttons.forEach(b => (b.disabled = true));
  setMsg(c.name, "odesílám…");
  try {
    const resp = await fetch("/api/cmd", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cmd: c.name, value: value }),
    });
    let answer = {};
    try { answer = await resp.json(); } catch (e) { /* not JSON (e.g. an nginx error page) */ }
    if (resp.ok && answer.ok) {
      pending[c.name] = { expected: expectedState(c, value), deadline: Date.now() + WAIT_MS };
      setMsg(c.name, "čekám na změnu…");
      schedulePoll(POLL_PENDING_MS);
      scheduleLog(1500);            // the gateway writes the row to the DB within a moment
    } else if (resp.status === 429) {
      setMsg(c.name, "příliš mnoho příkazů, chvíli počkejte", "error");
    } else if (resp.status === 503) {
      setMsg(c.name, "brána nemá spojení s ELECONem (" + (answer.error || "503") + ")", "error");
    } else {
      setMsg(c.name, "chyba " + resp.status + (answer.error ? ": " + answer.error : ""), "error");
    }
  } catch (e) {
    setMsg(c.name, "nelze odeslat: " + e.message, "error");
  } finally {
    r.buttons.forEach(b => (b.disabled = false));
  }
}

let pollTimer = null;
function schedulePoll(ms) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(poll, ms);
}

async function poll() {
  const info = document.getElementById("data-state");
  try {
    const resp = await fetch("/uha2.json", { cache: "no-store" });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    vars = data.Vars || {};
    const age = Date.now() / 1000 - data.UnixTime;
    if (age > STALE_S) {
      info.textContent = "Pozor: data jsou " + Math.round(age) + " s stará (brána nezapisuje).";
      info.className = "note error";
    } else {
      info.textContent = "Stav k " + new Date(data.UnixTime * 1000).toLocaleTimeString("cs-CZ");
      info.className = "note";
    }
    render();
  } catch (e) {
    info.textContent = "Nelze načíst stav: " + e.message;
    info.className = "note error";
  }
  schedulePoll(Object.keys(pending).length ? POLL_PENDING_MS : POLL_MS);
}

function commandText(row) {
  const c = commands.find(x => x.name === row.cmd);
  if (!c) return String(row.value);
  switch (kind(c)) {
    case "light": return row.value > 0 ? "zapnout" + (row.value < 100 ? " " + row.value + " %" : "") : "vypnout";
    case "bool": return row.value ? "zapnout" : "vypnout";
    case "enum": if (c.enum[String(row.value)] !== undefined) return c.enum[String(row.value)]; break;
  }
  return fmt(c, row.value) + (c.unit ? " " + c.unit : "");
}

function cell(text, cls) {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}

let logTimer = null;
function scheduleLog(ms) {
  clearTimeout(logTimer);
  logTimer = setTimeout(loadLog, ms);
}

async function loadLog() {
  const info = document.getElementById("log-state");
  try {
    const resp = await fetch("/api/log?limit=" + LOG_ROWS, { cache: "no-store" });
    let rowsData = null;
    try { rowsData = await resp.json(); } catch (e) { /* not JSON */ }
    if (!resp.ok) throw new Error((rowsData && rowsData.error) || "HTTP " + resp.status);
    const body = document.querySelector("#log tbody");
    body.textContent = "";
    const today = new Date().toDateString();
    for (const r of rowsData) {
      const t = new Date(r.ts * 1000);
      const when = (t.toDateString() === today ? "" : t.toLocaleDateString("cs-CZ") + " ") + t.toLocaleTimeString("cs-CZ");
      const c = commands.find(x => x.name === r.cmd);
      const tr = document.createElement("tr");
      tr.append(cell(when, "time"), cell(r.user), cell((c && c.desc) || r.desc || r.cmd), cell(commandText(r)));
      body.appendChild(tr);
    }
    info.textContent = rowsData.length ? "" : "Zatím žádný příkaz.";
    info.className = "note";
  } catch (e) {
    info.textContent = "Nelze načíst historii příkazů: " + e.message;
    info.className = "note error";
  }
  scheduleLog(LOG_MS);
}

async function start() {
  const info = document.getElementById("data-state");
  try {
    const resp = await fetch("/api/commands", { cache: "no-store" });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    commands = await resp.json();
  } catch (e) {
    info.textContent = "Nelze načíst seznam příkazů: " + e.message;
    info.className = "note error";
    return;
  }
  if (!commands.length) {
    info.textContent = "V konfiguraci (uha_vars.yaml) nejsou žádné příkazy.";
    return;
  }
  buildTable();
  poll();
  loadLog();
}

start();

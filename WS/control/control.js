// UHA control page (https://ctrl.uha.mkresta.cz, client certificate required).
// Commands from /api/commands (UhaGatePy, from uha_vars.yaml), states from /uha2.json (polled every 3 s).
// A command is a request: success = the state variable of the target node changed (CMD_spec.md, "Principles").
"use strict";

const POLL_MS = 3000;
const POLL_PENDING_MS = 1000;     // faster while waiting for a state change
const WAIT_MS = 10000;            // no change within this time -> "stav se nezměnil"
const STALE_S = 15;               // uha2.json older than this: the gateway does not write it
const LOG_MS = 15000;             // command log refresh (and right after a sent command)
const LOG_ROWS = 30;

let commands = [];                // from /api/commands
let vars = {};                    // uha2.json "Vars"
const pending = {};               // command name -> {expected, deadline}
const rows = {};                  // command name -> {state, msg, buttons}

function isLight(c) {
  return c.unit === "%" && c.min === 0 && c.max === 100;
}

function stateText(c, v) {
  if (!v || !v.valid || v.value === null) return { text: "neznámý", cls: "unknown" };
  if (isLight(c)) return v.value > 0 ? { text: "zapnuto" + (v.value < 100 ? " " + v.value + " %" : ""), cls: "on" }
                                     : { text: "vypnuto", cls: "" };
  if (c.type === "enum" && v.enum_name) return { text: v.enum_name, cls: "" };
  return { text: v.value + (c.unit ? " " + c.unit : ""), cls: "" };
}

function reached(c, v, expected) {
  if (!v || !v.valid || v.value === null) return false;
  if (isLight(c)) return expected > 0 ? v.value > 0 : v.value === 0;
  return Math.abs(v.value - expected) < 1e-6;
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

function buildTable() {
  const body = document.querySelector("#commands tbody");
  body.textContent = "";
  for (const c of commands) {
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
    if (isLight(c)) {
      buttons.push(button("Zapnout", 100, c, "on"), button("Vypnout", 0, c));
    } else if (c.type === "enum" && c.enum) {
      for (const [num, label] of Object.entries(c.enum)) buttons.push(button(label, Number(num), c));
    } else {
      const input = document.createElement("input");
      input.type = "number"; input.min = c.min; input.max = c.max; input.style.width = "6em";
      const b = document.createElement("button");
      b.textContent = "Odeslat";
      b.addEventListener("click", () => send(c, Number(input.value)));
      actions.appendChild(input);
      buttons.push(b);
    }
    buttons.forEach(b => actions.appendChild(b));
    tr.append(name, state, msg, actions);
    body.appendChild(tr);
    rows[c.name] = { state, msg, buttons };
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
      pending[c.name] = { expected: value, deadline: Date.now() + WAIT_MS };
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
  if (c && isLight(c)) return row.value > 0 ? "zapnout" + (row.value < 100 ? " " + row.value + " %" : "") : "vypnout";
  if (c && c.type === "enum" && c.enum && c.enum[String(row.value)] !== undefined) return c.enum[String(row.value)];
  return String(row.value) + (c && c.unit ? " " + c.unit : "");
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

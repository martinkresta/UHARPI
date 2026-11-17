"""HTTP API for the control web (CMD_spec.md section 1), on 127.0.0.1 only. nginx (ctrl.uha.mkresta.cz, client
certificate required) proxies /api/ here and sets X-Client-DN.

    GET  /api/commands                         -> 200 [{id, name, target, type, min, max, state, unit, desc}, ...]
    GET  /api/log?limit=n                      -> 200 [{ts, user, cmd, desc, value, seq}, ...] newest first (n <= 200,
                                                  default 50), from the DB table commands; 503 without the DB log
    POST /api/cmd  {"cmd": name, "value": n}   -> 200 {"ok": true, "seq": n}
         400 unknown command / bad value or body, 403 no X-Client-DN (or a foreign Origin), 415 not JSON,
         429 over the rate limit, 503 serial link down

Design: the stdlib ThreadingHTTPServer runs in its own thread (no web framework, no hand-written HTTP parser).
A request thread only parses and checks the request against the YAML commands (read only). The send itself -
serial port, seq counter, rate limit, journal, DB - runs in the gateway's asyncio loop: the thread hands it over
with loop.call_soon_threadsafe() and waits for the answer (at most 3 s). So the gateway state is still touched by
one thread only and needs no locks.

CSRF: the browser sends the client certificate also for requests that another web site triggers. A plain HTML form
cannot send Content-Type application/json, and a cross-site fetch() with it needs a CORS preflight, which this
server never allows. So POST requires application/json, and a present Origin header must be the control site.

Nothing here may stop the gateway: errors are answered with 500 and logged (rate-limited); if the port cannot be
opened the gateway runs without the API.
"""
import concurrent.futures
import json
import os
import pathlib
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, Tuple
from urllib.parse import parse_qs, urlsplit

from . import commands
from .log import log
from .vars_def import CmdDef, VarsFile

MAX_BODY = 1024
LOG_DEFAULT = 50
LOG_MAX = 200
ANSWER_TIMEOUT_S = 3
ERROR_REPEAT_S = 600

# (command, value, user) -> (HTTP status, JSON body); runs in the asyncio loop
Execute = Callable[[CmdDef, object, str], Tuple[int, dict]]


def command_list(defs: VarsFile) -> list:
    return [{"id": c.id, "name": c.name, "target": c.target, "type": c.type, "min": c.min, "max": c.max,
             "state": c.state, "unit": c.unit, "desc": c.desc,
             **({"enum": defs.enums[c.enum]} if c.type == "enum" else {})}
            for c in defs.commands.values()]


def command_log(db_path: str, defs: VarsFile, limit: int) -> list:
    """Newest commands from the DB (own read-only connection: WAL readers do not block the writer thread)."""
    by_id = {c.id: c for c in defs.commands.values()}
    uri = pathlib.Path(os.path.abspath(db_path)).as_uri() + "?mode=ro"     # file:///... (also on Windows)
    con = sqlite3.connect(uri, uri=True, timeout=2)
    try:
        rows = con.execute("SELECT ts, user, cmd_id, value, seq FROM commands ORDER BY rowid DESC LIMIT ?",
                           (limit,)).fetchall()
    finally:
        con.close()
    out = []
    for ts, user, cmd_id, value, seq in rows:
        c = by_id.get(cmd_id)
        out.append({"ts": ts, "user": user, "cmd": c.name if c else f"#{cmd_id}", "desc": c.desc if c else "",
                    "value": int(value) if c and c.type != "float" else value, "seq": seq})
    return out


class ApiServer:
    def __init__(self, port: int, defs: VarsFile, execute: Execute, origin: str, db_path: str = "") -> None:
        self.port = port
        self.defs = defs
        self.db_path = db_path
        self.execute = execute
        self.origin = origin.rstrip("/")
        self.loop = None
        self.requests = 0
        self.rejected: Dict[int, int] = {}          # HTTP status -> count (answered here, before the loop)
        self._lock = threading.Lock()
        self._logged: Dict[str, float] = {}
        self._server = None
        self._thread = None

    # ---- life cycle (called from the gateway) ----------------------------------------------

    def start(self, loop) -> bool:
        self.loop = loop
        try:
            server = ThreadingHTTPServer(("127.0.0.1", self.port), _Handler)
        except OSError as e:
            log.error("API: cannot listen on 127.0.0.1:%d: %s - running without the control API", self.port, e)
            return False
        server.daemon_threads = True
        server.api = self                            # type: ignore[attr-defined]
        self.port = server.server_address[1]         # the real port (tests bind port 0)
        self._server = server
        self._thread = threading.Thread(target=self._serve, name="api", daemon=True)
        self._thread.start()
        log.info("API: listening on 127.0.0.1:%d, %d commands from the YAML", self.port, len(self.defs.commands))
        return True

    def _serve(self) -> None:
        try:
            self._server.serve_forever(poll_interval=0.5)
        except Exception:
            log.exception("API: server thread stopped by an error - no control API, the gateway runs on")

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def status(self) -> dict:
        with self._lock:
            return {"Port": self.port, "Listening": self._server is not None, "Requests": self.requests,
                    "Rejected": {str(k): v for k, v in sorted(self.rejected.items())}}

    # ---- used by the request threads -------------------------------------------------------

    def count(self, status: int = 0) -> None:
        with self._lock:
            if status:
                self.rejected[status] = self.rejected.get(status, 0) + 1
            else:
                self.requests += 1

    def log_error(self, key: str, message: str, *args, exc: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            if now - self._logged.get(key, -1e9) < ERROR_REPEAT_S:
                return
            self._logged[key] = now
        (log.exception if exc else log.warning)("API: " + message, *args)

    def run_in_loop(self, cmd: CmdDef, value, user: str) -> Tuple[int, dict]:
        future: "concurrent.futures.Future[Tuple[int, dict]]" = concurrent.futures.Future()

        def call() -> None:
            try:
                future.set_result(self.execute(cmd, value, user))
            except Exception as e:                   # a bug in the send path: the loop goes on
                future.set_exception(e)

        self.loop.call_soon_threadsafe(call)
        return future.result(timeout=ANSWER_TIMEOUT_S)


class _Handler(BaseHTTPRequestHandler):
    server_version = "UhaGatePy"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 10                                     # a client that stops sending does not keep a thread forever

    @property
    def api(self) -> ApiServer:
        return self.server.api                       # type: ignore[attr-defined]

    def log_message(self, fmt, *args) -> None:       # no access log in the journal (nginx has one)
        pass

    def _answer(self, status: int, body) -> None:
        if status != 200:
            self.api.count(status)
            self.close_connection = True             # the body may be unread: do not parse it as a next request
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        if status != 200:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, text: str) -> None:
        self._answer(status, {"ok": False, "error": text})

    def _user(self):
        user = commands.user_from_dn(self.headers.get("X-Client-DN"))
        if user is None:
            self._error(403, "no client certificate")
        return user

    def do_GET(self) -> None:
        self.api.count()
        try:
            url = urlsplit(self.path)
            if url.path not in ("/api/commands", "/api/log"):
                return self._error(404, "not found")
            if self._user() is None:
                return
            if url.path == "/api/commands":
                return self._answer(200, command_list(self.api.defs))
            if not self.api.db_path:
                return self._error(503, "no command log (log-db not set)")
            try:
                limit = int(parse_qs(url.query).get("limit", [LOG_DEFAULT])[0])
            except ValueError:
                return self._error(400, "limit must be a number")
            try:
                rows = command_log(self.api.db_path, self.api.defs, max(1, min(limit, LOG_MAX)))
            except sqlite3.Error as e:
                self.api.log_error("log", "cannot read the command log: %s", e)
                return self._error(503, "command log not readable")
            self._answer(200, rows)
        except Exception:
            self.api.log_error("get", "error in GET %s", self.path, exc=True)
            self._error(500, "internal error")

    def do_POST(self) -> None:
        self.api.count()
        try:
            self._post()
        except concurrent.futures.TimeoutError:
            self.api.log_error("timeout", "the gateway loop did not answer in %d s", ANSWER_TIMEOUT_S)
            self._error(503, "gateway busy")
        except Exception:
            self.api.log_error("post", "error in POST %s", self.path, exc=True)
            self._error(500, "internal error")

    def _post(self) -> None:
        if self.path.split("?", 1)[0] != "/api/cmd":
            return self._error(404, "not found")
        user = self._user()
        if user is None:
            return
        origin = self.headers.get("Origin")
        if origin is not None and origin.rstrip("/") != self.api.origin:
            return self._error(403, "foreign origin")
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            return self._error(415, "Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._error(411, "Content-Length required")
        if length < 0 or length > MAX_BODY:
            return self._error(413, "body too large")
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return self._error(400, "body is not valid JSON")
        if not isinstance(body, dict) or not isinstance(body.get("cmd"), str) or "value" not in body:
            return self._error(400, 'body must be {"cmd": "<name>", "value": <number>}')
        cmd = self.api.defs.commands.get(body["cmd"])
        if cmd is None:
            return self._error(400, "unknown command")
        try:
            value = commands.check_value(cmd, body["value"])
        except commands.BadValue as e:
            return self._error(400, str(e))
        status, answer = self.api.run_in_loop(cmd, value, user)
        self._answer(status, answer)

    def _no_method(self) -> None:
        self.api.count()
        self._error(405, "method not allowed")

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _no_method

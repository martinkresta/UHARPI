"""Configuration: built-in defaults, then the optional config file, then the command line.

Config file: one "key = value" per line, "#" starts a comment. The keys are the long command
line options without the leading dashes (see OPTIONS below or run with --help).
"""
import argparse
import os
from dataclasses import dataclass, fields
from typing import Dict

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Stable name of the CP2102 USB-serial adapter; it survives a re-plug that would
# otherwise turn /dev/ttyUSB0 into /dev/ttyUSB1.
DEFAULT_PORT = "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"


@dataclass
class Config:
    config_file: str = ""
    port: str = DEFAULT_PORT
    out_dir: str = "/home/pi/Web"                      # uha.json, bms.json, uha2.json, uha_status.json
    log_file: str = "/home/pi/Web/log.txt"             # node log messages
    vars_yaml: str = os.path.join(APP_DIR, "uha_vars.yaml")
    json_period_ms: int = 1000
    rtc_period_s: int = 60                             # RTC sync whenever (unix time / period) changes
    reopen_s: int = 5                                  # retry period while the serial port is missing
    silence_warn_s: int = 60                           # warn when the link is open but silent this long
    error_summary_s: int = 600                         # period of the error summary
    compare_window_ms: int = 2000                      # old and VARS2 value must be this close to be compared
    compare_summary_s: int = 600                       # period of the old-vs-VARS2 comparison summary
    verbose: bool = False                              # debug log (every packet, every mismatch)


# name (= Config field, "-" instead of "_" on the command line / in the file), help text, minimum
OPTIONS = (
    ("port", "serial port", None),
    ("out_dir", "folder for the JSON outputs", None),
    ("log_file", "node event log file", None),
    ("vars_yaml", "path of uha_vars.yaml", None),
    ("json_period_ms", "output write period [ms]", 100),
    ("rtc_period_s", "RTC sync period [s]", 1),
    ("reopen_s", "serial reopen retry period [s]", 1),
    ("silence_warn_s", "warn after this many seconds without packets", 1),
    ("error_summary_s", "error summary period [s]", 1),
    ("compare_window_ms", "max time between old and VARS2 value for a comparison [ms]", 1),
    ("compare_summary_s", "old-vs-VARS2 comparison summary period [s]", 1),
)


def _apply(cfg: Config, values: Dict[str, object]) -> None:
    """Copy values (already converted) into cfg and check the minimums."""
    minimum = {name: low for name, _, low in OPTIONS}
    for name, value in values.items():
        if name in minimum and minimum[name] is not None and value < minimum[name]:
            raise SystemExit(f"option {name.replace('_', '-')} must be at least {minimum[name]}")
        setattr(cfg, name, value)


def _convert(name: str, text: str) -> object:
    """Convert a text from the config file to the type of the Config field."""
    kind = type(getattr(Config(), name))
    if kind is bool:
        return text.lower() in ("1", "true", "yes", "on")
    if kind is int:
        try:
            return int(text)
        except ValueError:
            raise SystemExit(f"option {name.replace('_', '-')}: '{text}' is not a number")
    return text


def _read_file(path: str) -> Dict[str, object]:
    known = {f.name for f in fields(Config)} - {"config_file"}
    values: Dict[str, object] = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise SystemExit(f"cannot read config file {path}: {e}")
    for number, line in enumerate(lines, 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        key, sep, text = line.partition("=")
        name = key.strip().replace("-", "_")
        if not sep or name not in known:
            raise SystemExit(f"{path}:{number}: invalid line: {line}")
        values[name] = _convert(name, text.strip())
    return values


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uhagatepy", description="UhaGatePy - UHA gateway for the Raspberry Pi")
    parser.add_argument("-c", "--config", help="key = value config file (keys = the long options below)")
    for name, text, _ in OPTIONS:
        kind = type(getattr(Config(), name))
        parser.add_argument("--" + name.replace("_", "-"), dest=name, type=kind, help=text)
    parser.add_argument("-v", "--verbose", action="store_true", default=None, help="debug log")
    return parser


def parse(argv) -> Config:
    """Build the configuration from the command line `argv` (without the program name)."""
    parser = _build_parser()
    cfg = Config()
    config_path = parser.parse_known_args(argv)[0].config
    if config_path:
        cfg.config_file = config_path
        _apply(cfg, _read_file(config_path))
    args = vars(parser.parse_args(argv))
    args.pop("config")
    _apply(cfg, {name: value for name, value in args.items() if value is not None})
    return cfg


def describe(cfg: Config) -> str:
    """One line with the effective configuration for the start-up log."""
    parts = []
    for f in fields(cfg):
        value = getattr(cfg, f.name)
        parts.append(f"{f.name.replace('_', '-')}={'(none)' if value == '' else value}")
    return " ".join(parts)

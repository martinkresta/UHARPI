"""Logging to journald.

The service writes to stdout and journald reads the level from a "<n>" prefix of each line
(3 = error, 4 = warning, 6 = info, 7 = debug), so no extra package is needed.
On a terminal a readable "HH:MM:SS L message" line is printed instead.
"""
import logging
import sys

log = logging.getLogger("uhagatepy")

_JOURNAL_PRIORITY = {
    logging.CRITICAL: 2,
    logging.ERROR: 3,
    logging.WARNING: 4,
    logging.INFO: 6,
    logging.DEBUG: 7,
}


class _JournalFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        text = record.getMessage()
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        priority = _JOURNAL_PRIORITY.get(record.levelno, 6)
        # journald needs the prefix on every line of a multi-line message
        return "\n".join(f"<{priority}>{line}" for line in text.splitlines())


def setup(verbose: bool) -> None:
    """Configure logging once at start-up. `verbose` enables the debug level."""
    handler = logging.StreamHandler(sys.stdout)
    if sys.stdout.isatty():
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname).1s %(message)s", "%H:%M:%S"))
    else:
        handler.setFormatter(_JournalFormatter())
    log.addHandler(handler)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    log.propagate = False

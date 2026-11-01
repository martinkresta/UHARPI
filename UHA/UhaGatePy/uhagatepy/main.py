"""Start-up: read the configuration, load the variable definitions, run the gateway."""
import asyncio
import sys
from typing import Optional, Sequence

from . import config, log as logging_setup, vars_def
from .gateway import Gateway
from .log import log


def main(argv: Optional[Sequence[str]] = None) -> int:
    cfg = config.parse(sys.argv[1:] if argv is None else list(argv))
    logging_setup.setup(cfg.verbose)
    try:
        defs = vars_def.load(cfg.vars_yaml)
    except vars_def.VarsDefError as e:
        log.error("cannot load the variable definitions: %s", e)
        return 1
    return asyncio.run(Gateway(cfg, defs).run())

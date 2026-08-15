"""Shared logger for diagnostic output.

All diagnostic messages go to standard error so nothing in this package
corrupts a protocol spoken over standard output.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("cal_auto_python")

if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

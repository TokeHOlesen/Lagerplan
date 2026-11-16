"""Loads rates.toml for the running app and reloads it when the file changes.

If the file becomes invalid, the last valid rates stay in use and the error is
logged, so a typo while tweaking never takes the site down. Run
`python manage.py check_rates` after editing to see any error immediately.
"""

import logging
import threading
from pathlib import Path

from django.conf import settings

from .calculation import Rates
from .ratesconfig import RatesError, load_rates

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {"key": None, "rates": None}


def get_rates() -> Rates:
    path = Path(settings.WORKLOAD_RATES_PATH)
    try:
        stat = path.stat()
    except OSError as exc:
        if _state["rates"] is not None:
            logger.error("Cannot read %s (%s); using the previously loaded rates.", path, exc)
            return _state["rates"]
        raise
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key == _state["key"]:
        return _state["rates"]
    with _lock:
        if key == _state["key"]:
            return _state["rates"]
        try:
            rates = load_rates(path)
        except (RatesError, OSError) as exc:
            if _state["rates"] is None:
                raise
            logger.error("Invalid %s: %s. Keeping the previously loaded rates.", path, exc)
            _state["key"] = key
            return _state["rates"]
        _state["key"] = key
        _state["rates"] = rates
        return rates

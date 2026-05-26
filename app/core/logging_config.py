"""
Synapse — merkezi logging konfigürasyonu.

Uygulama açılışında bir kez `configure_logging()` çağrılır. Tüm modüller
`logging.getLogger(__name__)` ile logger alır; format ve seviye burada
belirlenir. `LOG_LEVEL` env'i ile (`Settings.log_level`) değiştirilebilir.
"""

from __future__ import annotations

import logging
import logging.config

from app.core.settings import settings

_DEFAULT_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)

_DICT_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": _DEFAULT_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn":        {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error":  {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "sqlalchemy.engine": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "app":            {"handlers": ["console"], "level": settings.log_level, "propagate": False},
    },
    "root": {
        "handlers": ["console"],
        "level": settings.log_level,
    },
}


_configured: bool = False


def configure_logging() -> None:
    """Aynı süreçte birden çok kez çağrılması zararsızdır."""
    global _configured
    if _configured:
        return
    logging.config.dictConfig(_DICT_CONFIG)
    _configured = True

"""
Structured logging configuration using structlog + Sentry.

Use `get_logger(name)` to get a logger instance anywhere in the codebase:
    from logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("deal_created", deal_id="abc", user_id="xyz")
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


def _configure_sentry() -> None:
    """Initialize Sentry SDK if SENTRY_DSN is set."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlAlchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("AIBAA_ENV", "development"),
            integrations=[
                FastApiIntegration(transaction_style="url"),
                SqlAlchemyIntegration(),
            ],
            send_default_pii=False,
            attach_stacktrace=True,
            max_breadcrumbs=50,
        )
        structlog.get_logger().info("sentry_initialized", dsn_prefix=dsn[:20] + "...")
    except ImportError:
        structlog.get_logger().warning("sentry_sdk not installed — skipping Sentry init")
    except Exception as exc:
        structlog.get_logger().error("sentry_init_failed", error=str(exc))


def _add_log_level(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    event_dict["level"] = method_name.upper()
    return event_dict


def _add_timestamp(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    from datetime import datetime, timezone
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    return event_dict


def _rename_event_key(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    event_dict["event"] = event_dict.pop("event_", None) or event_dict.pop("message", "")
    return event_dict


def configure_logging() -> None:
    """Call once at application startup to configure structlog + stdlib logging."""

    # Processors applied in order
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        _add_log_level,
        structlog.stdlib.add_log_level_number,
        _add_timestamp,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        _rename_event_key,
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(serializer=_json_serializer),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib root logger
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))
    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configure_sentry()


def _json_serializer(obj: Any, **kwargs: Any) -> str:
    """JSON serializer for structlog — handles datetime, UUID, etc."""
    import json
    from datetime import datetime, timezone
    from uuid import UUID

    def default(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, UUID):
            return str(o)
        if hasattr(o, "__dict__"):
            return str(o)
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    return json.dumps(obj, default=default, **kwargs)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to *name*."""
    return structlog.get_logger(name)

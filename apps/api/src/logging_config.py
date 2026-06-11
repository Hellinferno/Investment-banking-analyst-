"""Structured logging configuration for AIBAA API."""
import logging
import os
import sys


def configure_logging() -> None:
    """Configure root logger with structured format and optional Sentry."""
    level_name = os.environ.get("AIBAA_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers on repeated calls
    if not root.handlers:
        root.addHandler(handler)

    # Quiet noisy third-party loggers
    for name in ("httpcore", "httpx", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)

    _configure_sentry()


def _configure_sentry() -> None:
    """Initialize Sentry error reporting when SENTRY_DSN is configured.

    Without this, exceptions raised inside background agent/parser threads are
    only visible in local stdout. Safe no-op when the DSN or SDK is absent.
    """
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logging.getLogger(__name__).warning(
            "SENTRY_DSN is set but sentry-sdk is not installed — error reporting disabled."
        )
        return

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("AIBAA_ENV", "development"),
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            # Never let Sentry capture request/response bodies — deal documents
            # and extracted financials are confidential (MNPI).
            send_default_pii=False,
        )
        logging.getLogger(__name__).info("Sentry error reporting initialized.")
    except Exception as exc:  # pragma: no cover - defensive
        logging.getLogger(__name__).warning("Sentry init failed: %s", exc)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

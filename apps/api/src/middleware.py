"""
FastAPI middleware: idempotency keys (Redis-backed) and rate limiting (slowapi).

Applies to all mutating routes (POST, PATCH, DELETE).  Idempotency keys have
a 24-hour TTL and return the cached response on replay.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

_IDEMPOTENCY_TTL = int(os.environ.get("AIBAA_IDEMPOTENCY_TTL_SECONDS", 86400))  # 24h
_IDEMPOTENCY_HEADER = "Idempotency-Key"
_SLOWAPI_INSTALLED = False
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    _SLOWAPI_INSTALLED = True
except ImportError:
    Limiter = None
    get_remote_address = None
    RateLimitExceeded = None

_redis_client: Optional[object] = None


def _get_redis() -> Optional[object]:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.from_url(url, decode_responses=True)
        _redis_client.ping()
        logger.info("Redis connected for middleware", url=url)
        return _redis_client
    except Exception as exc:
        logger.warning("Redis unavailable — idempotency middleware disabled: %s", exc)
        _redis_client = None
        return None


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Intercept POST/PATCH/DELETE requests that carry an `Idempotency-Key` header.

    On first request: execute handler, cache response in Redis with TTL.
    On replay (same key within TTL): return cached response immediately.

    Idempotency key format: `{method}:{path}:{key}` hashed with SHA-256.
    """

    _MUTATING_METHODS = {"POST", "PATCH", "DELETE", "PUT"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in self._MUTATING_METHODS:
            return await call_next(request)

        idempotency_key = request.headers.get(_IDEMPOTENCY_HEADER, "").strip()
        if not idempotency_key:
            return await call_next(request)

        key_scope = f"{request.method}:{request.url.path}:{idempotency_key}"
        cache_key = "idem:" + hashlib.sha256(key_scope.encode()).hexdigest()

        redis = _get_redis()
        if redis is not None:
            try:
                cached = redis.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    logger.debug("idempotency_hit", key=idempotency_key, cache_key=cache_key)
                    return JSONResponse(
                        content=data["body"],
                        status_code=data["status"],
                        headers={
                            "X-Idempotency-Replay": "true",
                            "X-Idempotency-Key": idempotency_key,
                        },
                    )
            except Exception as exc:
                logger.warning("Idempotency Redis read failed: %s", exc)

        response = await call_next(request)

        # Only cache successful 2xx responses
        if 200 <= response.status_code < 300 and redis is not None:
            try:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                response_body = json.loads(body.decode())
                cache_value = json.dumps({
                    "status": response.status_code,
                    "body": response_body,
                })
                redis.setex(cache_key, _IDEMPOTENCY_TTL, cache_value)
                logger.debug("idempotency_cached", key=idempotency_key, ttl=_IDEMPOTENCY_TTL)

                from starlette.responses import JSONResponse as JR
                return JR(content=response_body, status_code=response.status_code)

            except Exception as exc:
                logger.warning("Idempotency Redis write failed: %s", exc)

        return response


def get_limiter() -> Optional[object]:
    """Return a configured slowapi Limiter if available, else None."""
    if not _SLOWAPI_INSTALLED:
        return None
    default_limit = os.environ.get("AIBAA_RATE_LIMIT", "60/minute")
    return Limiter(
        key_func=get_remote_address,
        default_limits=[default_limit],
        storage_uri=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    )

"""Small, bounded SerpApi client. Never return provider URLs containing credentials."""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
from copy import deepcopy
from threading import Lock

import httpx
import config  # noqa: F401 - loads backend environment before reading keys


class SearchError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class SerpApiClient:
    _cache: OrderedDict = OrderedDict()
    _lock = Lock()

    def __init__(self, api_key: str | None = None, transport=None):
        self.api_key = (api_key if api_key is not None else os.getenv("SERPAPI_API_KEY", "")).strip()
        self.transport = transport

    def search(self, *, engine: str, q: str, gl: str = "in", hl: str = "en") -> tuple[dict, bool]:
        if not self.api_key:
            raise SearchError("missing_key", "Set SERPAPI_API_KEY in the backend environment to run live research.")
        if engine not in {"google", "google_news"}:
            raise SearchError("invalid_engine", "Unsupported search engine.")
        params = {"engine": engine, "q": q, "gl": gl, "hl": hl}
        fingerprint = hashlib.sha256(self.api_key.encode()).hexdigest()
        cache_key = (fingerprint, json.dumps(params, sort_keys=True))
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < 1800:
                self._cache.move_to_end(cache_key)
                return deepcopy(cached[1]), True

        # One retry for a server/network failure; never retry authentication or quota failures.
        for attempt in range(2):
            try:
                with httpx.Client(timeout=20, transport=self.transport, follow_redirects=False) as client:
                    response = client.get("https://serpapi.com/search.json", params={**params, "api_key": self.api_key})
                if response.status_code in (401, 403):
                    raise SearchError("authentication", "SerpApi rejected the API credentials.")
                if response.status_code == 429:
                    raise SearchError("quota", "SerpApi quota or rate limit reached. Check your account before retrying.")
                if response.status_code >= 500:
                    if attempt == 0:
                        time.sleep(0.25)
                        continue
                    raise SearchError("unavailable", "SerpApi is temporarily unavailable.")
                if response.status_code != 200:
                    raise SearchError("request_failed", "SerpApi rejected the search request.")
                try:
                    data = response.json()
                except ValueError:
                    raise SearchError("invalid_response", "SerpApi returned an invalid JSON response.") from None
                if not isinstance(data, dict):
                    raise SearchError("invalid_response", "SerpApi returned an unexpected response shape.")
                if data.get("error"):
                    # Do not reflect arbitrary upstream error text, which may include a URL/key.
                    err = str(data["error"]).lower()
                    if "hasn't returned any results" in err or "no results" in err:
                        return {"search_metadata": {"status": "Success"}}, False
                    code = "quota" if any(t in err for t in ("quota", "limit", "exceeded", "run out")) else "request_failed"
                    raise SearchError(code, "SerpApi could not complete this search. Check account status and query parameters.")
                metadata = data.get("search_metadata", {})
                if not isinstance(metadata, dict):
                    raise SearchError("invalid_response", "SerpApi returned an unexpected metadata shape.")
                if metadata.get("status") not in (None, "Success"):
                    raise SearchError("incomplete_response", "SerpApi search has not completed.")
                with self._lock:
                    self._cache[cache_key] = (time.monotonic(), deepcopy(data))
                    self._cache.move_to_end(cache_key)
                    while len(self._cache) > 128:
                        self._cache.popitem(last=False)
                return data, False
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == 0:
                    time.sleep(0.25)
                    continue
                raise SearchError("network", "Search timed out or the network is unavailable. Retry when connectivity returns.") from None
        raise SearchError("unavailable", "Search is unavailable.")

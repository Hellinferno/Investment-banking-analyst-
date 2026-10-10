"""Bounded, free-only OpenRouter chat for the existing analyst agents."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import logging
import os
from pathlib import Path
import threading
import time

import httpx

from config import DATA_ROOT
from engine.request_budget import RequestBudget

logger = logging.getLogger(__name__)
DEFAULT_MODEL = "apodex/apodex-1.1-mini:free"
DEFAULT_FALLBACK = "nvidia/nemotron-3.5-lightning:free"


class OpenRouterError(RuntimeError):
    """A safe error: no provider response body, prompt, or key is exposed."""


def _bounded_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(os.getenv(name, str(default)))))
    except ValueError:
        raise OpenRouterError(f"{name} must be an integer.") from None


class OpenRouterChat:
    def __init__(self, *, transport=None, budget_path: Path | None = None):
        self.key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.model = os.getenv("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL
        fallbacks = os.getenv("OPENROUTER_FALLBACK_MODELS", DEFAULT_FALLBACK)
        self.models = list(dict.fromkeys([self.model, *(m.strip() for m in fallbacks.split(",") if m.strip())]))
        if any(not model.endswith(":free") for model in self.models):
            raise OpenRouterError("OpenRouter requires explicit :free model IDs; paid models and routers are disabled.")
        self.timeout = _bounded_env("OPENROUTER_TIMEOUT_SECONDS", 45, 5, 90)
        self.max_tokens = _bounded_env("OPENROUTER_MAX_TOKENS", 4096, 256, 8192)
        self.max_chars = _bounded_env("OPENROUTER_MAX_PROMPT_CHARS", 120000, 1000, 500000)
        self.daily_limit = _bounded_env("OPENROUTER_DAILY_REQUEST_LIMIT", 40, 1, 50)
        self.requests_per_minute = _bounded_env("OPENROUTER_REQUESTS_PER_MINUTE", 10, 1, 20)
        self.attempt_limit = _bounded_env("OPENROUTER_MAX_ATTEMPTS", 2, 1, 2)
        self.budget_path = budget_path or DATA_ROOT / "openrouter_usage.sqlite3"
        self.budget = RequestBudget("OpenRouter", self.key, self.budget_path, self.daily_limit, self.requests_per_minute)
        self._catalog = {}
        self._catalog_until = 0.0
        self._lock = threading.Lock()
        self.last_model = None
        self.client = httpx.Client(
            base_url="https://openrouter.ai/api/v1",
            headers={"Authorization": f"Bearer {self.key}", "X-OpenRouter-Title": "AIBAA"},
            timeout=self.timeout,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def _get_json(self, path: str) -> dict:
        try:
            response = self.client.get(path, timeout=10)
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise OpenRouterError("OpenRouter configuration check is unavailable; try again later.") from None
        if response.is_error or not isinstance(data, dict) or data.get("error"):
            raise OpenRouterError(f"OpenRouter configuration check failed (HTTP {response.status_code}).")
        return data

    def _eligible_models(self, model_ids: list[str] | None = None) -> list[dict]:
        model_ids = model_ids or self.models
        if any(not model_id.endswith(":free") for model_id in model_ids):
            raise OpenRouterError("OpenRouter requires explicit :free model IDs; paid models and routers are disabled.")
        if time.time() >= self._catalog_until:
            data = self._get_json("/models")
            self._catalog = {model["id"]: model for model in data.get("data", []) if isinstance(model, dict) and model.get("id")}
            self._catalog_until = time.time() + 600
        eligible = []
        for model_id in model_ids:
            model = self._catalog.get(model_id)
            if not model or "content-safety" in model_id:
                continue
            architecture = model.get("architecture") or {}
            if "text" not in architecture.get("input_modalities", []) or "text" not in architecture.get("output_modalities", []):
                continue
            pricing = model.get("pricing") or {}
            try:
                free = bool(pricing) and all(Decimal(str(value)) == 0 for value in pricing.values() if value is not None)
            except InvalidOperation:
                free = False
            if free:
                eligible.append(model)
        if not eligible:
            raise OpenRouterError("No configured OpenRouter model is currently a free text-generation model.")
        return eligible

    def _quota(self) -> dict:
        data = self._get_json("/key").get("data") or {}
        quota = data.get("free_model_daily_requests") or {}
        if quota.get("remaining") is not None and quota["remaining"] <= 0:
            raise OpenRouterError("OpenRouter daily free-request quota is exhausted; wait for the UTC-day reset.")
        return quota

    def _reserve(self, remote_used: int = 0) -> None:
        """Persist a conservative per-key budget and pace across app restarts/workers."""
        try:
            self.budget.reserve(remote_used)
        except RuntimeError as exc:
            raise OpenRouterError(str(exc)) from None

    def _cooldown(self, seconds: int) -> None:
        self.budget.cooldown(seconds)

    def ask(self, system_prompt: str, user_prompt: str, *, model_id: str | None = None) -> str:
        if not self.key:
            raise OpenRouterError("Set OPENROUTER_API_KEY in the backend environment.")
        # Do not silently truncate financial evidence: reject oversize input.
        if len(system_prompt) + len(user_prompt) > self.max_chars:
            raise OpenRouterError(f"OpenRouter prompt exceeds the configured {self.max_chars}-character limit; reduce the document context.")
        with self._lock:
            candidates = list(dict.fromkeys([model_id, *self.models[1:]])) if model_id else self.models
            models = self._eligible_models(candidates)
            quota = self._quota()
            last_error = "OpenRouter returned no usable response."
            for model in models[:self.attempt_limit]:
                payload = {
                    "model": model["id"],
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    "max_tokens": self.max_tokens,
                    "stream": False,
                    "provider": {"max_price": {"prompt": 0, "completion": 0, "request": 0}},
                }
                supported = model.get("supported_parameters", [])
                reasoning = model.get("reasoning") or {}
                if "reasoning" in supported and not reasoning.get("mandatory"):
                    payload["reasoning"] = {"enabled": False}
                if "temperature" in supported:
                    payload["temperature"] = 0
                cap = (model.get("top_provider") or {}).get("max_completion_tokens")
                if cap:
                    payload["max_tokens"] = min(self.max_tokens, cap)
                # A byte per token is a conservative ceiling for arbitrary text.
                # Normal English fits much more efficiently, but cannot be silently cut.
                context = model.get("context_length") or 0
                if context and len((system_prompt + user_prompt).encode("utf-8")) + payload["max_tokens"] > context:
                    raise OpenRouterError("OpenRouter prompt may exceed the selected model's context; reduce it.")
                self._reserve(quota.get("used", 0))
                try:
                    response = self.client.post("/chat/completions", json=payload)
                except httpx.HTTPError:
                    last_error = "OpenRouter request timed out or could not connect."
                    continue
                try:
                    data = response.json()
                except ValueError:
                    data = {}
                error = data.get("error") if isinstance(data, dict) else None
                code = (error.get("code") if isinstance(error, dict) else None) or response.status_code
                try:
                    code = int(code)
                except (ValueError, TypeError):
                    code = response.status_code
                if code == 429:
                    try:
                        delay = max(60, min(86400, int(response.headers.get("Retry-After", "60"))))
                    except ValueError:
                        delay = 60
                    self._cooldown(delay)
                    raise OpenRouterError(f"OpenRouter rate limit reached; retry after {delay} seconds. No model rotation was attempted.")
                if code in (401, 402, 403):
                    raise OpenRouterError(f"OpenRouter access/credit restriction (HTTP {code}); check the key and model access.")
                if response.is_error or error:
                    last_error = f"OpenRouter request failed (HTTP {code})."
                    if code not in (408, 500, 502, 503, 504):
                        raise OpenRouterError(last_error)
                    continue
                if not isinstance(data, dict):
                    last_error = "OpenRouter returned an invalid response."
                    continue
                choices = data.get("choices") or []
                choice = choices[0] if choices and isinstance(choices[0], dict) else {}
                message = choice.get("message") or {}
                content = message.get("content") if isinstance(message, dict) else None
                if choice.get("finish_reason") == "length":
                    raise OpenRouterError("OpenRouter output was truncated; reduce the task or raise OPENROUTER_MAX_TOKENS.")
                if choice.get("finish_reason") in ("error", "content_filter") or not isinstance(content, str) or not content.strip():
                    last_error = "OpenRouter returned no usable answer."
                    continue
                logger.info("[LLM Engine] OpenRouter response from %s", model["id"])
                self.last_model = model["id"]
                return content
            raise OpenRouterError(last_error)


_client = None
_client_lock = threading.Lock()


def ask_openrouter(system_prompt: str, user_prompt: str, *, task: str = "general") -> str:
    global _client
    with _client_lock:
        if _client is None:
            _client = OpenRouterChat()
    override = os.getenv(f"OPENROUTER_{task.upper()}_MODEL", "").strip() if task != "general" else ""
    if task == "financial" and not override:
        override = "nvidia/nemotron-3-ultra-550b-a55b:free"
    return _client.ask(system_prompt, user_prompt, model_id=override or None)

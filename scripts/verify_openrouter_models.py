"""Inspect the supplied free models; opt in to one bounded probe per model.

No prompts from uploaded documents and no API keys are written to the report.
Run with --catalog-only first, then --probe after reviewing model modalities.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import re
import time

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MODELS = [
    "apodex/apodex-1.1-mini:free",
    "inception/mercury-decide:free",
    "respan/span-01-lite:free",
    "liquid/lfm-2.5-embedding-350m:free",
    "dots-studio/dots-3-note-preview:free",
    "liquid/lfm-2.5-2.6b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "thinkingmachines/inkling-small:free",
    "poolside/laguna-s-2.1:free",
    "thinkingmachines/inkling:free",
    "nvidia/nemotron-3-embed-1b:free",
    "poolside/laguna-xs-2.1:free",
    "cohere/north-mini-code:free",
    "nvidia/llama-nemotron-rerank-vl-1b-v2:free",
    "nvidia/nemotron-3.5-content-safety:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/llama-nemotron-embed-vl-1b-v2:free",
]


def is_free(pricing: dict) -> bool:
    return bool(pricing) and all(Decimal(str(value)) == 0 for value in pricing.values() if value is not None)


def probe(client: httpx.Client, row: dict, key: str) -> dict:
    """Use the advertised modality, never substitute a paid model or retry."""
    modalities = row["architecture"]["output_modalities"]
    model = row["model"]
    payload = {"model": model, "provider": {"max_price": {"prompt": 0, "completion": 0, "request": 0}}}
    if "embeddings" in modalities:
        endpoint = "/embeddings"
        payload["input"] = "A synthetic company filing needs analyst verification."
    elif "rerank" in modalities:
        endpoint = "/rerank"
        payload.update(query="company filing", documents=["A company annual filing.", "A recipe for soup."], top_n=2)
    elif "decisions" in modalities:
        endpoint = "https://openrouter.ai/api/alpha/decisions"
        payload.update(state=["User: Please verify the company filing. Assistant: I will check the cited source."],
                       questions={"source_review": {"type": "noul", "instructions": "The assistant agrees to review a cited source."}})
        if model.startswith("respan/"):
            payload["state"] = "User: Please verify the company filing. Assistant: I will check the cited source."
    else:
        endpoint = "/chat/completions"
        if "content-safety" in model:
            messages = [{"role": "user", "content": "Please summarize a public company annual report."}]
        else:
            messages = [
                {"role": "system", "content": 'Use only the supplied synthetic evidence. Output JSON only: {"findings":[{"statement":"...","source_ids":["S1"],"category":"..."}]}. Do not invent financial figures or buyer interest. Every finding must cite an input source ID.'},
                {"role": "user", "content": 'S1: ExampleCo published an annual report. S2: A newspaper reports that ExampleCo opened an office. Write two observations for analyst review; preserve the reported nature of S2.'},
            ]
        payload.update(messages=messages, max_tokens=1024, stream=False)
        supported = row.get("supported_parameters", [])
        if "response_format" in supported and "content-safety" not in model:
            payload["response_format"] = {"type": "json_object"}
        if "reasoning" in supported and not (row.get("reasoning") or {}).get("mandatory"):
            payload["reasoning"] = {"enabled": False}
    started = time.monotonic()
    result = {"endpoint": endpoint.replace("https://openrouter.ai", ""), "attempts": 1}
    try:
        response = client.post(endpoint, json=payload)
        result["http_status"] = response.status_code
        data = response.json()
        if response.is_error or data.get("error"):
            error = data.get("error") or {}
            error = error if isinstance(error, dict) else {"message": str(error)}
            message = str(error.get("message", "Request failed")).replace(key, "[REDACTED]")
            message = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", message)
            result.update(status="http_error", error_code=error.get("code"), message=message[:400])
            return result
        result["returned_model"] = data.get("model")
        result["cost"] = (data.get("usage") or {}).get("cost")
        if "embeddings" in modalities:
            vector = (data.get("data") or [{}])[0].get("embedding", [])
            valid = bool(vector) and all(isinstance(x, (int, float)) and math.isfinite(x) for x in vector)
            result.update(status="response_ok" if valid else "invalid_response", dimensions=len(vector))
        elif "rerank" in modalities:
            rankings = data.get("results", [])
            valid = bool(rankings) and all(isinstance(x.get("index"), int) and isinstance(x.get("relevance_score"), (int, float)) for x in rankings)
            result.update(status="response_ok" if valid else "invalid_response", ranking=rankings)
        elif "decisions" in modalities:
            answer = (data.get("answers") or {}).get("source_review", {})
            score = answer.get("noul")
            valid = isinstance(score, (int, float)) and 0 <= score <= 1
            result.update(status="response_ok" if valid else "invalid_response", answer=answer)
        else:
            choice = (data.get("choices") or [{}])[0]
            content = (choice.get("message") or {}).get("content") or ""
            result.update(status="response_ok" if isinstance(content, str) and content.strip() else "empty_response",
                          finish_reason=choice.get("finish_reason"), response_excerpt=content[:800],
                          completion_tokens=(data.get("usage") or {}).get("completion_tokens"))
            if "content-safety" not in model:
                try:
                    parsed = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip()))
                    findings = parsed["findings"]
                    valid = bool(findings) and all(isinstance(f.get("statement"), str) and f["statement"].strip()
                                                  and f.get("source_ids") and set(f["source_ids"]).issubset({"S1", "S2"}) for f in findings)
                    result["analyst_json_pass"] = bool(valid)
                except (ValueError, KeyError, TypeError, AttributeError):
                    result["analyst_json_pass"] = False
        return result
    except (httpx.HTTPError, ValueError) as exc:
        result.update(status="network_error" if isinstance(exc, httpx.HTTPError) else "invalid_response",
                      message=type(exc).__name__)
        return result
    finally:
        result["latency_seconds"] = round(time.monotonic() - started, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-only", action="store_true")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--models", nargs="+", choices=MODELS)
    parser.add_argument("--recheck", action="store_true", help="Retest selected models; otherwise resume the saved report.")
    parser.add_argument("--results", type=Path, default=ROOT / "docs" / "openrouter-verification.json")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise SystemExit("Set OPENROUTER_API_KEY in the root .env before verifying.")
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "models": []}
    previous = {}
    if args.results.exists():
        previous = {row["model"]: row for row in json.loads(args.results.read_text(encoding="utf-8"))["models"]}
    headers = {"Authorization": f"Bearer {key}", "X-OpenRouter-Title": "AIBAA model verification"}
    with httpx.Client(base_url="https://openrouter.ai/api/v1", headers=headers, timeout=75) as client:
        catalog_response = client.get("/models", params={"output_modalities": "all"})
        catalog_response.raise_for_status()
        catalog = {model["id"]: model for model in catalog_response.json()["data"]}
        key_response = client.get("/key")
        key_response.raise_for_status()
        account = key_response.json()["data"]
        report["account"] = {name: account.get(name) for name in ("is_free_tier", "free_model_daily_requests")}
        print(json.dumps({"account": report["account"]}), flush=True)
        selected = args.models or MODELS
        remaining = (account.get("free_model_daily_requests") or {}).get("remaining")
        needed = sum(not previous.get(model_id, {}).get("probe") or args.recheck for model_id in selected)
        if args.probe and remaining is not None and remaining < needed:
            raise SystemExit(f"Only {remaining} free requests remain; {needed} probes would exceed that budget.")
        for model_id in MODELS:
            model = catalog.get(model_id)
            row = {"model": model_id, "catalog_present": model is not None}
            if model:
                row.update({name: model.get(name) for name in (
                    "name", "architecture", "context_length", "pricing", "supported_parameters", "top_provider", "reasoning"
                )})
                row["zero_price"] = is_free(model.get("pricing", {}))
                row["status"] = "catalog_only"
            else:
                row["status"] = "not_in_catalog"
            if previous.get(model_id, {}).get("probe"):
                row["probe"] = previous[model_id]["probe"]
                row["probe_history"] = previous[model_id].get("probe_history", [])
            report["models"].append(row)
        args.results.parent.mkdir(parents=True, exist_ok=True)
        args.results.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if not args.probe:
            for row in report["models"]:
                print(json.dumps({key: row.get(key) for key in ("model", "status", "architecture", "zero_price", "context_length", "supported_parameters")}), flush=True)
        if args.probe:
            for row in report["models"]:
                if row["model"] not in selected or (row.get("probe") and not args.recheck):
                    continue
                if row.get("probe"):
                    row.setdefault("probe_history", []).append(row["probe"])
                if not row.get("zero_price"):
                    row["probe"] = {"status": "skipped_not_zero_price", "attempts": 0}
                else:
                    row["probe"] = probe(client, row, key)
                    row["probe"]["checked_at"] = datetime.now(timezone.utc).isoformat()
                args.results.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(json.dumps({"model": row["model"], **row["probe"]}, ensure_ascii=True), flush=True)
                # Single-threaded and under 20 request starts/minute, including failures.
                time.sleep(3.2)
                if row["probe"].get("http_status") in (401, 402):
                    print("Account authentication/credit error; stopping probes.", flush=True)
                    break
                if row["probe"].get("http_status") == 429:
                    current = client.get("/key").json().get("data", {})
                    if (current.get("free_model_daily_requests") or {}).get("remaining") == 0:
                        print("Daily free-request quota exhausted; stopping probes.", flush=True)
                        break
            final = client.get("/key").json().get("data", {})
            report["account_after"] = {name: final.get(name) for name in ("is_free_tier", "free_model_daily_requests")}
            args.results.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(json.dumps({"account_after": report["account_after"]}), flush=True)


if __name__ == "__main__":
    main()

"""Catalog and opt-in bounded chat checks for the NVIDIA screenshot models.

Specialist models are catalogued separately; they are not sent analyst prompts.
This script uses only NVIDIA's hosted trial endpoint, never partner endpoints.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CHAT_SLUGS = [
    "deepseek-v4.1-flash", "glm-5-3", "glm-5-3-flash", "kimi-k3",
    "nemotron-3.5-lightning-30b-a3b", "muse-glimmer-30b", "laguna-xs-2.1",
    "diffusiongemma-26b-a4b-it", "nemotron-3-ultra-550b-a55b",
    "nemotron-3-nano-omni-30b-a3b-reasoning", "gemma-4-31b-it",
    "nemotron-3-super-120b-a12b", "gpt-oss-20b",
    "llama-3.2-11b-vision-instruct", "llama-3.2-90b-vision-instruct",
]
SPECIALISTS = {
    "Kumo Tabular": "Structured-table prediction; no analyst chat use.",
    "3D Body Pose": "Video/pose estimation; outside analyst workflow.",
    "Kumo Relational": "Multi-table prediction; no analyst chat use.",
    "riva-translate-4b-instruct-v2": "Potential multilingual document translation; not a financial extractor or general drafter.",
    "ising-calibration-1.5-31b": "Quantum calibration; outside analyst workflow.",
    "nemotron-3-embed-1b": "Potential document retrieval/RAG; requires an embedding endpoint, not the chat boundary.",
    "nemotron-3.5-content-safety": "Potential input/output moderation; not a financial analyst generator.",
    "cosmos3-nano": "Image/video/action generation; outside analyst workflow.",
    "cosmos3-nano-reasoner": "Physical-world video reasoning; outside analyst workflow.",
    "synthetic-video-detector": "Synthetic-video detection; outside analyst workflow.",
    "ising-calibration-1-35b-a3b": "Quantum calibration; outside analyst workflow.",
    "cosmos-transfer2.5-2b": "Physics-aware video generation; no current investment-banking workflow.",
    "streampetr": "Autonomous-driving object detection; no current investment-banking workflow.",
    "llama-3.1-nemotron-safety-guard-8b-v3": "Potential multilingual document/prompt moderation; needs policy evaluation.",
    "llama-guard-4-12b": "Potential text/image moderation; not a financial extractor.",
    "Background Noise Removal": "Potential meeting-audio preprocessing; current ingestion is document/text only.",
    "magpie-tts-zeroshot": "Potential spoken report playback; current product has no speech output.",
    "sparsedrive": "Autonomous-driving planning; no current investment-banking workflow.",
    "bevformer": "Autonomous-driving perception; no current investment-banking workflow.",
    "Studio Voice": "Potential meeting-audio preprocessing; current ingestion is document/text only.",
    "paligemma": "Potential scanned-document captioning; requires image-specific evaluation and endpoint format.",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--models", nargs="+", choices=CHAT_SLUGS)
    parser.add_argument("--recheck", action="store_true")
    parser.add_argument("--results", type=Path, default=ROOT / "docs" / "nvidia-verification.json")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not key:
        raise SystemExit("Set NVIDIA_API_KEY in the root .env.")
    previous = {}
    if args.results.exists():
        previous = {row["slug"]: row for row in json.loads(args.results.read_text(encoding="utf-8"))["models"]}
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "endpoint": "https://integrate.api.nvidia.com/v1", "models": []}
    with httpx.Client(base_url=report["endpoint"], headers={"Authorization": f"Bearer {key}"}, timeout=60) as client:
        response = client.get("/models", timeout=15)
        response.raise_for_status()
        catalog = response.json()["data"]
        report["catalog_count"] = len(catalog)
        for slug in CHAT_SLUGS:
            matches = [model for model in catalog if model.get("id", "").split("/")[-1].replace(".", "-") == slug.replace(".", "-")]
            row = {"slug": slug, "role": "chat", "catalog_matches": [model["id"] for model in matches]}
            if previous.get(slug, {}).get("probe"):
                row["probe"] = previous[slug]["probe"]
            report["models"].append(row)
            print(json.dumps(row), flush=True)
        for slug, reason in SPECIALISTS.items():
            matches = [model["id"] for model in catalog if model.get("id", "").split("/")[-1] == slug]
            report["models"].append({"slug": slug, "role": "specialist", "catalog_matches": matches,
                                     "probe": {"status": "not_probed_specialist", "reason": reason, "attempts": 0}})
        args.results.parent.mkdir(parents=True, exist_ok=True)
        args.results.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not args.probe:
            return
        for row in report["models"]:
            if row["role"] != "chat" or (args.models and row["slug"] not in args.models) or (row.get("probe") and not args.recheck):
                continue
            if len(row["catalog_matches"]) != 1:
                row["probe"] = {"status": "missing_or_ambiguous_model", "attempts": 0}
                continue
            model_id = row["catalog_matches"][0]
            payload = {"model": model_id, "max_tokens": 1024, "stream": False,
                       "messages": [
                           {"role": "system", "content": 'Use only supplied synthetic evidence. Return only JSON: {"findings":[{"statement":"...","source_ids":["S1"],"category":"..."}]}. Do not invent financial figures or buyer interest.'},
                           {"role": "user", "content": 'S1: ExampleCo published an annual report. S2: A newspaper reports that ExampleCo opened an office. Write two cited observations; preserve the reported nature of S2.'}],
                       "chat_template_kwargs": {"enable_thinking": False}}
            started = time.monotonic()
            result = {"attempts": 1, "model": model_id, "checked_at": datetime.now(timezone.utc).isoformat()}
            try:
                response = client.post("/chat/completions", json=payload)
                result["http_status"] = response.status_code
                try:
                    data = response.json()
                except ValueError:
                    data = {}
                if response.is_error:
                    error = data.get("error") or data.get("detail") or {}
                    message = error.get("message", "Request failed") if isinstance(error, dict) else str(error)
                    result.update(status="http_error", message=re.sub(r"(?:nvapi-|sk-)[A-Za-z0-9_-]+", "[REDACTED]", message.replace(key, "[REDACTED]"))[:300])
                else:
                    choice = (data.get("choices") or [{}])[0]
                    content = (choice.get("message") or {}).get("content") or ""
                    result.update(status="response_ok" if content.strip() else "empty_response", finish_reason=choice.get("finish_reason"),
                                  response_excerpt=content[:800])
                    try:
                        parsed = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip()))
                        findings = parsed["findings"]
                        result["analyst_json_pass"] = bool(findings) and all(f.get("statement") and f.get("source_ids") and set(f["source_ids"]).issubset({"S1", "S2"}) for f in findings)
                    except (ValueError, KeyError, TypeError):
                        result["analyst_json_pass"] = False
            except httpx.HTTPError as exc:
                result.update(status="network_error", message=type(exc).__name__)
            result["latency_seconds"] = round(time.monotonic() - started, 2)
            row["probe"] = result
            args.results.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"slug": row["slug"], **result}), flush=True)
            if result.get("http_status") in (401, 402, 429):
                print("Account access/credit/rate limit error; stopping further NVIDIA probes.", flush=True)
                break
            time.sleep(3.2)


if __name__ == "__main__":
    main()

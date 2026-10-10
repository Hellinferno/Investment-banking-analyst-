# OpenRouter free-model verification and integration

All 21 supplied model IDs were present in the live OpenRouter catalog at zero price on 10 October 2026. Each received a small synthetic request through its advertised endpoint. There were 22 probe attempts: one per model and one corrected-format Respan request. Sixteen models returned usable responses; five were unavailable to this application during the check. These are point-in-time compatibility checks, not financial accuracy benchmarks or availability guarantees.

The JSON [verification record](openrouter-verification.json) preserves capabilities, price, probe time, HTTP status, latency, small synthetic response excerpts, and the Respan correction history. It contains no API keys or uploaded documents.

## Results

| Model ID | Endpoint/use | Observed result | Analyst chat selection |
| --- | --- | --- | --- |
| `apodex/apodex-1.1-mini:free` | Chat | 200, cited JSON, 1.14s | Default |
| `inception/mercury-decide:free` | Decisions | 200, typed probability | Specialist only |
| `respan/span-01-lite:free` | Decisions | 200 after correcting state to a string; initial array rejected with 400 | Specialist only |
| `liquid/lfm-2.5-embedding-350m:free` | Embeddings | 200, 1,024-dimensional vector | Specialist only |
| `dots-studio/dots-3-note-preview:free` | Chat | 200, cited JSON | Optional alternative |
| `liquid/lfm-2.5-2.6b:free` | Chat | 200, cited JSON | Optional alternative |
| `nvidia/nemotron-3.5-lightning:free` | Chat | 200, cited JSON, 1.78s | Single default fallback |
| `thinkingmachines/inkling-small:free` | Chat | 403: limited to supported agentic harnesses | Excluded |
| `poolside/laguna-s-2.1:free` | Chat | 200, cited JSON, 12.73s | Optional slower alternative |
| `thinkingmachines/inkling:free` | Chat | 403: limited to supported agentic harnesses | Excluded |
| `nvidia/nemotron-3-embed-1b:free` | Embeddings | 200, 2,048-dimensional vector | Specialist only |
| `poolside/laguna-xs-2.1:free` | Chat | 429, provider unavailable/rate limited | Excluded from defaults |
| `cohere/north-mini-code:free` | Chat | 200, cited JSON | Optional alternative |
| `nvidia/llama-nemotron-rerank-vl-1b-v2:free` | Rerank | 200, relevant filing ranked above unrelated text | Specialist only |
| `nvidia/nemotron-3.5-content-safety:free` | Chat moderation | 200, safety classification | Excluded from analyst generation |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | Chat | 200, cited JSON | Optional alternative |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | Chat | 200, cited JSON in a code fence | Optional alternative |
| `google/gemma-4-26b-a4b-it:free` | Chat | 429, provider unavailable/rate limited | Excluded from defaults |
| `google/gemma-4-31b-it:free` | Chat | 429, provider unavailable/rate limited | Excluded from defaults |
| `nvidia/nemotron-3-super-120b-a12b:free` | Chat | 200, cited JSON; simplified the reported wording in one statement | Optional alternative; review wording |
| `nvidia/llama-nemotron-embed-vl-1b-v2:free` | Embeddings | 200, 2,048-dimensional vector | Specialist only |

No restricted harness was impersonated, and no model was changed to a paid variant. The embedding, decision, rerank, and moderation checks establish that those endpoints respond; the current analyst workflow has no need to add extra specialist calls for every task.

## Integration plan implemented

1. Reuse the existing shared `ask_llm` boundary so research, extraction, auditing, drafting, pitchbooks, LBO, and coordination receive the selected provider without individual agent rewrites.
2. Use Apodex Mini for research/general prompts, drafting and coordination. Project-wide tests found two incorrect fields in its financial extraction, so financial extraction/auditing and DCF/LBO validation now use a separate `OPENROUTER_FINANCIAL_MODEL`, defaulting to Nemotron Ultra. Nemotron Lightning is one fallback after a network/server failure or empty answer. See [project-wide evaluation](LLM_PROJECT_PLAN.md); model choices are based on observed task behavior rather than an assumed model ranking.
3. Reject paid/router IDs before network access. Check the current model catalog for text input/output and zero pricing; send provider `max_price` values of zero. A retired or re-priced model cannot silently route to paid capacity.
4. Bound calls and preserve free quota: no SDK-hidden retries, maximum two inference attempts per prompt, 45-second request timeout, 4,096 output tokens, 120,000 prompt characters, ten inference starts per minute, and a conservative 40-attempt UTC-day limit.
5. Persist budget, spacing, and cooldown in `AIBAA_DATA_DIR/openrouter_usage.sqlite3`, partitioned by a key fingerprint and UTC day. Check `/key` before each prompt and seed the local count from reported account usage. The ledger conservatively counts attempts, including failures. It survives app restarts; multiple API instances must share the same data volume for the local guard to be shared.
6. Stop on authentication, credit, access, and rate-limit errors. Honor numeric `Retry-After` with at least a 60-second cooldown. Rotating models does not bypass account quota. Server/network failures may try the one configured free fallback; quota/access errors never call Gemini or NVIDIA.
7. Reject excessive input and truncated output. Keep the existing research schema/citation checks and source-excerpt fallback if synthesis fails. Citation IDs do not establish that a claim is true.

The account reported a 50-request daily ceiling. OpenRouter counters are asynchronous and some specialist endpoints are exempt from free-model caps, so the daily counter need not equal the number of probe attempts. Failed calls can still consume quota. Account-wide limits may also include calls made outside this app; OpenRouter's 429 remains authoritative.

## Configuration

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your-key-in-local-env-only
OPENROUTER_MODEL=apodex/apodex-1.1-mini:free
OPENROUTER_FINANCIAL_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
OPENROUTER_DRAFT_MODEL=apodex/apodex-1.1-mini:free
OPENROUTER_COORDINATION_MODEL=apodex/apodex-1.1-mini:free
OPENROUTER_FALLBACK_MODELS=nvidia/nemotron-3.5-lightning:free
OPENROUTER_DAILY_REQUEST_LIMIT=40
OPENROUTER_REQUESTS_PER_MINUTE=10
OPENROUTER_MAX_ATTEMPTS=2
OPENROUTER_TIMEOUT_SECONDS=45
OPENROUTER_MAX_TOKENS=4096
OPENROUTER_MAX_PROMPT_CHARS=120000
```

Restart the API after editing `.env`. Root `.env` is ignored by Git; `apps/api/.env`, when present, has precedence. Set `OPENROUTER_FALLBACK_MODELS=` to disable fallback. Override `OPENROUTER_MODEL` with an available free text model to change the selection. `LLM_PROVIDER=auto` prefers OpenRouter when a key is present; explicitly selecting a provider prevents cross-provider fallback. The old automatic Gemini/NVIDIA path remains available when no OpenRouter key is configured.

The local 40-attempt cap can be adjusted up to 50; it intentionally leaves headroom under this account's observed allowance. Multi-call extraction/auditing/CIM tasks can consume several requests per agent run. The source-only SerpApi workflow requires no LLM call.

## Reproduce the checks

Catalog checks make no inference request:

```powershell
.\.venv\Scripts\python.exe scripts/verify_openrouter_models.py --catalog-only
```

The following command makes at most one probe for each model that lacks a saved result, after checking remaining quota:

```powershell
.\.venv\Scripts\python.exe scripts/verify_openrouter_models.py --probe
```

To retest one model explicitly, use `--probe --recheck --models MODEL_ID`. Use `--results PATH` to keep a separate report. Test data is short and synthetic, and returned model IDs may be underlying provider aliases for the requested free variant.

The app integration can be checked against a previously saved live research JSON without another search:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_openrouter.py PATH_TO_RESEARCH_JSON --results PATH_TO_SMOKE_RESULT
```

Mocked regression checks cover free/paid routing, modality filters, bounded fallback, quota and cooldown, restart persistence, pacing, prompt/output limits, sanitization, provider selection, research configuration, and evidence-only recovery. The default pytest suite blanks OpenRouter, Gemini, NVIDIA, and SerpApi keys before imports.

## Official references

- [Models and capability catalog](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties)
- [Rate limits and account counters](https://openrouter.ai/docs/api_reference/limits)
- [Zero-price provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
- [Embeddings](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings)
- [Decisions](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request)
- [Reranking](https://openrouter.ai/docs/api/api-reference/rerank/submit-a-rerank-request)
- [Reasoning/output token constraints](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)

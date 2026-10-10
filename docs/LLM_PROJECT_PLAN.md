# Project-wide OpenRouter and NVIDIA evaluation

Scope: the entire existing AIBAA application, including uploaded financial-document extraction, auditing, deterministic DCF/LBO, pitchbooks, CIM drafting, research/diligence, meeting coordination, persistence, and exports. Model catalog presence, response availability, task-format compatibility, and financial accuracy are separate checks.

## Workflow routing

Every live generative agent uses the shared `engine.llm.ask_llm` boundary. Explicit task categories prevent a small research model from silently becoming the financial extractor.

| Project workflow | LLM role | OpenRouter default | Direct NVIDIA default | Deterministic responsibility |
| --- | --- | --- | --- | --- |
| DCF preparer / legacy extraction | financial | Nemotron Ultra free | Nemotron Super | Reporting-unit/citation review, computation/checkpoints |
| Financial auditor | financial | Nemotron Ultra free | Nemotron Super | Net-debt and lease-total arithmetic gate |
| Post-DCF validator | financial | Nemotron Ultra free | Nemotron Super | DCF calculations remain in `DCFEngine` |
| LBO extraction | financial | Same unit-aware preparer | Same unit-aware preparer | Latest-year EBITDA = revenue × EBITDA margin, then `LBOEngine` |
| Pitchbook | draft | Apodex Mini free | Nemotron Super | Existing PDF rendering, persistence, reviewer approval |
| CIM | draft | Apodex Mini free | Nemotron Super | Existing DOCX rendering and approval; missing biographies/market facts stay unknown |
| Meeting notes / tasks | coordination | Apodex Mini free | Nemotron Super | Owner/date validation, task persistence, Markdown export |
| Company / buyer / diligence discovery | research | Apodex Mini free | Nemotron Super | SerpApi evidence/citations; source-excerpt fallback |
| Agent orchestration | None required | Existing route rules | Existing route rules | Deterministic task routing |
| DCF/LBO/scenarios/sensitivity math | None | Existing numerical engines | Existing numerical engines | No generated valuation arithmetic |

The OpenRouter financial default is `nvidia/nemotron-3-ultra-550b-a55b:free`, while direct NVIDIA uses `nvidia/nemotron-3-super-120b-a12b`. These names are provider-specific. `OPENROUTER_FINANCIAL_MODEL`, `OPENROUTER_DRAFT_MODEL`, `OPENROUTER_COORDINATION_MODEL`, and the equivalent `NVIDIA_*_MODEL` variables can override roles. All roles share their provider's quota ledger; changing roles or models cannot reset quota.

`LLM_PROVIDER=openrouter` or `nvidia` selects an account explicitly. OpenRouter remains the configured local provider; both providers were evaluated. Automatic cross-provider rotation on quota exhaustion is not enabled. The source-only research path remains independent of LLM availability.

## Verification and repairs

The OpenRouter [model record](openrouter-verification.json) contains one probe for each of the 21 supplied IDs, plus the corrected Respan-format check. Sixteen returned usable responses. Inkling/Inkling Small returned 403 access restrictions; Laguna XS and both Gemma variants returned 429 provider errors.

The NVIDIA [model record](nvidia-verification.json) resolves the screenshot names against `https://integrate.api.nvidia.com/v1/models`. Fifteen general/vision-language models received bounded text probes. Eleven returned text; nine returned one valid cited JSON object. DeepSeek V4.1 Flash, GLM 5.3 Flash, Kimi K3, and Llama 90B Vision timed out at 60 seconds. Nano Omni returned malformed JSON, and Llama 11B Vision returned two JSON objects. Those results do not imply a permanent outage or prove image/OCR accuracy.

Direct NVIDIA successfully served Laguna XS and Gemma 31B when their OpenRouter variants were rate limited. GLM screenshot slugs use hyphens, but the hosted API IDs are `z-ai/glm-5.3` and `z-ai/glm-5.3-flash`. No restricted harness was impersonated and no partner endpoint was used.

Live project contract checks used a synthetic five-year INR-crore financial statement with known answers, a deliberate audit contradiction, missing management/market facts, and a two-person meeting transcript. They exercise real preparer/auditor helpers, existing prompt builders, and DCF/LBO numerical engines. These are reproducible finite-fixture checks, not broad financial-accuracy benchmarks or a human approval of outputs.

The checks identified and led to these repairs:

- Apodex's research response was valid, but its first full financial extraction had incorrect EBITDA margins and D&A ratio. Financial tasks now have a separate stronger-model route.
- NVIDIA's auditor initially approved a deliberately wrong net-debt value. Supplied numeric net-debt/lease contradictions are now flagged deterministically even if an LLM approves them or proposes an inconsistent correction. This verifies arithmetic, not source authenticity.
- Standalone LBO extraction mishandled reporting units through both providers. LBO now reuses the full unit-aware financial preparer and derives EBITDA deterministically. The existing direct-parameter path still skips LLM extraction.
- NVIDIA pitchbook/CIM drafting initially invented a market estimate or failed to acknowledge absent management facts. Shared instructions now require source grounding and explicit unknowns; updated probes checked those cases.

The [final contract record](llm-project-validation-final.json) contains eight passed checks for each provider, assembled from the original successful cases and targeted rechecks. [Earlier diagnostics](llm-project-validation.json) retain the pre-repair failures. A successful contract check confirms the tested parser, source-value and output-shape conditions; it does not establish that every paragraph is factually supported. The final backend regression suite passed 99 tests with two existing FastAPI startup deprecation warnings.

## Specialist models from both catalogs

| Model family | Possible project use | Current integration decision |
| --- | --- | --- |
| Liquid/Nemotron embedding models | Retrieve relevant annual-report passages instead of concatenating up to 400K characters | OpenRouter embedding endpoints were response-tested. Current document ingestion has no vector index; add retrieval only as a separately tested architecture change |
| Nemotron multimodal reranker | Rank retrieved source passages/table images | OpenRouter rerank endpoint was response-tested; no new retrieval stage is claimed |
| Gemma / Llama Vision / Nano Omni / PaliGemma | Scanned pages and financial tables | Text availability is recorded. Image/table extraction needs image-specific fixtures before replacing current PyMuPDF/Tesseract/RapidOCR behavior |
| Nemotron Content Safety / Safety Guard / Llama Guard | Optional document/prompt/output moderation | Content-safety response was tested through OpenRouter. A moderation score does not validate financial facts or authorize a transaction |
| Mercury Decide / Respan | Optional classification/routing/evaluation | Typed decisions were response-tested. Keep existing deterministic route/citation rules; these are not narrative or financial models |
| Riva Translate | Multilingual annual-report translation | Potential preprocessing; source units/citations must survive translation before adoption |
| Noise Removal / Studio Voice | Meeting-audio preprocessing | Useful only with an audio ingestion/transcription feature, which the current app does not have |
| Magpie TTS | Spoken report playback | Optional future interface; not required for existing workflows |
| Kumo Tabular / Relational | Predictive tabular analytics | Not a replacement for deterministic DCF/LBO or audited extraction; would require a dataset and validation plan |
| Ising calibration / body pose / autonomous-driving perception / Cosmos video generation | Quantum, physical-world, video generation | No current investment-banking workflow requires them; no unrelated inference calls or deployments were made |

Specialist rows explicitly marked `not_probed_specialist` are capability/fit assessments, not successful response tests. NVIDIA's common chat catalog does not expose every specialized endpoint. The screenshots show 38 free endpoints, but the supplied readable cards do not establish that every endpoint uses the same chat schema or account allowance.

## Limits and operation

OpenRouter enforces current catalog zero pricing and zero provider `max_price`, rejects paid/router IDs, checks `/key`, and permits at most two inference attempts per prompt. NVIDIA uses only the fixed hosted trial URL with OpenAI SDK retries disabled and one inference request per prompt. The trial's capacity/credits remain governed by NVIDIA's account/service policy; a free endpoint label is not an unlimited-use promise.

Both use persistent per-key UTC-day ledgers, ten request starts per minute by default, and conservative 40-attempt daily budgets. NVIDIA's local cap is our application setting, not an asserted NVIDIA account limit. Rate-limit responses cause a persisted cooldown and no automatic provider rotation. Multiple processes must share `AIBAA_DATA_DIR` to share these guards. External uses of the same key may consume provider quota independently.

Timeouts default to 45 seconds per OpenRouter attempt and 90 seconds for NVIDIA. Outputs are capped at 4,096 tokens; oversize prompts and truncated answers fail explicitly. Large annual reports may exceed the 120,000-character provider guard; retrieval/chunking must be designed before claiming arbitrary document-size support.

Use `LLM_PROVIDER=nvidia` to switch the whole app to direct NVIDIA after an API restart. Keep keys only in backend `.env` files. Existing API-specific `.env` values take precedence over root `.env`.

## Reproduce the whole-project checks

```powershell
.\.venv\Scripts\python.exe scripts/verify_nvidia_models.py
.\.venv\Scripts\python.exe scripts/verify_nvidia_models.py --probe
.\.venv\Scripts\python.exe scripts/verify_project_llm.py --provider openrouter --results docs/openrouter-project-check.json
.\.venv\Scripts\python.exe scripts/verify_project_llm.py --provider nvidia --results docs/nvidia-project-check.json
```

The project checker makes eight logical LLM calls. OpenRouter may use the one bounded free fallback after a transient failure. Use `--tasks` to rerun selected failed workflows without repeating successful checks. Separate report paths are required for concurrent provider runs. All input data is synthetic; no user upload is sent during verification.

Mocked regressions also verify role propagation, free-only role overrides, quotas, cooldown, sanitization, persistence, truncated responses, exact deterministic LBO inputs, and arithmetic audit gates. Existing historical modeling, tenant boundaries, review/export immutability, and frontend validation remain separate gates.

## Primary references

- [NVIDIA Nemotron Super hosted integration](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/build)
- [NVIDIA Nemotron Lightning hosted integration](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/build)
- [NVIDIA GLM 5.3 hosted model ID](https://build.nvidia.com/z-ai/glm-5-3?section=deploy)
- [OpenRouter model/capability catalog](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties)
- [OpenRouter account quotas](https://openrouter.ai/docs/api_reference/limits)

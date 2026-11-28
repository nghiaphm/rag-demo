# RAG Workspace Backend

The RAG Workspace Backend is a FastAPI modular monolith organized around Ports and Adapters (Hexagonal Architecture). It manages immutable document versions, text and spreadsheet ingestion, retrieval pipelines, agentic tool calling with DuckDB SQL queries, session persistence, typed SSE streaming, and Prometheus/Langfuse observability.

---

## Implementation status

| Status | Area | Notes |
| :--- | :--- | :--- |
| **Verified** | Hexagonal boundaries and core RAG | Enforced via AST tests (`9/9` PASS). Supports Hybrid Search (Dense + BM25 RRF), FlashRank/Cohere reranking, history-aware query rewriting, context budgeting, and citation ordinal mapping. |
| **Verified** | Document lifecycle and limits | `.pdf`, `.txt`, `.md`, `.markdown`, `.xlsx`; `25 MiB` default upload cap (`10 MiB` hard cap for `.xlsx`), returning HTTP `413 Content Too Large` on oversize uploads and safe `read_workbook()` validation on Excel inputs. |
| **Verified** | Corrective RAG and Agentic `run_sql` | `CorrectiveRagRunner` grades retrieval relevance with `CORRECTIVE_GRADER_MODEL` and runs up to 1 query retry before strict fallback. `AgenticRunner` coordinates `count_documents`, `list_documents`, `rag_search`, and DuckDB `run_sql` validated by `sqlglot` AST rules. |
| **Verified** | Observability and hardening | Secret-redacting JSON logs (`LOG_FORMAT=json`), validated `X-Request-ID`, Prometheus `GET /metrics` with low-cardinality labels, Langfuse v2 trace redaction (`LANGFUSE_TRACE_CONTENT_ENABLED=false`), dynamic `CORS_ORIGINS`, security headers middleware, and non-root multi-stage Dockerfile with pre-installed DuckDB `httpfs`. |
| **Tested (Offline/Isolated)** | S3 storage, Redis rate limits, ARQ worker, and eval runners | `S3FileStorage`, DuckDB `httpfs` S3 execution, `RedisRateLimiter` (atomic Lua script + bounded in-memory fallback), and `ArqIngestionQueue` / `WorkerSettings` pass offline integration tests with fakes/mocks; production execution depends on live S3/Redis services. |
| **Deferred** | `/auth/*`, multi-user RBAC, semantic cache, web search fallback | `AUTH_ENABLED=false`, `SEMANTIC_CACHE_ENABLED=false`, and `WEB_SEARCH_FALLBACK_ENABLED=false` remain off by default. `T2.4` SSE `status` events remain deferred to preserve pre-header HTTP errors and contract parity. |

---

## Stack and dependencies

- **Runtime**: Python `3.12` (`>= 3.10` compatible)
- **Web and config**: FastAPI (`>=0.115.0`), Uvicorn (`>=0.32.0`), Pydantic Settings (`>=2.5.0`)
- **LLM and embeddings**: `langchain-openai` targeting Groq OpenAI-compatible API (`openai/gpt-oss-120b`), `langchain-google-genai` (`gemini-embedding-001`)
- **Retrieval and tabular SQL**: Qdrant Client (`>=1.12.0`), FlashRank ONNX / Cohere, DuckDB (`2.0.0`), `sqlglot`, `pyarrow`, `openpyxl`, `defusedxml`
- **Persistence, cache, and queue**: PyMongo (`>=4.10.0`), Redis (`>=5.0.0`), ARQ (`>=0.26.0`), `boto3` (optional S3 storage)
- **Observability**: `langfuse>=2.50.0,<3.0.0`, `prometheus-client>=0.21.0,<1.0.0`

Dependency audit note: an OSV.dev advisory scan of installed packages flagged `unstructured==0.21.5` (`GHSA-4mvj-m6j5-pmf7` SSRF in URL partitioning and `GHSA-v5mq-3xhg-98m9` HTML XSS). Neither vector is reachable in this codebase because document loaders only parse uploaded local bytes and never pass URLs or render `unstructured` HTML; upgrading to `0.24.1` is held until `langfuse` moves past `<3.0.0` due to a shared `wrapt` constraint.

---

## Architecture and package boundaries

Dependencies under `backend/app/` follow one-way rules verified on every commit by `tests/architecture/test_dependency_rules.py`:

```text
backend/app/
├── main.py                      # FastAPI app factory, middlewares, /health, /health/dependencies, /metrics
├── api/                         # HTTP transport, schemas, request IP & auth dependencies, streaming/sse_schema.py
├── chat/                        # ChatOrchestrator, AgenticRunner, CorrectiveRagRunner, budget, query rewriting, citations
├── conversations/               # Session CRUD, surface isolation, SessionScope, atomic turn guard
├── documents/                   # Document lifecycle, ingestion, immutable versions, Excel validation/Parquet/sql_service
├── rag/                         # Splitters, loaders, embeddings, Qdrant retriever, FlashRank/Cohere rerankers, prompts
├── tool_use/                    # Domain-agnostic ToolCall/ToolEnvelope contracts and bounded ToolExecutor
├── workers/                     # ARQ ingestion worker (`WorkerSettings`)
├── infrastructure/              # MongoDB, Qdrant, S3, local storage, DuckDB executor, Redis rate limiter, metrics, Langfuse
└── shared/                      # Centralized Pydantic `Settings`, observability ports, auth primitives
```

Allowed import graph:

1. `api` imports `chat`, `conversations`, `documents`, `shared` (never imports `infrastructure`).
2. `chat` imports `rag`, `conversations`, `tool_use`, `shared` (never imports `api` or `sse_schema`).
3. `documents` imports `rag`, `tool_use`, `shared` (uses storage, queues, and vector indexes only through `ports.py` and `vector_index.py`).
4. `rag` and `tool_use` import only `shared`.
5. `infrastructure` imports `shared` and domain port definitions (never imports `api` or `chat`).
6. `shared` imports no sibling packages inside `app/`.

---

## API endpoints

All endpoints verified in `backend/app/main.py` and `backend/app/api/routes/*.py`:

| Group | Method | Path | Purpose |
| :--- | :--- | :--- | :--- |
| **System** | `GET` | `/health` | Basic liveness and configured `llm_model` |
| **System** | `GET` | `/health/dependencies` | Non-destructive pool readiness (`200 ok` / `503 degraded`; `mongodb` and `qdrant` required, `redis` and `s3` conditional) |
| **System** | `GET` | `/metrics` | Prometheus text exposition (`include_in_schema=False`, disabled returns `404`) |
| **Documents** | `POST` | `/documents/upload` | Upload new document (`201`, or `202` when async ingestion enabled; `413` on oversize) |
| **Documents** | `GET` | `/documents` | Paginated document list (`offset`, `limit`, `include_deleted`) |
| **Documents** | `GET` | `/documents/{document_id}` | Document metadata and immutable version history |
| **Documents** | `GET` | `/documents/{document_id}/versions/{version_id}/preview` | Preview TXT/MD/XLSX content (PDF returns explicit unsupported notice) |
| **Documents** | `PUT` | `/documents/{document_id}` | Upload new immutable version |
| **Documents** | `POST` | `/documents/{document_id}/re-index` | Re-index the active version from raw storage |
| **Documents** | `DELETE` | `/documents/{document_id}` | Unpublish document and remove vectors (`200`, or `202` when vector cleanup is pending) |
| **Chat** | `POST` | `/chat` | Synchronous JSON turn (stateless or persistent via `session_id`; optional `ui_context`) |
| **Chat** | `POST` | `/chat/stream` | Typed SSE streaming (`start`, `metadata`, `citation`, `delta`, `done`, `error`) |
| **Sessions** | `POST` / `GET` | `/sessions` | Create session (`surface`: `workspace` or `hr`) / List active sessions |
| **Sessions** | `GET` / `PATCH` / `DELETE` | `/sessions/{session_id}` | Get session (`410` if soft-deleted) / Rename title / Soft-delete session |
| **Sessions** | `PATCH` | `/sessions/{session_id}/scope` | Update session retrieval scope (`ALL_ACTIVE` or `SELECTED_DOCUMENTS`) |
| **Sessions** | `GET` | `/sessions/{session_id}/messages` | Paginated message history ordered by `sequence` |
| **Auth (Deferred)** | `POST` | `/auth/register`, `/auth/login`, `/auth/refresh` | Token issuance endpoints (inactive while `AUTH_ENABLED=false`) |
| **Auth (Deferred)** | `GET` | `/auth/me` | Current user context inspection |

Interactive Swagger docs are available at `/docs` (OpenAPI schema at `/openapi.json`). When terminating TLS or routing through a reverse proxy, configure proxy buffering off on `/chat/stream` so SSE chunks flush immediately.

---

## Environment variables (1-to-1 with `.env.example`)

`backend/app/shared/config.py` loads settings from `.env` at the repository root. Every variable defined in [`.env.example`](../.env.example) appears below with its default value from `.env.example`.

| Variable | `.env.example` Default | Purpose |
| :--- | :--- | :--- |
| **LLM and Tool Use** | | |
| `GROQ_API_KEY` | `gsk_xxxxxxxxxxxxxxxxxxxxxxxx` | Required Groq API key (must not stay empty) |
| `OPENAI_BASE_URL` | `https://api.groq.com/openai/v1` | Groq OpenAI-compatible HTTPS endpoint |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Chat and tool-selector LLM |
| `LLM_REQUEST_TIMEOUT_SECONDS` | `60.0` | Timeout per LLM request |
| `LLM_MAX_RETRIES` | `2` | Provider SDK retry count |
| `TOOL_USE_ENABLED` | `false` | Enables tool calling on `POST /chat` |
| `TOOL_SELECTOR_TIMEOUT_SECONDS` | `15.0` | Selector call timeout |
| `CHAT_TURN_TIMEOUT_SECONDS` | `120.0` | End-to-end turn deadline |
| `CHAT_MAX_ANSWER_CHARS` | `1000000` | Maximum generated response length |
| **Context Budget and Query Rewriting** | | |
| `RAG_CONTEXT_WINDOW_TOKENS` | `8192` | Total model context window |
| `RAG_SYSTEM_MAX_TOKENS` | `1024` | Budget for system instruction |
| `RAG_HISTORY_MAX_TOKENS` | `2048` | Budget for whole-turn history |
| `RAG_CHUNKS_MAX_TOKENS` | `3584` | Budget for retrieved context chunks |
| `RAG_QUERY_MAX_TOKENS` | `512` | Budget for user question |
| `RAG_OUTPUT_RESERVE_TOKENS` | `1024` | Reserved tokens for model output |
| `RAG_TOKEN_CHARS_PER_TOKEN` | `3.0` | Conservative char-to-token ratio |
| `RAG_REWRITE_TIMEOUT_SECONDS` | `15.0` | Query rewriting timeout |
| `RAG_REWRITE_MAX_CHARS` | `1000` | Max rewritten query length |
| **Embeddings and Chunking** | | |
| `EMBEDDING_PROVIDER` | `google` | Embedding provider backend |
| `EMBEDDING_API_KEY` | `AIza-xxxxxxxxxxxxxxxxxxxxxxxx` | Required Google AI Studio API key (`SecretStr`) |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model name |
| `EMBEDDING_TIMEOUT_SECONDS` | `30.0` | Timeout for embedding API calls |
| `CHUNK_SIZE` | `500` | Standard splitter chunk size (chars) |
| `CHUNK_OVERLAP` | `50` | Standard splitter chunk overlap (chars) |
| **Retrieval, Reranking, Hybrid, and Streaming** | | |
| `TOP_K` | `5` | Final chunks injected into context |
| `RERANKER_ENABLED` | `false` | Enables post-retrieval reranking |
| `RERANKER_PROVIDER` | `flashrank` | `flashrank`, `cohere`, or `none` |
| `RERANKER_MODEL` | `ms-marco-TinyBERT-L-2-v2` | Cross-encoder model name |
| `RERANKER_CANDIDATE_TOP_K` | `15` | Initial candidate count before reranking |
| `RERANKER_RELEVANCE_THRESHOLD` | `0.0` | Minimum relevance score threshold |
| `COHERE_API_KEY` | *(commented, `None`)* | API key when `RERANKER_PROVIDER=cohere` |
| `HYBRID_SEARCH_ENABLED` | `false` | Enables Dense + BM25 hybrid retrieval |
| `HYBRID_RRF_K` | `60` | Reciprocal Rank Fusion constant |
| `STREAM_TIMEOUT_SECONDS` | `120.0` | Total deadline for `/chat/stream` |
| **Storage and Uploads** | | |
| `DOCUMENTS_DIR` | `./data/documents` | Local raw storage directory |
| `STORAGE_BACKEND` | `local` | `local` or `s3` |
| `MAX_UPLOAD_BYTES` | `26214400` | General upload cap (`25 MiB`; HTTP `413` if exceeded) |
| `DEFAULT_TENANT_ID` | `default` | Tenant namespace for storage keys |
| `S3_BUCKET` | *(commented, `None`)* | Required bucket when `STORAGE_BACKEND=s3` |
| `S3_REGION` | *(commented, `us-east-1` in code / `ap-southeast-1` example)* | S3 region |
| `S3_ENDPOINT_URL` | *(commented, `None`)* | Custom S3-compatible endpoint |
| `S3_INGEST_ACCESS_KEY_ID` | *(commented, `None`)* | Write-scoped S3 key for ingestion |
| `S3_INGEST_SECRET_ACCESS_KEY` | *(commented, `None`)* | Write-scoped S3 secret for ingestion |
| `S3_USE_IF_NONE_MATCH` | *(commented, `true`)* | Conditional S3 put guard |
| **Excel Parquet and DuckDB SQL** | | |
| `EXCEL_PARQUET_INGESTION_ENABLED` | `false` | Normalizes `.xlsx` sheets to Parquet + catalog |
| `EXCEL_CATALOG_SAMPLE_ROWS` | `3` | Sample rows stored in table catalog |
| `S3_QUERY_ACCESS_KEY_ID` | *(commented, `None`)* | Read-only S3 key for DuckDB queries (must differ from ingest key) |
| `S3_QUERY_SECRET_ACCESS_KEY` | *(commented, `None`)* | Read-only S3 secret for DuckDB queries |
| `DUCKDB_MEMORY_LIMIT` | `512MB` | Per-connection DuckDB memory cap |
| `DUCKDB_THREADS` | `2` | Per-connection DuckDB worker threads |
| `DUCKDB_QUERY_TIMEOUT_SECONDS` | `15.0` | Watchdog interrupt timeout for SQL queries |
| `DUCKDB_MAX_ROWS` | `200` | Maximum AST-enforced rows returned by `run_sql` |
| `EXCEL_SQL_ENABLED` | `false` | Exposes `run_sql` inside Agentic Mode (requires `AGENTIC_MODE_ENABLED=true` and `EXCEL_PARQUET_INGESTION_ENABLED=true`) |
| `EXCEL_TEXT_ONLY_EMBEDDING_ENABLED` | `false` | Embeds only free-text Excel columns (requires `EXCEL_PARQUET_INGESTION_ENABLED=true`) |
| `EXCEL_SENSITIVE_COLUMN_PATTERNS` | `luong,salary,thu_nhap,...` | Column name patterns masked in sample rows |
| **MongoDB and Qdrant** | | |
| `MONGODB_URI` | `mongodb+srv://username:password@...` | MongoDB connection string |
| `MONGODB_DB_NAME` | `rag_demo` | Target MongoDB database |
| `MONGODB_TIMEOUT_MS` | `5000` | MongoDB driver timeout |
| `QDRANT_URL` | `https://cluster-id.region.cloud.qdrant.io:6333` | Qdrant endpoint (HTTPS enforced unless `QDRANT_ALLOW_INSECURE_HTTP=true`) |
| `QDRANT_API_KEY` | `replace-with-qdrant-api-key` | Qdrant API key |
| `QDRANT_COLLECTION` | `rag_documents` | Target vector collection |
| `QDRANT_TIMEOUT_SECONDS` | `5.0` | Qdrant client timeout |
| `QDRANT_ALLOW_INSECURE_HTTP` | `false` | Allows `http://` Qdrant URLs for local Docker `local-infra` |
| **Observability** | | |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `LOG_FORMAT` | `json` | `json` (redacting structured output) or `text` |
| `METRICS_ENABLED` | `true` | Exposes `GET /metrics` for Prometheus |
| `LANGFUSE_ENABLED` | `false` | Enables Langfuse v2 tracing (`SecretStr` keys required) |
| `LANGFUSE_TRACE_CONTENT_ENABLED` | `false` | When `false`, replaces prompt/answer text with char counts |
| `LANGFUSE_PUBLIC_KEY` | *(commented, `None`)* | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | *(commented, `None`)* | Langfuse secret key |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse host URL |
| **Corrective RAG and Agentic Mode** | | |
| `CORRECTIVE_RAG_ENABLED` | `false` | Enables grading + single retry fallback loop |
| `CORRECTIVE_MAX_RETRIES` | `1` | Maximum corrective re-retrieval retries |
| `CORRECTIVE_GRADER_MODEL` | `llama-3.1-8b-instant` | Lightweight Groq model used for grading/correction |
| `WEB_SEARCH_FALLBACK_ENABLED` | `false` | Deferred external web fallback (keep `false`) |
| `TAVILY_API_KEY` | *(commented, `None`)* | Tavily API key (unused while web fallback is off) |
| `AGENTIC_MODE_ENABLED` | `false` | Enables iterative `AgenticRunner` loop |
| `MAX_AGENT_STEPS` | `4` | Maximum planner iterations per turn |
| **Auth, Cache, Rate Limit, CORS, and Worker** | | |
| `AUTH_ENABLED` | `false` | Deferred multi-user auth gate (keep `false`) |
| `JWT_SECRET_KEY` | `replace-with-strong-random-secret` | Must be `>= 32` non-default chars if `AUTH_ENABLED=true` |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRE_MINUTES` | `10080` | Refresh token lifetime (7 days) |
| `SEMANTIC_CACHE_ENABLED` | `false` | Deferred semantic cache flag (keep `false`) |
| `SEMANTIC_CACHE_SIMILARITY_THRESHOLD` | `0.95` | Cosine similarity threshold for semantic cache |
| `SEMANTIC_CACHE_TTL_SECONDS` | `3600` | Semantic cache TTL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL for rate limiter and ARQ worker |
| `RATE_LIMIT_ENABLED` | `false` | Enables sliding-window rate limiting per user/IP |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Per-minute request limit when rate limit is enabled |
| `TRUSTED_PROXY_IPS` | *(empty)* | Comma-separated proxy IPs trusted for `X-Forwarded-For` |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowed browser origins |
| `MAX_TOKENS_PER_TURN` | `8192` | Turn token ceiling setting |
| `ASYNC_INGESTION_ENABLED` | `false` | Queues `/documents/upload` and `PUT` to ARQ (`202 Accepted`) |

Optional tuning flags defined with defaults in `backend/app/shared/config.py` (omitted from `.env.example`): `PARENT_CHILD_ENABLED=false`, `PARENT_CHUNK_SIZE=1200`, `PARENT_CHUNK_OVERLAP=100`, `CHILD_CHUNK_SIZE=300`, `CHILD_CHUNK_OVERLAP=30`, `MULTI_QUERY_ENABLED=false`, `MULTI_QUERY_COUNT=3`, `MULTI_QUERY_TIMEOUT_SECONDS=10.0`.

---

## Testing, smoke relocation, and evaluation

Offline test suites require zero cloud credentials (`backend/tests/_test_env.py` overrides local `.env` flags with safe defaults automatically):

```powershell
# Run from backend/
Set-Location backend
..\.venv\Scripts\python.exe -m unittest discover -s tests/architecture -v
..\.venv\Scripts\python.exe -m unittest discover -s tests/unit -v
..\.venv\Scripts\python.exe -m unittest discover -s tests/integration -v
```

Legacy cloud/live scripts: 16 `smoke_*.py` files previously mixed inside `backend/tests/integration/` (10 MongoDB/Qdrant-dependent and 6 live-provider scripts) were moved to `backend/tests/smoke/` with explicit warnings so `tests/integration/` contains only offline `test_*.py` suites (`186` tests across `20` files). Standalone offline smokes live in `backend/tests/smoke/`: `smoke_sse_schema.py`, `smoke_context_budget.py`, and `smoke_query_rewriting.py`.

Evaluation framework (`backend/evaluation/`):

- Uses **RAGAS-inspired custom metrics** (`ragas_metrics.py`) separating `correct_refusal_rate` on out-of-scope cases (`expect_refusal=true`) from `faithfulness` on in-scope cases, plus `CustomLlmJudge` (`llm_judge.py`) which never mixes heuristic scores into failed judge items.
- Agent and Excel SQL evaluation (`eval_agent_cli.py`, `benchmark_matrix.py`) enforces a strict boundary between offline plumbing checks (`--mode offline_smoke`, `--offline-check`, stamped `valid_for_model_quality: false`) and live evaluation (`--live --approve-live --qdrant-collection rag_documents_eval`), blocking production `rag_documents`.
- For safe demo workspace seeding (`--dry-run` default targeting `rag_documents_demo`), use `python backend/scripts/seed_demo_workspace.py`.

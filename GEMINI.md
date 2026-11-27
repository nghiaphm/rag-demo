# GEMINI.md — RAG Workspace Project Instructions

Operational instructions for AI assistants working in `<repo-root>`. This file complements [AGENTS.md](AGENTS.md) and [frontend/AGENTS.md](frontend/AGENTS.md) without duplicating project changelogs.

---

## 1. Project Overview & Stack

**RAG Workspace** is an immutable-document RAG Q&A platform paired with an isolated HR Policy & Support demo portal.

- **Backend (`backend/`)**: Python 3.12 (3.10+ compatible), FastAPI modular monolith (Hexagonal Architecture), LangChain, Groq LLM (`openai/gpt-oss-120b`), Google Gemini Embeddings (`gemini-embedding-001`), FlashRank / Cohere reranker, MongoDB Atlas, Qdrant Cloud, local raw file storage (`./data/documents`).
- **Frontend (`frontend/`)**: Next.js 16.4 (App Router), React 19.3, TypeScript, Tailwind CSS v4, Base UI, typed SSE streaming, Node/Playwright offline test suites.
- **OS & Shell**: Windows (`powershell`). Use `npm.cmd` / `npx.cmd` in `frontend/`. Keep the repository root as the working directory when running the backend server so `.env` and `./data/documents` resolve properly.

```text
<repo-root>/
├── backend/app/        # api, chat, documents, rag, tool_use, infrastructure, shared
├── backend/tests/      # architecture, unit, integration, smoke
├── backend/scripts/    # operational scripts (e.g. check_cloud_connections.py)
├── frontend/app/       # (workspace)/ and hr/ route groups
├── frontend/types/     # DTOs mirrored from FastAPI OpenAPI
├── data/documents/     # local raw file storage
├── task/               # Task.md and change-log.md (workspace + hr-portal)
├── .githooks/          # versioned Git hooks (pre-commit, commit-msg)
└── .agent/skills/      # local design skills
```

---

## 2. Hard Guardrails (read first)

These rules take priority over everything else in this file.

### 2.1 Execution Protocol

- **Plan-First**: Before any of the following, present a short plan (files to touch, contract impact, test plan) and **wait for confirmation**:
  - edits that span **2 or more** backend layers (`api`, `chat`, `documents`, `rag`, `tool_use`, `infrastructure`, `shared`);
  - changes to API DTOs or SSE events;
  - changes to RAG retrieval, prompt, or reranker logic.
- **Repro-First for Bugs**: Never patch a bug directly. Add or run a failing test/repro script first, fix the root cause, then re-run to prove it passes.
- **Precedence**: For a bug that also triggers Plan-First, do the repro first, then present the plan with the repro result attached, and wait for confirmation before fixing.
- **No Silent Shortcuts**: Never install new dependencies, loosen TypeScript/Python types, weaken existing tests, or catch-and-swallow errors to make checks pass without explicit approval.
- **Pre-existing Failures**: If a test fails before your change, report it explicitly. Do not skip, disable, or "fix" unrelated tests unless asked.
- **Blocked**: Report `BLOCKED` immediately if blocked by missing env, unclear spec, or unverified assumptions. Do not guess.

### 2.2 Autonomy Limits

- Committing locally on a feature branch is allowed. **Never** push, merge, rebase onto shared branches, or force-push without explicit approval.
- Never bypass Git hooks with `--no-verify` (`-n`) when committing without explicit approval; fix the underlying check failure instead.
- Never commit `.env`, log connection strings, or expose secrets (see §5).
- Never touch live cloud data from tests (see §5).

### 2.3 Working Style

- Preserve existing comments and docstrings unrelated to your diff.
- Prefer reading targeted line ranges over whole large files.

---

## 3. Architecture & Non-Negotiable Invariants

### 3.1 Backend Hexagonal Boundaries (`backend/app/`)

Enforced automatically by AST dependency tests in `backend/tests/architecture/test_dependency_rules.py`.

| Package | May import | Must never | Notes |
|---|---|---|---|
| `api/` (`routes/`, `schemas/`, `streaming/`) | `chat`, `conversations`, `documents`, `shared` | import `infrastructure`; embed business logic | HTTP & SSE transport only |
| `chat/` | `rag`, `conversations`, `tool_use`, `shared` | import `api` or `sse_schema` | Turn orchestration, query rewriting, multi-query expansion, context budgeting, citation mapping |
| `documents/` | `rag`, `tool_use`, `shared` | access storage/vectors directly | Lifecycle, immutable versions, ingestion, Excel safe validation; use `FileStorage` and `VectorIndex` ports only |
| `rag/` | `shared` | import any other app package | Purely technical: loaders, splitters, embeddings, retriever, reranker, prompts |
| `tool_use/` | `shared` | import any other app package | Domain-agnostic tool contract & executor |
| `infrastructure/` | `shared` (implements domain ports) | import `api` or `chat` | Concrete MongoDB, Qdrant, local filesystem adapters |
| `shared/` | nothing | import any sibling app package | Pydantic Settings (`config.py`) and cross-cutting primitives |

When modifying SSE events or API DTOs, preserve JSON/SSE parity and keep `sse_schema` isolated inside `backend/app/api/streaming/`.

### 3.2 Frontend App Router & Contract Parity (`frontend/`)

- **Next.js docs first**: Before writing or changing App Router code, read the relevant guide in `frontend/node_modules/next/dist/docs/` (per `frontend/AGENTS.md`).
- **Route isolation**:
  - `app/(workspace)/`: main workspace routes (`/chat`, `/chat/[sessionId]`, `/documents`) wrapped in `AppShell`.
  - `app/hr/`: standalone HR Demo Portal (`/hr`, `/hr/documents`, `/hr/sessions`, `/hr/sessions/[sessionId]`), scoped via `hr-theme.css` (`[data-hr-portal]`). Changes to `/hr/*` must never regress `(workspace)` layout, styling, or navigation.
- **OpenAPI DTO parity**: Keep `frontend/types/{api,chat,sessions,document}.ts` 1-to-1 aligned with FastAPI's `app.openapi()` schemas (verified by `npm.cmd run test:contract`). Keep HR-only presentation/fixture types separate in `frontend/types/hr.ts`.

---

## 4. Commands & Verification

### 4.1 Backend

```powershell
# Run API server (keep cwd at repo root)
python -m uvicorn app.main:app --app-dir backend --reload --port 8000

# Offline test suites (run inside backend/)
Set-Location backend
python -m unittest discover -s tests/architecture -v
python -m unittest discover -s tests/unit -v
python -m unittest discover -s tests/integration -v
```

- Offline smoke scripts (from root, with `$env:PYTHONPATH = "backend"`): `python backend/tests/smoke/smoke_sse_schema.py`, `smoke_context_budget.py`, `smoke_query_rewriting.py`.
- Cloud connectivity check (only when debugging live Mongo/Qdrant): `python backend/scripts/check_cloud_connections.py`.

### 4.2 Frontend (run inside `frontend/`)

```powershell
npm.cmd run test:contract
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npx.cmd next build --webpack
```

- Provider-free mock API for local UI/QA without cloud credentials: `node scripts/qa-mock-api.mjs`.
- Playwright Chromium suite: `npm.cmd run build:e2e`, then `npm.cmd run test:e2e`.

### 4.3 Targeted Verification Matrix

| Change type | Required checks |
|---|---|
| Backend logic / boundary edits | `tests/architecture` + `tests/unit` + `tests/integration` |
| API / SSE schema edits | add or update `smoke_sse_schema.py` + frontend `npm.cmd run test:contract` + `npm.cmd run typecheck` |
| RAG pipeline / prompt / reranker edits | relevant smoke tests; state whether offline eval on `rag_documents_eval` is required |
| Frontend component / route edits | `typecheck` + `lint` + `npm.cmd test`; add `build:e2e` + `test:e2e` for route or layout changes |
| Git hooks (`.githooks/*`) | `bash -n .githooks/<hook>` + verify LF line endings and `100755` mode (`git ls-files --stage .githooks/`) |

### 4.4 Reporting Rule

Always run the relevant checks after edits and report the exact commands and observed counts. Never extrapolate results for tests you did not run.

End every task with:

```text
Status: PASS | FAIL | BLOCKED
Verification: <exact commands> → <observed results, e.g. "Ran 42 tests, OK">
Modified files: <list>
```

---

## 5. Coding, Testing & Security Conventions

- **Python**: 4-space indentation, explicit type annotations, `snake_case` modules/functions, `unittest` (`test_*.py`) with offline mocks/fakes.
- **TypeScript / React**: 2-space indentation, `PascalCase` components, `kebab-case` file names, match local semicolon style, Node test runner (`*.test.mjs`) and Playwright (`*.spec.mts`).
- **Offline-first testing**: Never invoke live Groq, Gemini, or Cohere, and never mutate production MongoDB/Qdrant collections, inside unit/integration/UI test suites. Keep evaluation collections (`rag_documents_eval`) separate from application collections (`rag_documents`).
- **Secrets & env**: Keep all API keys and database URIs in the root `.env` (modeled after `.env.example`). Never commit `.env`, never log connection strings, and never expose secrets via `NEXT_PUBLIC_*` (only `NEXT_PUBLIC_API_BASE_URL` belongs in `frontend/.env.local`).

---

## 6. Git Workflow & Task Tracking

- **Branching**: Always branch feature work from an up-to-date `master`:
  ```powershell
  git checkout master
  git pull origin master
  git checkout -b <branch>
  ```
- **Commits**: Group commits by discrete functional scope. Format subjects using either **Conventional Commits** (`<type>[(<scope>)][!]: <description>`, allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`) or **Project Milestone Prefix** (`<ID> — <description>`, e.g. `T4.3 — ...`, `H1.1 — ...`, `F6 — ...`). Keep descriptions `>= 5` chars and subjects `<= 100` chars recommended (`<= 120` hard limit). Never lump an entire phase into generic `feat(phase-N)` branches or commits.
- **Git hooks (`.githooks/`)**: Versioned hooks run automatically on every commit once activated (`git config core.hooksPath .githooks`; keep `LF` via `.gitattributes` and mode `100755` via `git update-index --chmod=+x`). Always satisfy both hooks when preparing commits — never bypass with `--no-verify`:
  - `.githooks/pre-commit`: Inspects staged files only — blocks `.env`/private-key files and hardcoded secrets/API keys (use `pragma: allowlist secret` for synthetic test fixtures), validates staged `*.json`, runs `py_compile` + optional `ruff` + `backend/tests/architecture` (when touching `backend/app/*`), and runs `eslint` on staged `frontend/` files + incremental `tsc --noEmit` (`SKIP_TYPECHECK=1` only when explicitly approved).
  - `.githooks/commit-msg`: Enforces the commit subject format above, blocks generic `phase-N` scopes and overlong/empty subjects, and skips automatic commits (`Merge`, `Revert`, `fixup!`, `squash!`, `amend!`, `Initial commit`).
- **Task tracking**: When executing tracked project phases, update `task/Task.md`, `task/change-log.md`, `task/hr-portal/Task.md`, and `task/hr-portal/change-log.md` with milestone status and architectural/UI changes.

---

## 7. Skills & References

- **Frontend design**: Consult `.agent/skills/frontend-design/SKILL.md` and `.agent/skills/taste-skill/SKILL.md` when designing or polishing UI components.
- **Related docs**: [AGENTS.md](AGENTS.md), [frontend/AGENTS.md](frontend/AGENTS.md), bundled Next.js docs in `frontend/node_modules/next/dist/docs/`.

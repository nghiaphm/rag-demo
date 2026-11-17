# GEMINI.md — RAG Workspace Project Instructions

Operational instructions for AI assistants working in `d:\Project\rag-demo`. This file complements [AGENTS.md](AGENTS.md) and [frontend/AGENTS.md](frontend/AGENTS.md) without duplicating project changelogs.

---

## 1. Project Overview & Stack

**RAG Workspace** is an immutable-document RAG Q&A platform paired with an isolated HR Policy & Support demo portal:

- **Backend (`backend/`)**: Python 3.12 (3.10+ compatible), FastAPI modular monolith (Hexagonal Architecture), LangChain, Groq LLM (`openai/gpt-oss-120b`), Google Gemini Embeddings (`gemini-embedding-001`), FlashRank / Cohere reranker, MongoDB Atlas, Qdrant Cloud, and local raw file storage (`./data/documents`).
- **Frontend (`frontend/`)**: Next.js 16.4 (App Router), React 19.3, TypeScript, Tailwind CSS v4, Base UI, typed SSE streaming, and Node/Playwright offline test suites.
- **OS & Shell**: Windows (`powershell`). Use `npm.cmd` / `npx.cmd` in `frontend/` and keep the repository root (`d:\Project\rag-demo`) as working directory when running the backend server so `.env` and `./data/documents` resolve properly.

---

## 2. Architecture & Non-Negotiable Invariants

### 2.1 Backend Hexagonal Boundaries (`backend/app/`)
Enforced automatically by AST dependency tests in `backend/tests/architecture/test_dependency_rules.py`:

- `api/` (`routes/`, `schemas/`, `streaming/`): HTTP & SSE transport only. May import `chat`, `conversations`, `documents`, `shared`. **Never** import `infrastructure` or embed business logic.
- `chat/`: Turn orchestration, query rewriting, multi-query expansion, context budgeting, citation mapping. May import `rag`, `conversations`, `tool_use`, `shared`. **Never** import `api` or `sse_schema`.
- `documents/`: Document lifecycle, immutable versions, ingestion, Excel safe validation. May import `rag`, `tool_use`, `shared`. Access storage/vectors strictly through `FileStorage` and `VectorIndex` ports.
- `rag/`: Purely technical loaders, splitters, embeddings, retriever, reranker, prompts. May import `shared` only.
- `tool_use/`: Domain-agnostic tool contract & executor. May import `shared` only.
- `infrastructure/`: Concrete MongoDB, Qdrant, and local filesystem adapters. May import `shared` (and implement domain ports); never imports `api` or `chat`.
- `shared/`: Centralized Pydantic Settings (`config.py`) and cross-cutting primitives; zero imports from sibling app packages.

When modifying SSE events or API DTOs, preserve JSON/SSE parity and keep `sse_schema` isolated inside `backend/app/api/streaming/`.

### 2.2 Frontend App Router & Contract Parity (`frontend/`)
- **Next.js Bundled Docs First**: Before writing or changing Next.js App Router code, read the relevant guide inside `frontend/node_modules/next/dist/docs/` (per `frontend/AGENTS.md`).
- **Route Isolation**:
  - `app/(workspace)/`: Main workspace routes (`/chat`, `/chat/[sessionId]`, `/documents`) wrapped in `AppShell`.
  - `app/hr/`: Standalone HR Demo Portal (`/hr`, `/hr/documents`, `/hr/sessions`, `/hr/sessions/[sessionId]`) scoped via `hr-theme.css` (`[data-hr-portal]`). Changes to `/hr/*` must never regress `(workspace)` layout, styling, or navigation.
- **OpenAPI DTO Parity**: Keep `frontend/types/{api,chat,sessions,document}.ts` 1-to-1 aligned with FastAPI's `app.openapi()` schemas (verified by `npm.cmd run test:contract`). Keep HR-only presentation/fixture types separate in `frontend/types/hr.ts`.

---

## 3. Standard Development & Verification Commands

### Backend (from `d:\Project\rag-demo` unless noted)
```powershell
# Run API server (keep cwd at repo root)
python -m uvicorn app.main:app --app-dir backend --reload --port 8000

# Offline test suites (run inside backend/)
Set-Location backend
python -m unittest discover -s tests/architecture -v
python -m unittest discover -s tests/unit -v
python -m unittest discover -s tests/integration -v
```
- Offline smoke scripts (from root with `$env:PYTHONPATH = "backend"`): `python backend/tests/smoke/smoke_sse_schema.py`, `smoke_context_budget.py`, `smoke_query_rewriting.py`.
- Cloud connectivity check (only when debugging live Mongo/Qdrant): `python backend/scripts/check_cloud_connections.py`.

### Frontend (run inside `frontend/`)
```powershell
npm.cmd run test:contract
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npx.cmd next build --webpack
```
- Provider-free mock API for local UI/QA without cloud credentials: `node scripts/qa-mock-api.mjs`.
- Playwright Chromium suite: `npm.cmd run build:e2e`, then `npm.cmd run test:e2e`.

**Verification Rule**: Always run the relevant checks above after edits and report exact commands and observed counts—never extrapolate unrun tests.

---

## 4. Coding, Testing & Security Conventions

- **Python**: 4-space indentation, explicit type annotations, `snake_case` modules/functions, `unittest` (`test_*.py`) with offline mocks/fakes.
- **TypeScript / React**: 2-space indentation, `PascalCase` components, `kebab-case` file names, match local semicolon style, Node test runner (`*.test.mjs`) and Playwright (`*.spec.mts`).
- **Offline-First Testing**: Never invoke live Groq, Gemini, Cohere, or mutate production MongoDB/Qdrant collections inside unit/integration/UI test suites. Keep evaluation collections (`rag_documents_eval`) separate from application collections (`rag_documents`).
- **Secrets & Env**: Keep all API keys and database URIs in root `.env` (modeled after `.env.example`). Never commit `.env`, log connection strings, or expose secrets via `NEXT_PUBLIC_*` (only `NEXT_PUBLIC_API_BASE_URL` belongs in `frontend/.env.local`).
- **Docs Integrity**: Preserve existing comments/docstrings unrelated to your diff; prefer reading targeted line ranges over whole large files.

---

## 5. Git Workflow, Task Tracking & Local Skills

- **Branching**: Always branch feature work from an up-to-date `master` (`git checkout master`, `git pull origin master`, then `git checkout -b <branch>`).
- **Commits**: Group commits cleanly by discrete functional scope (e.g., `H1.1 — ...`, descriptive feature/fix subjects). Never lump an entire phase into generic `feat(phase-N)` branches or commits.
- **Task Tracking**: Track active milestone status and architectural/UI changes in `task/` (`task/Task.md`, `task/change-log.md`, `task/hr-portal/Task.md`, `task/hr-portal/change-log.md`) when executing tracked project phases.
- **Project Skills**: Consult `.agent/skills/frontend-design/SKILL.md` and `.agent/skills/taste-skill/SKILL.md` when designing or polishing frontend UI components.

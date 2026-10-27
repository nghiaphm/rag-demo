# Repository Guidelines

## Project Structure & Module Organization

- `backend/app/` contains FastAPI routes (`api/`), document/session services and repositories, and the retrieval pipeline (`rag/`). MongoDB stores metadata and conversations; Qdrant indexes embeddings; raw documents use local storage.
- `backend/tests/` holds Python tests; `backend/scripts/` contains smoke checks and evaluation commands. Evaluation corpora and results live in `backend/evaluation/`.
- `frontend/app/` contains Next.js App Router pages. Shared UI, hooks, API clients, and types live in `components/`, `hooks/`, `lib/`, and `types/`; static assets live in `public/`.
- `frontend/tests/` contains Node tests; `frontend/e2e/` contains Playwright scenarios. See `docs/` for QA runbooks and `data/` for sample documents and prompts.

## Build, Test, and Development Commands

Run backend setup and development from the repository root:

```powershell
pip install -r backend/requirements.txt
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Keep the root working directory for relative storage paths. Run backend tests from `backend/`: `python -m unittest discover -s tests -v`.

Run frontend commands from `frontend/`:

- `npm.cmd ci`: install locked dependencies.
- `npm.cmd run dev`: start local development.
- `npm.cmd run build` / `npm.cmd run start`: build and serve production output.
- `npm.cmd run lint` / `npm.cmd run typecheck`: check ESLint and TypeScript.
- `npm.cmd test` / `npm.cmd run test:contract`: run Node tests and offline API-contract checks.
- `npm.cmd run build:e2e`, then `npm.cmd run test:e2e`: build fixtures and run Playwright Chromium tests.

## Coding Style & Naming Conventions

Use four-space Python indentation, type annotations, and `snake_case` modules/functions. Use two-space TypeScript indentation, PascalCase React components, and kebab-case filenames such as `chat-composer.tsx`. Follow surrounding semicolon conventions. Frontend linting uses Next.js ESLint presets. Follow `frontend/AGENTS.md`, including consulting bundled Next.js documentation before frontend changes.

## Testing Guidelines

Use Python `unittest` (`test_*.py`), Node's test runner (`*.test.mjs`), and Playwright (`*.spec.mts`). Add regression coverage for changed behavior, particularly document lifecycle, session isolation, and JSON/SSE parity. No numeric coverage threshold is configured. Prefer offline fixtures; follow the live-test runbook before provider calls or cloud mutations.

## Commit & Pull Request Guidelines

History uses short phase-oriented subjects such as `F6 — Document Management`; match that style when applicable. Keep commits focused. PRs should explain behavior changes, link relevant issues, list validation commands/results, and include screenshots for UI changes.

## Security & Configuration

Use root `.env.example` and `frontend/.env.example` as templates. Keep credentials in backend configuration; expose only `NEXT_PUBLIC_API_BASE_URL` to the browser. Never commit secrets or log connection strings. Keep evaluation collections separate from application data.

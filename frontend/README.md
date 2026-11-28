# RAG Workspace Frontend

The RAG Workspace Frontend is a Next.js 16 (App Router, `output: "standalone"`) and React 19 web application that connects directly from the browser to the FastAPI Backend. It provides SSE chat streaming, interactive source citations, session retrieval scoping, document management and preview, and an isolated HR Demo Portal.

---

## Implementation status

| Status | Area | Notes |
| :--- | :--- | :--- |
| **Verified** | Primary workspace (`/chat`, `/chat/[sessionId]`, `/documents`) | Session creation/rename/deletion, paginated message history, `POST /chat/stream` incremental UTF-8 SSE rendering, stop/cancel handling, citation `[n]` ordinal mapping, upload/version/re-index/delete lifecycle, HTTP `413` size-limit UX, TXT/MD/XLSX preview, and `DocumentScopeSelector` (`ALL_ACTIVE` / `SELECTED_DOCUMENTS`). |
| **Verified** | HR Demo Portal (`/hr`, `/hr/documents`, `/hr/guide`) | Isolated styling scope under `app/hr/hr-theme.css`, mock workforce charts/KPIs (`HR_ANALYTICS_FIXTURE`), live `GET /documents` strip, client-side document category tabs, guided tour, and multi-turn `HrChatbotWidget` (`surface="hr"`). |
| **Verified** | Build, contract parity, and E2E | `output: "standalone"` serving both workspace and `/hr/*` routes, strict 1-to-1 DTO parity against FastAPI OpenAPI (`64` schemas), `238` Node unit tests, `71` Playwright Chromium E2E scenarios running against `.next/standalone/server.js`, and `0` runtime npm vulnerabilities (`npm audit --omit=dev`). |
| **Deferred** | Login UI and inline PDF viewer | Authentication UI is deferred (`AUTH_ENABLED=false` on Backend). PDF files can be ingested, attached, and cited with 1-based page numbers, while inline PDF rendering is not built yet. |

---

## Technology stack

- **Runtime**: Node.js `>= 20.9` (Node.js `20` verified on CI)
- **Framework**: Next.js `^16.4.6` (App Router, standalone output), React `19.3.0`, TypeScript `^5`
- **Styling and UI**: Tailwind CSS `^4`, `@tailwindcss/turbopack`, Base UI (`@base-ui/react`), Lucide React, `shadcn`
- **Markdown**: `react-markdown`, `remark-gfm`, `rehype-highlight`
- **Testing**: Node built-in test runner (`node --test`), Playwright (`^1.64.1`)

Note on local vs lockfile Next.js version: `package-lock.json` pins `next@16.4.6` with `0` audit vulnerabilities; run `npm.cmd ci` if your local `node_modules` contains an older patch release.

---

## Directory structure

```text
frontend/
├── app/                         # Next.js App Router
│   ├── layout.tsx               # Root layout and workspace font setup
│   ├── page.tsx                 # Server redirect "/" -> "/chat"
│   ├── (workspace)/             # RAG Workspace (/chat, /chat/[sessionId], /documents)
│   └── hr/                      # Isolated HR Demo Portal (/hr, /hr/documents, /hr/guide)
├── components/
│   ├── chat/                    # ChatPreview, SessionChat, ChatComposer, DocumentScopeSelector, DocumentPreview
│   ├── documents/               # DocumentsPreview, DocumentUpload, DocumentActions, DocumentStatusBadge
│   ├── hr/                      # HrShell, HrDashboardView, HrDocumentsView, HrChatbotWidget, HrGuideView
│   ├── layout/                  # AppShell, ServiceHealth, LoadingSkeleton
│   └── ui/                      # Base UI / shadcn primitives
├── hooks/                       # React state hooks for chat, documents, sessions, attachments
├── lib/                         # API clients (error-ux, health, chat, documents, sessions), SSE parser, HR helpers
├── fixtures/                    # Offline mock datasets for tests and QA mock server
├── types/                       # TypeScript DTOs aligned with FastAPI OpenAPI (plus hr.ts)
├── scripts/                     # qa-mock-api.mjs, build-e2e.mjs, run-e2e.mjs, demo-smoke.mjs
├── tests/                       # Node unit tests (*.test.mjs) and verify-api-contract.mjs
├── e2e/                         # Playwright E2E specs (*.spec.mts)
├── Dockerfile                   # Multi-stage non-root Alpine standalone image
└── next.config.ts               # output: "standalone" and Turbopack config
```

---

## Environment configuration

Only one public environment variable is exposed to the browser, configured in `frontend/.env.local` (copied from [`frontend/.env.example`](.env.example)):

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Never place API keys or database URIs in `frontend/.env.local`. Next.js bakes `NEXT_PUBLIC_*` values at build time (`npm run build`), so changing the backend URL for a standalone build requires rebuilding.

---

## Running locally

### Install dependencies

```powershell
Set-Location frontend
npm.cmd ci
if (!(Test-Path .env.local)) { Copy-Item .env.example .env.local }
```

### Provider-free mock mode

Runs `qa-mock-api.mjs` on `http://127.0.0.1:4011` with an in-memory dataset (no Backend or LLM API keys needed):

```powershell
# Terminal A (inside frontend/)
node scripts/qa-mock-api.mjs

# Terminal B (inside frontend/)
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:4011/lifecycle"
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

### Real FastAPI Backend mode

Start the Backend on `http://127.0.0.1:8000`, then run:

```powershell
Set-Location frontend
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

---

## Testing and quality checks

All checks below run offline against mocks and OpenAPI schema exports:

```powershell
Set-Location frontend

npm.cmd run lint
npm.cmd run typecheck
npm.cmd test                   # 238 Node tests across 10 files
npm.cmd run test:contract      # Verifies 64 OpenAPI REST/SSE/health schemas
npm.cmd audit --omit=dev       # Runtime dependency vulnerability check

# Playwright Chromium E2E against standalone build (71 scenarios across 10 specs)
npm.cmd run build:e2e
npm.cmd run test:e2e

# Automated demo smoke script (workspace + /documents + /hr)
node scripts/demo-smoke.mjs
```

Note on `.next/standalone`: `npm run build` produces `.next/standalone/server.js`. As documented in Next.js `output: "standalone"`, standalone execution requires copying `public/` and `.next/static/` into `.next/standalone/`; both `frontend/Dockerfile` and `frontend/scripts/build-e2e.mjs` handle this automatically.

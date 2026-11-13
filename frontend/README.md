# RAG Workspace Frontend

The **RAG Workspace Frontend** is a **Next.js 16 (App Router)** and **React 19** user interface that communicates directly from the browser to the FastAPI Backend (without a Next.js API proxy). It provides real-time AI chat via Server-Sent Events (SSE), interactive source citations, persistent session management, and document lifecycle management.

> **MVP Scope**: This application implements a **Functional Single-user RAG MVP**. Authentication/RBAC and multi-tenancy are deferred.

---

## 1. Technology Stack

- **Runtime**: Node.js `>= 20.9` (Node.js 20 verified on CI).
- **Framework**: Next.js `16.4.0` (App Router), React `19.3.0`, TypeScript `^5`.
- **Styling & UI**: Tailwind CSS `^4`, `@tailwindcss/turbopack`, Base UI (`@base-ui/react`), Lucide React icons, `shadcn` components.
- **Markdown & Code Rendering**: `react-markdown`, `remark-gfm` (GFM tables), `rehype-highlight`.
- **Testing**: Node.js built-in test runner (`node --test`), Playwright (`^1.64.1`).

---

## 2. Architecture & Directory Structure

Presentation components (React) are decoupled from business controllers and API clients (`lib/` and `hooks/`):

```text
frontend/
├── app/                         # Next.js App Router
│   ├── layout.tsx               # Root layout, Geist fonts & AppShell
│   ├── page.tsx                 # Server redirect "/" -> "/chat"
│   ├── chat/
│   │   ├── page.tsx             # New Chat workspace
│   │   └── [sessionId]/page.tsx # Restores an existing persistent session
│   └── documents/page.tsx       # Document library management workspace
├── components/
│   ├── chat/                    # ChatPreview, SessionChat, ChatComposer, CitationContent, DocumentPreview
│   ├── documents/               # DocumentsPreview, DocumentUpload, DocumentActions, DocumentStatusBadge
│   ├── layout/                  # AppShell (session sidebar, navigation)
│   └── ui/                      # UI primitives (Button, Dialog, Sheet, Badge...)
├── hooks/                       # React lifecycle hooks (useChatAttachments, useSessions, useDocuments...)
├── lib/
│   ├── api/                     # HTTP clients (chat.ts, documents.ts, sessions.ts, health.ts, client.ts)
│   ├── chat/                    # ChatController, composer-service, source-mapper, citation-panel
│   ├── documents/               # UploadController, validation, actions-controller, text-preview
│   ├── sessions/               # HistoryController, session actions-controller
│   └── sse/                     # Incremental UTF-8 SSE stream parser
├── types/                       # TypeScript DTOs matching Backend Pydantic schemas
├── scripts/                     # Mock API server (qa-mock-api.mjs) & Playwright smoke scripts
├── tests/                       # Node unit tests & API contract parity checks
└── e2e/                         # Playwright E2E specs (*.spec.mts)
```

---

## 3. Core Features & Workflows

### 3.1 Chat, Sessions & SSE Streaming
- **Routing**: `/chat` opens a fresh workspace and creates a session upon the first valid submit; `/chat/[sessionId]` loads paginated message history from MongoDB.
- **SSE Streaming**: [`lib/api/chat.ts`](lib/api/chat.ts) and [`lib/sse/parser.ts`](lib/sse/parser.ts) consume typed frames from `POST /chat/stream`:
  - `start`: Attaches durable `session_id`, `request_id`, and `message_id`.
  - `metadata`: Supplies ordered `sources` matching context ordinals.
  - `delta`: Streams incremental response text tokens.
  - `done` / `error`: Finalizes status (`PARTIAL` / `FAILED` / `COMPLETED`) and token usage.
- **Reconciliation & Stop**:
  - Upon terminal event, the client fetches session history to verify consistency; any mismatch triggers a warning banner without auto-retrying generation.
  - Clicking **Stop** or navigating away aborts the local browser request (reload to verify durable server state if needed).
- **Session Management**: Supports renaming (`PATCH`) and deletion (`DELETE`). Sessions default to `ALL_ACTIVE` retrieval scope (custom scope selection UI is not implemented).

### 3.2 Citations & Source Drawer
- Citation markers `[n]` in Markdown responses are matched by [`lib/chat/source-mapper.ts`](lib/chat/source-mapper.ts) strictly against the assistant message's ordered `sources` metadata (markers inside code blocks/links or out-of-range ordinals are ignored).
- Clicking a `[n]` badge opens a source drawer displaying filename, page number, `document_id`, `version_id`, and `chunk_id`. Direct inline PDF page viewing is not yet implemented.

### 3.3 Document Management, Attachments & Previews
- `/documents` supports uploading (`.pdf`, `.txt`, `.md`, `.markdown`, `.xlsx`), uploading new immutable versions (`PUT`), re-indexing (`POST`), and deleting (`DELETE`).
- **Draft Attachments**: Selecting a file in the chat composer triggers immediate upload/indexing. Up to 20 attachments can be submitted once they reach `INDEXED` and `activated=true`. Attachments are message-level references and **do not restrict session retrieval scope**.
- **Document Preview** ([`components/chat/document-preview.tsx`](components/chat/document-preview.tsx)):

| Format | Current Preview Behavior |
| :--- | :--- |
| **Local TXT** | Reads up to 256 KiB locally before upload (uploaded file remains intact) |
| **Remote TXT / MD** | Fetches immutable version (`kind=text`); capped at 256 KiB, supports UTF-8 / UTF-16 BOM |
| **Remote XLSX** | Waits for indexing; `kind=excel` renders bounded sheets/columns/rows with literal formulas |
| **PDF** | Ingestion and attachment supported; inline PDF content viewer not implemented |

---

## 4. Environment Configuration

The sole Frontend environment variable is `NEXT_PUBLIC_API_BASE_URL`, configured in `frontend/.env.local` (copied from [`.env.example`](.env.example)):

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

> **Security & Build Note**: Never place API keys or database URIs in `frontend/.env.local`. `NEXT_PUBLIC_*` variables are baked into the bundle at `npm run build` time — changing the URL for production requires rebuilding.

---

## 5. Installation & Local Development

### 5.1 Install Dependencies
Run from the repository root and navigate to `frontend/`:

```powershell
Set-Location frontend
npm.cmd ci
if (!(Test-Path .env.local)) { Copy-Item .env.example .env.local }
```

### 5.2 Provider-Free Demo Mock Mode
Runs an in-memory mock API server on port `4011` without requiring Backend services or LLM costs:

```powershell
# Terminal A (inside frontend/)
node scripts/qa-mock-api.mjs

# Terminal B (inside frontend/)
$env:NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:4011/lifecycle'
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`. All mutations are stored in memory and reset when the mock server restarts.

### 5.3 Connecting to the Real FastAPI Backend
Ensure the FastAPI Backend is running at `http://127.0.0.1:8000` (see [`backend/README.md`](../backend/README.md)):

```powershell
# Inside frontend/
$env:NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:8000'
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

#### Verifying CORS
FastAPI allows only `http://localhost:3000` and `http://127.0.0.1:3000` (`credentials=false`). Verify preflight/headers with `curl`:

```powershell
curl.exe -i -H "Origin: http://localhost:3000" http://127.0.0.1:8000/sessions
curl.exe -i -X OPTIONS http://127.0.0.1:8000/chat/stream `
  -H "Origin: http://localhost:3000" `
  -H "Access-Control-Request-Method: POST" `
  -H "Access-Control-Request-Headers: content-type"
```

---

## 6. Production Build & Execution

```powershell
Set-Location frontend
$env:NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:8000'
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
npm.cmd run start -- --hostname 127.0.0.1 --port 3000
```

> Deployment note: Any reverse proxy placed in front of the Backend must disable response buffering on `/chat/stream` for real-time SSE token delivery.

---

## 7. Testing & Quality Assurance

Run all checks from `frontend/` (offline fixtures; zero live provider calls):

```powershell
# Linting & TypeScript verification
npm.cmd run lint
npm.cmd run typecheck

# Run all 210 Node.js unit tests
npm.cmd test

# Verify Frontend DTO parity with Backend Pydantic schemas
npm.cmd run test:contract

# Run Playwright Chromium E2E tests (spawns mock server automatically)
npm.cmd run build:e2e
npm.cmd run test:e2e

# Or run the automated demo smoke script
node node_modules/playwright/cli.js install chromium --no-shell
node scripts/demo-smoke.mjs
```

> Note: `npm run test:contract` invokes the root Python `.venv` interpreter to export schemas offline. Detailed QA runbooks are located in [`docs/frontend-demo-readiness.md`](../docs/frontend-demo-readiness.md) and [`docs/frontend-automated-tests.md`](../docs/frontend-automated-tests.md).

# REF-01: Module Mapping (Source -> Target Architecture)

## 1. Overview

Tài liệu này ghi nhận toàn bộ ánh xạ di chuyển, tách module và tái cấu trúc các tệp tin backend của dự án `rag-demo` từ cấu trúc phẳng/lai trước đây sang cấu trúc mục tiêu theo Feature-based & Ports and Adapters Architecture.

---

## 2. Application Modules Mapping (`backend/app/`)

| Đường dẫn cũ (`backend/app/`) | Đường dẫn mới (`backend/app/`) | Phân loại | Trách nhiệm & Ghi chú |
| :--- | :--- | :--- | :--- |
| `main.py` | `main.py` | Preserved / Root | Composition root & FastAPI lifespan; khởi tạo kết nối Cloud, mount routers. |
| `config.py` | `shared/config.py` | Relocated | Pydantic Settings, biến môi trường, đường dẫn gốc dự án `PROJECT_ROOT`. |
| `excel.py` | `documents/excel/validation.py` | Split (1/3) | Bounded XLSX parser, limit constants, mime validation, `WorkbookError`. |
| `excel.py` | `documents/excel/preview.py` | Split (2/3) | Bounded tabular preview logic (sheets, headers, row preview). |
| `excel.py` | `rag/loaders/excel.py` | Split (3/3) | LangChain `Document` row generator cho ingestion RAG. |
| `ingestion.py` | `documents/ingestion.py` | Split (1/2) | Business lifecycle, document/version records, storage orchestration. |
| `ingestion.py` | `rag/indexing.py` | Split (2/2) | Kỹ thuật thuần: `parse_and_split`, `embed_chunks`, `build_vector_records`. |
| `chat_orchestration.py` | `chat/orchestrator.py` | Relocated | Central orchestrator, turn resolution, tool calling vs direct answer. |
| `rag/pipeline.py` | `chat/pipeline.py` | Relocated | Shared chat pipeline thực thi RAG và tổng hợp ngữ cảnh cho JSON/SSE. |
| `query_rewriting.py` | `chat/query_rewriting.py` | Relocated | Rewriting multi-turn query dựa trên hội thoại gần nhất. |
| `context_budget.py` | `chat/context_budget.py` | Relocated | Cắt tỉa ngữ cảnh, phân bổ token budget cho history và documents. |
| `citation_mapping.py` | `chat/citation_mapping.py` | Relocated | Mapping số hiệu trích dẫn `[1]`, `[2]` với source metadata. |
| *(Mới tách từ SSE)* | `chat/events.py` | Extracted | Domain events trung lập: `ProviderStreamChunk`, stream lifecycle signals. |
| *(Mới tách từ SSE)* | `api/streaming/event_adapter.py` | Extracted | Adapter chuyển đổi domain event sang SSE event frames và JSON format. |
| `sse_schema.py` | `api/streaming/sse_schema.py` | Relocated | DTO và contract SSE streaming (`start`, `metadata`, `delta`, `done`, `error`). |
| `stream_metrics.py` | `api/streaming/stream_metrics.py`| Relocated | Stream metrics tracker (TTFT, total duration, chunk count). |
| `api/documents.py` | `api/routes/documents.py` | Relocated | Route handler quản lý tài liệu, upload, preview, delete. |
| `api/chat.py` | `api/routes/chat.py` | Relocated | Route handler chat JSON (`/chat`) và SSE streaming (`/chat/stream`). |
| `api/sessions.py` | `api/routes/sessions.py` | Relocated | Route handler quản lý phiên hội thoại (`/sessions`). |
| `schemas.py` | `api/schemas/chat_documents.py` | Relocated | Request/Response DTOs cho chat, attachments và documents. |
| `conversation_schemas.py` | `api/schemas/conversations.py` | Relocated | DTOs cho session CRUD, pagination, message history. |
| `conversation_models.py` | `conversations/models.py` | Relocated | Domain entities: `SessionRecord`, `MessageRecord`, `MessageRole`, `MessageStatus`. |
| `conversation_indexes.py` | `conversations/indexes.py` | Relocated | Định nghĩa và khởi tạo MongoDB compound indexes cho conversations. |
| `conversation_repository.py` | `conversations/repository.py` | Relocated | MongoDB persistence adapter cho sessions và messages. |
| `conversation_service.py` | `conversations/service.py` | Relocated | Application service cho session lifecycle và message persistence. |
| `history.py` | `conversations/history.py` | Relocated | Quản lý buffer lịch sử hội thoại cho model context. |
| `document_models.py` | `documents/models.py` | Relocated | Domain entities: `DocumentRecord`, `DocumentVersionRecord`, `DocumentStatus`. |
| `document_indexes.py` | `documents/indexes.py` | Relocated | Định nghĩa và khởi tạo MongoDB indexes cho document collection. |
| `document_repository.py` | `documents/repository.py` | Relocated | MongoDB persistence adapter cho documents và document versions. |
| `document_service.py` | `documents/service.py` | Relocated | Application service cho document management (CRUD, active version). |
| `document_queries.py` | `documents/queries.py` | Relocated | Read queries phục vụ tool use (count, list active documents). |
| `attachments.py` | `documents/attachments.py` | Relocated | Resolve attachments, preview version logic. |
| `attachment_models.py` | `documents/attachment_models.py` | Relocated | Value objects: `AttachmentReference`, `MessageAttachment`. |
| `storage.py` (interface) | `documents/ports.py` | Port Split | Contract `FileStorage`, `StoredFile`, `StorageError` (không phụ thuộc disk). |
| `storage.py` (concrete) | `infrastructure/storage.py` | Adapter Split | `LocalFileStorage` concrete implementation và factory `create_file_storage`. |
| `tool_use/document_handlers.py` | `documents/tool_handlers.py` | Relocated | Handlers thực thi tool liên quan đến tài liệu (`count_documents`, `list_documents`). |
| `tool_use/contracts.py` | `tool_use/contracts.py` | Preserved | DTOs trung lập cho tool calling: `ToolCall`, `ToolDefinition`, `ToolResult`. |
| `tool_use/executor.py` | `tool_use/executor.py` | Preserved | Tool registry và executor routing lệnh tool call. |
| `vector_index.py` | `rag/vector_index.py` | Port Neutral | Contract `VectorIndex`, `VectorRecord`, `VectorFilter`, `VectorIndexError`. |
| `qdrant_ingestion.py` | `infrastructure/qdrant_vector_index.py` | Adapter Split | Concrete `QdrantVectorIndex` adapter giao tiếp Qdrant client. |
| `rag/loaders.py` | `rag/loaders/files.py` | Relocated | File loaders đa định dạng (.txt, .md, .pdf, .xlsx). |
| `rag/splitter.py` | `rag/splitter.py` | Relocated | Recursive character text splitter logic. |
| `rag/embeddings.py` | `rag/embeddings.py` | Relocated | Google Gemini Embeddings adapter. |
| `rag/retriever.py` | `rag/retriever.py` | Relocated | Active-version scoped LangChain retriever. |
| `rag/prompt.py` | `rag/prompt.py` | Relocated | Prompt templates cho RAG QA. |
| `rag/llm.py` | `rag/llm.py` | Relocated | Groq Chat model adapter (`ChatGroq`). |
| `rag/chain.py` | `rag/chain.py` | Historical | Legacy LCEL chain (đã được thay thế bởi `chat/orchestrator.py`). |
| `cloud_connections.py` | `infrastructure/connections.py` | Refactored | Quản lý vòng đời kết nối đa dịch vụ MongoDB & Qdrant. |
| *(Tách từ connections)* | `infrastructure/mongo.py` | Extracted | Adapter quản lý MongoClient và MongoDatabase lifecycle. |
| *(Tách từ connections)* | `infrastructure/qdrant.py` | Extracted | Adapter quản lý QdrantClient lifecycle. |
| *(Tách từ connections)* | `infrastructure/status.py` | Extracted | Value object biểu diễn trạng thái kết nối Cloud `ConnectionStatus`. |
| `data_migration.py` | `documents/migrations/demo_corpus.py` | Relocated | Logic cốt lõi nạp demo corpus. |

---

## 3. Evaluation Package Mapping (`backend/evaluation/`)

| Đường dẫn cũ | Đường dẫn mới | Phân loại |
| :--- | :--- | :--- |
| `evaluation/golden_set.json` | `evaluation/datasets/golden_set.json` | Dataset |
| `evaluation/history_golden_set.json` | `evaluation/datasets/history_golden_set.json` | Dataset |
| `evaluation/corpus/*` | `evaluation/datasets/corpus/*` | Dataset Corpus |
| `scripts/eval_cli.py` | `evaluation/runner/eval_cli.py` | Runner CLI |
| `scripts/eval_history_cli.py` | `evaluation/runner/eval_history_cli.py` | Runner CLI |
| `evaluation/metrics.py` | `evaluation/scoring/metrics.py` | Scoring Metric |
| `evaluation/history_eval.py` | `evaluation/scoring/history_eval.py` | Scoring Metric |

---

## 4. Scripts Package Mapping (`backend/scripts/`)

| Đường dẫn cũ | Đường dẫn mới | Ghi chú |
| :--- | :--- | :--- |
| `scripts/data_migration.py` | `scripts/migrate_demo_corpus.py` | Thin CLI script wrapper gọi `app.documents.migrations.demo_corpus`. |
| `scripts/controlled_live_e2e.py` | `scripts/controlled_live_e2e.py` | Live E2E script cho phase R2-06B. |
| `scripts/verify_*.py` | `scripts/verify_*.py` | Giữ nguyên verification scripts cho audit và historical records. |

---

## 5. Tests Package Mapping (`backend/tests/`)

### 5.1. Unit Tests (`backend/tests/unit/`)
- `test_chat_orchestration.py`
- `test_chat_response_schema.py`
- `test_citation_mapping.py`
- `test_cloud_connections.py`
- `test_context_budget.py`
- `test_conversation_concurrency.py`
- `test_conversation_models.py`
- `test_document_models.py`
- `test_document_queries.py`
- `test_evaluation_metrics.py`
- `test_history.py`
- `test_history_evaluation.py`
- `test_llm.py`
- `test_query_rewriting.py`
- `test_retriever.py`
- `test_session_actions.py`
- `test_sse_schema.py`
- `test_storage.py`
- `test_stream_metrics.py`
- `test_streaming_pipeline.py`
- `test_tool_use.py`
- `test_vector_index.py`
- `test_xlsx_loader.py`

### 5.2. Integration Tests (`backend/tests/integration/`)
- `test_chat_json_tools.py`
- `test_chat_persistence.py`
- `test_chat_stream.py`
- `test_chat_stream_tools.py`
- `test_controlled_live_guards.py`
- `test_cors.py`
- `test_documents_api.py`
- `test_ingestion.py`
- `test_m06_verification.py`
- `test_message_attachments_excel.py`
- `test_multi_session_isolation.py`
- `test_rag_integration.py`
- `test_sessions_api.py`
- `test_stream_terminal_parity.py`
- 16 live smoke scripts kiểm thử với cloud/database mocks/spies.

### 5.3. Offline Smoke Tests (`backend/tests/smoke/`)
- `smoke_context_budget.py`
- `smoke_provider_stream.py`
- `smoke_query_rewriting.py`
- `smoke_sse_schema.py`

### 5.4. Architecture Tests (`backend/tests/architecture/`)
- `test_dependency_rules.py` (9 automated tests kiểm tra quy tắc phụ thuộc một chiều qua AST).

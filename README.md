# RAG Demo (API-first)

RAG demo dùng FastAPI + LangChain, OpenRouter cho LLM, Google Gemini cho embedding,
MongoDB Atlas cho document lifecycle, Qdrant Cloud cho vector retrieval và local filesystem
cho raw documents. `/chat` đã cutover sang Qdrant; PostgreSQL/pgvector không còn nằm trong
runtime hoặc dependency manifest.

## Kiến trúc hiện tại

```text
Client
  │
  ▼
FastAPI
  ├── Document APIs ── MongoDB metadata ── LocalFileStorage
  │                         │
  │                         └── parse/chunk/embed ── Qdrant Cloud
  ├── Session/message models + indexes ── MongoDB Atlas
  └── /chat ── Mongo active-version scope ── Qdrant retriever ── OpenRouter LLM
```

- MongoDB là source of truth cho document identity, versions, status và `active_version_id`.
- Qdrant là retrieval index có thể dựng lại từ raw files và MongoDB metadata.
- Retriever lấy danh sách active versions từ MongoDB ở mỗi query và dùng server-side
  Qdrant filter; inactive/failed/deleted versions không được đưa vào context.
- Raw file key có dạng `documents/{document_id}/{version_id}/original`, không dùng filename
  người dùng làm filesystem path.
- Evaluation dùng Qdrant collection riêng, mặc định `rag_documents_eval`, không trộn với
  collection ứng dụng `rag_documents`.
- MongoDB có persistence contract cho `sessions` và `messages`: UUID, UTC timestamps,
  retrieval scope, message lifecycle, citations/usage/request linkage và stable sequence.
  Session CRUD, paginated history và optional `/chat` persistence đã được xác minh qua
  nhiều lần khởi động lại FastAPI.

## Yêu cầu

- Python 3.10+; dự án đã được kiểm tra với Python 3.10.11.
- MongoDB Atlas cluster và database user.
- Qdrant Cloud cluster và database API key.
- OpenRouter API key và Google AI Studio API key.
- Không cần Docker hoặc PostgreSQL để chạy backend hiện tại.

## Cấu hình

Từ project root:

```powershell
Copy-Item .env.example .env
```

| Biến | Mặc định | Mô tả |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | bắt buộc | OpenRouter credential |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter endpoint |
| `LLM_MODEL` | `nvidia/nemotron-3-super-120b-a12b:free` | Chat model |
| `EMBEDDING_PROVIDER` | `google` | Embedding provider |
| `EMBEDDING_API_KEY` | bắt buộc | Google embedding credential |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model |
| `CHUNK_SIZE` | `500` | Chunk size |
| `CHUNK_OVERLAP` | `50` | Chunk overlap |
| `TOP_K` | `5` | Số chunks retrieve |
| `DOCUMENTS_DIR` | `./data/documents` | Local raw-file root |
| `STORAGE_BACKEND` | `local` | Hiện chỉ hỗ trợ local |
| `MONGODB_URI` | bắt buộc | MongoDB Atlas URI; không commit |
| `MONGODB_DB_NAME` | bắt buộc | Application database |
| `MONGODB_TIMEOUT_MS` | `5000` | MongoDB timeout |
| `QDRANT_URL` | bắt buộc | Qdrant Cloud HTTPS URL |
| `QDRANT_API_KEY` | bắt buộc | Qdrant database API key |
| `QDRANT_COLLECTION` | `rag_documents` | Application vector collection |
| `QDRANT_TIMEOUT_SECONDS` | `5.0` | Qdrant timeout |

Không commit `.env`. Health checks và scripts không in URI, API keys hoặc raw provider
exceptions.

## Chạy backend

```powershell
# project root
pip install -r backend/requirements.txt

Set-Location backend
uvicorn app.main:app --reload --port 8000
```

Swagger: `http://127.0.0.1:8000/docs`.

Kiểm tra dependencies:

```powershell
python backend/scripts/check_cloud_connections.py
Invoke-RestMethod http://127.0.0.1:8000/health/dependencies
```

`/health/dependencies` trả HTTP 200 chỉ khi MongoDB và Qdrant đều sẵn sàng.

## APIs

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/health` | Process health |
| GET | `/health/dependencies` | MongoDB/Qdrant readiness |
| POST | `/documents/upload` | Tạo document và active version đầu tiên |
| GET | `/documents` | List documents; có pagination và `include_deleted` |
| GET | `/documents/{document_id}` | Identity, active version và version history |
| PUT | `/documents/{document_id}` | Tạo immutable version từ raw file mới |
| POST | `/documents/{document_id}/re-index` | Tạo version từ raw file active hiện tại |
| DELETE | `/documents/{document_id}` | Unpublish, xóa Qdrant points, giữ raw/audit history |
| POST | `/chat` | Qdrant RAG; optional `session_id` để persist turn |
| POST | `/sessions` | Tạo session với scope mặc định `ALL_ACTIVE` |
| GET | `/sessions` | List active sessions với `offset/limit/total` |
| GET | `/sessions/{session_id}` | Lấy session; tombstone trả HTTP 410 |
| PATCH | `/sessions/{session_id}` | Cập nhật title |
| GET | `/sessions/{session_id}/messages` | History theo `sequence`, có pagination |
| DELETE | `/sessions/{session_id}` | Soft-delete session, hard-delete related messages |

Upload:

```powershell
curl.exe -X POST -F "file=@data/documents/research_paper_1_ai_rag.pdf" `
  http://127.0.0.1:8000/documents/upload
```

Chat:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/chat `
  -ContentType "application/json" `
  -Body '{"question":"Retrieval-Augmented Generation kết hợp những thành phần nào?"}'
```

Request cũ không có `session_id` vẫn stateless và response vẫn là `answer + sources`.
Để lưu hội thoại, gửi session đã tạo:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/chat `
  -ContentType "application/json" `
  -Body "{`"question`":`"RAG là gì?`",`"session_id`":`"$($session.session_id)`"}"
```

Với persistent chat, backend cấp atomically hai sequence, ghi user `COMPLETED` và assistant
`PENDING` trước generation, sau đó chuyển assistant thành `COMPLETED` hoặc `FAILED`.
Hai messages dùng chung `request_id`; failure chỉ lưu error code an toàn. Token usage hiện
`null` vì pipeline chưa trả usage metadata. MongoDB atomic guard chỉ cho một generation
hoạt động trên mỗi session; request đồng thời thứ hai trả HTTP 409 và không tạo messages.
Guard chỉ được chính `request_id` sở hữu release, kể cả completion, error hoặc cancellation.

Mỗi source trả `file_name`, `document_id`, `version_id`, `chunk_id`, `chunk_index` và
`page` nếu loader cung cấp. `source` không chứa local filesystem path.

Session:

```powershell
$session = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/sessions `
  -ContentType "application/json" -Body '{"title":"RAG research"}'
Invoke-RestMethod "http://127.0.0.1:8000/sessions/$($session.session_id)/messages?offset=0&limit=50"
```

Session delete giữ tombstone để phân biệt `404` không tồn tại và `410` đã xóa, đồng thời
hard-delete toàn bộ messages liên quan. DELETE lặp lại idempotent và tiếp tục cleanup nếu
lần trước bị gián đoạn. DELETE trong lúc session có generation active trả HTTP 409. Session
đã xóa không xuất hiện trong default list.

DELETE đặt `active_version_id=null` trước khi cleanup Qdrant. Nếu cleanup tạm thời lỗi,
API trả HTTP 202 với `cleanup_pending=true`; gọi DELETE lại để retry. Raw files, versions
và jobs vẫn được giữ cho audit/manual recovery.

## Demo corpus migration

Manifest M-04 chỉ định đúng ba repository-owned files trong `data/documents/`; migration
không scan file runtime ngoài manifest.

```powershell
python backend/scripts/migrate_demo_corpus.py
```

Migration đã được xác minh với 3 documents và 68 chunks (`37/16/15`). `source_key` có
unique partial index nên rerun cùng checksum chỉ verify, không tạo document/version trùng.
Source bytes thay đổi sẽ tạo immutable version mới và chỉ activate sau khi raw checksum,
Mongo state, Qdrant count và filtered retrieval đều PASS.

Raw copies nằm dưới `data/documents/documents/...` và được `.gitignore` loại khỏi source
control; ba source files ở root vẫn được track.

## Verification

```powershell
# Document lifecycle, failed re-index, page metadata và delete cleanup
python backend/scripts/verify_phase1.py

# M-05 counts/retrieval/Q&A/page/active-version/delete cutover checks
python backend/scripts/verify_cutover.py

# Vector adapter contract trên Qdrant Cloud
python backend/scripts/smoke_vector_adapter.py

# P2-01 models/indexes trên MongoDB Atlas; test data được cleanup chính xác
python backend/scripts/init_mongodb_indexes.py
python backend/scripts/smoke_conversation_models.py

# P2-02 Session APIs; isolated test session/messages được cleanup chính xác
python backend/scripts/smoke_session_api.py

# P2-03 persistent /chat success/failure lifecycle; exact cleanup
python backend/scripts/smoke_message_persistence.py

# P2-04 two concurrent HTTP requests + Atlas atomic guard
python backend/scripts/smoke_session_concurrency.py

# P2-05 restart persistence, ordering/pagination và failure/delete contracts
python backend/scripts/verify_phase2.py
```

`verify_cutover.py` dùng namespace test riêng cho version/delete checks và cleanup chính
xác; không xóa demo corpus hoặc collection/database dùng chung.
`verify_phase2.py` dùng FastAPI lifespan thật qua ba lần khởi động, nhưng mock generation
deterministic để phép thử persistence không phụ thuộc quota LLM. Script tạo một session UUID
riêng trên Atlas, kiểm tra 8 messages gồm một failed turn, rồi cleanup chính xác theo ID;
không xóa collection/database dùng chung.

## Evaluation

```powershell
python backend/scripts/eval_cli.py
python backend/scripts/eval_cli.py --no-reindex
python backend/scripts/eval_cli.py --out backend/evaluation/results/run.json
```

- Corpus: `backend/evaluation/corpus/`.
- Golden set: 9 cases, gồm 7 in-document và 2 fallback.
- Collection eval: `<QDRANT_COLLECTION>_eval`, tách khỏi application collection.
- Metrics: retrieval hit/recall, fact coverage, faithfulness proxy, fallback accuracy,
  latency và token usage nếu provider trả metadata.
- Provider errors được retry tối đa ba lần rồi ghi nhận theo case.

Kết quả M-05 gần nhất: Qdrant eval PASS 9/9, không lỗi; retrieval hit/recall, answer
relevance, faithfulness và fallback accuracy đều đạt `1.0`.

## Project structure chính

```text
backend/
├── app/
│   ├── api/                    # document/chat routes
│   ├── rag/                    # loader, splitter, embeddings, retriever, chain
│   ├── cloud_connections.py    # MongoDB/Qdrant lifecycle
│   ├── conversation_models.py  # session/message persistence contract
│   ├── conversation_indexes.py # stable ordering/query indexes
│   ├── conversation_repository.py
│   ├── conversation_service.py
│   ├── conversation_schemas.py
│   ├── document_models.py      # Mongo records/status
│   ├── document_repository.py  # Mongo persistence
│   ├── storage.py              # FileStorage + LocalFileStorage
│   ├── ingestion.py            # raw → parse/chunk/embed → Qdrant → activate
│   ├── vector_index.py         # backend-neutral vector contract
│   ├── qdrant_ingestion.py     # Qdrant adapter
│   └── data_migration.py       # idempotent demo migration
├── evaluation/                 # isolated corpus/golden set/results
├── migration/demo_corpus.json
├── scripts/
│   ├── migrate_demo_corpus.py
│   ├── smoke_conversation_models.py
│   ├── smoke_session_api.py
│   ├── smoke_message_persistence.py
│   ├── smoke_session_concurrency.py
│   ├── verify_phase1.py
│   ├── verify_phase2.py
│   ├── verify_cutover.py
│   └── eval_cli.py
└── tests/
```

## Rollback M-05

Cutover không xóa PostgreSQL container, volume hoặc dữ liệu cũ. Trong phiên M-05,
container baseline được để nguyên để rollback có thể thực hiện nếu production smoke phát
hiện lỗi.

Rollback là code rollback, không phải dual-write tự động:

1. Chọn Git ref ngay trước M-05 và restore `backend/app/db.py`,
   `backend/app/rag/vectorstore.py`, retriever/pipeline/chat cũ, ba scripts V1,
   `docker-compose.yml`, requirements, config và `.env.example` từ ref đó.
2. Cài lại requirements của ref trước M-05 và đặt `DATABASE_URL` trong `.env`.
3. Chạy lại Compose PostgreSQL với volume cũ, xác minh `pg_isready` và bảng baseline.
4. Chạy eval V1 trước khi đưa traffic `/chat` trở lại.
5. Không xóa MongoDB/Qdrant data khi rollback; chúng vẫn là bản migration có thể kiểm tra
   hoặc dùng lại cho lần cutover sau.

Không chạy `docker compose down -v` nếu còn cần rollback vì lệnh đó xóa volume.

## Giới hạn hiện tại

- Chưa có frontend, authentication hoặc streaming.
- Non-streaming provider call chạy trong worker thread; nếu transport disconnect không thể
  ngắt SDK call ngay, guard được giữ tới khi worker thực sự về terminal state.
- Process crash giữa generation có thể để lại persistent guard; automatic lease/stale-guard
  reconciliation chưa triển khai. P2-05 xác minh clean restart sau terminal state, không mô
  phỏng hard process kill giữa provider call.
- Chưa có tenant/document authorization đầy đủ; hiện phù hợp single-user development.
- Không reranker, hybrid search, query rewriting, Agent, LangGraph hoặc S3 adapter.
- Soft delete giữ raw file và audit history; chưa có garbage-collection dài hạn.
- Qdrant payload giữ chunk text để retrieval nhanh.
- Với câu hỏi ngoài tài liệu, response vẫn có thể trả top-k candidates kèm fallback.
- Evaluation dùng metrics heuristic trên corpus nhỏ; free LLM có thể biến động giữa runs.
- Đổi embedding model/dimension yêu cầu re-index application và evaluation collections.

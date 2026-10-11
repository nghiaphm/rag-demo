# RAG Demo (API-first)

RAG demo dùng **FastAPI + LangChain**, gọi **LLM qua OpenRouter** và **embedding qua Google Gemini API**. Document APIs dùng kiến trúc V2 với MongoDB Atlas, local raw-file storage và Qdrant Cloud; riêng query/chat vẫn giữ pipeline V1 PostgreSQL/pgvector cho tới khi migration/cutover được nghiệm thu. **Chưa có frontend**.

- API-first: **không self-host** LLM hoặc embedding model.
- Baseline dùng **free model / free tier** để giữ chi phí gần $0 khi học và test.
- LLM baseline: OpenRouter + `nvidia/nemotron-3-super-120b-a12b:free`.
- Embedding baseline: Google Gemini + `gemini-embedding-001` (3072 chiều).
- Vector store: Qdrant Cloud cho ingestion V2; PostgreSQL 16 + pgvector vẫn phục vụ retrieval V1.

---

## 1. Overview

Luồng chính:

1. **Ingestion V2**: upload file → raw file local → metadata MongoDB (`UPLOADED/PROCESSING`) → loader/splitter → embedding API → upsert + verify Qdrant → activate version (`INDEXED`) hoặc ghi `FAILED`.
2. **Query/Chat**: câu hỏi → retriever (top-k) → prompt (context + question) → LLM OpenRouter → trả `answer` + `sources`.
3. **Evaluation**: golden set nhỏ → chạy qua đúng retriever/chain → metric retrieval / answer / faithfulness + latency / token usage.

Nguyên tắc thiết kế: mọi cấu hình runtime (API key, provider, model, chunk size, top_k, database URL...) lấy từ `app.config.settings`; không hard-code trong code.

---

## 2. Architecture

```text
Terminal / Client
      │ HTTP
      ▼
FastAPI  (app/api/documents.py, app/api/chat.py)
      │
      ▼
Application services
      │
      ├── Upload V2: MongoDB metadata ↔ LocalFileStorage ↔ loader/splitter/embedding ↔ Qdrant
      └── Query V1 : retriever → prompt → chain → LLM
      │
      ▼
MongoDB Atlas + Qdrant Cloud + local files    PostgreSQL/pgvector (V1 query)
```

- API layer chỉ validate request/response và gọi service; không chứa logic RAG.
- LLM và embedding là hai provider độc lập, đổi model bằng config.

---

## 3. Tech Stack

- Backend: Python 3.10+, FastAPI, Uvicorn.
- RAG framework: LangChain (`langchain-core` + các integration package rời; **không** dùng package meta `langchain`/`langgraph`).
- LLM: OpenRouter qua `langchain-openrouter` (`ChatOpenRouter`).
- Embedding: Google Gemini qua `langchain-google-genai`.
- Document loaders: `langchain-community` (+ `pypdf`, `chardet`).
- Vector store: Qdrant Cloud qua `qdrant-client` cho upload/ingestion V2; PostgreSQL + pgvector qua `langchain-postgres` vẫn dùng cho retrieval V1.
- Application database V2: MongoDB Atlas qua `pymongo`.
- Config: `pydantic-settings` (đọc `.env`).
- Infra: Docker Compose (chỉ service PostgreSQL).

---

## 4. Project Structure

```text
rag-demo/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app + GET /health
│   │   ├── config.py             # settings (đọc .env ở project root)
│   │   ├── db.py                 # PGEngine / sync engine / table_exists
│   │   ├── cloud_connections.py  # MongoDB Atlas + Qdrant Cloud lifecycle/readiness
│   │   ├── document_models.py    # MongoDB document/version/ingestion-job models
│   │   ├── document_indexes.py   # Idempotent MongoDB index specifications
│   │   ├── document_repository.py # MongoDB ingestion lifecycle repository
│   │   ├── storage.py            # FileStorage contract + local filesystem adapter
│   │   ├── ingestion.py          # P1-05 orchestration, retry và reconciliation
│   │   ├── qdrant_ingestion.py   # Qdrant upsert/verify/cleanup cho ingestion
│   │   ├── schemas.py            # Pydantic request/response
│   │   ├── api/
│   │   │   ├── documents.py      # upload / list / delete
│   │   │   └── chat.py           # /chat
│   │   └── rag/
│   │       ├── loader.py         # PDF/Markdown/TXT -> Document
│   │       ├── splitter.py       # RecursiveCharacterTextSplitter
│   │       ├── embeddings.py     # get_embeddings()
│   │       ├── llm.py            # get_llm() (ChatOpenRouter)
│   │       ├── vectorstore.py    # pgvector add/list/delete
│   │       ├── retriever.py      # as_retriever (top_k)
│   │       ├── prompt.py         # system + context + question
│   │       ├── chain.py          # LCEL RAG chain
│   │       └── pipeline.py       # index_document / answer_question / list / delete
│   ├── evaluation/
│   │   ├── corpus/               # 3 tài liệu nhỏ cho eval
│   │   ├── golden_set.json       # 9 test case
│   │   ├── metrics.py            # metric deterministic
│   │   └── results/              # output JSON của các lần chạy
│   ├── scripts/
│   │   ├── try_step.py           # load + split
│   │   ├── try_vectorstore.py    # embed + lưu pgvector
│   │   ├── try_rag.py            # retrieve + generate
│   │   ├── try_pipeline.py       # end-to-end index + chat
│   │   ├── eval_cli.py           # evaluation
│   │   ├── check_cloud_connections.py # smoke test cloud chỉ-đọc
│   │   ├── init_mongodb_indexes.py     # tạo/xác minh indexes P1-03
│   │   ├── reconcile_ingestion.py      # reconcile job bị gián đoạn
│   │   ├── smoke_qdrant_ingestion.py  # live Qdrant write/verify/cleanup
│   │   └── smoke_ingestion.py          # live end-to-end smoke namespace riêng
│   ├── requirements.txt
│   └── Dockerfile                # (hiện đang rỗng, chưa dùng)
├── data/
│   └── documents/                # nơi lưu file upload + file mẫu
├── docker-compose.yml            # PostgreSQL + pgvector
├── .env.example
├── .env                          # KHÔNG commit (đã có trong .gitignore)
└── README.md
```

> Backend chạy **local** (không nằm trong Docker Compose). `backend/Dockerfile` hiện rỗng.

---

## 5. Prerequisites

- Python **3.10+** (đã test với 3.10.11).
- Docker + Docker Compose (để chạy PostgreSQL/pgvector).
- Tài khoản/khoá:
  - **OpenRouter API key** (dùng free model): https://openrouter.ai/keys
  - **Google AI Studio API key** (free tier) cho embedding: https://aistudio.google.com/apikey

---

## 6. Environment Configuration

Tạo file `.env` ở **project root** (ngang hàng `docker-compose.yml`) từ mẫu:

```powershell
Copy-Item .env.example .env
```

Các biến (giá trị mặc định lấy từ `backend/app/config.py`):

| Biến | Mặc định | Ghi chú |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | (bắt buộc) | Key OpenRouter, dùng cho LLM |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Base URL OpenRouter |
| `LLM_MODEL` | `nvidia/nemotron-3-super-120b-a12b:free` | Model free; đổi = sửa biến này |
| `EMBEDDING_PROVIDER` | `google` | Provider embedding |
| `EMBEDDING_API_KEY` | (bắt buộc) | Key Google dạng `AIza...` |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | 3072 chiều |
| `CHUNK_SIZE` | `500` | Số ký tự mỗi chunk |
| `CHUNK_OVERLAP` | `50` | Overlap giữa 2 chunk |
| `TOP_K` | `5` | Số chunk retrieve |
| `DATABASE_URL` | `postgresql+psycopg://rag:rag_password@localhost:5433/rag` | Kết nối PostgreSQL |
| `DOCUMENTS_DIR` | `./data/documents` | Nơi lưu file upload (tính từ project root) |
| `STORAGE_BACKEND` | `local` | Backend raw-file storage; P1-04 hiện chỉ hỗ trợ `local` |
| `MONGODB_URI` | (bắt buộc cho MongoDB) | URI Atlas; giữ bí mật, ưu tiên `mongodb+srv://` |
| `MONGODB_DB_NAME` | (bắt buộc cho MongoDB) | Tên application database |
| `MONGODB_TIMEOUT_MS` | `5000` | Timeout kết nối/ping MongoDB |
| `QDRANT_URL` | (bắt buộc cho Qdrant) | Endpoint HTTPS của Qdrant Cloud; giữ bí mật |
| `QDRANT_API_KEY` | (bắt buộc cho Qdrant) | Database API key; giữ bí mật |
| `QDRANT_COLLECTION` | `rag_documents` | Collection dense vector cosine cho ingestion V2 |
| `QDRANT_TIMEOUT_SECONDS` | `5.0` | Timeout kết nối/readiness Qdrant |

Lưu ý:

- **Không commit `.env`** (đã được `.gitignore` chặn).
- `.env` luôn được đọc theo project root, không phụ thuộc thư mục chạy.
- P1-04 cung cấp `FileStorage` và `LocalFileStorage`; key dạng
  `documents/{document_id}/{version_id}/original` được sinh từ UUID nội bộ, không từ
  filename. Mỗi key là immutable, thao tác lưu trả SHA-256 và size, và mọi path đều
  được kiểm tra nằm trong `DOCUMENTS_DIR`.
- Upload P1-05 dùng storage abstraction, MongoDB lifecycle và Qdrant; activation chỉ xảy ra
  sau khi số chunk trong Qdrant được verify. Raw file/version lỗi được giữ để retry;
  `reconcile_ingestion.py` xử lý cửa sổ lỗi sau upsert/verify.
- API upload/list/get/update/re-index/delete dùng MongoDB/Qdrant/local storage. Chat/retrieval
  vẫn dùng PostgreSQL/pgvector, nên document V2 chưa được `/chat` truy hồi trước task cutover.

---

## 7. Quick Start

Chạy từ **project root**:

```powershell
# 1) Tạo .env và điền key
Copy-Item .env.example .env

# 2) Cài dependencies
pip install -r backend/requirements.txt

# 3) Chạy PostgreSQL + pgvector
docker compose up -d db

# 4) Chạy backend (mở terminal thứ hai)
Set-Location backend
uvicorn app.main:app --reload --port 8000
```

Kiểm tra API đang chạy: mở `http://127.0.0.1:8000/docs` (Swagger UI) hoặc:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Smoke test end-to-end nhanh (terminal thứ ba, từ project root):

```powershell
python backend/scripts/try_step.py        # load + split file mẫu
python backend/scripts/try_vectorstore.py # embed + lưu vào pgvector
python backend/scripts/try_rag.py "Hệ thống dùng vector database nào?"
```

Chi tiết Quick Start đầy đủ ở **cuối README** (mục 17).

---

## 8. Chạy PostgreSQL + pgvector

Chạy từ **project root**:

```powershell
docker compose up -d db
```

Thông tin container (theo `docker-compose.yml`):

- Image: `pgvector/pgvector:pg16` (PostgreSQL 16 + pgvector).
- Container: `rag-demo-postgres`.
- Port: host **5433** → container `5432` (host 5432 thường đã bị PostgreSQL native chiếm).
- User/Password/Database: `rag` / `rag_password` / `rag`.

Kiểm tra:

```powershell
docker compose ps
docker exec rag-demo-postgres pg_isready -U rag -d rag
```

Bảng vector được tạo tự động khi index lần đầu (extension `vector` cũng được tạo tự động). Với model mặc định, tên table là:

```text
rag_chunks_gemini_embedding_001
```

Dừng database:

```powershell
docker compose down          # giữ dữ liệu (volume pgdata)
docker compose down -v       # xoá luôn dữ liệu
```

---

## 9. Chạy backend

Cài dependencies (từ project root hoặc `backend/`):

```powershell
pip install -r backend/requirements.txt
```

Chạy API — **phải chạy từ thư mục `backend/`** vì app import theo package `app.*`:

```powershell
Set-Location backend
uvicorn app.main:app --reload --port 8000
```

Endpoints:

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/health` | Health check, trả `{"status": "ok", "llm_model": "..."}` |
| GET | `/health/dependencies` | Readiness MongoDB/Qdrant; HTTP 503 khi thiếu cấu hình hoặc không kết nối được, không trả secrets |
| POST | `/documents/upload` | Upload đồng bộ qua local storage + MongoDB lifecycle + Qdrant |
| GET | `/documents` | Danh sách MongoDB documents; hỗ trợ `include_deleted`, `offset`, `limit` |
| GET | `/documents/{document_id}` | Chi tiết identity, active version và lịch sử versions |
| PUT | `/documents/{document_id}` | Upload raw file mới và tạo immutable version mới |
| POST | `/documents/{document_id}/re-index` | Tạo version mới từ raw file của active version |
| DELETE | `/documents/{document_id}` | Soft-delete/unpublish, cleanup Qdrant, giữ raw file và audit history |
| POST | `/chat` | Hỏi đáp RAG, trả `answer` + `sources` |
| GET | `/docs` | Swagger UI |

Kiểm tra độc lập hai cloud connection mà không ghi dữ liệu hoặc in credentials:

```powershell
python backend/scripts/check_cloud_connections.py
```

Script trả exit code `0` chỉ khi cả MongoDB Atlas và Qdrant Cloud đều kết nối/xác thực thành công. Document APIs đã dùng MongoDB/Qdrant/local storage; riêng `/chat` vẫn dùng PostgreSQL/pgvector cho tới task migration/cutover.

MongoDB Atlas hiện có ba collection metadata cho V2: `documents`, `document_versions` và `ingestion_jobs`. Backend tạo các indexes có tên cố định khi startup; có thể chạy initializer độc lập và idempotent bằng:

```powershell
python backend/scripts/init_mongodb_indexes.py
```

`document_id`, `version_id` và `job_id` là UUID độc lập filename. Unique constraint nghiệp vụ chỉ áp dụng cho cặp `(document_id, version)`; filename và SHA-256 checksum không unique. Toàn bộ document management API dùng V2; `/chat` vẫn dùng PostgreSQL/pgvector ở giai đoạn này.

---

## 10. Upload / index document

Định dạng hỗ trợ: `.pdf`, `.md`, `.markdown`, `.txt`, `.xlsx`.

**Cách A — qua API** (backend đã chạy). Bash/WSL:

```bash
curl -X POST -F "file=@data/documents/sample_rag.md" http://127.0.0.1:8000/documents/upload
```

PowerShell:

```powershell
curl.exe -X POST -F "file=@data/documents/sample_rag.md" http://127.0.0.1:8000/documents/upload
```

Response mẫu (HTTP 201):

```json
{
  "document_id": "<uuid-v4>",
  "version_id": "<uuid-v4>",
  "job_id": "<uuid-v4>",
  "file_name": "sample_rag.md",
  "num_chunks": 7,
  "status": "INDEXED",
  "activated": true
}
```

File được lưu bằng key `documents/{document_id}/{version_id}/original`; filename không được dùng làm filesystem path. Mỗi lần gọi upload tạo một document UUID mới, kể cả khi trùng filename. `PUT` tạo version từ file mới; `re-index` tạo version từ raw file của active version. Active version chỉ đổi sau khi Qdrant verify thành công.

**Cách B — qua script** (từ project root):

```powershell
python backend/scripts/try_step.py data/documents/sample_rag.md        # chỉ load + split
python backend/scripts/try_vectorstore.py data/documents/sample_rag.md # embed + lưu pgvector
python backend/scripts/try_pipeline.py                                 # index + chat end-to-end
```

- `try_step.py` không truyền path sẽ dùng/tạo fixture `backend/fixtures/sample_rag.md`,
  không ghi vào thư mục runtime `data/documents/`.
- `try_vectorstore.py --fake` chạy offline bằng `DeterministicFakeEmbedding` (không cần API key), dùng table `..._fake`.

---

## 11. Chat / query document

API (PowerShell):

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/chat `
  -ContentType "application/json" `
  -Body '{"question": "Hệ thống dùng vector database nào?"}'
```

Bash/WSL:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Hệ thống dùng vector database nào?"}'
```

Response mẫu:

```json
{
  "answer": "Hệ thống lưu vector trong PostgreSQL 16 kèm extension pgvector.",
  "sources": [
    {"file_name": "sample_rag.md", "source": "D:\\Project\\rag-demo\\data\\documents\\sample_rag.md",
     "document_id": "sample-doc", "chunk_index": 2, "page": null}
  ]
}
```

Nếu context không chứa câu trả lời, prompt buộc model trả về: `Không tìm thấy thông tin trong tài liệu.`

Script (từ project root):

```powershell
python backend/scripts/try_rag.py "Tài liệu nói gì về chunk_size và chunk_overlap?"
```

---

## 12. Delete / list document

List:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/documents
```

Response list gồm trạng thái identity, active version, số chunk/version và cleanup state. Thêm `?include_deleted=true` để xem cả document đã soft-delete.

Get chi tiết:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/documents/<document_id>"
```

Update bằng raw file mới:

```powershell
curl.exe -X PUT -F "file=@data/documents/sample_rag.md" "http://127.0.0.1:8000/documents/<document_id>"
```

Re-index từ raw file của active version:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/documents/<document_id>/re-index"
```

Delete (thay `<document_id>` bằng UUID thật):

```powershell
Invoke-RestMethod -Method Delete -Uri "http://127.0.0.1:8000/documents/<document_id>"
```

Response mẫu:

```json
{
  "document_id": "<document_id>",
  "status": "DELETED",
  "deleted_chunks": 14,
  "raw_file_policy": "retained",
  "retained_files": 2,
  "cleanup_pending": false,
  "retrieval_eligible": false
}
```

Lưu ý:

- DELETE unpublish metadata trước (`active_version_id=null`), rồi xóa và verify toàn bộ Qdrant points theo `document_id`.
- Raw files, document versions và ingestion jobs được giữ để audit/manual recovery. Chính sách garbage collection dài hạn chưa được triển khai.
- Nếu Qdrant cleanup tạm thời lỗi, API trả HTTP `202` với `cleanup_pending=true`; gọi lại DELETE sẽ retry idempotent.
- Nếu `document_id` không tồn tại → HTTP `404`.

---

## 13. Phase 1 verification

Chạy kiểm chứng live bằng namespace test riêng (MongoDB Atlas + local raw storage +
Gemini embedding + Qdrant Cloud):

```powershell
python backend/scripts/verify_phase1.py
```

Script kiểm tra upload; bytes/checksum file gốc; metadata và số chunk; payload Qdrant
(`document_id`, `version_id`, `chunk_id`, `chunk_index`, `file_name`, `page`,
`chunk_text`); similarity retrieval; chuyển active version; failed re-index không làm
mất active version; và delete không còn retrieval hit. Dữ liệu dùng marker
`p1-07-verify-<uuid>.md`, được cleanup chính xác trên MongoDB, Qdrant và local storage.
Script không in URI, API key hoặc raw exception.

Unit test dùng loader fixture có `page=7` để xác minh page metadata được giữ qua
chunking/upsert/query. Live Markdown smoke xác minh field `page` hiện diện với giá trị
`null`, đúng vì Markdown không có page number.

Regression/evaluation hiện tại vẫn là pipeline V1 PostgreSQL/pgvector. Docker Desktop
và service `db` phải hoạt động trước khi chạy:

```powershell
docker compose up -d db
python backend/scripts/eval_cli.py
```

Nếu PostgreSQL tại cổng cấu hình không sẵn sàng, eval sẽ dừng trước bước index corpus;
không được coi là PASS.

Kết quả verification gần nhất: live V2 PASS và cleanup PASS; unit/API/in-memory
38/38 PASS. Regression/eval V1 PASS 9/9 cases, không có error; retrieval hit/recall,
answer relevance, faithfulness và fallback accuracy đều đạt `1.0`. Report:
`backend/evaluation/results/eval_20261011_150123.json`.

---

## 14. Evaluation

Evaluation đo chất lượng baseline bằng golden set nhỏ (deterministic metric, **không** dùng LLM-judge).

Chạy từ **project root**:

```powershell
python backend/scripts/eval_cli.py
python backend/scripts/eval_cli.py --no-reindex                 # bỏ qua bước index lại corpus
python backend/scripts/eval_cli.py --out backend/evaluation/results/run.json
```

Thành phần:

- `backend/evaluation/corpus/`: 3 tài liệu nhỏ (`postgresql.md`, `chunking.md`, `llm-embedding.md`).
- `backend/evaluation/golden_set.json`: 9 case (7 in-document + 2 out-of-document).
- `backend/evaluation/metrics.py`: metric deterministic.
- Corpus được index vào table **riêng** `rag_eval_gemini_embedding_001` (không đụng dữ liệu demo).
- Kết quả in ra console + lưu JSON vào `backend/evaluation/results/`.

Metric:

- **Retrieval**: `retrieval_hit` (có source đúng không) và `retrieval_recall`.
- **Answer relevance**: `answer_fact_coverage` (tỉ lệ expected facts có trong answer) → `answer_relevant`.
- **Faithfulness**: `faithfulness_ratio` (tỉ lệ token nội dung của answer có trong retrieved context), ngưỡng `0.7`; case out-of-document phải chứa đúng câu fallback.
- **Latency**: thời gian mỗi query; **Token usage**: input/output/total nếu provider trả metadata.
- Case lỗi tạm thời của provider được retry tối đa 3 lần, sau đó ghi nhận là `error` (không làm sập cả run).

---

## 15. PDF test

Loader PDF dùng `PyPDFLoader(mode="page")` nên **giữ metadata `page`** (0-based).

Cách 1 — load + split:

```powershell
python backend/scripts/try_step.py "C:\duong\dan\file.pdf"
```

Cách 2 — index + xác nhận lưu pgvector:

```powershell
python backend/scripts/try_vectorstore.py "C:\duong\dan\file.pdf"
```

Cách 3 — upload qua API:

```powershell
curl.exe -X POST -F "file=@C:\duong\dan\file.pdf" http://127.0.0.1:8000/documents/upload
```

Sau đó hỏi bằng `/chat` hoặc `python backend/scripts/try_rag.py "..."`. Source trả về sẽ có `page` (thay vì `null` như Markdown).

---

## 16. Troubleshooting

- **`docker: ... daemon is not running`**: mở Docker Desktop rồi chạy lại `docker compose up -d db`.
- **Cổng 5432 bị chiếm**: không sao — container đã được map ra host **5433**; `DATABASE_URL` cũng dùng 5433.
- **`Field required` khi import settings / API lỗi khởi động**: thiếu `.env` hoặc thiếu `OPENROUTER_API_KEY` / `EMBEDDING_API_KEY`. Tạo `.env` từ `.env.example`.
- **`/chat` trả HTTP 502** (`Lỗi RAG pipeline: ...`): lỗi khi retrieve/generate — thường do API key LLM/embedding sai, hết quota, hoặc provider quá tải. Kiểm tra key và thử lại.
- **Free model trả 429 / provider overloaded**: free model có thể bị rate-limit tạm thời; thử lại, hoặc đổi `LLM_MODEL` sang free model khác.
- **Import `app...` thất bại khi chạy uvicorn**: phải chạy từ thư mục `backend/` (`Set-Location backend`).
- **`ModuleNotFoundError: pydantic_settings`**: chưa cài dependencies → `pip install -r backend/requirements.txt`.
- **Cảnh báo `langchain-community is being sunset`**: dự kiến, không phải lỗi.
- **Tiếng Việt hiển thị lỗi trên console Windows**: các script đã tự cấu hình UTF-8; nếu vẫn lỗi, đặt `$env:PYTHONIOENCODING="utf-8"` trước khi chạy.
- **Đổi embedding model**: vector nằm ở table khác (`rag_chunks_<model>`) → **phải re-index** dữ liệu.
- **Đổi sang embedding model nhiều/ít chiều**: table mới sẽ được tạo theo số chiều thực tế (probe 1 lần), không cần cấu hình thủ công.

---

## 17. Current Limitations

- **Chưa có frontend** (ngoài scope V1); thao tác qua terminal/API.
- **Không authentication**, **không streaming**, **không chat memory/history**.
- Không reranker, hybrid search, query rewriting, không Agent/tool calling, không LangGraph/MCP.
- Backend chạy local; `docker-compose.yml` chỉ có PostgreSQL (backend **chưa** container hoá).
- Chưa tạo ANN index cho vector (đang quét tuần tự). `gemini-embedding-001` mặc định 3072 chiều > giới hạn 2000 chiều của HNSW/IVFFlat, nên muốn dùng ANN index cần giảm `output_dimensionality`.
- DELETE document V2 soft-delete metadata, xóa Qdrant points nhưng giữ raw file và audit history;
  garbage collection dài hạn chưa được triển khai.
- Với câu hỏi ngoài tài liệu, response vẫn trả `top_k` source đã retrieve kèm câu fallback (chưa lọc source không liên quan).
- Evaluation dùng **metric heuristic deterministic** (không phải ground-truth tuyệt đối); corpus nhỏ nên retrieval metric dễ bão hoà; free LLM không deterministic nên điểm có thể thay đổi giữa các lần chạy.
- Mỗi lần đổi embedding model cần re-index (kể cả corpus eval).

---

## 18. Quick Start (đầy đủ)

```powershell
# 0) Lấy source và vào project root
Set-Location D:\Project\rag-demo

# 1) Tạo .env và điền OPENROUTER_API_KEY + EMBEDDING_API_KEY
Copy-Item .env.example .env

# 2) Cài dependencies
pip install -r backend/requirements.txt

# 3) Bật PostgreSQL + pgvector (host port 5433)
docker compose up -d db
docker exec rag-demo-postgres pg_isready -U rag -d rag

# 4) Chạy backend (terminal riêng)
Set-Location backend
uvicorn app.main:app --reload --port 8000
# -> Swagger: http://127.0.0.1:8000/docs

# 5) Upload + chat thử (terminal khác, từ project root)
curl.exe -X POST -F "file=@data/documents/sample_rag.md" http://127.0.0.1:8000/documents/upload
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/chat -ContentType "application/json" -Body '{"question": "Hệ thống dùng vector database nào?"}'
Invoke-RestMethod http://127.0.0.1:8000/documents

# 6) Test pipeline bằng script
python backend/scripts/try_pipeline.py

# 7) Evaluation
python backend/scripts/eval_cli.py
```

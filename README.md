# RAG Demo (API-first)

RAG demo dùng **FastAPI + LangChain + PostgreSQL/pgvector**, gọi **LLM qua OpenRouter** và **embedding qua Google Gemini API**. Toàn bộ V1 thao tác qua terminal, script và HTTP API; **chưa có frontend**.

- API-first: **không self-host** LLM hoặc embedding model.
- Baseline dùng **free model / free tier** để giữ chi phí gần $0 khi học và test.
- LLM baseline: OpenRouter + `nvidia/nemotron-3-super-120b-a12b:free`.
- Embedding baseline: Google Gemini + `gemini-embedding-001` (3072 chiều).
- Vector store: PostgreSQL 16 + pgvector.

---

## 1. Overview

Luồng chính:

1. **Ingestion**: upload file → LangChain loader → text splitter → embedding API → lưu vector vào PostgreSQL/pgvector.
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
RAG service pipeline  (app/rag/pipeline.py)
      │
      ├── Ingestion: loader → splitter → embeddings → vectorstore
      └── Query    : retriever → prompt → chain → LLM
      │
      ▼
PostgreSQL + pgvector        OpenRouter (LLM)  +  Google Gemini (Embedding)
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
- Vector store: PostgreSQL + pgvector qua `langchain-postgres`.
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
│   │   └── eval_cli.py           # evaluation
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

Lưu ý:

- **Không commit `.env`** (đã được `.gitignore` chặn).
- `.env` luôn được đọc theo project root, không phụ thuộc thư mục chạy.

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
| POST | `/documents/upload` | Upload + index tài liệu (multipart form, field `file`) |
| GET | `/documents` | Danh sách document đã index |
| DELETE | `/documents/{document_id}` | Xoá document và toàn bộ chunk/vector liên quan |
| POST | `/chat` | Hỏi đáp RAG, trả `answer` + `sources` |
| GET | `/docs` | Swagger UI |

---

## 10. Upload / index document

Định dạng hỗ trợ: `.pdf`, `.md`, `.markdown`, `.txt`.

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
{"document_id": "upload-...", "file_name": "sample_rag.md", "num_chunks": 7}
```

File được lưu vào `DOCUMENTS_DIR`; `document_id` sinh **deterministic theo tên file**, nên **upload lại cùng tên = re-index/replace** (chunk cũ cùng `document_id` bị xoá trước khi thêm mới).

**Cách B — qua script** (từ project root):

```powershell
python backend/scripts/try_step.py data/documents/sample_rag.md        # chỉ load + split
python backend/scripts/try_vectorstore.py data/documents/sample_rag.md # embed + lưu pgvector
python backend/scripts/try_pipeline.py                                 # index + chat end-to-end
```

- `try_step.py` không truyền path sẽ tự tạo `data/documents/sample_rag.md`.
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

Response mẫu:

```json
[{"document_id": "sample-doc", "file_name": "sample_rag.md", "chunk_count": 14}]
```

Delete (thay `<document_id>` bằng id thật):

```powershell
Invoke-RestMethod -Method Delete -Uri "http://127.0.0.1:8000/documents/<document_id>"
```

Response mẫu:

```json
{"document_id": "<document_id>", "deleted_chunks": 14}
```

Lưu ý:

- DELETE xoá **vector/chunk** theo `document_id`; **không xoá file** trong `data/documents`.
- Nếu `document_id` không tồn tại → HTTP `404`.

---

## 13. Evaluation

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

## 14. PDF test

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

## 15. Troubleshooting

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

## 16. Current Limitations

- **Chưa có frontend** (ngoài scope V1); thao tác qua terminal/API.
- **Không authentication**, **không streaming**, **không chat memory/history**.
- Không reranker, hybrid search, query rewriting, không Agent/tool calling, không LangGraph/MCP.
- Backend chạy local; `docker-compose.yml` chỉ có PostgreSQL (backend **chưa** container hoá).
- Chưa tạo ANN index cho vector (đang quét tuần tự). `gemini-embedding-001` mặc định 3072 chiều > giới hạn 2000 chiều của HNSW/IVFFlat, nên muốn dùng ANN index cần giảm `output_dimensionality`.
- DELETE chỉ xoá vector/metadata, không xoá file nguồn trong `data/documents`.
- Với câu hỏi ngoài tài liệu, response vẫn trả `top_k` source đã retrieve kèm câu fallback (chưa lọc source không liên quan).
- Evaluation dùng **metric heuristic deterministic** (không phải ground-truth tuyệt đối); corpus nhỏ nên retrieval metric dễ bão hoà; free LLM không deterministic nên điểm có thể thay đổi giữa các lần chạy.
- Mỗi lần đổi embedding model cần re-index (kể cả corpus eval).

---

## 17. Quick Start (đầy đủ)

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

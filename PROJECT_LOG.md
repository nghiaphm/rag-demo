# PROJECT_LOG.md — RAG Demo

> File này là **project memory + execution log** dùng khi làm việc với AI Agent.
> Mục tiêu: giúp Agent làm từng phase theo đúng architecture, tránh tự ý đổi stack/luồng,
> đồng thời lưu lại các quyết định và output quan trọng để các phase sau không phải đọc lại toàn bộ code.

## Cách dùng file này

1. Trước khi nhờ Agent làm một phase, copy phần **"Quy tắc chung"** + **"Prompt"** của phase đó.
2. Nếu là session mới, luôn đưa kèm **"Trạng thái tổng quan"** và các phần **"Đã hoàn thành"** của dependency trực tiếp.
3. Sau khi Agent làm xong, **phải tự test** trước khi đánh dấu hoàn thành.
4. Sau khi test pass, điền **"Đã hoàn thành"** với tên file, function/class, input/output và thay đổi đáng chú ý.
5. Đổi Status: `TODO` → `IN PROGRESS` → `DONE`.
6. Mọi thay đổi architecture, package, API contract hoặc quyết định quan trọng phải ghi vào **"Ghi chú/Quyết định"**.
7. Không yêu cầu Agent làm nhiều phase trong một lần trừ khi được ghi rõ trong prompt.

---

## Mục tiêu project

> Xây dựng một **RAG demo API-first** bằng LangChain để thực hành kiến thức RAG đã học,
> có cấu trúc code đủ chuyên nghiệp để có thể mở rộng và benchmark nhiều LLM / embedding model,
> nhưng vẫn giữ scope nhỏ và kiểm soát chi phí.

### Scope V1

- Upload tài liệu.
- Load và extract text.
- Chunk tài liệu.
- Tạo embedding qua API.
- Lưu vector bằng PostgreSQL + pgvector.
- Retrieve các chunk liên quan.
- Gửi context + câu hỏi tới LLM API.
- Trả về answer + source metadata.
- Có evaluation cơ bản bằng golden set.
- Có khả năng đổi LLM / embedding bằng configuration.
- Toàn bộ V1 có thể thao tác/test qua terminal và script; chưa yêu cầu frontend.

### Non-goals của V1

- Không self-host LLM.
- Không self-host embedding model.
- Không dùng LangGraph.
- Không dùng MCP.
- Không xây Agent / tool calling.
- Không làm multi-agent.
- Không làm hybrid search / reranker / query rewriting ở V1.
- Không over-engineer thành microservices.
- Không xây frontend trong V1; frontend là phạm vi có thể cân nhắc ở giai đoạn sau.
- Không tích hợp nhiều provider chỉ để "có cho đủ"; benchmark sẽ làm ở phase riêng sau khi baseline chạy ổn.

---

# Quy tắc chung (đưa cho Agent ở MỌI session)

```text
Bạn đang làm việc trên một project RAG demo API-first.

Architecture chính:
Terminal / Client → FastAPI → LangChain → PostgreSQL + pgvector → LLM/Embedding APIs

Stack:
- Backend: Python + FastAPI
- RAG framework: LangChain
- LLM: gọi qua OpenRouter API
- Embedding: gọi qua một embedding API provider hỗ trợ qua LangChain
- Vector store: PostgreSQL + pgvector
- Frontend: Chưa triển khai trong V1; có thể bổ sung sau.
- Infrastructure: Docker Compose
- Evaluation: script/CLI + golden set; LangSmith là tùy chọn ở phase observability/evaluation

Quy tắc bắt buộc:
- API-first: KHÔNG self-host LLM hoặc embedding model.
- LangChain là framework RAG chính. Dùng abstraction/integration có sẵn của LangChain;
  KHÔNG tự viết lại logic loader, text splitting, embedding, vector store, retriever hoặc
  model client nếu LangChain đã cung cấp abstraction phù hợp.
- Không dùng LangGraph, MCP hoặc Agent framework trong V1.
- Mọi cấu hình runtime (API key, provider, model name, chunk size, chunk overlap, top_k,
  database URL...) phải lấy từ `from app.config import settings`.
- Không đọc `os.environ` trực tiếp trong các module business khác.
- Không hard-code API key, model name hoặc provider trong source code.
- Phải thiết kế LLM và Embedding có thể đổi provider/model bằng config mà không sửa pipeline chính.
- Type hint đầy đủ cho public function.
- Docstring ngắn cho public function/class khi cần.
- Không dùng bare `except:` hoặc silent fail.
- Lỗi input/config/integration phải được raise hoặc chuyển thành lỗi API rõ ràng.
- Không tạo abstraction thừa chỉ để "trông enterprise". Mỗi layer phải có trách nhiệm rõ ràng.
- Không tự ý đổi database, framework, folder structure hoặc API contract.
  Nếu thấy cần đổi, dừng lại và ghi rõ lý do trong `Ghi chú/Quyết định`.
- Chỉ làm đúng scope của phase hiện tại; không làm trước phase kế tiếp.
- Sau mỗi phase phải có cách test rõ ràng.
- Không xóa code hiện có chỉ để viết lại đẹp hơn nếu không nằm trong scope.
- Ưu tiên implementation đơn giản, dễ đọc, dễ debug và đúng với workflow RAG.

Dependency flow chính:
- Ingestion: api/documents.py -> loader -> splitter -> embeddings -> vectorstore
- Query: api/chat.py -> retriever -> prompt/chain -> LLM
- Evaluation: eval script -> cùng retriever/chain hoặc các component được chỉ định -> metrics
- `rag/` không import vòng lẫn nhau.
- API layer không tự thực hiện logic RAG; chỉ validate request và gọi service/RAG components.
```

---

## Architecture hiện tại

```text
                           ┌──────────────────┐
                           │ Terminal / Client │
                           └────────┬─────────┘
                                    │ HTTP
                                    ↓
                           ┌──────────────────┐
                           │     FastAPI      │
                           │       API        │
                           └────────┬─────────┘
                                    │
                     ┌──────────────┴──────────────┐
                     │                             │
                     ↓                             ↓
              Document Ingestion              Query / Chat
                     │                             │
                     ↓                             ↓
                 LangChain                    Retriever
                     │                             │
          ┌──────────┼──────────┐                  ↓
          ↓          ↓          ↓           PostgreSQL + pgvector
        Loader    Splitter   Embedding              │
          │          │          │                   ↓
          └──────────┴──────────┘              Top-K chunks
                     │                             │
                     └──────────────┐              │
                                    ↓              ↓
                             PostgreSQL + pgvector
                                                   │
                                                   ↓
                                            Prompt / Chain
                                                   │
                                                   ↓
                                            OpenRouter API
                                                   │
                                                   ↓
                                                 Answer
                                                   +
                                                Sources
```

### Folder structure mục tiêu

```text
rag-demo/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── schemas.py
│   │   │
│   │   ├── api/
│   │   │   ├── documents.py
│   │   │   └── chat.py
│   │   │
│   │   └── rag/
│   │       ├── loader.py
│   │       ├── splitter.py
│   │       ├── embeddings.py
│   │       ├── llm.py
│   │       ├── vectorstore.py
│   │       ├── retriever.py
│   │       ├── prompt.py
│   │       └── chain.py
│   │
│   ├── scripts/
│   │   ├── try_step.py
│   │   └── eval_cli.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── data/
│   └── documents/
│
├── docker-compose.yml
├── .env
├── .env.example
└── README.md
```

> Folder/file names ở trên là target architecture, không có nghĩa Agent được tự ý tạo tất cả ngay
> từ Phase 0. Mỗi phase chỉ tạo phần thuộc scope của phase đó.

---

## Trạng thái tổng quan

| Phase | Nội dung | Status |
|---|---|---|
| 0 | Foundation & configuration theo architecture mới | ✅ DONE |
| 1 | Document ingestion: loader + splitter | ✅ DONE |
| 2 | Embedding + PostgreSQL/pgvector vector store | ✅ DONE |
| 3 | Retrieval + prompt + LLM generation | ✅ DONE |
| 4 | Ghép thành RAG pipeline + source metadata | ✅ DONE |
| 5 | FastAPI endpoints + terminal testing | ✅ DONE |
| 6 | Evaluation với golden set | 🔲 TODO |
| 7 | Benchmark nhiều LLM / embedding model | 🔲 TODO |

> **Reset lý do:** Phase 0 cũ dùng LlamaIndex/Chroma. Architecture đã được đổi sang
> **LangChain + PostgreSQL/pgvector + API-first**, nên Phase 0–8 cần được thực hiện lại theo contract này.

---

# Phase 0 — Foundation & Configuration

**Status: ✅ DONE**

### Mục tiêu

Đưa project về đúng stack/architecture mới trước khi xây RAG pipeline.

### Prompt

```text
Bạn đang làm Phase 0 của project RAG demo.

Hãy kiểm tra source hiện tại trước khi sửa. Không giả định rằng architecture cũ là đúng.

Mục tiêu:
- Backend Python + FastAPI
- LangChain làm RAG framework
- LLM gọi qua OpenRouter API
- Embedding gọi qua provider API
- PostgreSQL + pgvector
- Docker Compose
- Frontend sẽ làm ở phase sau

Việc cần làm:
1. Cập nhật requirements.txt cho stack LangChain/FastAPI/PostgreSQL/pgvector.
2. Cập nhật app/config.py để export `settings`.
3. `.env.example` phải có config cần thiết, không chứa secret thật.
4. Database connection config dùng PostgreSQL.
5. Không tạo RAG logic ở phase này.
6. Nếu source cũ còn package/import của LlamaIndex hoặc Chroma, loại bỏ/chuyển đổi
   những phần thuộc architecture cũ trong phạm vi foundation.
7. Không tự thêm LangGraph, MCP, Agent hoặc self-host model.

Config tối thiểu cần có:
- openrouter_api_key
- openrouter_base_url (nếu integration cần)
- llm_model
- embedding_provider
- embedding_api_key
- embedding_model
- chunk_size
- chunk_overlap
- top_k
- database_url
- documents_dir

Yêu cầu test:
- Có thể import `settings`.
- App FastAPI có thể khởi động.
- Có thể kết nối PostgreSQL container sau khi Docker Compose chạy.
- Không commit secret.
```

### Đã hoàn thành

```text
- backend/requirements.txt: stack LangChain + FastAPI + PostgreSQL/pgvector.
  LangChain: langchain-core, langchain-openrouter, langchain-openai,
  langchain-text-splitters, langchain-postgres. DB: pgvector, psycopg[binary].
  Đã bỏ chromadb/openai SDK thô/tiktoken của kiến trúc cũ.
- backend/app/config.py: export `settings` (pydantic-settings), field:
  openrouter_api_key, openrouter_base_url, llm_model, embedding_provider,
  embedding_api_key, embedding_model, chunk_size, chunk_overlap, top_k,
  database_url, documents_dir. Đọc .env theo project root; extra="ignore".
- backend/app/main.py: FastAPI app + GET /health (version 0.0.1, chưa có endpoint RAG).
- docker-compose.yml: service `db` image pgvector/pgvector:pg16, healthcheck, volume;
  map host 5433 -> container 5432.
- .env.example / .env: config mới (EMBEDDING_*, DATABASE_URL PostgreSQL), chỉ placeholder.
- .gitignore: chặn commit .env + cache Python.
- Đã xóa placeholder kiến trúc cũ (rỗng): app/rag/llm_client.py, app/rag/memory.py;
  thư mục data/vectorstore (Chroma).

Test đã pass:
- `from app.config import settings` OK.
- FastAPI khởi động; GET /health -> 200 {"status": "ok", "llm_model": "..."}.
- Kết nối PostgreSQL qua chính settings.database_url OK (PostgreSQL 16.15; pgvector 0.8.6 available).
- `docker compose config` hợp lệ; container rag-demo-postgres chạy healthy.
- LangChain stack import OK; xác nhận KHÔNG có package meta `langchain` và KHÔNG có `langgraph`.
- Repo chưa init git; .env chỉ chứa placeholder, không có secret thật.
```

### Ghi chú/Quyết định

```text
- Architecture cũ LlamaIndex + Chroma đã được thay bằng LangChain + PostgreSQL/pgvector.
- Project API-first, không self-host model.
- LLM: OpenRouter qua `langchain-openrouter` (ChatOpenRouter).
- Embedding: provider độc lập với LLM, cấu hình qua EMBEDDING_PROVIDER/MODEL/API_KEY.
- KHÔNG dùng package meta `langchain`: bản 1.x kéo theo `langgraph` (vi phạm non-goal V1).
  Chỉ dùng `langchain-core` + các integration package rời.
- PostgreSQL container map host port 5433 vì host 5432 đã bị một PostgreSQL native chiếm.
  => DATABASE_URL dùng port 5433; các phase sau phải giữ đúng port này.
- config.py resolve .env theo project root (Path(__file__).parents[2] / ".env"),
  không phụ thuộc CWD khi chạy uvicorn/script.
- Docker Compose Phase 0 chỉ có service `db`; service backend + Dockerfile để phase sau.
- Đã bật Docker Desktop để test; container rag-demo-postgres đang chạy (dừng bằng `docker compose down`).
- `frontend/` tồn tại sẵn nhưng rỗng; không tạo code frontend (ngoài scope V1).
- Dependency resolver hạ pydantic xuống 2.12.5 theo yêu cầu của langchain-core.
```

---

# Phase 1 — Document Ingestion

**Status: ✅ DONE**

### Prompt

```text
Bạn đang làm Phase 1.

Mục tiêu: xây pipeline từ file → LangChain Document → chunks.

Chỉ làm:
- `app/rag/loader.py`
- `app/rag/splitter.py`
- `scripts/try_step.py`
- requirements liên quan nếu thực sự cần

Yêu cầu:
1. Dùng loader có sẵn của LangChain.
2. V1 hỗ trợ tối thiểu PDF, Markdown và TXT.
3. Trả về `list[Document]`.
4. Dùng `RecursiveCharacterTextSplitter` làm chiến lược chunk mặc định.
5. chunk_size/chunk_overlap lấy từ `settings` nếu không truyền explicit.
6. Giữ metadata nguồn như file name và page number khi loader cung cấp được.
7. Không embed ở phase này.
8. Không lưu DB ở phase này.

Test:
- Tạo file mẫu.
- Load thành công.
- Split thành nhiều chunk.
- In ra số document, số chunk và metadata của chunk đầu tiên.
```

### Đã hoàn thành

```text
- rag/loader.py: `load_document(file_path) -> list[Document]` — dispatch theo đuôi file:
  PDF dùng PyPDFLoader(mode="page"); MD/TXT dùng TextLoader(autodetect_encoding=True).
  Chuẩn hóa metadata `file_name` + `source`; giữ `page` khi loader cung cấp.
  Raise FileNotFoundError nếu file không tồn tại; ValueError nếu đuôi không hỗ trợ.
- rag/splitter.py: `split_documents(documents, chunk_size=None, chunk_overlap=None) -> list[Document]`
  dùng RecursiveCharacterTextSplitter; mặc định lấy settings.chunk_size / settings.chunk_overlap;
  giữ nguyên metadata trên từng chunk; raise ValueError nếu chunk_size <= chunk_overlap.
- scripts/try_step.py: script test load + split; tự tạo file mẫu data/documents/sample_rag.md
  nếu không truyền đường dẫn; in số document, số chunk và metadata chunk[0].
- requirements.txt: thêm langchain-community (PyPDFLoader/TextLoader), pypdf, chardet (pin <6).

Test đã pass:
- try_step.py (file mẫu .md): 1 document -> 7 chunk; metadata chunk[0] có file_name + source.
- TXT (UTF-8 tiếng Việt): 1 doc -> 6 chunk. PDF: 1 doc, metadata page=0, trích đúng text.
- Markdown (.markdown): 1 doc -> 5 chunk.
- Override chunk_size=100/overlap=10 -> 27 chunk (so với 6 mặc định).
- .csv -> ValueError; file thiếu -> FileNotFoundError; chunk_size <= overlap -> ValueError.
```

### Ghi chú/Quyết định

```text
- Loader dùng langchain-community (PyPDFLoader/TextLoader). Package này đã ở trạng thái
  "sunset" (in cảnh báo deprecation khi import) nhưng vẫn là nơi chứa loader chuẩn của
  LangChain; chưa có package standalone thay thế, và không kéo theo langgraph.
- Markdown xử lý như plain text bằng TextLoader để tránh dependency nặng `unstructured`.
- TextLoader autodetect_encoding=True cần `chardet`; pin `chardet>=5,<6` vì chardet 7.x
  phá API của langchain-community (FileEncoding ... mime_type).
- PDF dùng mode="page" để giữ metadata page (0-based).
- KHÔNG thêm chunk_index/document_id vào metadata ở phase này (thuộc Phase 2).
- try_step.py tự thêm backend vào sys.path (chạy trực tiếp được) và reconfigure stdout
  UTF-8 cho console Windows cp1252; documents_dir tương đối resolve từ project root.
```

---

# Phase 2 — Embedding + Vector Store

**Status: ✅ DONE**

### Prompt

```text
Bạn đang làm Phase 2.

Mục tiêu:
chunks → embedding API → PostgreSQL + pgvector

Chỉ làm:
- `app/rag/embeddings.py`
- `app/rag/vectorstore.py`
- `app/db.py` nếu cần
- Docker Compose PostgreSQL + pgvector nếu chưa có
- script test nhỏ

Yêu cầu:
1. Embedding phải được tạo qua LangChain Embeddings abstraction.
2. Provider/model/API key lấy từ `settings`.
3. Không tự gọi SDK embedding provider trực tiếp nếu LangChain integration tương ứng đã có.
4. Vector store dùng PostgreSQL + pgvector thông qua integration của LangChain.
5. Mỗi chunk phải giữ metadata tối thiểu:
   - document_id
   - file_name
   - chunk_index
   - page (nếu có)
6. Có khả năng add/update document.
7. Thiết kế để sau này có thể tạo collection/table/index riêng cho từng embedding model
   khi benchmark; không trộn vectors của các embedding model khác nhau trong cùng experiment.
8. Không implement retrieval logic ở phase này.

Test:
- PostgreSQL + pgvector chạy bằng Docker.
- Embedding một chunk thành công.
- Insert chunks + embeddings thành công.
- Có thể query trực tiếp vector store để xác nhận dữ liệu tồn tại.
```

### Đã hoàn thành

```text
- rag/embeddings.py: `get_embeddings() -> Embeddings` — chọn provider theo
  `settings.embedding_provider`; `google`/`google-genai`/`gemini` dùng
  GoogleGenerativeAIEmbeddings(model, google_api_key); provider khác -> ValueError.
- rag/vectorstore.py:
  + `table_name_for_embedding_model(model) -> str` (vd rag_chunks_gemini_embedding_001)
  + `get_embedding_dimension(embeddings) -> int` (probe 1 lần lúc tạo table)
  + `get_vectorstore(embeddings=None, table_name=None, *, overwrite=False) -> PGVectorStore`
  + `add_document(chunks, *, document_id=None, embeddings=None, table_name=None) -> str`
    gán metadata document_id/chunk_index, giữ file_name/page; dùng id uuid5 deterministic
    nên add lại cùng document_id là update; raise ValueError nếu chunks rỗng.
- db.py: `get_engine()` (PGEngine), `get_sync_engine()` (SQLAlchemy sync),
  `table_exists(table_name, schema_name)`; set WindowsSelectorEventLoopPolicy trên Windows
  (psycopg async mà langchain-postgres dùng không chạy trên ProactorEventLoop).
- scripts/try_vectorstore.py: test load -> split -> embedding -> pgvector -> query trực tiếp;
  cờ `--fake` dùng DeterministicFakeEmbedding để test riêng vector store khi chưa có key.
- config.py: embedding_provider="google", embedding_model="gemini-embedding-001".
- requirements.txt: thêm langchain-google-genai>=4.0.0; bỏ langchain-openai.
- .env / .env.example: EMBEDDING_PROVIDER=google, EMBEDDING_MODEL=gemini-embedding-001,
  EMBEDDING_API_KEY dạng AIza... (Google AI Studio free tier).

Test đã pass:
- Real API (Google, gemini-embedding-001): try_vectorstore.py lưu 14 chunk vào table
  rag_chunks_gemini_embedding_001; DB xác nhận cột embedding = vector(3072), 14 row;
  similarity_search trả top-1 kèm metadata đúng; chạy lại vẫn 14 row (upsert idempotent).
- Offline (--fake, pgvector thật): metadata contract (document_id/file_name/chunk_index/page);
  PDF giữ page=0; upsert không nhân đôi row; chunks rỗng -> ValueError; provider lạ -> ValueError.
- Gọi API thật với key placeholder trả 400 "API key not valid" -> xác nhận wiring LangChain đúng.
```

### Ghi chú/Quyết định

```text
- Baseline embedding = Google Gemini free tier (`gemini-embedding-001`, 3072 chiều);
  thêm `langchain-google-genai`, bỏ `langchain-openai` (tránh tích hợp provider thừa).
- Dùng API hiện hành của langchain-postgres: PGEngine + PGVectorStore (không dùng lớp
  `PGVector` deprecated).
- Mỗi embedding model có table riêng `rag_chunks_<model>` để không trộn vector giữa các model.
- Số chiều vector lấy bằng probe `embed_query` lúc tạo table; không hard-code.
- ID chunk = uuid5(document_id:chunk_index) -> add lại cùng document_id là update.
- Windows: bắt buộc WindowsSelectorEventLoopPolicy vì psycopg async (langchain-postgres)
  không chạy trên ProactorEventLoop.
- Chưa tạo ANN index (đang quét tuần tự). gemini-embedding-001 3072 chiều vượt giới hạn
  2000 chiều của HNSW/IVFFlat -> nếu cần index ở Phase 7 phải giảm output_dimensionality.
- Update chỉ ghi đè theo chunk_index; nếu số chunk giảm, chunk dư cần xử lý ở Phase 5 (DELETE).
- Giữ table rag_chunks_gemini_embedding_001 và data/documents/sample_rag.md để Phase 3 dùng.
```

---

# Phase 3 — Retrieval + Prompt + LLM

**Status: ✅ DONE**

### Prompt

```text
Bạn đang làm Phase 3.

Mục tiêu:
User query → retrieve top-k chunks → prompt → LLM answer

Chỉ làm:
- `app/rag/retriever.py`
- `app/rag/prompt.py`
- `app/rag/llm.py`
- `app/rag/chain.py`
- script test nhỏ nếu cần

Yêu cầu:
1. Retriever lấy `top_k` từ settings.
2. LLM dùng LangChain Chat Model integration cho OpenRouter.
3. Prompt phải có:
   - system instruction
   - retrieved context
   - user question
4. Prompt bắt buộc yêu cầu:
   - chỉ sử dụng context được cung cấp;
   - nếu context không đủ, nói rõ không tìm thấy thông tin trong tài liệu;
   - không tự bịa nguồn.
5. Chain phải trả về answer và raw/source documents cần thiết cho phase 4.
6. Không thêm memory/chat history ở phase này.
7. Không dùng Agent/tool calling.

Test:
- Dùng dữ liệu đã index ở Phase 2.
- Query một câu có thông tin trong tài liệu.
- Xác nhận retriever trả đúng số lượng chunk dự kiến.
- Xác nhận LLM trả lời dựa trên context.
- Test một câu không có trong tài liệu để kiểm tra fallback.
```

### Đã hoàn thành

```text
- rag/llm.py: `get_llm() -> BaseChatModel` (lru_cache) — ChatOpenRouter(model=settings.llm_model,
  api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url).
- rag/prompt.py: `get_rag_prompt() -> ChatPromptTemplate` (system instruction + human chứa
  context và question); `format_context(documents) -> str` ghép chunk kèm file/page.
- rag/retriever.py: `get_retriever(embeddings=None, table_name=None, *, top_k=None) -> BaseRetriever`
  — dùng vector store Phase 2 qua `as_retriever(search_kwargs={"k": settings.top_k})`.
- rag/chain.py: `build_rag_chain(retriever=None, llm=None, prompt=None) -> Runnable` (LCEL);
  input `str`, output `{question, documents, answer}`; `_to_prompt_inputs(payload) -> dict`.
- scripts/try_rag.py: script test question -> retrieve top-k -> prompt -> LLM -> answer + sources.
- config.py + .env/.env.example: LLM baseline dùng free model qua OpenRouter.

Test đã pass (test thực tế bằng free model `nvidia/nemotron-3-super-120b-a12b:free`):
- TEST 1 (câu hỏi có trong tài liệu): retriever trả đúng 5 chunk; LLM trả lời dựa trên context;
  output có `documents`. PASS.
- TEST 2 (câu hỏi không có trong tài liệu): LLM trả đúng fallback
  "Không tìm thấy thông tin trong tài liệu." (không suy đoán). PASS.
- TEST 3 (source metadata): output chain gồm `answer` + `documents` + `question`; 5 document,
  mỗi document đủ `source`, `file_name`, `document_id`, `chunk_index`. PASS.
```

### Ghi chú/Quyết định

```text
- Chain dùng LCEL, input là câu hỏi dạng str, output là dict gồm answer + documents
  (documents để Phase 4 lấy sources).
- Prompt bắt buộc: chỉ dùng Context; nếu thiếu thông tin phải trả lời
  "Không tìm thấy thông tin trong tài liệu"; không bịa nguồn.
- Retriever dùng đúng abstraction `as_retriever` của LangChain, không tự viết logic similarity.
- Trong lúc test, model `qwen/qwen3.8-27b:free` bị 429 (TooManyRequests) liên tục từ provider;
  đã test thành công bằng `nvidia/nemotron-3-super-120b-a12b:free`.
  => Chốt LLM baseline = `nvidia/nemotron-3-super-120b-a12b:free` (free tier), cập nhật ở
  config.py + .env/.env.example; đổi model chỉ cần sửa `LLM_MODEL`.
- Không thêm memory/chat history, Agent, tool calling, reranker, hybrid search, query rewriting.
```

---

# Phase 4 — Ghép RAG Pipeline + Sources

**Status: ✅ DONE**

### Prompt

```text
Bạn đang làm Phase 4.

Mục tiêu: ghép ingestion và query thành luồng RAG hoàn chỉnh,
nhưng chưa xây HTTP API.

Yêu cầu:
1. Tạo service/use-case rõ ràng cho:
   - index_document(...)
   - answer_question(...)
2. `answer_question(...)` phải trả:
   - answer
   - sources
3. Sources phải lấy từ metadata của các Document đã retrieve.
4. Không lưu chat history ở phase này.
5. Không tự thêm reranker, hybrid search hoặc query rewriting.
6. Chạy end-to-end hoàn toàn trong script trước khi đưa ra API.

Test:
- Index một document.
- Query document đó.
- Nhận answer + source file/page/chunk nếu có.
- Test document không tồn tại / query không có thông tin phù hợp.
```

### Đã hoàn thành

```text
- rag/pipeline.py: service/use-case layer ghép các component Phase 1–3:
  + `index_document(file_path, *, document_id=None, table_name=None) -> dict`
    = load_document -> split_documents -> add_document (pgvector);
    trả {document_id, file_name, num_chunks}.
  + `answer_question(question, *, table_name=None) -> dict`
    = get_retriever -> build_rag_chain -> {answer, sources}.
  + `_to_source(document) -> dict` trích metadata file_name/source/document_id/chunk_index/page.
- scripts/try_pipeline.py: chạy end-to-end index -> hỏi -> answer + sources.
- config.py + .env.example: chốt LLM baseline = nvidia/nemotron-3-super-120b-a12b:free
  (.env đã set sẵn). Embedding giữ google / gemini-embedding-001.

Test đã pass (end-to-end với API thật):
- Index sample_pipeline.md (document_id=sample-pipeline-doc): num_chunks=2.
- Hỏi "Chunk size và chunk overlap mặc định là bao nhiêu?" -> trả 500/50 đúng context; sources=5.
- Hỏi "Hệ thống dùng vector database nào?" -> PostgreSQL 16 + pgvector 0.8.6; sources=5.
- Hỏi ngoài tài liệu -> fallback "Không tìm thấy thông tin trong tài liệu."
- Mỗi source đủ file_name/source/document_id/chunk_index (page=None với Markdown).
- DB: sample-doc=14 chunk, sample-pipeline-doc=2 chunk.
```

### Ghi chú/Quyết định

```text
- pipeline.py là service/use-case layer; đặt trong rag/ để không tạo package mới.
- `answer_question` trả `sources` dạng dict lấy từ metadata của Document đã retrieve;
  Phase 5 sẽ map sang Pydantic schema.
- Phase 4 KHÔNG có DELETE; add_document ghi đè theo chunk_index nên chunk dư khi số chunk
  giảm chưa được dọn -> xử lý ở Phase 5 (delete theo document_id + re-index an toàn).
- Không thêm memory/chat history, reranker, hybrid search, query rewriting, Agent/LangGraph/MCP.
```

---

# Phase 5 — FastAPI + Terminal Testing

**Status: ✅ DONE**

### Prompt

```text
Bạn đang làm Phase 5.

Mục tiêu: expose RAG pipeline qua HTTP API và kiểm thử toàn bộ flow qua terminal/curl/script; chưa có frontend.

Endpoint tối thiểu:

POST /documents/upload
- Upload document.
- Validate file type.
- Lưu file.
- Gọi indexing pipeline.

GET /documents
- Danh sách document đã index.

DELETE /documents/{document_id}
- Xóa document metadata + vector data liên quan.

POST /chat
Request:
{
  "question": "..."
}

Response:
{
  "answer": "...",
  "sources": [...]
}

Yêu cầu:
- Request/response dùng Pydantic schemas.
- API layer không chứa business logic RAG.
- Error response rõ ràng.
- Không expose API key.
- Không làm streaming ở phase này trừ khi cần để giữ implementation đơn giản.
- Không thêm authentication nếu chưa nằm trong scope.
```

### Đã hoàn thành

```text
- app/schemas.py: Source, ChatRequest, ChatResponse, DocumentIndexInfo, DocumentInfo,
  DeleteDocumentResponse (Pydantic).
- app/api/documents.py: POST /documents/upload, GET /documents, DELETE /documents/{document_id}.
- app/api/chat.py: POST /chat -> pipeline.answer_question.
- app/main.py: include routers documents + chat; giữ GET /health.
- app/rag/pipeline.py: index_document delete-then-add; thêm list_documents(), delete_document().
- app/rag/vectorstore.py: thêm delete_document(document_id), list_documents()
  (SQL parameterized trên cột JSON langchain_metadata).

Test đã pass (FastAPI TestClient, API thật):
- Upload hợp lệ -> 201; num_chunks=7; DB đúng 7 row; file lưu trong data/documents.
- GET /documents -> chứa document vừa upload (chunk_count đúng).
- POST /chat có thông tin -> 200; answer bám context; sources=5; mỗi source đủ
  file_name/source/document_id/chunk_index.
- POST /chat ngoài tài liệu -> 200; fallback "Không tìm thấy thông tin trong tài liệu."
- DELETE /documents/{id} -> 200; deleted_chunks=7; DB còn 0 row; GET không còn document.
- Lỗi: .csv -> 400; delete id lạ -> 404; question "" / "   " / thiếu field -> 422.
- Re-index shrink: upload dài 17 chunk rồi ngắn 1 chunk cùng tên -> chunk_count=1, hết chunk cũ.
```

### Ghi chú/Quyết định

```text
- document_id khi upload là deterministic theo tên file: upload-<uuid5(tên_file)>;
  upload lại cùng tên = replace/re-index (đồng thời xử lý trường hợp số chunk giảm).
- delete/list dùng SQL parameterized trên cột JSON `langchain_metadata` vì
  `PGVectorStore.delete(filter=...)` chỉ hỗ trợ `metadata_columns` (document_id nằm trong JSON).
- Lỗi chat -> 502, chỉ trả tên loại exception (không lộ message/API key).
- API layer không chứa logic RAG; chỉ validate và gọi service pipeline.
- Không auth, streaming, frontend, memory, reranker, hybrid search, Agent/LangGraph/MCP.
```

---

# Phase 6 — Evaluation

**Status: 🔲 TODO**

### Prompt

```text
Bạn đang làm Phase 6.

Mục tiêu: đo chất lượng baseline RAG thay vì chỉ kiểm tra "chat có trả lời".

Tạo:
- `backend/scripts/eval_cli.py`
- `backend/evaluation/` nếu thực sự cần

Yêu cầu:
1. Tạo golden set nhỏ từ chính dữ liệu demo.
2. Mỗi case có ít nhất:
   - question
   - expected answer hoặc expected facts
   - expected source/chunk nếu phù hợp
3. Đánh giá tối thiểu:
   - retrieval correctness / relevance
   - answer relevance
   - faithfulness
4. Ghi lại latency và token usage nếu provider/integration trả metadata.
5. Không dùng benchmark công khai làm kết luận cuối cùng cho project này.
6. Output evaluation phải có thể lưu lại để so sánh các configuration khác nhau.

Ưu tiên:
- dataset nhỏ nhưng có chất lượng;
- reproducible;
- cùng một golden set cho các experiment.
```

### Đã hoàn thành

```text
[Điền sau khi test xong]
```

### Ghi chú/Quyết định

```text
[Điền nếu có thay đổi]
```


# Phase 7 — Benchmark LLM / Embedding

**Status: 🔲 TODO**

### Prompt

```text
Bạn đang làm Phase 7.

Mục tiêu: dùng project RAG hiện tại để so sánh nhiều LLM và embedding model
mà không thay đổi architecture chính.

Nguyên tắc:
1. Không benchmark trước khi baseline Phase 6 chạy ổn.
2. LLM comparison:
   - giữ nguyên embedding;
   - giữ nguyên dataset;
   - giữ nguyên retriever;
   - thay model LLM.
3. Embedding comparison:
   - giữ nguyên LLM;
   - giữ nguyên dataset;
   - giữ nguyên questions;
   - mỗi embedding model phải có vector index/store riêng;
   - không query vector của model này bằng embedding của model khác.
4. Mọi experiment phải ghi:
   - provider
   - model
   - embedding model
   - chunk_size
   - chunk_overlap
   - top_k
   - latency
   - cost/usage nếu có
   - evaluation results
5. Chỉ benchmark số lượng model cần thiết; không tạo hàng chục tổ hợp vô nghĩa.
6. Kết quả phải là dữ liệu so sánh, không hard-code "model tốt nhất" vào application.

Output mong muốn:
- experiment config
- raw results
- summary table
```

### Đã hoàn thành

```text
[Điền sau khi test xong]
```

### Ghi chú/Quyết định

```text
[Điền nếu có thay đổi]
```


## Phạm vi frontend

> Frontend **không thuộc V1**. Trong giai đoạn hiện tại, project được kiểm thử và sử dụng qua terminal, script và HTTP API.
> Có thể bổ sung Next.js ở một phase tương lai mà không thay đổi RAG core. Không tạo folder `frontend/` hoặc code frontend trong các phase V1.

# Quyết định kỹ thuật quan trọng

## 1. API-first

```text
LLM        → API
Embedding  → API
```

Không self-host trong project này.

Mục tiêu là thực hành RAG + LangChain + integration + evaluation,
không phải học vận hành GPU/model serving.

## 2. LLM provider

```text
OpenRouter
    ↓
model được cấu hình qua `LLM_MODEL`
```

OpenRouter là gateway để truy cập nhiều chat model thông qua một API; LangChain hiện có integration `ChatOpenRouter` trong package `langchain-openrouter`. 

## 3. Embedding provider

Embedding là một provider độc lập với LLM.

```text
EMBEDDING_PROVIDER
EMBEDDING_MODEL
EMBEDDING_API_KEY
```

Có thể thay provider/model ở phase benchmark mà không đổi architecture RAG.

## 4. Vector database

```text
PostgreSQL + pgvector
```

LangChain có integration `langchain-postgres` cho PostgreSQL/pgvector. Vector store dùng chung backend PostgreSQL nhưng experiment với embedding model khác nhau phải tách index/store/collection phù hợp. 

## 5. Chunking baseline

V1 dùng:

```text
RecursiveCharacterTextSplitter
```

vì đây là chiến lược baseline được LangChain khuyến nghị bắt đầu cho nhiều use case; tối ưu chunking sẽ nằm ở phase sau nếu cần. 

## 6. Cost control

Project ưu tiên:

- Dùng **free model/free tier** cho LLM và Embedding ở baseline, hướng tới chi phí gần $0 trong giai đoạn xây dựng và test RAG cơ bản.
- Không self-host LLM hoặc Embedding model.
- Dataset nhỏ.
- Không gọi API dư thừa.
- Benchmark riêng, chỉ sử dụng model trả phí khi thực sự cần so sánh.
- Khi đổi embedding model phải re-index dữ liệu tương ứng.
- Khi sử dụng model trả phí, ghi nhận provider, model và usage/cost của experiment.

---

# Checklist trước khi bắt đầu mỗi phase

```text
[ ] Đã đọc Quy tắc chung
[ ] Đã đọc dependency phase trước
[ ] Đã xác nhận scope phase hiện tại
[ ] Không đổi architecture ngoài spec
[ ] Có test trước khi DONE
[ ] Đã ghi function/class + input/output
[ ] Đã ghi quyết định phát sinh
[ ] Không để secret trong Git
```

# Checklist trước khi coi project hoàn thành V1

```text
[ ] Upload document
[ ] Parse document
[ ] Chunk document
[ ] Create embeddings
[ ] Store vectors in PostgreSQL + pgvector
[ ] Retrieve Top-K
[ ] Generate answer with LLM API
[ ] Return sources
[ ] FastAPI hoạt động
[ ] Docker Compose chạy được
[ ] Golden set evaluation chạy được
[ ] Có thể đổi LLM/embedding bằng config
[ ] README mô tả architecture + cách chạy bằng terminal/API
```

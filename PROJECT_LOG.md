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
| 0 | Foundation & configuration theo architecture mới | 🔲 TODO |
| 1 | Document ingestion: loader + splitter | 🔲 TODO |
| 2 | Embedding + PostgreSQL/pgvector vector store | 🔲 TODO |
| 3 | Retrieval + prompt + LLM generation | 🔲 TODO |
| 4 | Ghép thành RAG pipeline + source metadata | 🔲 TODO |
| 5 | FastAPI endpoints + terminal testing | 🔲 TODO |
| 6 | Evaluation với golden set | 🔲 TODO |
| 7 | Benchmark nhiều LLM / embedding model | 🔲 TODO |

> **Reset lý do:** Phase 0 cũ dùng LlamaIndex/Chroma. Architecture đã được đổi sang
> **LangChain + PostgreSQL/pgvector + API-first**, nên Phase 0–8 cần được thực hiện lại theo contract này.

---

# Phase 0 — Foundation & Configuration

**Status: 🔲 TODO**

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
[Điền sau khi test xong]
- ...
```

### Ghi chú/Quyết định

```text
- Architecture cũ LlamaIndex + Chroma đã được thay bằng LangChain + PostgreSQL/pgvector.
- Project API-first, không self-host model.
- LLM: OpenRouter.
- Embedding: provider có thể thay đổi bằng config.
```

---

# Phase 1 — Document Ingestion

**Status: 🔲 TODO**

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
[Điền sau khi test xong]
- rag/loader.py: ...
- rag/splitter.py: ...
- scripts/try_step.py: ...
```

### Ghi chú/Quyết định

```text
[Điền nếu có thay đổi]
```

---

# Phase 2 — Embedding + Vector Store

**Status: 🔲 TODO**

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
[Điền sau khi test xong]
- rag/embeddings.py: ...
- rag/vectorstore.py: ...
- db.py: ...
- docker-compose.yml: ...
```

### Ghi chú/Quyết định

```text
[Điền nếu có thay đổi]
```

---

# Phase 3 — Retrieval + Prompt + LLM

**Status: 🔲 TODO**

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
[Điền sau khi test xong]
- rag/retriever.py: ...
- rag/prompt.py: ...
- rag/llm.py: ...
- rag/chain.py: ...
```

### Ghi chú/Quyết định

```text
[Điền nếu có thay đổi]
```

---

# Phase 4 — Ghép RAG Pipeline + Sources

**Status: 🔲 TODO**

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
[Điền sau khi test xong]
- ...
```

### Ghi chú/Quyết định

```text
[Điền nếu có thay đổi]
```

---

# Phase 5 — FastAPI + Terminal Testing

**Status: 🔲 TODO**

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
[Điền sau khi test xong]
- schemas.py: ...
- api/documents.py: ...
- api/chat.py: ...
- main.py: ...
```

### Ghi chú/Quyết định

```text
[Điền nếu có thay đổi]
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
- free/low-cost model ở baseline;
- dataset nhỏ;
- không gọi API dư thừa;
- benchmark riêng;
- chỉ re-index khi đổi embedding model.

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

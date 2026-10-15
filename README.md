# RAG Demo (API-first)

RAG demo dùng FastAPI + LangChain, Groq cho LLM qua OpenAI-compatible API, Google Gemini cho embedding,
MongoDB Atlas cho document lifecycle, Qdrant Cloud cho vector retrieval và local filesystem
cho raw documents. `/chat` đã cutover sang Qdrant; PostgreSQL/pgvector không còn nằm trong
runtime hoặc dependency manifest.

Frontend Next.js: [setup/run, API env và CORS](frontend/README.md),
[demo smoke checklist và known limitations](docs/frontend-demo-readiness.md).

## Kiến trúc hiện tại

```text
Client
  │
  ▼
FastAPI
  ├── Document APIs ── MongoDB metadata ── LocalFileStorage
  │                         │
  │                         └── parse/chunk/embed ── Qdrant Cloud
  ├── Session/message models + indexes ── MongoDB Atlas ── whole-turn history loader
  └── /chat + /chat/stream ── history/budget/rewrite ── scoped Qdrant ── Groq LLM
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
- P5 history loader giữ nguyên session retrieval scope, đọc message theo stable sequence và
  chỉ trả cặp user/assistant hoàn chỉnh. Mặc định assistant `PARTIAL`, `FAILED`, `PENDING`
  hoặc `STREAMING` làm cả lượt bị loại; không đưa orphan message vào history.
- JSON và SSE dùng chung prepared-request builder. Builder snapshot active versions theo scope
  session, dùng query rewrite chỉ cho retrieval, còn generation luôn nhận original query cùng
  recent whole-turn history và ranked chunks đã nằm trong context budget.

### Luồng history-aware RAG

Với request có `session_id`, JSON và SSE cùng đi qua một luồng chuẩn bị duy nhất:

1. Đọc session scope và toàn bộ message theo stable sequence từ MongoDB; chỉ ghép các cặp
   user `COMPLETED` + assistant `COMPLETED` có cùng `request_id`. Orphan hoặc turn
   `PENDING/STREAMING/PARTIAL/FAILED` không vào history mặc định.
2. Chọn suffix các whole turns mới nhất trong history allocation. Nếu câu hỏi có dấu hiệu phụ
   thuộc ngữ cảnh, gọi rewriter; câu rewrite chỉ dùng cho retrieval. Timeout, provider error,
   output invalid hoặc thiếu lexical grounding đều fallback về original query.
3. Resolve session scope thành snapshot các `active_version_id` từ MongoDB rồi áp Qdrant filter
   server-side. `SELECTED_DOCUMENTS` chỉ nhận document còn active/`INDEXED`; missing, deleted và
   inactive version bị loại.
4. Dựng prompt trong budget cố định theo thứ tự system + whole-turn history + ranked chunks +
   original query + output reserve. System prompt không bị cắt; history không bị cắt rời turn;
   chunks giữ ranking và chỉ chunk cuối được chọn mới có thể bị prefix-truncate; query dài dùng
   head–tail truncation marker.
5. `/chat` và `/chat/stream` dùng cùng prepared prompt/sources. History chỉ giúp resolve tham
   chiếu, không phải nguồn sự thật; answer phải grounded trong Qdrant context và citation chỉ map
   từ metadata của chunk thực, đang active.

## Yêu cầu

- Python 3.10+; dự án đã được kiểm tra với Python 3.10.11.
- MongoDB Atlas cluster và database user.
- Qdrant Cloud cluster và database API key.
- Groq API key và Google AI Studio API key.
- Không cần Docker hoặc PostgreSQL để chạy backend hiện tại.

## Cấu hình

Từ project root:

```powershell
Copy-Item .env.example .env
```

| Biến | Mặc định | Mô tả |
| --- | --- | --- |
| `GROQ_API_KEY` | bắt buộc | Groq credential; không ghi vào source/log |
| `OPENAI_BASE_URL` | `https://api.groq.com/openai/v1` | Groq OpenAI-compatible API base |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Chat model đang được Groq/tier tài khoản hỗ trợ |
| `EMBEDDING_PROVIDER` | `google` | Embedding provider |
| `EMBEDDING_API_KEY` | bắt buộc | Google embedding credential |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model |
| `CHUNK_SIZE` | `500` | Chunk size |
| `CHUNK_OVERLAP` | `50` | Chunk overlap |
| `TOP_K` | `5` | Số chunks retrieve |
| `RAG_CONTEXT_WINDOW_TOKENS` | `8192` | Tổng context window dùng để kiểm tra budget |
| `RAG_SYSTEM_MAX_TOKENS` | `1024` | Allocation system instruction |
| `RAG_HISTORY_MAX_TOKENS` | `2048` | Allocation các whole turns gần nhất |
| `RAG_CHUNKS_MAX_TOKENS` | `3584` | Allocation retrieved chunks |
| `RAG_QUERY_MAX_TOKENS` | `512` | Allocation query hiện tại |
| `RAG_OUTPUT_RESERVE_TOKENS` | `1024` | Phần giữ trước cho output |
| `RAG_TOKEN_CHARS_PER_TOKEN` | `3.0` | Hệ số approximate counter đa ngôn ngữ |
| `RAG_REWRITE_TIMEOUT_SECONDS` | `15.0` | Timeout riêng cho query rewrite provider call |
| `RAG_REWRITE_MAX_CHARS` | `1000` | Độ dài tối đa của retrieval query được rewrite |
| `STREAM_TIMEOUT_SECONDS` | `120.0` | Deadline tổng cho provider SSE stream |
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
| POST | `/chat/stream` | Cùng RAG context qua typed SSE; optional `session_id` |
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

Request cũ không có `session_id` vẫn stateless. Hai field `answer` và `sources` được giữ,
response P3-01 bổ sung ID, citations, metadata, usage, status và error. Để lưu hội thoại,
gửi session đã tạo:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/chat `
  -ContentType "application/json" `
  -Body "{`"question`":`"RAG là gì?`",`"session_id`":`"$($session.session_id)`"}"
```

Ví dụ hai lượt để câu sau dùng history của cùng session:

```powershell
$session = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/sessions `
  -ContentType "application/json" -Body '{"title":"History-aware demo"}'

$first = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/chat `
  -ContentType "application/json" `
  -Body "{`"question`":`"Hệ thống dùng vector database nào?`",`"session_id`":`"$($session.session_id)`"}"

$followUp = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/chat `
  -ContentType "application/json" `
  -Body "{`"question`":`"Collection mặc định của nó tên gì?`",`"session_id`":`"$($session.session_id)`"}"
```

Không gửi message history trong request: server luôn nạp history và retrieval scope đã lưu bằng
`session_id`. Không dùng ID session của người dùng khác trong môi trường multi-user cho tới khi có
authentication/authorization đầy đủ.

Với persistent chat, backend cấp atomically hai sequence, ghi user `COMPLETED` và assistant
`PENDING` trước generation, sau đó chuyển assistant thành `COMPLETED` hoặc `FAILED`.
Hai messages dùng chung `request_id`; failure chỉ lưu error code an toàn. Token usage được
chuẩn hóa khi provider trả metadata, nếu không có thì vẫn là `null`. MongoDB atomic guard chỉ cho một generation
hoạt động trên mỗi session; request đồng thời thứ hai trả HTTP 409 và không tạo messages.
Guard chỉ được chính `request_id` sở hữu release, kể cả completion, error hoặc cancellation.

Khi request có `session_id`, retrieval chỉ dùng active versions thuộc scope lưu trên server.
Whole-turn history gần nhất được chọn theo budget; query phụ thuộc context có thể được rewrite
để retrieve, nhưng prompt tạo câu trả lời luôn giữ câu hỏi gốc. History không được dùng làm
nguồn citation; `[n]` chỉ map về ranked Qdrant chunks có metadata khớp MongoDB active version.

Response JSON thành công có một contract thống nhất. Ví dụ stateless:

```json
{
  "request_id": "11111111-1111-4111-8111-111111111111",
  "session_id": null,
  "user_message_id": null,
  "assistant_message_id": null,
  "answer": "Câu trả lời có căn cứ.",
  "sources": [],
  "citations": [],
  "metadata": {"mode": "STATELESS", "model": "provider/model"},
  "usage": null,
  "status": "COMPLETED",
  "error": null
}
```

Tất cả field trên luôn hiện diện. `sources` và `citations` luôn là array, dùng `[]` khi
không có dữ liệu. Stateless dùng `null` cho session/message IDs; persistent bắt buộc có đủ
ba ID và chúng khớp MongoDB history. `usage=null` khi provider không trả token accounting.
`COMPLETED` bắt buộc có answer khác rỗng và `error=null`; schema `FAILED` yêu cầu error
gồm `code`, message an toàn và `retryable`. Nếu generation thất bại sau khi logical reply
đã bắt đầu, `/chat` trả HTTP 502 với đầy đủ schema trên, `status=FAILED`, `answer=null`,
`sources=[]`, `citations=[]`, `usage=null` và không lộ raw provider detail. Với persistent
request, ba request/message IDs vẫn trỏ đúng failed turn đã lưu. Validation, session 404/410,
concurrency 409 và persistence 503 xảy ra trước logical reply vẫn giữ FastAPI `detail`.

Compatibility là additive, không đổi URL hoặc version: client cũ tiếp tục gửi request không
có `session_id` và chỉ đọc `answer`/`sources`; các field mới có thể được bỏ qua. Fallback
`Không tìm thấy thông tin trong tài liệu` không tạo citation giả; khi không có candidates thì
`sources=[]`, `citations=[]`. Response nhiều tài liệu giữ toàn bộ candidates trong `sources`
và chỉ đưa candidates thực sự được answer tham chiếu vào `citations`.

`sources` là toàn bộ retrieved candidates theo đúng thứ tự context `[1]…[n]`. `citations`
chỉ gồm candidates có ordinal `[n]` thực sự xuất hiện trong answer và có `chunk_id`,
`document_id`, `version_id` là UUID hợp lệ cùng `page` hợp lệ. IDs luôn lấy từ metadata
retrieval phía server; UUID/citation object do model tự viết, ordinal ngoài phạm vi,
metadata lỗi và citation trùng đều bị bỏ qua. Nếu model không emit marker thì
`citations=[]` thay vì gắn giả mọi candidate. Persistent response và MongoDB history lưu
cùng tập verified citations.

### SSE contract

P3-03 định nghĩa contract mà endpoint `/chat/stream` sử dụng cho cả stateless và persistent mode.
Mỗi frame dùng đúng `event: <name>` và `data: <JSON>`, kết thúc bằng một dòng trống. Success
transcript có thứ tự:

```text
event: start
data: {"sequence":1,"request_id":"...","session_id":"...","user_message_id":"...","assistant_message_id":"...","mode":"PERSISTENT"}

event: metadata
data: {"sequence":2,"model":"provider/model","sources":[]}

event: delta
data: {"sequence":3,"content":"Xin "}

event: delta
data: {"sequence":4,"content":"chào"}

event: done
data: {"sequence":5,"status":"COMPLETED","usage":null}
```

Nếu có verified citations, các event `citation` nằm sau `metadata` và trước `delta` đầu
tiên. Client dựng answer bằng cách nối `delta.content` theo sequence (`"Xin " + "chào"`).
Sequence bắt đầu từ 1 và liên tục; `start` duy nhất luôn đầu tiên; chỉ một terminal event
và terminal luôn cuối. `done` chỉ mang `COMPLETED` và cần ít nhất một delta. `error` thay
cho `done`: status `FAILED` nếu chưa phát delta, `PARTIAL` nếu đã phát nội dung; error chỉ
chứa code/message/retryable an toàn. Lỗi sau khi đã gửi headers phải dùng event `error`,
không đổi HTTP status giữa stream.

Mỗi source trả `file_name`, `document_id`, `version_id`, `chunk_id`, `chunk_index` và
`page` nếu loader cung cấp. `source` không chứa local filesystem path.

### POST `/chat/stream`

`POST /chat/stream` giữ nguyên `/chat` JSON và trả `Content-Type: text/event-stream`.
Request không có `session_id` giữ stateless. Request có `session_id` chuẩn bị retrieval/prompt
trước headers, sau đó atomically tạo user message và assistant `PENDING → STREAMING`; LangChain/Groq
`astream()` phát các text delta hợp lệ và backend tích lũy chúng để ghi terminal state.
Chunk control/empty bị bỏ qua; usage provider (nếu có, kể cả ở chunk không có text) được đưa
vào `done`. Transcript là `start → metadata → delta* → done`; citation theo answer ordinal
chưa được phát realtime vì contract yêu cầu citation đứng trước delta, nên được để trống thay
vì buffer toàn bộ answer. Stream thành công mới ghi `COMPLETED`; provider lỗi/no-content ghi
`PARTIAL`/`FAILED` theo content đã phát và release session guard. Provider error, output rỗng,
timeout hoặc persistence failure sau headers phát đúng một SSE `error` an toàn; không tự retry sau
khi đã phát output. `STREAM_TIMEOUT_SECONDS` (mặc định 120 giây) giới hạn toàn bộ provider stream.
Cancel/disconnect đóng downstream iterator nếu có thể, persist `RAG_STREAM_CANCELLED` và release
guard; client đã ngắt thì không thể nhận terminal frame. Response dùng `no-cache, no-transform`
và `X-Accel-Buffering: no` để hạn chế proxy buffering.
Nếu lỗi xảy ra trước headers, endpoint trả JSON HTTP 502 an toàn.

Mỗi request stream ghi một metric one-shot bằng monotonic clock: `first_event_ms`, nullable
`first_content_ms`, `total_latency_ms`, `delta_count`, mode và safe outcome. Thời gian bắt đầu
được lấy trước retrieval nên bao gồm cả pre-header preparation. Metric chỉ chứa `request_id` và
các trường vận hành trên; không log question, answer, sources hoặc credentials. Với pre-header
failure, first-event/first-content là `null`; với output rỗng, first-content là `null`.

Native `EventSource` không gửi được POST body, nên client dùng `fetch` và đọc
`ReadableStream`:

```javascript
const response = await fetch("/chat/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
  body: JSON.stringify({ question: "RAG là gì?" }),
});
if (!response.ok || !response.body) throw new Error("Stream không khởi tạo được");

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
for (;;) {
  const { value, done } = await reader.read();
  buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
  for (;;) {
    const boundary = buffer.indexOf("\n\n");
    if (boundary < 0) break;
    const frame = buffer.slice(0, boundary);
    buffer = buffer.slice(boundary + 2);
    const event = frame.match(/^event: (.+)$/m)?.[1];
    const raw = frame.match(/^data: (.+)$/m)?.[1];
    if (event && raw) console.log(event, JSON.parse(raw));
  }
  if (done) break;
}
```

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

Kiểm tra offline/unit từ project root, không cần ghi dữ liệu cloud:

```powershell
Push-Location backend
python -m unittest discover -s tests -v
python -m unittest tests.test_history tests.test_context_budget `
  tests.test_query_rewriting tests.test_rag_integration tests.test_history_evaluation -v
python -m compileall -q app evaluation scripts tests
python -m pip check
Pop-Location
```

Các smoke dưới đây dùng cloud credentials trong `.env`. Chỉ chạy với corpus không nhạy cảm.
Smoke ghi MongoDB dùng namespace/UUID riêng và cleanup chính xác; evaluation chỉ ghi vào Qdrant
collection eval tách biệt, không ghi application collection.

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

# P3-01/P3-04 unified JSON contract, legacy projection, fallback, multi-document và safe failure
python backend/scripts/smoke_response_contract.py

# P3-02 read-only real Qdrant candidate → verified citation mapping
python backend/scripts/smoke_citation_mapping.py

# P3-03 typed SSE events, ordering, terminal and reconstruction contract
python backend/scripts/smoke_sse_schema.py

# P4-01 live readiness + stateless POST SSE endpoint (mocked answer, no data write)
python backend/scripts/smoke_stream_endpoint.py

# P4-02 read-only Groq/LangChain async provider stream
python backend/scripts/smoke_provider_stream.py

# P4-03 Atlas persistent lifecycle (deterministic provider; exact cleanup)
python backend/scripts/smoke_stream_lifecycle.py

# P4-04 post-header error + timeout persistence on Atlas; exact cleanup
python backend/scripts/smoke_stream_errors.py

# P4-05 latency metrics, empty/partial streams, reconstruction + Atlas persistence
python backend/scripts/smoke_stream_metrics.py

# P5-01 Atlas session scope, stable order, paging và whole-turn filtering
python backend/scripts/smoke_history_loader.py

# P5-02 offline context allocations, recent whole turns và deterministic truncation
python backend/scripts/smoke_context_budget.py

# P5-03 offline conditional rewrite, grounding guard, fallback và metrics
python backend/scripts/smoke_query_rewriting.py

# P5-04 live selected scope, budgeted history/context và citation provenance; exact cleanup
python backend/scripts/smoke_rag_integration.py

# P5-05 paired baseline/history-aware trên isolated eval collection
python backend/scripts/eval_history_cli.py --no-reindex

# M-06 cross-phase: real Atlas/Qdrant/embedding + deterministic rewrite/generation
python backend/scripts/verify_m06.py
```

`verify_cutover.py` dùng namespace test riêng cho version/delete checks và cleanup chính
xác; không xóa demo corpus hoặc collection/database dùng chung.
`verify_phase2.py` dùng FastAPI lifespan thật qua ba lần khởi động, nhưng mock generation
deterministic để phép thử persistence không phụ thuộc quota LLM. Script tạo một session UUID
riêng trên Atlas, kiểm tra 8 messages gồm một failed turn, rồi cleanup chính xác theo ID;
không xóa collection/database dùng chung.
`verify_m06.py` dùng Atlas, Qdrant application collection, Gemini embedding và FastAPI routes
thật; rewrite/generation deterministic để kiểm tra ổn định JSON/SSE trên cùng selected-scope
session. Script chỉ tạo một session cùng messages test, không sửa document/raw file/Qdrant point,
và cleanup chính xác theo `session_id`.

Kết quả M-06 gần nhất: PASS selected active scope, whole-turn history, conditional rewrite,
JSON/SSE contracts, citation provenance và persistence trên một session test; 2 transports,
6 messages, 2 rewrite calls, 5 scoped sources mỗi transport và cleanup PASS. Groq async provider
smoke riêng PASS 13 text deltas kèm usage; full regression PASS 155/155.

## Evaluation

```powershell
python backend/scripts/eval_cli.py
python backend/scripts/eval_cli.py --no-reindex
python backend/scripts/eval_cli.py --out backend/evaluation/results/run.json
python backend/scripts/eval_history_cli.py --no-reindex
python backend/scripts/eval_history_cli.py --no-reindex --retrieval-only --out backend/evaluation/results/p5_history_retrieval.json
```

Lần chạy đầu cần `python backend/scripts/eval_history_cli.py` để index corpus eval nếu collection
chưa có dữ liệu. Các lần sau dùng `--no-reindex`. Live generation tiêu thụ quota Groq; khi quota
không khả dụng, `--retrieval-only` vẫn xác minh Qdrant retrieval, conditional rewrite và context
budget nhưng cố ý ghi các metric answer/faithfulness/referent-answer là `null`.

- Corpus: `backend/evaluation/corpus/`.
- Golden set: 9 cases, gồm 7 in-document và 2 fallback.
- Collection eval: `<QDRANT_COLLECTION>_eval`, tách khỏi application collection.
- Metrics: retrieval hit/recall, fact coverage, faithfulness proxy, fallback accuracy,
  latency và token usage nếu provider trả metadata.
- Provider errors được retry tối đa ba lần rồi ghi nhận theo case.

P5-05 dùng `history_golden_set.json` với 5 nhóm: pronoun/follow-up, topic switch,
long session, out-of-document và cross-document. Mỗi case chạy theo cặp baseline không có
history và history-aware trên cùng collection eval, sau đó ghi retrieval hit/recall, fact
coverage, faithfulness proxy, fallback/referent accuracy, context budget, latency và token.
`--retrieval-only` là đường kiểm tra an toàn khi quota generation không khả dụng; rewrite
vẫn chạy theo điều kiện và lỗi chỉ được ghi bằng loại lỗi, không ghi raw provider response.

Kết quả M-05 gần nhất: Qdrant eval PASS 9/9, không lỗi; retrieval hit/recall, answer
relevance, faithfulness và fallback accuracy đều đạt `1.0`.

Kết quả P5-05 gần nhất: paired live generation PASS 5/5; baseline và history-aware đều đạt
retrieval hit/recall, answer relevance, faithfulness proxy và fallback accuracy `1.0`;
referent accuracy `1.0`, mọi context budget hợp lệ. History-aware tăng trung bình `5873.7 ms`
và `4120` tokens trên toàn bộ 5 case so với baseline trong lần chạy này. Một long-session
rewrite timeout và một candidate bị grounding guard từ chối đều fallback nguyên query an toàn,
nhưng vẫn vượt các gate retrieval/answer; kết quả nằm tại
`backend/evaluation/results/p5_history_eval.json`.

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
│   ├── history.py              # stable whole-turn loader + session scope
│   ├── context_budget.py       # system/history/chunk/query/output allocations
│   ├── query_rewriting.py      # conditional rewrite + grounded safe fallback
│   ├── citation_mapping.py     # verified server-side source mapping
│   ├── sse_schema.py           # typed SSE contract + reconstruction rules
│   ├── stream_metrics.py       # first-event/content/total latency
│   ├── document_models.py      # Mongo records/status
│   ├── document_repository.py  # Mongo persistence
│   ├── storage.py              # FileStorage + LocalFileStorage
│   ├── ingestion.py            # raw → parse/chunk/embed → Qdrant → activate
│   ├── vector_index.py         # backend-neutral vector contract
│   ├── qdrant_ingestion.py     # Qdrant adapter
│   └── data_migration.py       # idempotent demo migration
├── evaluation/
│   ├── corpus/                   # non-sensitive isolated eval corpus
│   ├── golden_set.json           # single-turn baseline cases
│   ├── history_golden_set.json   # P5 multi-turn paired cases
│   ├── history_eval.py           # deterministic scoring/summary helpers
│   └── results/                  # timestamped and P5 reports
├── migration/demo_corpus.json
├── scripts/
│   ├── migrate_demo_corpus.py
│   ├── smoke_conversation_models.py
│   ├── smoke_session_api.py
│   ├── smoke_message_persistence.py
│   ├── smoke_session_concurrency.py
│   ├── smoke_response_contract.py
│   ├── smoke_citation_mapping.py
│   ├── smoke_sse_schema.py
│   ├── verify_phase1.py
│   ├── verify_phase2.py
│   ├── verify_m06.py
│   ├── verify_cutover.py
│   ├── eval_cli.py
│   └── eval_history_cli.py
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

- Chưa có frontend hoặc authentication. Streaming hỗ trợ lifecycle persistent, safe error/cancel,
  latency metrics và client reconstruction verification. P4-02 dùng Groq qua OpenAI-compatible API;
  live `smoke_provider_stream.py` với `openai/gpt-oss-120b` đã phát text delta và usage metadata.
- History loader, context budget và conditional rewrite đã được nối vào cả JSON/SSE runtime.
  Budget mặc định là `1024 system + 2048 history + 3584 chunks + 512 query + 1024 output
  reserve = 8192`. Startup từ chối tổng allocation vượt window. System không bị truncate;
  history chỉ lấy suffix whole turns mới nhất; chunks giữ ranking và chỉ cắt prefix chunk cuối;
  query dùng head–tail marker. Counter là xấp xỉ `3 chars/token`, không phải tokenizer chính xác
  theo model. Query rewriter chỉ gọi provider khi detector thấy tham chiếu context; original
  query luôn được giữ cho final generation, còn candidate retrieval query phải có lexical
  provenance từ original/history. Error, timeout, entity/số mới hoặc output invalid đều fallback
  original. Metrics ghi provider calls, latency và provider/estimated token cost; không suy đoán
  USD cost vì pricing phụ thuộc model/provider. Query rewrite thêm một provider call chỉ với
  follow-up được detector xác định là phụ thuộc context.
- History loader hiện đọc/paginate toàn bộ message của session rồi mới áp token budget; session
  rất dài sẽ cần giới hạn truy vấn hoặc summary tier ở bước tối ưu scale sau này.
- Dependency detector cố ý bảo thủ và lexical grounding guard không phải semantic entailment
  proof: detector có thể bỏ sót follow-up không có marker, còn rewrite hợp lệ về nghĩa có thể bị
  từ chối. Cả hai trường hợp đều dùng original query an toàn.
- `SELECTED_DOCUMENTS` đã được thực thi server-side trong runtime nhưng public Session API hiện
  chỉ tạo scope mặc định `ALL_ACTIVE` và chưa có endpoint đổi scope. Scope được snapshot lúc
  prepare; nếu active version đổi trong lúc provider đang generation, response có thể dựa trên
  version vừa hết active nhưng không thể mở rộng sang version ngoài snapshot.
- SSE phát metadata candidates trước delta nhưng hiện không phát realtime citation events, vì
  verified citation chỉ biết sau khi có toàn bộ answer trong khi contract yêu cầu citation đứng
  trước delta đầu tiên. Persistent terminal message vẫn recompute và lưu verified citations.
- Non-streaming provider call chạy trong worker thread; nếu transport disconnect không thể
  ngắt SDK call ngay, guard được giữ tới khi worker thực sự về terminal state.
- Process crash giữa generation có thể để lại persistent guard; automatic lease/stale-guard
  reconciliation chưa triển khai. P2-05 xác minh clean restart sau terminal state, không mô
  phỏng hard process kill giữa provider call.
- Chưa có tenant/document authorization đầy đủ; hiện phù hợp single-user development.
- Không reranker, hybrid search, Agent, LangGraph hoặc S3 adapter.
- Soft delete giữ raw file và audit history; chưa có garbage-collection dài hạn.
- Qdrant payload giữ chunk text để retrieval nhanh.
- Với câu hỏi ngoài tài liệu, response vẫn có thể trả top-k candidates kèm fallback.
- Evaluation dùng metrics heuristic trên corpus nhỏ; P5 baseline đã đạt retrieval `1.0` nên chưa
  chứng minh uplift retrieval dù referent answer đạt `1.0`. Provider latency/token và rewrite
  outcome có thể biến động giữa runs; report không thay thế human review hoặc production eval.
- External Groq/Google APIs nhận query/context hoặc chunk text. Không dùng tài liệu nhạy cảm trước
  khi có policy/consent, tenant authorization và đánh giá data processing phù hợp.
- Đổi embedding model/dimension yêu cầu re-index application và evaluation collections.

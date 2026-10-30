# RAG Workspace

RAG demo dùng FastAPI + LangChain, Groq cho LLM qua OpenAI-compatible API, Google Gemini cho embedding,
MongoDB Atlas cho document lifecycle, Qdrant Cloud cho vector retrieval và local filesystem
cho raw documents. `/chat` đã cutover sang Qdrant; PostgreSQL/pgvector không còn nằm trong
runtime hoặc dependency manifest.

Workspace Next.js đã có chat/session, streaming, document management, attachment và preview.
Dự án hỗ trợ **Functional Single-user RAG MVP ở mức implementation**; độ tin cậy runtime,
chất lượng ngữ nghĩa và production readiness chưa được chứng nhận. Authentication/RBAC và
multi-tenancy được defer, không phải yêu cầu chặn MVP single-user này.

Frontend Next.js: [setup/run, API env và CORS](frontend/README.md),
[demo smoke checklist và known limitations](docs/frontend-demo-readiness.md).

## Kiến trúc hiện tại

```text
Browser / Next.js workspace (gọi API trực tiếp)
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
- Evaluation mặc định dùng `rag_documents_eval`, khác application collection `rag_documents`;
  naming hiện tại không bảo đảm cách ly với mọi cấu hình. Xem [Evaluation](#evaluation).
- MongoDB có persistence contract cho `sessions` và `messages`: UUID, UTC timestamps,
  retrieval scope, message lifecycle, citations/usage/request linkage và stable sequence.
  Kết quả kiểm tra session/history/persistence qua restart được ghi nhận trong các lần chạy
  lịch sử; không phải xác minh runtime mới. Xem [Verification](#verification).
- P5 history loader giữ nguyên session retrieval scope, đọc message theo stable sequence và
  chỉ trả cặp user/assistant hoàn chỉnh. Mặc định assistant `PARTIAL`, `FAILED`, `PENDING`
  hoặc `STREAMING` làm cả lượt bị loại; không đưa orphan message vào history.
- JSON và SSE dùng chung prepared-request builder. Builder snapshot active versions theo scope
  session, dùng query rewrite chỉ cho retrieval, còn generation luôn nhận original query cùng
  recent whole-turn history và ranked chunks đã nằm trong context budget.

HTTP routes validate/map errors rồi gọi services; repositories thực hiện MongoDB operations,
ingestion điều phối raw storage/parser/vector adapter. Các bước qua MongoDB, filesystem và
Qdrant không nằm trong một distributed transaction. Nguồn chính:
[main.py](backend/app/main.py), [ingestion.py](backend/app/ingestion.py),
[conversation_service.py](backend/app/conversation_service.py),
[pipeline.py](backend/app/rag/pipeline.py). UI routes và modules ở
[README frontend](frontend/README.md#kiến-trúc-frontend).

### Luồng history-aware RAG

Với request có `session_id`, JSON và SSE cùng đi qua một luồng chuẩn bị duy nhất:

1. Đọc session scope và toàn bộ message theo stable sequence từ MongoDB; chỉ ghép các cặp
   user `COMPLETED` + assistant `COMPLETED` có cùng `request_id`. Orphan hoặc turn
   `PENDING/STREAMING/PARTIAL/FAILED` không vào history mặc định.
2. Resolve session scope thành snapshot các `active_version_id` từ MongoDB.
   `SELECTED_DOCUMENTS` chỉ nhận document còn active/`INDEXED`; missing/deleted bị loại.
3. Chọn suffix các whole turns mới nhất trong history allocation. Nếu câu hỏi có dấu hiệu phụ
   thuộc ngữ cảnh, gọi rewriter; câu rewrite chỉ dùng cho retrieval. Timeout, provider error,
   output invalid hoặc thiếu lexical grounding đều fallback về original query.
4. Retrieve với active-version filter server-side, rồi dựng prompt theo allocation system + whole-turn history + ranked chunks +
   original query + output reserve. System prompt không bị cắt; history không bị cắt rời turn;
   chunks giữ ranking và chỉ chunk cuối được chọn mới có thể bị prefix-truncate; query dài dùng
   head–tail truncation marker.
5. `/chat` và `/chat/stream` dùng cùng prepared prompt/sources. History chỉ giúp resolve tham
   chiếu, không phải nguồn sự thật; answer phải grounded trong Qdrant context và citation chỉ map
   từ metadata của chunk được chọn vào prompt, thuộc snapshot active khi chuẩn bị.

Snapshot không được liên tục revalidate trong lúc generation. `sources` chỉ gồm candidates
được chọn sau budgeting, không phải tất cả kết quả Qdrant ban đầu. Counter là ước lượng;
final rendered prompt chưa được recount và output reserve chưa được bind thành provider
output cap. Shared builder không đồng nghĩa JSON/SSE nhận guard cùng thời điểm
(xem [stream lifecycle](#post-chatstream)).

### Document ingestion và immutable versions

Hỗ trợ ingestion `.pdf`, `.txt`, `.md`, `.markdown`, `.xlsx`
([loader.py](backend/app/rag/loader.py), [excel.py](backend/app/excel.py)). PDF load theo trang;
Markdown xử lý như text; XLSX chuyển hàng thành text kèm sheet/row metadata, công thức giữ
literal, không tính toán. XLSX có giới hạn 10 MiB và kiểm tra ZIP/workbook/sheet/row/cell.

Upload lưu raw immutable → tạo document/version/job → parse/chunk → embed → ghi chunk plan →
upsert Qdrant → kiểm tra count → publish `active_version_id`. Update và re-index tạo version mới;
re-index đọc raw của active version, không sửa version cũ. Candidate lỗi thông thường không
thay active version đã publish. DELETE unpublish trước cleanup vectors và giữ raw/versions/jobs.

Retry chỉ nhận version FAILED. Reconciler chưa bao phủ job PENDING hoặc PROCESSING chưa có
chunk plan; selector giới hạn jobs trước khi lọc eligibility có thể bỏ đói job mới hơn.
Không có bảo đảm tự phục hồi toàn bộ sau process crash hay mọi tình huống concurrent cleanup.
Chi tiết: [ingestion.py](backend/app/ingestion.py),
[document_repository.py](backend/app/document_repository.py), [giới hạn](#giới-hạn-hiện-tại).

## Yêu cầu

- Python 3.10+; Python 3.10.11 là môi trường kiểm tra lịch sử, không chứng minh mọi tổ hợp
  Python/dependency hiện tại đều tương thích. Cần interpreter đang hoạt động; requirements
  dùng ranges, chưa có Python lock tái tạo bit-for-bit.
- MongoDB Atlas cluster và database user.
- Qdrant Cloud cluster và database API key.
- Groq API key và Google AI Studio API key.
- Không cần Docker hoặc PostgreSQL để chạy backend hiện tại.
- Frontend prerequisites: [Chuẩn bị](frontend/README.md#chuẩn-bị).

## Cấu hình

Từ project root:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
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
| `STREAM_TIMEOUT_SECONDS` | `120.0` | Deadline vòng lặp provider SSE, không phải toàn request/cleanup |
| `DOCUMENTS_DIR` | `./data/documents` | Raw root; path tương đối được anchor vào `PROJECT_ROOT` |
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

`create_file_storage` resolve path tương đối theo `PROJECT_ROOT`, không theo CWD; path tuyệt đối
được giữ nguyên ([storage.py](backend/app/storage.py)). Giữ CWD rõ ràng cho lệnh/module/scripts.
Chỉ browser được nhận `NEXT_PUBLIC_API_BASE_URL`; provider/database secrets thuộc backend.

## Chạy backend

```powershell
# project root
python -m pip install -r backend/requirements.txt
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Swagger: `http://127.0.0.1:8000/docs`.

Dùng interpreter tương thích đã chọn; ví dụ Windows venv hiện có là
`.\.venv\Scripts\python.exe` thay cho `python`. Lệnh cài dependency là setup, không phải hướng
dẫn sửa/xóa venv đang dùng. Backend đọc root `.env`; startup kết nối cloud và có thể tạo MongoDB
indexes. Cần namespace/data đã được phép sử dụng trước khi khởi động.

Kiểm tra dependencies:

```powershell
python backend/scripts/check_cloud_connections.py
Invoke-RestMethod http://127.0.0.1:8000/health/dependencies
```

`/health` chỉ xác nhận process/config; `/health/dependencies` trả HTTP 200 khi MongoDB/Qdrant
đều sẵn sàng, không kiểm tra Groq/Gemini. Startup/index creation không phải thao tác read-only.

## APIs

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/health` | Process health |
| GET | `/health/dependencies` | MongoDB/Qdrant readiness |
| POST | `/documents/upload` | Tạo document và active version đầu tiên |
| GET | `/documents` | List documents; có pagination và `include_deleted` |
| GET | `/documents/{document_id}` | Identity, active version và version history |
| GET | `/documents/{document_id}/versions/{version_id}/preview` | Preview đúng immutable version; text/Excel hoặc unsupported |
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
$session = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/sessions `
  -ContentType "application/json" -Body '{"title":"RAG research"}'
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

Atomic ở đây chỉ là guard acquisition/sequence reservation trên một session record.
Message-pair insertion, STREAMING transition, terminal write và release là các thao tác riêng,
có compensation best-effort; không có exactly-once logical replay guarantee. Lỗi setup có thể
để placeholder chưa terminal; lỗi release sau terminal write đã thành công có thể làm wire
outcome khác history. Xem [stream lifecycle](#post-chatstream) và [assessment](RAG-CODEBASE-ASSESSMENT-0C.md).

Khi request có `session_id`, retrieval chỉ dùng active versions thuộc scope lưu trên server.
Whole-turn history gần nhất được chọn theo budget; query phụ thuộc context có thể được rewrite
để retrieve, nhưng prompt tạo câu trả lời luôn giữ câu hỏi gốc. History không được dùng làm
nguồn citation; `[n]` chỉ map về ranked chunks đã chọn cho prompt trong active-version snapshot.
Internal scope có `ALL_ACTIVE`/`SELECTED_DOCUMENTS`; public Session API chỉ tạo `ALL_ACTIVE`,
chưa có endpoint đổi scope hoặc UI scope editor (NOT_IMPLEMENTED).

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
`sources=[]`, `citations=[]`. Response nhiều tài liệu giữ prompt-selected candidates trong `sources`
và chỉ đưa eligible candidates có raw marker trong answer vào `citations`.

`sources` là prompt-selected candidates sau budgeting theo đúng thứ tự context `[1]…[n]`,
không phải toàn bộ Qdrant retrieval hits trước budget. `citations`
chỉ gồm candidates có ordinal `[n]` thực sự xuất hiện trong answer và có `chunk_id`,
`document_id`, `version_id` là UUID hợp lệ cùng `page` hợp lệ. IDs luôn lấy từ metadata
retrieval phía server; UUID/citation object do model tự viết, ordinal ngoài phạm vi,
metadata lỗi và citation trùng đều bị bỏ qua. Nếu model không emit marker thì
`citations=[]` thay vì gắn giả mọi candidate. Persistent response và MongoDB history lưu
cùng tập verified citations.

“Verified” ở đây là ordinal/identity eligibility, không xác nhận câu trả lời được source
hỗ trợ về nghĩa. Mapper scan raw `[digits]`, có thể gồm marker trong code/link mà renderer
không biến thành nút citation. Không suy ra semantic grounding từ UUID hợp lệ.

### Attachments và version preview

`POST /chat` và `/chat/stream` nhận `attachments` là array `{document_id, version_id}`,
tối đa 20, không trùng pair và bắt buộc có `session_id`. Backend kiểm tra version thuộc document,
document chưa bị delete và version INDEXED; filename được resolve phía server. User message lưu
IDs cùng filename và history trả lại references đó
([attachment_models.py](backend/app/attachment_models.py), [attachments.py](backend/app/attachments.py)).

Ví dụ request body sau khi tạo session và upload/index thành công (thay các placeholder bằng UUID thật):

```json
{
  "question": "Tóm tắt tài liệu này",
  "session_id": "<session UUID>",
  "attachments": [{"document_id": "<document UUID>", "version_id": "<version UUID>"}]
}
```

Attachment **không tự đổi retrieval scope**. Reference có thể trỏ version INDEXED cũ trong khi
retrieval dùng current active version theo session scope; attachment không pin retrieval vào version đó.
Frontend chỉ cho gửi draft attachment khi upload result INDEXED và `activated=true`.

GET `/documents/{document_id}/versions/{version_id}/preview` trả `DocumentPreviewResponse`:
`document_id`, `version_id`, `file_name`, `kind`, nullable `text`, `sheets`, `truncated`.

| Format | Ingestion | Preview version |
| --- | --- | --- |
| TXT/MD/Markdown | Có | `kind=text`; tối đa 256 KiB, UTF-8 hoặc UTF-16 BOM |
| XLSX | Có | `kind=excel`; sheet/columns/rows có giới hạn, công thức literal |
| PDF | Có | `kind=unsupported`; chưa có PDF content viewer |

Preview đọc đúng raw version, có thể báo unavailable khi document đã delete/raw không đọc được;
không tự thay bằng active version. Đây là attachment preview, không phải citation-to-content opening.
History persist citation identities nhưng không lưu đầy đủ ordered source metadata để khôi phục
chắc chắn ordinal `[n]`; source drawer hiện không mở nội dung tài liệu.
Xem [workflow attachment](frontend/README.md#documents-attachments-và-preview) và
[citation UI](frontend/README.md#citations-và-sources).

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
và terminal luôn cuối trên luồng được xử lý bình thường. `done` chỉ mang `COMPLETED` và cần
nội dung có nghĩa. `error` thay cho `done`: status `FAILED` nếu nội dung tích lũy chỉ là
whitespace/rỗng, kể cả đã phát delta; `PARTIAL` nếu có nội dung sau Python `str.strip()`. Error chỉ
chứa code/message/retryable an toàn. Lỗi sau khi đã gửi headers phải dùng event `error`,
không đổi HTTP status giữa stream.

Các ký tự whitespace đã phát vẫn được giữ nguyên. `SSETranscript` backend hiện còn rule
delta-presence cũ và có thể reject terminal whitespace hợp lệ của runtime (C01); đây là
known mismatch chưa được sửa, không phải validator đã đồng bộ. Schema cho phép `citation`
nhưng emitter hiện chỉ gửi candidate metadata, không gửi realtime citation events.

Mỗi source trả `file_name`, `document_id`, `version_id`, `chunk_id`, `chunk_index` và
`page` nếu loader cung cấp. `source` không chứa local filesystem path.

### POST `/chat/stream`

`POST /chat/stream` giữ nguyên `/chat` JSON và trả `Content-Type: text/event-stream`.
Request không có `session_id` giữ stateless. Request có `session_id` chuẩn bị retrieval/prompt
trước headers, rồi nhận guard/cấp sequences, insert user + assistant PENDING và chuyển
assistant sang STREAMING qua các writes riêng. JSON persistent nhận guard trước khi callback
chuẩn bị RAG; SSE chuẩn bị trước rồi mới nhận guard, nên request bị 409 vẫn có thể đã làm
retrieval/rewrite và snapshot có thể cũ lúc nhận guard. LangChain/Groq
`astream()` phát các text delta hợp lệ và backend tích lũy chúng để ghi terminal state.
Chunk control/empty bị bỏ qua; usage provider (nếu có, kể cả ở chunk không có text) được đưa
vào `done`. Transcript là `start → metadata → delta* → done`; citation theo answer ordinal
chưa được phát realtime vì contract yêu cầu citation đứng trước delta, nên được để trống thay
vì buffer toàn bộ answer. Stream thành công mới ghi `COMPLETED`; provider lỗi/no-content ghi
`PARTIAL`/`FAILED` theo content đã phát và release session guard. Provider error, output rỗng,
timeout hoặc persistence failure được bắt sau headers phát SSE `error` an toàn; không tự retry sau
khi đã phát output. `STREAM_TIMEOUT_SECONDS` (mặc định 120 giây) giới hạn vòng provider iteration.
Cancel/disconnect đóng downstream iterator nếu có thể, persist `RAG_STREAM_CANCELLED` và release
guard theo cleanup path; client đã ngắt thì không thể nhận terminal frame. Response dùng `no-cache, no-transform`
và `X-Accel-Buffering: no` để hạn chế proxy buffering.
Trước headers, validation dùng 422; session missing/deleted dùng 404/410, conflict 409,
dependency/persistence unavailable 503, generation/preparation failure 502. Attachment có thêm
validation/unavailable errors theo [contract](#attachments-và-version-preview). HTTP error body
có thể là FastAPI `detail` hoặc ChatResponse theo nhánh stateless/persistent; không ép mọi lỗi
thành cùng JSON schema. Sau headers không thể đổi HTTP status, dùng SSE terminal khi xử lý được.

Deadline trên không bao phủ preparation, iterator close hay terminal persistence/release.
Setup/encoder-prefix/send lỗi và hard process kill chưa có bảo đảm cleanup toàn diện;
guard/placeholder có thể bị bỏ lại. Finalization bình thường ghi terminal trước khi emit terminal
SSE, nhưng release lỗi sau commit có thể gây wire/history mismatch. Không có automatic stale-guard
recovery. Tham khảo [chat.py](backend/app/api/chat.py),
[conversation_service.py](backend/app/conversation_service.py).

Mỗi request stream ghi một metric one-shot bằng monotonic clock: `first_event_ms`, nullable
`first_content_ms`, `total_latency_ms`, `delta_count`, mode và safe outcome. Thời gian bắt đầu
được lấy trước retrieval nên bao gồm cả pre-header preparation. Metric chỉ chứa `request_id` và
các trường vận hành trên; không log question, answer, sources hoặc credentials. Với pre-header
failure, first-event/first-content là `null`; với output rỗng, first-content là `null`.

Native `EventSource` không gửi được POST body, nên client dùng `fetch` và đọc
`ReadableStream`:

Ví dụ framing tối giản dưới đây giả định API local đã được cấu hình/CORS cho origin của trang;
không thay thế [SSE parser](frontend/lib/sse/parser.ts) và [stream validator](frontend/lib/api/chat.ts)
thực tế (ordering, terminal, abort, CRLF/multiline và error handling).

```javascript
const apiBaseUrl = "http://127.0.0.1:8000"; // Thay bằng API URL browser truy cập được.
const response = await fetch(`${apiBaseUrl}/chat/stream`, {
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

Migration có kết quả HISTORICAL_EVIDENCE với 3 documents và 68 chunks (`37/16/15`). `source_key` có
unique partial index nên rerun cùng checksum chỉ verify, không tạo document/version trùng.
Source bytes thay đổi sẽ tạo immutable version mới và chỉ activate sau khi raw checksum,
Mongo state, Qdrant count và filtered retrieval đều PASS.

Raw copies nằm dưới `data/documents/documents/...` và được `.gitignore` loại khỏi source
control; ba source files ở root vẫn được track.

Lệnh migration có thể ghi raw/MongoDB/Qdrant và gọi embeddings; chỉ chạy với data/namespace đã
được duyệt. Kết quả lịch sử không bảo đảm rerun thành công. Nguồn:
[manifest](backend/migration/demo_corpus.json), [migration](backend/app/data_migration.py).

## Verification

### Phạm vi và bằng chứng

IMPLEMENTED/SOURCE_CONFIRMED là bằng chứng mã nguồn, không tự thành runtime PASS.
Các kết quả M/P/F phase bên dưới là **HISTORICAL_EVIDENCE**, không phải chạy lại cho README này.
DESIGN_RISK là tình huống cần xác minh, không phải production incident đã chứng minh;
source-confirmed defect cũng không nhất thiết đã được tái hiện runtime. Không có official test
baseline 0C-A được công bố ở đây và không cộng các số test có thể overlap.
[Assessment](RAG-CODEBASE-ASSESSMENT-0C.md) giữ 26 finding IDs với classification gốc;
[kế hoạch reconciliation](README-GAP-REPORT-0D.md) không phải evidence chạy tests.

### Offline và tác động local

Kiểm tra offline/unit từ project root, không cần ghi dữ liệu cloud:

```powershell
Push-Location backend
python -m unittest discover -s tests -v
python -m unittest tests.test_history tests.test_context_budget `
  tests.test_query_rewriting tests.test_rag_integration tests.test_history_evaluation -v
python -m compileall -q app evaluation scripts tests
python -m pip check
Pop-Location
# Offline deterministic schema/budget/rewrite checks, từ project root
python backend/scripts/smoke_sse_schema.py
python backend/scripts/smoke_context_budget.py
python backend/scripts/smoke_query_rewriting.py
```

Unit fixtures dùng fakes/in-memory/temp files; `compileall` ghi bytecode/cache, `pip check` chỉ
kiểm tra dependency metadata, không xác nhận provider. Cần Python/dependencies hoạt động;
không suy ra interpreter bị xóa chỉ vì PATH hoặc launcher lỗi. Không tự repair venv theo README.
Frontend Node/contract/mock browser commands và yêu cầu Windows `.venv` ở
[Checks](frontend/README.md#checks-và-giới-hạn). Contract export không chạy lifespan, có network
guard; browser build/test tạo `.next` và có thể tạo artifacts, không phải kiểm tra read-only.

### Cloud/provider và thao tác ghi — cần phạm vi được duyệt riêng

Các smoke dưới đây truy cập cloud/provider theo từng script và credentials trong `.env`.
Chỉ chạy với corpus không nhạy cảm.
Nhiều smoke tạo records theo UUID riêng và có cleanup theo ID; cleanup không phải bảo đảm khi
process/crash/network lỗi. FastAPI lifespan có thể tạo indexes ngay cả khi answer được mock.
Evaluation có naming collision U01; chỉ chạy sau khi xác nhận namespace khác application,
provider budget, data và cleanup được phép. `--retrieval-only` không đồng nghĩa offline.

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

# P4-01 stateless SSE với mocked answer; lifespan vẫn có thể tạo cloud indexes
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

Kết quả lịch sử M-06 (HISTORICAL_EVIDENCE): PASS selected active scope, whole-turn history, conditional rewrite,
JSON/SSE contracts, citation provenance và persistence trên một session test; 2 transports,
6 messages, 2 rewrite calls, 5 scoped sources mỗi transport và cleanup PASS. Groq async provider
smoke riêng PASS 13 text deltas kèm usage; full regression PASS 155/155.

Các số M-06/provider/regression trên được giữ từ README lịch sử, không phải evidence mới hoặc
một report M-06 mới được tạo. Nguồn mô tả phép kiểm: [verify_m06.py](backend/scripts/verify_m06.py);
QA có [stream terminal parity](docs/bugs/stream-terminal-parity.md) và
[frontend QA](docs/frontend-functional-qa.md). Provenance của từng PASS cần đối chiếu artifact cũ
khi muốn dùng làm tiêu chí nghiệm thu; lượt chạy runtime mới phải có phạm vi được duyệt riêng.

## Evaluation

**Live/cloud/provider commands, không phải offline checks.** Mặc định index/re-index corpus
có thể delete/upsert Qdrant points và gọi Gemini; query embedding gọi Gemini, generation và
conditional rewrite gọi Groq. `--no-reindex` bỏ corpus writes nhưng vẫn truy cập cloud/providers;
`--out` ghi file kết quả, nên dùng tên run mới thay vì ghi đè evidence có sẵn.

```powershell
python backend/scripts/eval_cli.py
python backend/scripts/eval_cli.py --no-reindex
python backend/scripts/eval_cli.py --out backend/evaluation/results/run.json
python backend/scripts/eval_history_cli.py --no-reindex
python backend/scripts/eval_history_cli.py --no-reindex --retrieval-only --out backend/evaluation/results/run_retrieval.json
```

Lần chạy đầu cần `python backend/scripts/eval_history_cli.py` để index corpus eval nếu collection
chưa có dữ liệu. Các lần sau dùng `--no-reindex`. Live generation tiêu thụ quota Groq; khi quota
không khả dụng, `--retrieval-only` vẫn xác minh Qdrant retrieval, conditional rewrite và context
budget nhưng cố ý ghi các metric answer/faithfulness/referent-answer là `null`. Conditional
rewrite vẫn có thể gọi Groq; chế độ này không bảo đảm không dùng quota LLM.

- Corpus: `backend/evaluation/corpus/`.
- Golden set: 9 cases, gồm 7 in-document và 2 fallback.
- Collection eval thực tế: `f"{settings.qdrant_collection[:250]}_eval"`. Với mặc định là
  `rag_documents_eval`. U01: application name gồm 250 ký tự hợp lệ + `_eval` (tổng 255) được
  config chấp nhận và có thể bằng chính derived eval name. Chưa có guard bảo đảm namespace
  inequality; không coi isolation là phổ quát hoặc chạy eval để thử collision trên data thật.
- Metrics: retrieval hit/recall, fact coverage, faithfulness proxy, fallback accuracy,
  latency và token usage nếu provider trả metadata.
- Provider errors được retry tối đa ba lần rồi ghi nhận theo case.

P5-05 dùng `history_golden_set.json` với 5 nhóm: pronoun/follow-up, topic switch,
long session, out-of-document và cross-document. Mỗi case chạy theo cặp baseline không có
history và history-aware trên cùng collection eval, sau đó ghi retrieval hit/recall, fact
coverage, faithfulness proxy, fallback/referent accuracy, context budget, latency và token.
`--retrieval-only` bỏ answer generation khi quota generation không khả dụng; rewrite
vẫn chạy theo điều kiện và lỗi chỉ được ghi bằng loại lỗi, không ghi raw provider response.

Kết quả lịch sử M-05 (HISTORICAL_EVIDENCE): Qdrant eval PASS 9/9, không lỗi; retrieval hit/recall, answer
relevance, faithfulness và fallback accuracy đều đạt `1.0`.

Kết quả lịch sử P5-05 (HISTORICAL_EVIDENCE): paired live generation PASS 5/5; baseline và history-aware đều đạt
retrieval hit/recall, answer relevance, faithfulness proxy và fallback accuracy `1.0`;
referent accuracy `1.0`, mọi context budget hợp lệ. History-aware tăng trung bình `5873.7 ms`
và `4120` tokens trên toàn bộ 5 case so với baseline trong lần chạy này. Một long-session
rewrite timeout và một candidate bị grounding guard từ chối đều fallback nguyên query an toàn,
nhưng vẫn vượt các gate retrieval/answer; kết quả nằm tại
`backend/evaluation/results/p5_history_eval.json`.

Các giới hạn khi đọc kết quả:

- Single-turn CLI dùng alternate `build_rag_chain`; history CLI dùng shared internal preparation
  với history được cung cấp, không chạy complete HTTP/SSE/Mongo persistence/frontend flow.
- Corpus chỉ có ba Markdown ngắn; hit/recall theo filename-set không đo rank/noise, PDF/XLSX/table
  quality hay retrieval uplift khi top-k đã phủ corpus. Fact coverage/faithfulness là heuristic,
  không chứng nhận semantic grounding hoặc human-reviewed quality.
- Gate chưa kiểm tra citation usability/ordinal restoration/current UI; unsupported marker có thể
  vẫn vượt fact-based gate. UUID eligibility không phải entailment.
- Retry metrics chủ yếu giữ successful attempt; failed-attempt work/backoff/usage không được cộng
  đầy đủ (U02). Latency/tokens lịch sử không phải retry-inclusive cost ledger; missing usage không
  có nghĩa zero cost.

Nguồn: [eval_cli.py](backend/scripts/eval_cli.py), [eval_history_cli.py](backend/scripts/eval_history_cli.py),
[metrics.py](backend/evaluation/metrics.py). Historical outputs:
[M-05](backend/evaluation/results/m05_qdrant_eval.json),
[P5](backend/evaluation/results/p5_history_eval.json). Chưa có current end-to-end quality certification.

## Project structure chính

```text
backend/
├── app/
│   ├── api/                    # document/chat/session routes
│   ├── rag/                    # parse/split/embed/retrieve; pipeline JSON/SSE dùng chung
│   │   └── chain.py            # alternate LCEL chain cho single-turn evaluator
│   ├── attachments.py         # resolve immutable refs + version preview
│   ├── attachment_models.py
│   ├── excel.py               # XLSX validation, row text và bounded preview
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
│   ├── corpus/                   # non-sensitive eval inputs; namespace caveat xem Evaluation
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

frontend/
├── app/                       # /chat, /chat/[sessionId], /documents và root redirect
├── components/                # workspace, document/attachment/citation UI
├── hooks/                     # React state lifecycle
├── lib/                       # API clients, controllers, SSE parser
├── types/                     # DTOs
├── tests/                     # Node và offline contract exporter
├── e2e/                       # Playwright mock scenarios
└── scripts/                   # mock/build/browser tooling
```

## Rollback M-05

**Ghi chú lịch sử, không phải rollback runbook đã nghiệm thu cho checkout hiện tại.**
Các modules/Compose trong recipe dưới thuộc Git ref trước M-05, không phải runtime hiện tại.
Cần xác định ref, dependency compatibility và availability của container/volume/data trước khi
cân nhắc rollback; tài liệu không bảo đảm chúng vẫn tồn tại và không cấp phép thao tác dữ liệu.

Theo ghi nhận phiên M-05, cutover không xóa PostgreSQL container, volume hoặc dữ liệu cũ;
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

- Đã có [frontend workspace](frontend/README.md); authentication/RBAC/multi-tenancy được defer.
  Single-user implementation không phải production/security certification. Chưa có message
  edit/regenerate/delete, public scope editor, PDF viewer hay citation-to-content opening.
- History/rewrite/budget có trong JSON/SSE; tổng allocation mặc định
  `1024 system + 2048 history + 3584 chunks + 512 query + 1024 output reserve = 8192`.
  Startup từ chối allocation vượt window. Counter `3 chars/token` là xấp xỉ, chưa recount final
  rendered messages/bind hard output limit. Chi tiết ở [RAG flow](#luồng-history-aware-rag).
- UTF-8 text fallback có mismatch exception với TextLoader local langchain-community 0.4.2;
  non-UTF8 ingestion có thể bị parse_failed dù preview hỗ trợ UTF-16 BOM. Non-XLSX upload và
  pre-rewrite/query processing chưa có application bounds tương đương XLSX; resource exhaustion
  là rủi ro chưa đo, không phải incident đã chứng minh.
- Retry/reconciliation chưa bao phủ early interrupted jobs; bounded selector có thể starvation.
  Concurrent candidate writers/recovery và ambiguous cross-store commits vẫn cần verification,
  không có bảo đảm atomic raw/metadata/vector rollback. Xem [document lifecycle](#document-ingestion-và-immutable-versions).
- History loader hiện đọc/paginate toàn bộ message của session rồi mới áp token budget; session
  rất dài sẽ cần giới hạn truy vấn hoặc summary tier ở bước tối ưu scale sau này.
- Dependency detector cố ý bảo thủ và lexical grounding guard không phải semantic entailment
  proof: detector có thể bỏ sót follow-up không có marker, còn rewrite hợp lệ về nghĩa có thể bị
  từ chối. Cả hai trường hợp fallback original query; không có semantic intent/injection-resistance guarantee.
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
- [Evaluation](#evaluation) dùng tiny heuristic corpus; historical high scores không chứng minh
  uplift, representative PDF/XLSX quality, citation usability hay current end-to-end behavior.
  U01 isolation và retry accounting limitations chưa được sửa bởi việc cập nhật README.
- External Groq/Google APIs nhận query/context hoặc chunk text. Không dùng tài liệu nhạy cảm trước
  khi có policy/consent, tenant authorization và đánh giá data processing phù hợp.
- Đổi embedding model/dimension cần migration/re-index có kế hoạch; adapter check dimension/distance
  nhưng chưa enforce model-space identity. Same-dimension model drift là design risk, không phải
  bằng chứng collection hiện đang mixed. Không tự re-index application/eval data theo docs này.

Chi tiết và classification của 26 findings ở [assessment](RAG-CODEBASE-ASSESSMENT-0C.md),
không được coi tất cả design risks là confirmed bugs hoặc các kết quả lịch sử là current PASS.

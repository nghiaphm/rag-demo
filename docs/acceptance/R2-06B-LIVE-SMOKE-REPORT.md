# R2-06B — Controlled Live Smoke Report

Ngày hoàn tất: 2026-10-30 (Asia/Bangkok).
**Final verdict: LIVE_ACCEPTED_WITH_LIMITATIONS.**

**6/6 logical chat requests PASS; 12/12 Groq generation attempts HTTP 200; 0 observed retries, 0 HTTP 429.** JSON/SSE count và list xác nhận 6 document identities; hai knowledge requests đi RAG, không chọn metadata tools. LIVE03 không chạy vì chỉ có 6 nondeleted documents. Không tuyên bố production readiness hoặc hoàn tất mọi deferred acceptance case.

Báo cáo này thay verdict PRECHECK_BLOCKED của các lần trước. Offline R2-06A (384 regression tests, 18 probes) là historical evidence, không cộng vào số live PASS.

## A. Preflight & Authorization

### A1. Các gates đã được mở bằng authorization mới

Trong turn này, sau câu hỏi nêu đầy đủ ba điều kiện, owner trả lời: **“Xác nhận cả ba điều kiện”**:
1. Configured MongoDB là dev/test riêng, không phải production/shared customer database.
2. Cả sáu tài liệu được phép gửi metadata và nội dung sang Groq.
3. Cho phép startup initialize indexes đúng existing definitions trên chính target đó.

Đây là owner attestation trực tiếp về mục đích target và quyền dữ liệu, không phải suy luận từ filenames. Target alias khớp lần kiểm tra trước: **mongo-b24b3685a17d**; không ghi URI, hostname, credentials hoặc database name. Không đổi target/provider/model.

Authorization mới cũng cho phép request generation đầu tiên nhỏ để kiểm chứng capability/rate-limit response; không còn yêu cầu biết trước remaining quota tuyệt đối. Đã dùng chính LIVE01 JSON làm request đầu tiên, không thêm probe synthetic hay generation ngoài matrix.

### A2. Local process và phương pháp

- Python 3.10.11; FastAPI app thật, existing app.router.lifespan_context(app), existing MongoDB/Qdrant managed connections và repositories/services.
- Gọi existing /sessions, /chat và /chat/stream bằng HTTPX ASGITransport trong local test process. Không mock providers, MongoDB, Qdrant, executor, routing, retrieval, persistence hoặc lifespan.
- ASGI client không mở public server/socket: đây là live API/service/provider integration, không phải TCP/proxy/browser acceptance.
- TOOL_USE_ENABLED=true chỉ bằng process-local environment trước import settings. Model giữ **openai/gpt-oss-120b**, existing Groq credential/base URL. Không sửa prompt, top_k hoặc output-reserve configuration.
- Safe HTTP event observers trên SDK client ghi native tool calls, matching ToolMessages, status/usage/rate headers; không thay response hoặc route. Có abort guard nếu 429; nhánh đó không chạy.
- Mongo command monitoring chỉ quan sát collection/command/index metadata; không thay query/result.
- Chạy tuần tự, nghỉ 15 giây giữa metadata requests và 30 giây trước mỗi RAG request. Không whole-request retry, không load test hoặc background jobs.
- Existing SDK default max_retries=2, không thay đổi. Quan sát đúng 2 HTTP attempts/request tương ứng selector + final, nên không có observed retry.
- MongoDB và Qdrant startup health đều **connected / PASS**. Gemini/Qdrant dùng production RAG path; không thay embeddings hoặc vector store.

Installed SDK versions đã đọc: langchain-core 1.6.10, langchain-openai 1.7.2, OpenAI 3.31.0, PyMongo 4.18.3, qdrant-client 1.19.1. Credentials không xuất ra tool evidence/report.

### A3. Ground truth và version semantics

Startup refresh xác nhận **6 nondeleted identities, đều INDEXED**; cuối round count vẫn **6**. Sáu active IDs khớp manifest đã xác minh trước. Historical inventory ghi 19 DELETED / 25 total identities; con số đó không được dùng làm 25 eligible pagination items.

| Filename | Document identity | Status | Active version identity | Version number(s) |
| --- | --- | --- | --- | --- |
| test4.txt | a5f3e2c2-f6a7-4113-917b-cece0b4ed6f9 | INDEXED | f2a12c4d-4c52-43ce-a70b-b1758aec8fef | 1 |
| test4.txt | 95e77280-b241-4d19-98c5-9cb4824be4d7 | INDEXED | c2c8cc2a-9036-4771-b5f2-5c9fa36df5ad | 1 |
| test2.txt | 61d89422-f0d2-4884-8975-42dceae27534 | INDEXED | 7f001e35-a070-4cd7-bf53-854f2c21f1e1 | 1 |
| research_paper_1_ai_rag.pdf | 1f8a0e03-a248-4119-939d-f42754b22e07 | INDEXED | d56d71b8-ff15-4b25-b877-61ac4ec23a02 | 1 |
| test3.txt | 3fd92d63-f698-45b3-9e6d-c279c3e0e4d0 | INDEXED | 85b8813a-8f78-4bfa-b443-251ea8d39fa3 | 1 |
| test.txt | 10d97e16-bd86-468f-9703-a9e6403943bd | INDEXED | e6a060ae-d7d1-40ff-a120-d9570b27b6bf | 1 |

- Hai test4.txt có hai document IDs và hai version IDs riêng; mỗi identity có version number=1.
- Sáu upload user mô tả khớp sáu current identities và 5 distinct filenames. Count không deduplicate filename, không đếm versions/chunks.
- Default count expected=6; legacy RAG answer 5 không phải ground truth.
- Trước/sau live round, full projected-from-DB serialization hashes của **documents và document_versions đều bằng nhau**. Đây là checks cho mọi rows/fields đọc từ hai collections trong round, không chỉ active IDs.

### A4. Existing index comparison và DDL thực tế

Trước startup, list_indexes read-only đối chiếu 17 named specs theo ordered keys, unique, sparse và partialFilterExpression: **17 MATCH, 0 MISSING, 0 MISMATCH**.

| Collection | Index | Ordered key | Unique | Extra option | Before startup |
| --- | --- | --- | --- | --- | --- |
| documents | idx_documents_file_name | {"file_name":1} | false | — | MATCH |
| documents | uq_documents_source_key | {"source_key":1} | true | {"source_key":{"$type":"string"}} | MATCH |
| documents | idx_documents_status_updated_at | {"status":1,"updated_at":-1} | false | — | MATCH |
| documents | idx_documents_active_version_id | {"active_version_id":1} | false | sparse | MATCH |
| document_versions | uq_document_versions_document_version | {"document_id":1,"version":1} | true | — | MATCH |
| document_versions | idx_document_versions_document_created_at | {"document_id":1,"created_at":-1} | false | — | MATCH |
| document_versions | idx_document_versions_checksum | {"checksum_sha256":1} | false | — | MATCH |
| document_versions | idx_document_versions_status_updated_at | {"status":1,"updated_at":-1} | false | — | MATCH |
| ingestion_jobs | idx_ingestion_jobs_status_created_at | {"status":1,"created_at":1} | false | — | MATCH |
| ingestion_jobs | idx_ingestion_jobs_document_version_created_at | {"document_id":1,"version_id":1,"created_at":-1} | false | — | MATCH |
| sessions | idx_sessions_updated_id | {"updated_at":-1,"_id":-1} | false | — | MATCH |
| sessions | idx_sessions_user_updated_id | {"user_id":1,"updated_at":-1,"_id":-1} | false | {"user_id":{"$type":"string"}} | MATCH |
| sessions | idx_sessions_scope_updated | {"scope.mode":1,"updated_at":-1} | false | — | MATCH |
| messages | uq_messages_session_sequence | {"session_id":1,"sequence":1} | true | — | MATCH |
| messages | idx_messages_session_created_id | {"session_id":1,"created_at":1,"_id":1} | false | — | MATCH |
| messages | idx_messages_session_request | {"session_id":1,"request_id":1} | false | — | MATCH |
| messages | idx_messages_session_status_updated | {"session_id":1,"status":1,"updated_at":-1} | false | — | MATCH |

Explicit unique indexes là source_key (partial string), (document_id,version) và (session_id,sequence); **filename index không unique**, nên hai test4.txt hợp lệ.

Sau authorization, normal lifespan thực hiện **5 createIndexes commands** trên documents, document_versions, ingestion_jobs, sessions, messages, mang đúng 17 existing definitions trên. Startup thành công; không drop indexes, không đổi spec, không thêm index ngoài definitions hoặc migration. Các specs đã tồn tại matching nên không có evidence cần build index mới. Command initialization vẫn được ghi nhận là DDL, không gọi round này là read-only.

## B. Live Provider Capability

### B1. Native tool selection và correlation

| Case | Native call ID | Tool | Actual arguments | Actual tool result | Protocol |
| --- | --- | --- | --- | --- | --- |
| LIVE01_JSON | fc_fc832ae9-8380-402d-99f2-0786d915f11a | count_documents | {"include_deleted":false} | count=6 | ID match; final tool_choice=none |
| LIVE02_JSON | fc_2136ec03-30ad-42ec-a11e-ca27f4772d1f | list_documents | {"include_deleted":false,"limit":10,"offset":0} | returned_count=6, has_more=false, next_offset=null | ID match; final tool_choice=none |
| LIVE01_SSE | fc_ba05e9b7-2617-4957-a051-25d124aa0ab7 | count_documents | {"include_deleted":false} | count=6 | ID match; final tool_choice=none |
| LIVE02_SSE | fc_20d6099a-91c3-4331-a6cc-47abd2874526 | list_documents | {"include_deleted":false,"limit":20,"offset":0} | returned_count=6, has_more=false, next_offset=null | ID match; final tool_choice=none |

Cả bốn metadata selectors nhận cùng count/list tool schemas và dùng tool_choice=auto; mỗi selector trả một native structured tool call. Arguments hợp lệ, không include_deleted=true. Final provider request có native assistant tool call + ToolMessage với đúng ID, envelope ok=true. Final generation gửi **tools=[] / tool_choice=none** và không phát thêm tool call.

RAG selectors ở LIVE04_JSON và LIVE04_SSE trả **không tool calls**. Mỗi request chỉ có selector + final invocation; không có additional tool round hoặc rewrite-provider call trên fresh empty-history sessions.

### B2. Capability gate đầu tiên

LIVE01 JSON:
- Native count_documents call, arguments include_deleted=false.
- Command monitor: **đúng 1 documents aggregate/count query**, không documents retrieval/list query trong generation path.
- ToolMessage data.count=6, correlation ID khớp native call.
- Final: “Có 6 tài liệu đã được tải lên.”.
- sources=[], citations=[], HTTP 200, request status COMPLETED.
- Một user/assistant pair và guard release verified trước khi tiếp tục.
- Native usage: selector total=648, final total=370; aggregate=1018.
- Cả hai provider requests HTTP 200 và có rate-limit headers.

Capability gate đã PASS bằng real Groq/native messages; không dùng model fallback, fake output hoặc prompt sửa lại để đạt PASS.

### B3. Actual rate-limit evidence

Observed limit headers: requests=1000, tokens=8000. Theo [Groq rate-limit documentation](https://console.groq.com/docs/rate-limits), remaining-requests là daily request budget, remaining-tokens là minute token budget; không diễn giải chúng là RPM hoặc account-wide remaining TPD.

| Provider attempt | HTTP | Remaining requests | Remaining tokens | Token reset |
| --- | --- | ---: | ---: | --- |
| LIVE01_JSON/selector | 200 | 999 | 7264 | 5.52s |
| LIVE01_JSON/final | 200 | 998 | 6753 | 9.352s |
| LIVE02_JSON/selector | 200 | 997 | 7188 | 6.09s |
| LIVE02_JSON/final | 200 | 996 | 6116 | 14.129s |
| LIVE01_SSE/selector | 200 | 995 | 7229 | 5.782s |
| LIVE01_SSE/final | 200 | 994 | 7133 | 6.502s |
| LIVE02_SSE/selector | 200 | 993 | 7225 | 5.812s |
| LIVE02_SSE/final | 200 | 992 | 6149 | 13.882s |
| LIVE04_JSON/selector | 200 | 991 | 6478 | 11.415s |
| LIVE04_JSON/final | 200 | 990 | 5377 | 19.672s |
| LIVE04_SSE/selector | 200 | 989 | 7132 | 6.51s |
| LIVE04_SSE/final | 200 | 988 | 5951 | 15.367s |

Đã nhận rate-limit/reset headers từ generation thật; tất cả HTTP 200, không 429. Số remaining requests giảm 999 ->988 trong 12 calls. Đây là point-in-time evidence; không hứa quota tương lai hoặc unlimited Free Plan. Không cần suy đoán quota từ GET models như round trước.

## C. JSON/SSE Results

Prompts:
- Count: “Có bao nhiêu tài liệu đã upload?”
- List: “Hãy liệt kê các tài liệu tôi đã tải lên.”
- Knowledge: “Theo research_paper_1_ai_rag.pdf, RAG kết hợp truy xuất và sinh câu trả lời như thế nào?”

| Case | Request ID | Endpoint | Result | Actual route/tool | End-to-end ms |
| --- | --- | --- | --- | --- | ---: |
| LIVE01_JSON | 45a7ee39-7246-4913-b443-da9f33199e31 | /chat | PASS | count_documents | 2281 |
| LIVE02_JSON | 18dadf09-d6c5-4c53-9ef4-59f6ababd291 | /chat | PASS | list_documents | 2844 |
| LIVE01_SSE | d5e22743-3f4a-43bf-9c70-6e03805a796b | /chat/stream | PASS | count_documents | 2203 |
| LIVE02_SSE | 694f5bbb-8cad-47a8-940d-cb0e439b0d0d | /chat/stream | PASS | list_documents | 3047 |
| LIVE04_JSON | 031b2f83-227a-42e1-803f-5b64e5046383 | /chat | PASS | RAG (no tools) | 6406 |
| LIVE04_SSE | 132687a1-3ed1-4735-9b17-23bc0b0581e0 | /chat/stream | PASS | RAG (no tools) | 6906 |
| LIVE03 pagination | — | JSON/SSE | NOT_RUN_DATASET_UNAVAILABLE | Chỉ 6 eligible identities | — |

### C1. Expected vs actual assertions

| Check | Expected | Actual | Status |
| --- | --- | --- | --- |
| JSON count / SSE count | Exact 6 identities | Tool result=6, answer nêu 6; đúng một count query mỗi request | PASS ×2 |
| JSON list / SSE list | Sáu distinct IDs; test4.txt hai dòng | Internal result IDs bằng active manifest; final answer giữ cả hai test4.txt với hai IDs riêng | PASS ×2 |
| Pagination completeness của page hiện tại | offset=0, page đủ 6; has_more=false | JSON limit=10, SSE limit=20; cả hai returned_count=6, has_more=false, next_offset=null | PASS |
| Metadata sources/citations | Rỗng | Wire sources=[], JSON citations=[], persisted citations=[] | PASS |
| Final options | Không thêm tool round | All final requests tool_choice=none, không tools/native calls bổ sung | PASS |
| RAG routing | Không metadata tools | Hai selectors no tool calls, production RAG xử lý | PASS ×2 |
| RAG scope | Chỉ eligible active versions của session | Fresh sessions scope ALL_ACTIVE; 5 sources đều thuộc published PDF identity/version trong active set | PASS cho ALL_ACTIVE |
| JSON DTO / SSE transcript | Existing contract | ChatResponse/SSETranscript validate; không thêm fields/events | PASS |

Sáu final answers nguyên bản dưới đây là model outputs, không được sửa nội dung để đạt assertions. Dataset đã được owner xác nhận an toàn; không ghi source document bodies hoặc credentials.

### LIVE01_JSON — actual final answer

> Có 6 tài liệu đã được tải lên.

### LIVE02_JSON — actual final answer

> Dưới đây là các tài liệu mà bạn đã tải lên (được trả về từ thư viện của bạn):
> 
> | Tên tệp | ID tài liệu | Trạng thái | Ngày tạo |
> |---|---|---|---|
> | test4.txt | a5f3e2c2-f6a7-4113-917b-cece0b4ed6f9 | INDEXED | 2026‑10‑29 14:28:23 |
> | test4.txt | 95e77280-b241-4d19-98c5-9cb4824be4d7 | INDEXED | 2026‑10‑29 14:28:10 |
> | test2.txt | 61d89422-f0d2-4884-8975-42dceae27534 | INDEXED | 2026‑10‑29 14:27:46 |
> | research_paper_1_ai_rag.pdf | 1f8a0e03-a248-4119-939d-f42754b22e07 | INDEXED | 2026‑10‑29 14:27:17 |
> | test3.txt | 3fd92d63-f698-45b3-9e6d-c279c3e0e4d0 | INDEXED | 2026‑10‑28 08:01:59 |
> | test.txt | 10d97e16-bd86-468f-9703-a9e6403943bd | INDEXED | 2026‑10‑28 08:00:31 |
> 
> *Danh sách này bao gồm toàn bộ tài liệu hiện có trong thư viện của bạn (has_more = false, truncated_by_bytes = false).*

### LIVE01_SSE — actual final answer

> Có **6** tài liệu đã được upload.

### LIVE02_SSE — actual final answer

> Dưới đây là danh sách các tài liệu mà bạn đã tải lên (được liệt kê theo thời gian tạo mới nhất trước):
> 
> | Tên tệp | ID tài liệu | Trạng thái |
> |---|---|---|
> | test4.txt | a5f3e2c2-f6a7-4113-917b-cece0b4ed6f9 | INDEXED |
> | test4.txt | 95e77280-b241-4d19-98c5-9cb4824be4d7 | INDEXED |
> | test2.txt | 61d89422-f0d2-4884-8975-42dceae27534 | INDEXED |
> | research_paper_1_ai_rag.pdf | 1f8a0e03-a248-4119-939d-f42754b22e07 | INDEXED |
> | test3.txt | 3fd92d63-f698-45b3-9e6d-c279c3e0e4d0 | INDEXED |
> | test.txt | 10d97e16-bd86-468f-9703-a9e6403943bd | INDEXED |
> 
> *Lưu ý:* Kết quả trên là toàn bộ tài liệu trong thư viện của bạn vì trang trả về có `has_more = false` và `truncated_by_bytes = false`.

### LIVE04_JSON — actual final answer

> RAG hoạt động theo một quy trình gồm hai bước chính:
> 
> 1. **Truy xuất (retrieval)** – Hệ thống chia tài liệu nguồn thành các đoạn (chunks), chuyển chúng thành biểu diễn vector và tìm các đoạn có nghĩa semantically liên quan nhất với câu hỏi của người dùng. Các đoạn này được lấy ra như “bằng chứng” cho câu hỏi.  
>    *Nguồn: [4]*  
> 
> 2. **Sinh (generation)** – Các đoạn đã được truy xuất được đưa vào làm ngữ cảnh cho mô hình ngôn ngữ lớn (LLM). LLM sau đó tạo ra câu trả lời dựa trên ngữ cảnh này, thay vì chỉ dựa vào kiến thức nội tại của mình. Như vậy câu trả lời được “đóng băng” (grounded) trong bằng chứng đã thu thập.  
>    *Nguồn: [1]*  
> 
> Nhờ việc tách riêng chất lượng truy xuất và sinh, RAG cho phép kết hợp thông tin mới, riêng tư hoặc thay đổi thường xuyên với khả năng sinh ngôn ngữ tự nhiên của LLM.  
> 
> (Tham khảo: [4], [1])

### LIVE04_SSE — actual final answer

> RAG (Retrieval‑Augmented Generation) hoạt động theo một quy trình hai bước:
> 
> 1. **Truy xuất** – Hệ thống chuyển đổi các tài liệu nguồn thành các đoạn (chunks), mã hoá chúng thành biểu diễn vector và thực hiện tìm kiếm ngữ nghĩa để lấy những đoạn liên quan nhất với truy vấn của người dùng [4].
> 
> 2. **Sinh câu trả lời** – Các đoạn đã được truy xuất được đưa vào như “bối cảnh” cho mô hình ngôn ngữ lớn (LLM). LLM sau đó tạo ra câu trả lời dựa trên thông tin trong bối cảnh này, giúp câu trả lời được “đánh rễ” (grounded) trong bằng chứng và có thể kèm theo tham chiếu nguồn [1].
> 
> Như vậy, RAG kết hợp việc lấy thông tin từ kho kiến thức (retrieval) với việc sinh ngôn ngữ (generation) để cung cấp câu trả lời có căn cứ và có thể kiểm chứng.

### C2. Ordered RAG source/citation identity

Cả hai RAG requests trả cùng ordered sources, cùng document **1f8a0e03-a248-4119-939d-f42754b22e07**, version **d56d71b8-ff15-4b25-b877-61ac4ec23a02**, file research_paper_1_ai_rag.pdf:

| Ordinal | Chunk ID | Chunk index | Page |
| --- | --- | ---: | ---: |
| 1 | 837b38d1-cf4c-5376-ac5c-58bfdfbede40 | 8 | 1 |
| 2 | 0437c7fc-95d9-5459-9580-aa049640fbfa | 1 | 0 |
| 3 | a47c55bb-b5d7-5aa4-a102-7f533cdc6a6c | 3 | 0 |
| 4 | caa83424-0c3c-5f45-972f-a9e9b2cc8bef | 2 | 0 |
| 5 | 088ed70f-2065-5d62-a036-d58ccbb1a890 | 0 | 0 |

JSON citations và persisted citations của cả hai transports trỏ đúng chunks cho markers [4] rồi [1]: **caa83424-0c3c-5f45-972f-a9e9b2cc8bef, 837b38d1-cf4c-5376-ac5c-58bfdfbede40**. Không fabricate document/version/chunk ID. Sources là prompt-selected retrieval sources; không biến metadata tool results thành chunks.

Phạm vi live này dùng existing session creation API với **ALL_ACTIVE**. Không có API parameter tạo selected-document subset; không tự update session scope bằng DB để ép test. **SELECTED_DOCUMENTS subset behavior chưa được live-verified**; source/offline coverage trước không thay thế điều này.

### C3. SSE wire contract

| Case | Events | Deltas | Sequence | Terminal/count | Terminal usage total |
| --- | ---: | ---: | --- | --- | ---: |
| LIVE01_SSE | 13 | 10 | 1…13 | done / 1 | 1029 |
| LIVE02_SSE | 296 | 293 | 1…296 | done / 1 | 2058 |
| LIVE04_SSE | 211 | 208 | 1…211 | done / 1 | 2768 |

Tất cả bắt đầu start -> metadata -> delta*, kết thúc done, không error và chỉ một terminal; sequences contiguous. Count/list metadata sources=[]; RAG metadata giữ ordered five sources. Final deltas không chứa tool calls, raw ToolMessage hoặc raw result envelopes.

ASGITransport buffers body để kiểm tra transcript đầy đủ; không chứng nhận chunk delivery timing qua TCP/proxy hoặc disconnect behavior. Latency tại E là đến hoàn tất body/persistence.

## D. Persistence

Fresh sessions tạo qua existing POST /sessions, không tự insert/replay fixtures. Sau mỗi request đọc live Mongo messages/session theo đúng session_id:

| Case | Session ID | User message ID | Assistant message ID | Statuses | Guard |
| --- | --- | --- | --- | --- | --- |
| LIVE01_JSON | d5e51359-ac9e-4769-844c-102fd52105c6 | 648f7b48-e84f-4d2c-807a-6583603c4dd6 | 5c4d49e4-0497-42ce-98b7-4bcf01cced8d | COMPLETED / COMPLETED | null |
| LIVE02_JSON | 5f99faea-7fa8-43c2-ae1f-4e23821bf241 | 0dc27a60-1505-4a04-9530-5cac7beeac0f | 68e6dd9f-7403-4891-8dc9-40f21663d21c | COMPLETED / COMPLETED | null |
| LIVE01_SSE | 8f47d804-d318-4901-a7d6-a508461aa178 | 61db1fb8-fd9a-4085-91d0-9af6fee237ba | 9be47b52-a3d1-4a6c-a982-70007918753b | COMPLETED / COMPLETED | null |
| LIVE02_SSE | 95c06c0d-317f-4659-98da-23bc8bc9d6c8 | f06eefe4-eeb0-4d83-b2a8-d641df008569 | 9cfa3a74-2266-4a66-b009-35ea8acfae0a | COMPLETED / COMPLETED | null |
| LIVE04_JSON | f7155516-4490-4a4c-99ff-d91639a36b70 | 329cacc8-08a0-47ef-9496-04632ff1d123 | 34281c63-4091-4153-9b38-61ba90d4cae2 | COMPLETED / COMPLETED | null |
| LIVE04_SSE | 085887be-984a-41b7-b010-9db11fc941c7 | 12781cbc-c54c-4fa0-a354-43c7685522e3 | 5d46e3c6-fb13-46a3-aa98-69cbc952d690 | COMPLETED / COMPLETED | null |

- **6 sessions, 12 messages**, đúng một USER/ASSISTANT pair/request.
- Hai messages cùng request_id trên wire; không persisted native ToolMessage/tool-protocol role.
- Assistant content khớp toàn bộ reconstructed final answer; usage khớp wire/terminal.
- Tất cả messages COMPLETED; không để lại PENDING/STREAMING hoặc guard thuộc round này.
- Metadata answers persisted citations=[]; RAG citations match source identities nêu tại C2.
- SSE monitor thấy PENDING->STREAMING và terminal replacement (2 messages update commands/request); JSON terminal replacement 1 messages update/request.
- Không delete sessions/messages sau test; các IDs trên được giữ để owner kiểm tra.
- Existing unrelated conversations/guards không được sửa, release hoặc coi là đã được kiểm tra sạch.

## E. Operational Metrics

| Case | Input tokens | Output tokens | Aggregate total | Request ms | Groq attempts / statuses |
| --- | ---: | ---: | ---: | ---: | --- |
| LIVE01_JSON | 785 | 233 | 1018 | 2281 | 2 / 200,200 |
| LIVE02_JSON | 1532 | 619 | 2151 | 2844 | 2 / 200,200 |
| LIVE01_SSE | 785 | 244 | 1029 | 2203 | 2 / 200,200 |
| LIVE02_SSE | 1532 | 526 | 2058 | 3047 | 2 / 200,200 |
| LIVE04_JSON | 1283 | 1356 | 2639 | 6406 | 2 / 200,200 |
| LIVE04_SSE | 1283 | 1485 | 2768 | 6906 | 2 / 200,200 |
| **Total** | **7200** | **4463** | **11663** | — | **12 / all 200** |

- **6/8 logical chat requests**, **12/16 logical LLM invocations**; không dùng hai slots còn lại để rerun hoặc mở rộng scope.
- Actual total tokens=11663, gồm selector/final và reasoning tokens theo provider accounting; không phải token estimates.
- Với ba JSON requests, tổng raw provider usage của selector+final lần lượt 1018, 2151, 2639, khớp public aggregate độc lập.
- Với SSE, public terminal aggregate khớp persisted usage; raw HTTP streaming usage snapshots không được lưu riêng trong observer. Không cộng lặp deltas/cumulative snapshots; ledger giữ accepted implementation. Không bịa breakdown final-only từ aggregate.
- Fresh sessions empty history nên không có provider rewrite invocation; đúng hai calls mỗi request.
- **0 observed SDK retries, 0 application retries, 0 HTTP 429**, không fallback model/provider.
- Khoảng nghỉ không nằm trong per-request latency. Header latency cũng được observer ghi nhận; không lấy ASGI buffer completion làm time-to-first-content.
- Gemini embedding/Qdrant HTTP request counts không instrument riêng; không dùng 12 Groq attempts làm tổng mọi external-service requests.
- Session writes và 5 startup DDL commands là authorized; document/version mutations=0, chứng minh thêm bằng full-collection hashes.

## F. Safety & Regression

### F1. Integrity và scope

Live integrity evidence:
- documents unchanged: **true**.
- document_versions unchanged: **true**.
- nondeleted count cuối round: **6**.
- Không upload/delete/update/reindex/provision documents; không migrations, drop indexes hoặc destructive fault injection.
- Không sửa RAG prompt/top_k/model/provider, application/tests hoặc dependencies; HTTP/Mongo observers không mocks.
- Không có observed unexpected document/session ownership mutation; authorized session/message writes giới hạn ở IDs mục D.
- Không cần phục hồi stale guard/ambiguous commit; không replay hoặc cố làm failing request PASS.

### F2. Classification / limitations

Không phát hiện PROVIDER_CAPABILITY_FAILURE, TOOL_SELECTION_FAILURE, FINAL_GROUNDING_FAILURE, EXECUTOR, DATABASE, TRANSPORT, PERSISTENCE hoặc QUOTA failure trong sáu requests này. Các gates TARGET_OR_DATA_AUTHORIZATION_REQUIRED và STARTUP_DDL_NOT_AUTHORIZED được giải quyết bằng owner attestation + matching index specs, không bypass.

Các giới hạn còn lại:
1. **LIVE03 = NOT_RUN_DATASET_UNAVAILABLE**; 25 total gồm 19 deleted không phải 25 eligible documents.
2. **SELECTED_DOCUMENTS subset scope chưa live-test**; ALL_ACTIVE production scope đã PASS. Không tự tạo endpoint/config/DB scope override.
3. ASGI integration không kiểm chứng proxy/TCP/browser streaming/disconnect; không fault-inject 429, provider failure, crash hoặc ambiguous commit.
4. Provider behavior với dữ liệu/prompt khác hoặc quota tương lai chưa được chứng nhận. Count/list outcomes là observed runs, không bảo đảm selector luôn đúng.
5. Raw SSE provider usage snapshots/first-content timing không lưu riêng; terminal/persistence parity đã kiểm tra.

C01–C08 giữ nguyên theo R2-06A: whitespace validator divergence; setup placeholder gap; terminal-write/release ambiguity; abandoned guard recovery; pre-guard SSE preparation; multi-write/replay uncertainty; pre-iterator cleanup gap; cleanup/persistence ngoài hard deadline. Không sửa hoặc waive chúng. Existing stale config comment vẫn chưa sửa.

## G. Rollback Evidence

- Trong local smoke process: startup effective flag=true; finally đặt settings.tool_use_enabled=false và process env TOOL_USE_ENABLED=false.
- Rollback event ghi **effective_flag=false**, sau lifespan đóng managed clients. Không tác động deployment chính.
- Một Python process mới đọc normal settings sau smoke: **flag=false**, model=openai/gpt-oss-120b. Process-local override không tồn tại trong parent/.env.
- **87 protected files unchanged=true** qua SHA-256 before/after: app/test Python, .env/.env.example, requirements, R0-B/R1 và R2-06A reports. Không sửa source/test/config vĩnh viễn.
- Full live Mongo documents/versions hashes unchanged; index initialization chỉ existing matching specs đã duyệt.
- Giữ nguyên 6 test sessions và 12 messages; không delete/release/replay sau test.
- Legacy branches nguyên vẹn. Không gọi generation legacy thêm sau rollback vì matrix/budget đã hoàn thành; code/flag preservation là evidence, không ghi một legacy runtime PASS giả.
- Git working tree giữ các thay đổi phase trước; deliverable sửa duy nhất của round này: R2-06B-LIVE-SMOKE-REPORT.md. Không commit/reset/clean/refactor.

## H. Final Verdict

**LIVE_ACCEPTED_WITH_LIMITATIONS**

Core Tool Use count/list và knowledge RAG fallback đã được kiểm chứng qua JSON/SSE với Groq/MongoDB/Qdrant thật trong local development, sau owner authorization. Count đúng **6 identities**, list giữ hai test4.txt riêng, native ToolMessage IDs khớp, all terminal/persistence checks PASS, no observed retries/429 và rollback flag=false.

Live pagination 25 eligible items, selected-document subset, real network/proxy/disconnect và inherited failure scenarios chưa được chứng nhận. Không coi verdict này là production rollout approval, đóng C01–C08 hoặc tuyên bố mọi Tool Use MVP acceptance case hoàn tất.

**R2-06B — READY_FOR_OWNER_REVIEW**


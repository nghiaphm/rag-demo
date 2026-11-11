# BACKEND-MODULE-BOUNDARIES — R1

Ngày: 2026-10-29 (Asia/Bangkok). Phạm vi: thiết kế boundary cho hai tool đọc metadata count_documents và list_documents; analyze_document chỉ là extension point tương lai. Deliverable duy nhất: báo cáo này. Không tạo package, implementation hoặc placeholder.

Hiệu chỉnh quyết định owner: 2026-10-30 (Asia/Bangkok). R1: APPROVE_WITH_CORRECTIONS; ba quyết định cuối được ghi tại mục 5–7, 9–10. Documentation verdict: **READY_FOR_OWNER_APPROVAL**. Chưa có authorization triển khai R2.

## 1. Executive Summary

**Đề xuất giữ nguyên layout backend, thêm một orchestration facade dùng chung cho JSON/SSE và một Tool Use boundary nhỏ, chỉ đọc Documents.** Documents sở hữu truy vấn metadata; Tool Use sở hữu schema/validation/dispatch; Conversations tiếp tục sở hữu session guard, message pair và terminal persistence. Không đưa tool loop vào cả hai HTTP handlers hoặc vào repository.

Thiết kế tối thiểu cần hai query methods **mới được đề xuất**, vì source hiện tại chưa có count toàn library và chưa có list với tie-breaker ổn định. Không gọi len(page) là tổng document, không đếm Qdrant points, không đếm versions. Không thay chữ ký hoặc sort của list_documents hiện phục vụ API chỉ để thêm tools. Evidence: backend/app/document_repository.py:98–115, :124–136; backend/app/document_models.py:54–65, :92–108.

Routing đã chốt cho MVP: **LLM-first**, một non-streaming selector request cho mỗi tools-enabled chat turn; không chọn tool thì đi qua RAG pipeline hiện có. Không thêm hybrid/regex router. Selection làm tăng model latency và token cost, kể cả turn sau đó dùng RAG. Giữ **một tool-call round, tối đa hai calls chạy tuần tự**, rồi tạo final answer với tools disabled. Tool calls/results là dữ liệu nội bộ trong request, không thành public SSE events hoặc MessageRole mới. SSE chỉ stream final answer. List tối đa 20 items/call; khi has_more=true, answer phải nói rõ danh sách chưa đầy đủ. Feature flag mặc định disabled; khả năng configured Groq model thực hiện structured selection và final response generation/streaming sau tool messages vẫn **NOT_VERIFIED**, phải kiểm chứng trước enablement ở vòng implementation sau, không thực hiện trong vòng hiệu chỉnh này.

Đồ thị đề xuất kiểm tra trên 102 cạnh từ R0-B được duyệt: thêm 5 module có nội dung và 17 cạnh nội bộ được cho phép → **43 node, 119 cạnh, vẫn DAG**. Đây là kiểm tra thiết kế có điều kiện: implementation phải tuân thủ danh sách import tại mục 4; không chứng nhận implementation chưa tồn tại.

Báo cáo dùng ba nhãn xuyên suốt:

| Nhãn | Ý nghĩa |
| --- | --- |
| CURRENT_IMPLEMENTATION | Hiện diện trong source được dẫn line; không đồng nghĩa đã chạy thành công. |
| PROPOSED_DESIGN | Quyết định, file, contract hoặc giá trị giới hạn đề xuất, cần owner duyệt trước implementation. |
| NOT_VERIFIED | Thiếu tài liệu, cần kiểm chứng SDK/provider/runtime hoặc chưa có implementation. |

R0-B là APPROVED. R1 được APPROVE_WITH_CORRECTIONS; giữ các quyết định kiến trúc đã được chấp nhận và bổ sung ba quyết định owner trong vòng hiệu chỉnh documentation-only này. READY_FOR_OWNER_APPROVAL không phải phê duyệt triển khai hoặc bắt đầu R2.

## 2. Existing Architecture Boundaries

### Tài liệu và phạm vi kiểm tra

Có BACKEND-DEPENDENCY-ANALYSIS.md (R0-B), docs/audits/RAG-CODEBASE-ASSESSMENT-0C.md và docs/audits/RAG-CONVERSATION-AUDIT-0B02.md. BACKEND-ARCHITECTURE-REVIEW.md và tooluse.md **vẫn không tìm thấy trong checkout** khi tìm file gồm hidden files, loại .git/dependencies/build. Nội dung/tên từng phase T0–T6 gốc: NOT_VERIFIED. Các nhãn T0–T3 trong mục 8 chỉ là **integration sequence đề xuất cho phạm vi prompt hiện tại**, không tái tạo roadmap bị thiếu. Không suy diễn scope P1–P8.

Chỉ đọc tập trung source về document query/schema, chat/pipeline, conversation lifecycle, SSE/history, config/provider và metrics. Không re-audit chức năng toàn backend, không tính lại toàn bộ import graph từ source; tái sử dụng inventory R0-B cho dependency check thiết kế. Fingerprint 38 Python files chỉ để bảo đảm không bị sửa, không phải chạy application.

### Các boundary hiện có — CURRENT_IMPLEMENTATION

| Boundary hiện tại | Evidence và ý nghĩa |
| --- | --- |
| API/composition | backend/app/main.py:21–38 tạo/đóng cloud clients dùng chung; backend/app/api/chat.py:338–368, :449–470 lấy clients từ app.state. API sở hữu HTTP/DTO/error mapping/SSE encoding, nhưng hiện cũng điều phối provider và durable turn. |
| JSON generation | backend/app/api/chat.py:342–348 gọi answer_question cho stateless; :354–368 truyền closure generate vào ConversationService.answer_with_persistence. Service nhận guard/pair trước generate: backend/app/conversation_service.py:97–132. |
| SSE generation | backend/app/api/chat.py:453–470 chuẩn bị RAG trước, rồi begin_streaming_turn; :118–253 emit start/metadata, iterate provider, finalize, emit terminal. Không giống thứ tự acquire của JSON. |
| RAG preparation/generation | backend/app/rag/pipeline.py:64–155 load history/scope, rewrite, retrieve, budget; :175–188 generate JSON; :228–239 stream provider. PreparedRagStream (:43–53) chứa prompt, ordered sources và history/scope. |
| Documents | backend/app/document_repository.py:98–115 query document identities, loại status DELETED theo mặc định; :124–136 query active version IDs cho retrieval. backend/app/document_service.py:56–75 dựng summaries bằng list_versions từng document, không phải primitive count. |
| Conversations | backend/app/conversation_repository.py:117–166 guard/sequence; :168–220 pair insert, streaming transition, finalize. backend/app/conversation_service.py:188–278 sở hữu durable SSE turn và finalization. |
| Tool lifecycle | Chưa có boundary structured tool execution. backend/app/rag/pipeline.py:265–279 chỉ trích text, không đọc tool-call protocol. ProviderStreamChunk (:57–61) chỉ có content/usage. |
| Provider | backend/app/rag/llm.py:15–24 tạo cached ChatOpenAI bằng settings; backend/app/config.py:25–27 có default model openai/gpt-oss-120b. Đây là source default, không chứng minh runtime override, tool support hoặc cấu hình deployment hiện tại. |

Không di chuyển history.py, attachments.py, excel.py hoặc citation_mapping.py: áp dụng ownership logic đã duyệt ở R0-B. History thuộc Conversations; resolve version/preview thuộc Documents; Excel parsing thuộc Ingestion và được preview dùng lại; citation identity mapping thuộc RAG. Tool Use ban đầu không cần đọc file, parse Excel, embed hoặc query Qdrant.

## 3. Proposed Module Ownership Matrix

Tất cả rule ở bảng là PROPOSED_DESIGN; source interfaces trong cột cuối là CURRENT_IMPLEMENTATION, trừ phần được ghi rõ proposed. **Logical owner không đồng nghĩa physical directory**: rag/pipeline.py tiếp tục nằm yên nhưng có trách nhiệm Chat Orchestration.

| Owner | Owns | May call/import | Must not own | Reuse / physical location |
| --- | --- | --- | --- | --- |
| API | HTTP validation, IDs mapping, response/exception mapping, SSE event encoding và phối hợp durable lifecycle theo transport | Shared orchestration facade; ConversationService; DTOs; existing composition inputs | Tool registry, argument validation policy riêng, tool loop, Documents queries tự viết | backend/app/api/chat.py:118–312, :333–421, :439–516; backend/app/schemas.py:98–190; backend/app/sse_schema.py:23–105. Thay call target tối thiểu về facade; giữ routers/DTOs. |
| Chat Orchestration | Lựa chọn RAG/tool route, model tool-call detection, request-local plan, chung policy rounds/deadline/budget/usage; final answer context | RAG pipeline/provider factory; Conversations history/repository để đọc theo pattern đang có; Tool Use executor/registry; injected Documents read facade | Mongo query predicates, guard acquisition/release, message writes, SSE framing | Reuse backend/app/rag/pipeline.py:64–155, :175–239; backend/app/history.py:66–86; backend/app/context_budget.py:134–192. Proposed app/chat_orchestration.py là facade mới, không chuyển pipeline. |
| Tool Use | Hai tool schemas, allowlist, strict validation, dispatch, normalized result/error; invocation correlation; bounded execution | Contracts; Documents query facade/capability được inject. Executor nhận registry/callables; không mở clients | Business query semantics, HTTP, model/RAG pipeline recursion, persistence/guard, arbitrary Python execution, mutations | Proposed app/tool_use/contracts.py, document_tools.py, executor.py. Không có module này hiện tại. |
| Documents | Định nghĩa document identity/deleted visibility, count/list predicates/order, metadata projection và giới hạn query output | MongoDocumentRepository và DocumentRecord; nhận database handle đang có qua composition | Tool selection/LLM protocol, SSE, session guard, count bằng retrieved chunks | Reuse backend/app/document_repository.py:37–43, :98–115; backend/app/document_models.py:54–65. Proposed app/document_queries.py là read facade nhẹ; không dùng full DocumentService factory vốn lắp storage/Qdrant/ingestion. |
| Conversations | Session identity/scope, guard owner, sequence allocation, một user/assistant pair, trạng thái và terminal persistence; load durable history | Existing conversation repository/models/history và citation mapper | Tool execution loop, tool-specific MessageRole/schema, auto retry/recovery mới trong R1 | backend/app/conversation_service.py:97–186, :188–278; backend/app/conversation_repository.py:117–220; backend/app/history.py:23–30, :106–139. Reuse as is, không chuyển quyền guard sang tool executor. |
| RAG | Retrieval filtering, document-chunk provenance, prompt/context format, citations; shared request preparation đang nằm trong pipeline làm facade hiện hữu | Document active versions, vector/provider adapters; orchestration gọi vào | Library-wide count bằng top-k; Tool Use dispatch hoặc import ngược chat_orchestration | backend/app/rag/retriever.py:31–50, :71–102; backend/app/rag/pipeline.py:242–262, :312–323; backend/app/citation_mapping.py:12–56. Ordinary content questions dùng đường cũ. |
| Infrastructure | Client lifecycle, SDK/provider factories, FileStorage/VectorIndex implementation; settings là Shared/Core dependency | Config, SDKs, contracts thấp hơn; clients được inject | Tool-specific client instances, Documents query business rules, imports ngược API/orchestrator/tool registry | cloud_connections.py; backend/app/main.py:21–38; backend/app/rag/llm.py:15–24; backend/app/storage.py:47–68; backend/app/vector_index.py:147–176. Không tạo MongoClient/QdrantClient trong tools. |

Tool Use không nhận database object hoặc collection object trong model arguments. Chỉ composition facade tạo MongoDocumentRepository(database) từ handle sẵn có, inject Documents read capability vào document_tools. Mọi raw Mongo predicate/order nằm ở document_repository, không ở tool schema hoặc prompt.

## 4. Dependency Direction & Mermaid Diagram

### Existing source-confirmed graph slice — CURRENT_IMPLEMENTATION

Mũi tên là import trực tiếp, không phải runtime callback. Đây là slice liên quan R1, không thay đồ thị 38-module trong R0-B.

~~~mermaid
flowchart TD
  A[app.api.chat] --> P[app.rag.pipeline]
  A --> C[app.conversation_service]
  A --> DR[app.document_repository]
  P --> DR
  P --> CR[app.conversation_repository]
  P --> H[app.history]
  P --> L[app.rag.llm]
  C --> CR
  CR --> CM[app.conversation_models]
  H --> CR
  H --> CM
  DR --> DM[app.document_models]
~~~

Evidence: backend/app/api/chat.py:10, :22, :28; backend/app/rag/pipeline.py:21, :23, :27, :32; backend/app/conversation_service.py:19; backend/app/conversation_repository.py:12; backend/app/history.py:13, :20; backend/app/document_repository.py:15. API callback generate → pipeline không tạo import conversation_service → pipeline.

### Additive integration graph — PROPOSED_DESIGN

Solid arrows trong diagram sau giữ source-confirmed dependencies chính; dashed arrows là imports mới đề xuất. Các module mới chỉ là tên file được đề xuất, chưa tồn tại.

~~~mermaid
flowchart TD
  A[app.api.chat] --> P[app.rag.pipeline]
  A --> C[app.conversation_service]
  P --> DR[app.document_repository]
  P --> CR[app.conversation_repository]
  P --> H[app.history]
  P --> L[app.rag.llm]
  P --> B[app.context_budget]
  P --> CFG[app.config]
  C --> CR
  DR --> DM[app.document_models]
  A -.-> O[app.chat_orchestration NEW]
  O -.-> P
  O -.-> E[app.tool_use.executor NEW]
  O -.-> T[app.tool_use.document_tools NEW]
  O -.-> K[app.tool_use.contracts NEW]
  O -.-> Q[app.document_queries NEW]
  O -.-> DR
  O -.-> CR
  O -.-> H
  O -.-> B
  O -.-> CFG
  O -.-> L
  E -.-> K
  T -.-> K
  T -.-> Q
  Q -.-> DR
  Q -.-> DM
~~~

Executor không import document_tools: facade compose registry và inject callables vào executor. Tool trả normalized envelope qua contracts; Documents facade không import Tool Use contracts. Runtime callback executor → document tool là invocation qua injected registry, không thêm import ngược.

**Danh sách 17 cạnh mới được phép:**

| Importer mới/thay đổi | Targets |
| --- | --- |
| app.api.chat | app.chat_orchestration |
| app.chat_orchestration | app.rag.pipeline, app.tool_use.executor, app.tool_use.document_tools, app.tool_use.contracts, app.document_queries, app.document_repository, app.conversation_repository, app.history, app.context_budget, app.config, app.rag.llm |
| app.tool_use.executor | app.tool_use.contracts |
| app.tool_use.document_tools | app.tool_use.contracts, app.document_queries |
| app.document_queries | app.document_repository, app.document_models |

External LangChain/Pydantic/stdlib imports không được tính là cạnh nội bộ. Proposed tool_use/__init__.py phải rỗng, không eager re-export/import facade; vì không có cạnh và không có nội dung, không tính vào 43 node có nội dung của phép kiểm tra additive này.

**Cycle verification — PROPOSED_DESIGN:** dựng lại 102 unique edges từ bảng inventory R0-B; thêm đúng 17 cạnh trên; sắp xếp topo loại được toàn bộ 43 node/119 cạnh. Không có path từ pipeline, repository, Documents facade hoặc Tool Use quay về chat_orchestration/API. Giữ cả API → pipeline cũ trong phép tính là kiểm tra bảo thủ, không giả định đã xóa imports khi tích hợp. Không có new static cycle nếu implementation theo tập cạnh này. Cần kiểm tra lại khi code được viết; future dynamic imports/SDK behavior: NOT_VERIFIED.

Import prohibitions: Tool Use không import app.api.chat hoặc app.rag.pipeline; Documents/query modules không import tool_use/chat_orchestration; rag.pipeline không import facade mới; contracts không import executor/registry/domain services. Không dùng lazy import để né vòng.

## 5. Document Tool Contracts

Toàn bộ tool contracts/output examples và query additions ở mục này là **PROPOSED_DESIGN**, không phải signature đang tồn tại. Tool output là nội bộ để model dùng, không thêm public endpoint/DTO.

### Source signatures đã đối chiếu — CURRENT_IMPLEMENTATION

| Interface thật | Đủ/chưa đủ cho hai tools |
| --- | --- |
| MongoDocumentRepository(database: Any), backend/app/document_repository.py:38–43 | Nhận database handle; không tạo independent client. Reuse qua composition. |
| list_documents(*, include_deleted: bool = False, offset: int = 0, limit: int = 100) -> list[DocumentRecord], :98–115 | Query đúng document collection, có deleted toggle/offset/limit; sort chỉ created_at DESCENDING. Không count, không tie-breaker, không trả total. Không tự thêm status/filename filter vào lời gọi này. |
| list_versions(document_id: str) -> list[DocumentVersionRecord], :117–122 | Versions của một document; không dùng để count identities. |
| list_active_version_ids() -> list[str], :124–136 | Chỉ INDEXED với active_version_id kiểu string; semantics retrieval, không phải số document không deleted. |
| DocumentService.list_documents(*, include_deleted: bool = False, offset: int = 0, limit: int = 100) -> list[DocumentSummary], backend/app/document_service.py:56–75 | Gọi list_versions mỗi item để tạo active_version/version_count. Hai metadata tools không cần thông tin này; tránh N+1 và composition Qdrant/ingestion tại :131–146. |
| is_document_deleted(document_id: str) -> bool, backend/app/document_repository.py:369–375 | Có gọi SDK collection.count_documents(..., limit=1) để kiểm tra một ID, không có repository count toàn library. Tên SDK method không phải interface repository sẵn có. |

### Document query semantics dùng chung

- Phạm vi ban đầu là **document metadata toàn library single-user**, không phải session retrieval scope. Trả rõ scope=library. count/list không dùng session.selected_document_ids, attachment IDs hoặc active versions để ngầm thu hẹp. Nếu owner muốn count trong selected scope thì phải duyệt scope contract khác; không thêm scope argument tùy ý vào model tool trong T0–T3.
- Đếm **một DocumentRecord identity (_id/document_id)** là một document, bất kể có bao nhiêu versions, jobs hay chunks. Hai uploads có cùng file_name nhưng khác _id vẫn là hai identities; nhiều versions của cùng _id vẫn là một.
- Mặc định include_deleted=false dùng đúng predicate của repository hiện tại: status != DELETED. Bao gồm UPLOADED, PROCESSING, INDEXED, FAILED; không đồng nghĩa tất cả đều có thể retrieve. include_deleted=true bỏ predicate status, bao gồm DELETED. Không tự đổi thành deleted_at is null: schema có cả status/deleted_at nhưng list hiện tại chỉ dùng status (backend/app/document_repository.py:105; backend/app/document_models.py:31–36, :61–65). Bất nhất dữ liệu nếu có: NOT_VERIFIED, không sửa trong R1.
- Không gọi count của Qdrant, độ dài list_active_version_ids hoặc len(list_documents(limit=...)) thay cho total. Không distinct theo filename. Không quét nhiều page rồi cộng để đếm.
- Bộ lọc T0–T3 duy nhất: include_deleted. Status enum, keyword/regex filename, ready-only, date range và arbitrary sort được DEFER; không gán cho repository interfaces chưa có. Đây vẫn là filtering có định nghĩa rõ, không mở thêm scope ngoài hai tools.

### count_documents

| Thành phần | Logical contract đề xuất |
| --- | --- |
| Tool name | count_documents, exact allowlist string. |
| Arguments | JSON object, chỉ include_deleted: strict boolean, optional/default false. {} hợp lệ; null, string boolean, number 0/1 và unknown keys bị từ chối. |
| Query | Server-side exact count_documents của document collection với predicate do repository sở hữu. Không estimated_document_count. Count là kết quả của một query, không chứng nhận snapshot liên kết với list gọi sau đó. |
| Result | ok=true; tool=count_documents; data.count nonnegative integer; data.unit=document; data.scope=library; data.include_deleted boolean. |
| Empty library | Thành công count=0; không lỗi/not-found. |
| Failure | Envelope ở phần errors dưới đây; không trả 0 khi query thất bại. |

Ví dụ dữ liệu minh họa, không phải kết quả query thực tế:

~~~json
{"ok":true,"tool":"count_documents","data":{"count":7,"unit":"document","scope":"library","include_deleted":false},"error":null}
~~~

### list_documents

| Thành phần | Logical contract đề xuất |
| --- | --- |
| Arguments | include_deleted: strict bool/default false; offset: strict int >=0/default 0; limit: strict int 1..20/default 10; extra keys forbidden. Reject bool ở integer fields. Kiểm tra giới hạn skip của driver trước query; không để lỗi overflow thành raw exception cho model. |
| Filtering | Giống count, chỉ include_deleted; reject status/filter/sort arguments chưa hỗ trợ. |
| Stable ordering | created_at DESC, _id DESC. Document IDs là canonical UUID strings ở schema; _id là tie-breaker duy nhất để timestamp bằng nhau không tùy tiện đảo thứ tự. Không đổi order của API list hiện tại. |
| Pagination | Offset-based; repository fetch tối đa limit+1 (max 21) để có sentinel. Trả <=limit items, has_more và next_offset; khi hết: has_more=false, next_offset=null. Không tự gọi tiếp page trong cùng turn. |
| Maximum size | Tối đa 20 returned items và 8 KiB UTF-8 cho toàn bộ result envelope sau compact JSON serialization. Nếu vượt bytes, bỏ các item cuối nguyên vẹn cho tới khi vừa; không truncate JSON hoặc tên file giữa chừng. returned_count là số thực trả, next_offset=offset+returned_count nếu còn item; has_more=true khi có sentinel hoặc item bị bỏ vì byte cap. |
| Item projection | document_id, file_name, status, active_version_id nullable, created_at và updated_at dạng ISO-8601 UTC. Không raw _id object, source_key, storage_key, checksum, connection info, version count hoặc full file text. |
| Page metadata | scope=library, include_deleted, offset, limit (requested), returned_count, has_more, next_offset, truncated_by_bytes boolean, order=[created_at:desc,document_id:desc]. Không total; muốn total dùng count_documents. |
| Consistency | Stable total order cho dữ liệu không đổi; không snapshot isolation. Upload/delete giữa pages hoặc giữa count/list có thể làm offset drift/count khác list; không tuyên bố đồng bộ snapshot. |
| Empty page | ok=true, items=[], returned_count=0, has_more=false, next_offset=null; offset vượt dữ liệu không phải not-found. Nếu tồn tại items nhưng không pack được một item thì OUTPUT_LIMIT, không trả empty page giả là hết. |
| Answer completeness | Khi has_more=true, final answer bắt buộc nói danh sách chưa đầy đủ, nêu returned_count thực trả và hướng dẫn người dùng yêu cầu page tiếp theo ở chat turn sau bằng next_offset. Không suy ra total từ returned_count hoặc claim đã liệt kê tất cả. has_more=false chỉ xác nhận hết từ offset đã query; chỉ được gọi danh sách là toàn bộ theo bộ lọc khi query bắt đầu offset=0, has_more=false và truncated_by_bytes=false. |

Answer-generation instructions ở mục 6 phải mang đầy đủ pagination metadata vào final model context và áp dụng quy tắc completeness này cho cả JSON lẫn SSE. Byte cap không thay đổi has_more/next_offset/returned_count semantics đã định nghĩa; khi phải bỏ item vì byte cap, answer vẫn phải công bố danh sách chưa đầy đủ. Người dùng có thể yêu cầu trang kế tiếp trong turn sau; không tự lặp fetch hoặc tự hoàn tất toàn library. Automatic full-library pagination tiếp tục DEFER.

Ví dụ empty page hợp lệ:

~~~json
{"ok":true,"tool":"list_documents","data":{"scope":"library","include_deleted":false,"items":[],"offset":0,"limit":10,"returned_count":0,"has_more":false,"next_offset":null,"truncated_by_bytes":false,"order":["created_at:desc","document_id:desc"]},"error":null}
~~~

Stable order không cần index mới để định nghĩa correctness. Chi phí sort/skip và index hiện hữu có phù hợp hay không cần kiểm chứng workload riêng, NOT_VERIFIED; không thêm index/cloud mutation như một yêu cầu ngầm của R1.

### Minimal repository additions — chỉ là đề xuất, chưa tồn tại

Giữ list_documents hiện tại nguyên signature và semantics. Bổ sung **hai methods rõ tên phục vụ bounded reads**, cùng một internal predicate builder trong repository; helper mới theo chính xác include_deleted semantics hiện tại, không tạo rule ở tool. Chữ ký thiết kế sau cần owner duyệt:

~~~python
# PROPOSED ONLY — not present in current MongoDocumentRepository
count_documents_for_tools(
    *, include_deleted: bool = False, max_time_ms: int = 5000
) -> int

list_documents_for_tools(
    *, include_deleted: bool = False, offset: int = 0,
    limit: int = 21, max_time_ms: int = 5000
) -> list[DocumentRecord]
~~~

max_time_ms là policy server-injected, không model argument. Count dùng document collection count với maxTimeMS; list áp compound sort, skip, fetch bound và server-side query max time phù hợp SDK. Không đưa Mongo query/sort từ model xuống collection. Catch/wrap SDK errors theo RepositoryError đang có tại backend/app/document_repository.py:25–34. Cần kiểm tra SDK timeout API khi implementation; source chỉ khai báo pymongo version range trong backend/requirements.txt:13, không chứng minh từng option được runtime chấp nhận.

Proposed document_queries.py là Documents read facade: gọi đúng hai methods mới, project DocumentRecord, pack byte cap và pagination metadata. Không instantiate full DocumentService/Qdrant. document_tools.py chỉ validate/mapping call → facade → tool envelope; không tái hiện filter/order. Không tạo general DocumentRepository protocol hoặc giả vờ source đã có query interface tổng quát.

### Internal errors cho cả hai tools

Envelope lỗi: ok=false, tool=name nếu nhận diện được, data=null, error={code,message,retryable}. tool_call_id/correlation được executor giữ riêng trong invocation context để ghép model message; không nhận ID do người dùng gửi như quyền truy cập.

| Code đề xuất | Trigger | retryable flag |
| --- | --- | --- |
| TOOL_UNKNOWN | Tool ngoài allowlist, kể cả analyze_document hiện chưa đăng ký | false |
| TOOL_INVALID_ARGUMENTS | JSON/schema/extra keys/type/range/driver skip bounds sai | false |
| TOOL_QUERY_FAILED | RepositoryError hoặc invalid stored metadata không thể project an toàn | true với lỗi transient đã phân loại, còn lại false |
| TOOL_TIMEOUT | Hết logical deadline/query time budget | true |
| TOOL_OUTPUT_LIMIT | Không thể tạo một result hợp lệ trong byte/token budget | false |
| TOOL_LIMIT_EXCEEDED | >1 round hoặc >2 calls/turn, duplicate/missing invocation IDs | false |
| TOOL_PROVIDER_UNAVAILABLE | Model/provider capability chưa được enable/verify hoặc provider request không tương thích | false, cần operator/config decision |

retryable chỉ là metadata mô tả, **không kích hoạt automatic retry**. Không leak raw SDK/provider exception, query, URI hoặc secrets. Cancellation được truyền như cancellation, không nuốt rồi thành count=0/list=[]; terminal handling thuộc lớp orchestration/Conversations hiện tại. Tool errors dùng internal envelope, không thêm public ChatError enum/DTO; API có thể giữ generation error codes hiện hữu và log internal code có giới hạn.

## 6. Shared Tool Orchestration Design

Tất cả flow dưới đây là PROPOSED_DESIGN. Không generic autonomous agent, không planner graph, không delegation, không text-to-Python executor.

### Một facade, hai transport adapters

Proposed app/chat_orchestration.py có hai bước logic dùng chung: **prepare plan** và **run answer**. PreparedChatAnswer là in-memory type mới ở facade, không sửa PreparedRagStream/public schemas. Nó chứa route RAG hoặc DOCUMENT_TOOLS, immutable ordered sources, request-local model history/validated calls, usage ledger và monotonic deadline. Tên type/function mô tả design, chưa phải API có thật.

- API JSON gọi facade bằng sync wrapper trong generate closure đang được ConversationService gọi; stateless dùng cùng facade không persistence. Facade aggregate answer → dict có answer, sources, usage như result hiện tại, không tự cấp durable IDs.
- API SSE gọi prepare plan trước begin_streaming_turn như thứ tự hiện có. Sau khi có turn và encoder đã vào body, dùng run answer async iterator của facade thay chỗ astream_rag_answer; chỉ normalized content/usage đi qua SSE adapter. Mọi validation/tool policy giống JSON.
- Tách API lifecycle orchestration và tool execution policy: API vẫn begin/finalize turn như hiện tại; facade/tool executor không gọi ConversationService hay ghi messages. Không sửa service để nó import facade mới.
- Tools gate mặc định disabled, server-only. Off: delegate legacy RAG entrypoints hiện tại, không gọi selector hoặc thay usage/timeout behavior của đường cũ. Enablement chỉ sau khi kiểm chứng configured Groq model/SDK thực hiện structured non-streaming tool selection, nhận matched tool results và tạo final response cho JSON/SSE theo design; tên model/OpenAI compatibility không đủ. Provider capability verification là future implementation gate, không thuộc vòng hiệu chỉnh này. Đây là gate kỹ thuật, không thêm UI/HTTP request field.

**Routing policy đã chốt: LLM-first.** Mỗi tools-enabled chat turn dùng đúng một non-streaming selector request; không chọn tool thì tiếp tục existing RAG pipeline. Không hybrid/regex router, không skip selector theo keyword và không retry selector. Selection thêm model latency và token cost cho cả tool route lẫn no-tool/RAG route; usage ledger và latency metrics phải tính overhead này như đã thiết kế.

### Selection → execution → final answer

1. **Prepare bounded context.** Load completed whole-turn history qua ConversationHistoryLoader với existing repository handle, dùng whole-turn pruning. Cho tool selector original question và recent history; không dùng rewritten retrieval query để hỏi count/list. Ban đầu không retrieve content chỉ để quyết định metadata operation. Tool descriptions nêu rõ library scope, non-deleted default và count khác active retrieval.
2. **Detect model tool calls trước text normalization.** Gọi tool-bound model bằng đúng một non-stream selector invocation cho tools-enabled turn theo LLM-first policy; không thêm hybrid/regex routing. Đọc structured calls/invalid calls trong response ở facade/provider adapter, trước _text_delta. Không parse content bằng regex thành executable tool, không coi natural-language tool instruction là call. Giữ ID/name/args của structured response; verify missing/duplicate ID, invalid JSON và call count.
3. **No tool calls là RAG route.** Bỏ draft answer của selector để không dùng câu trả lời chưa grounded. Gọi shared RAG preparation hiện có; freeze prompt-selected ordered sources trước SSE metadata. JSON và SSE cùng dùng policy này. Có thêm selection request khi tools gate on, là overhead được ghi usage/latency; off không phát sinh overhead.
4. **Có calls là DOCUMENT_TOOLS route.** Validate toàn bộ allowlisted names/args trước thực thi. Tối đa hai calls tuần tự, không parallel fan-out, không auto-fetch thêm page. Tool route chỉ trả metadata nên sources=[] cố định; không cần retrieve hay embed. Mixed request vừa library operation vừa phân tích nội dung không được tự bật analyze_document; final answer giới hạn điều đã query và đề nghị câu hỏi tiếp cho phần nội dung nếu cần.
5. **Execute.** Với persistent JSON: callback đã có guard/pair. Với persistent SSE: query chỉ chạy sau begin_streaming_turn và sau iterator entry; selector/preparation vẫn có thể ở trước guard như hiện tại. Executor kiểm deadline/cancellation trước mỗi call, dispatch injected Documents facade. Count/list cùng request không có database snapshot chung.
6. **Return results to model.** Giữ assistant structured tool-call message và tạo đúng một model-native tool-result message theo từng call ID, content là serialized normalized envelope; tất cả chỉ sống trong request. Dùng LangChain message/protocol adapter tương thích SDK/provider được verify sau; không persist role TOOL vì MessageRole hiện chỉ USER/ASSISTANT (backend/app/conversation_models.py:23–25). Treat filenames/result strings như dữ liệu, không prompt instructions. Không tự thêm tools khác từ output.
7. **Generate final answer với tools disabled.** Một non-stream answer call cho JSON hoặc ordinary text stream cho SSE; final model không được mở vòng tool mới. JSON aggregate final text; SSE chỉ forward final text deltas và final usage. Selector draft, argument fragments và tool results không được emit thành delta. Empty/whitespace final answer đi qua existing empty-generation failure semantics, không lấy tool success làm assistant COMPLETED.

   **Instructions bắt buộc cho list_documents, dùng chung JSON/SSE:** đọc offset, returned_count, has_more, next_offset và truncated_by_bytes từ tool result. Khi has_more=true, phải nói rõ “Danh sách này chưa đầy đủ”, chỉ mô tả số item thực trả và cho biết người dùng có thể yêu cầu trang tiếp theo ở turn sau với next_offset. Không gọi returned_count là tổng library; không dùng count_documents riêng để khẳng định page đã chứa tất cả. has_more=false ở offset>0 chỉ là hết phần còn lại, không chứng minh đã liệt kê mọi document. Chỉ claim toàn bộ theo bộ lọc tại thời điểm query khi offset=0, has_more=false và truncated_by_bytes=false. Giữ disclosure trong final answer được persist/stream, không chỉ trong hidden tool context. Không tự fetch thêm page hoặc tự tiếp tục full-library pagination.

8. **Finalize ở owner hiện hữu.** Facade trả answer/sources/usage hoặc lỗi; API/ConversationService hoàn thành durable turn và wire terminal. Tool query thành công không chứng minh final model thành công, persistence commit thành công hoặc guard release thành công.

Protocol thực sự của tool-call IDs/messages, binding của cached ChatOpenAI và việc provider nhận ToolMessage khi final call không bind tools: NOT_VERIFIED. Nếu SDK/provider bắt buộc gửi tool schemas trong final request thì phải chứng minh tool_choice=none có hiệu lực hoặc dừng capability enablement; không nới round limit theo mặc định.

### Giới hạn cụ thể đề xuất

| Policy | Giá trị PROPOSED_DESIGN | Ràng buộc/giới hạn claim |
| --- | --- | --- |
| Routing / selector count | LLM-first; 1 non-streaming selector request/tools-enabled turn | No tool → existing RAG; không hybrid/regex router hoặc selector retry; chấp nhận latency/token overhead. |
| Tool-call rounds | 1 round/turn | Một selection response có tối đa 2 calls; không model-controlled loop tiếp theo. |
| Calls/round và calls/turn | 2; 2 | Validate cả batch trước execution; sequential, không automatic retry/correction round. |
| Argument bytes | <=2 KiB UTF-8 compact/raw argument payload mỗi call | Strict schema/allowlist; oversized/nested unexpected fields fail trước query. |
| Result bytes | <=8 KiB/result; <=16 KiB/tổng tool messages | List tối đa 20 items; byte pack ở Documents facade; không cắt JSON. |
| Context budget | Trước mỗi model request tính cả system/history/query, schemas, call messages, tool results và output reserve | Dùng configured context window/output reserve làm trần ứng dụng, không tự suy ra provider window. Reuse whole-turn budget helpers, thêm guard ở facade cho native tool messages/schema overhead; ContextBudgetBuilder hiện không có tool fields. Drop old complete history nếu cần; không truncate tool payload/IDs; còn vượt thì fail. |
| Selector timeout | 15 giây hoặc remaining deadline, lấy nhỏ hơn | Gọi không stream; không dựa trên Groq tool-stream capability. |
| Query budget | max_time_ms=5000/call; await <=5 giây hoặc remaining deadline | Server-side max time là requested DB execution bound, không phải hard wall-clock guarantee cho thread/network/driver. |
| Tool-stage budget | <=10 giây tổng hai reads trong logical deadline | Không tiếp tục call thứ hai sau timeout/cancellation. |
| Tools-enabled execution deadline | min(120 giây, settings.stream_timeout_seconds) từ trước selector; JSON và SSE cùng policy | Bao gồm selector, route preparation và final generation trong logical budget. API/facade phải dùng cùng deadline, không reset sau selection hoặc start event. Không bao gồm terminal DB persistence/guard release hiện hữu; không tuyên bố toàn request hard deadline. |
| Final model invocation | remaining deadline; output reserve cấu hình được áp vào supported output-limit option sau khi verify | Provider có thể không hỗ trợ mọi option; không thay model hoặc assume tool/stream mode. |
| Added adapter close | Best effort, cooperative, ngân sách chờ riêng tối đa 2 giây | Không kill threads; không diễn giải hết thời gian chờ là đã dừng provider. Existing encoder shielded close/finalization vẫn có C08. |

Byte bound không đảm bảo token bound: JSON Unicode, schemas và tool-message overhead được tính riêng trước mỗi request. ApproximateTokenCounter hiện chỉ có public system/human/turn và private _messages (backend/app/context_budget.py:96–119); không gọi private helper rồi giả vờ đã có native ToolMessage contract. Khi implementation phải kiểm tra estimation cho message shapes thực tế; không sửa toàn bộ context_budget architecture hoặc ước lượng provider usage thành usage thật.

Cancellation: propagate qua await boundaries, không schedule thêm queries/model calls sau logical abort. Hủy await asyncio.to_thread/threadpool **không kill synchronous Mongo call**; server query timeout/client timeout chỉ giới hạn phần tương ứng. Kết quả đến muộn bị bỏ, không tự ghi conversation hoặc chạy tiếp tool. Client disconnect JSON không được giả định chắc chắn truyền vào worker closure; đây là giới hạn inherited, không được R1 chữa ngầm.

### Failures và fallback policy

- Unknown tool/invalid args/over-limit: fail trước execution; không gửi lại prompt yêu cầu model tự sửa. Partial batch thành công rồi call sau fail: toàn answer execution thất bại; không trình kết quả batch thiếu như hoàn chỉnh.
- Query error/timeout/output-budget failure: tạo internal error envelope cho diagnostics/dispatch outcome, abort final answer call; không nhờ model đoán count/list từ memory. **Success results** được gửi lại model theo bước 6; **failure envelopes** không bắt buộc thêm một model round để viết lời giải thích, vì terminal error đã có public contract.
- Selector không chọn tool: đây là ordinary RAG routing, không phải lỗi; dùng original question với history/rewrite/scope của pipeline hiện tại.
- Selector/provider lỗi hoặc capability bị reject trong một tools-enabled request: terminal generation error; không silent fallback sang retrieval để giả trả lời câu hỏi library count. Không tự đổi model, provider hoặc tool-calling mode.
- Gate off: đường RAG legacy được giữ, không quảng bá hai tool đã sẵn sàng. T0–T3 chỉ được coi complete về tools khi gate có đủ evidence enablement; off không phải bằng chứng count/list hoạt động.
- Sau final answer đã emit: không retry/restart RAG/tool execution hoặc thay source list; giữ PARTIAL/FAILED semantics theo meaningful content của runtime. Không tạo thêm pair tự động.

## 7. JSON/SSE/Conversation Compatibility

### Lifecycle và public contracts

| Invariant | CURRENT_IMPLEMENTATION | PROPOSED_DESIGN bảo toàn |
| --- | --- | --- |
| Guard owner/sequence | backend/app/conversation_repository.py:117–166 reserve hai sequence và release theo request owner | Tool executor không acquire/release; không reset guard khi tool timeout. JSON giữ callback trong answer_with_persistence; SSE vẫn begin/finalize qua ConversationService. |
| Message-pair creation | backend/app/conversation_service.py:112–129, :197–222; backend/app/conversation_repository.py:168–201 là insert/transition riêng | Một user và một assistant cho cả logical answer, dù có 0/1/2 tool calls. Không persist planner/tool messages; không gọi insert pair mỗi tool. Không gọi multi-write path là transaction. |
| JSON states | backend/app/conversation_service.py:140–186 finalize COMPLETED hoặc FAILED; API backend/app/api/chat.py:397–420 dựng ChatResponse | Same dict keys answer/sources/usage và existing service IDs. Tools fail trước final answer thì existing generation error path; không thêm tool_result field. JSON không được coi hỗ trợ partial streaming chỉ vì ChatResponseStatus có PARTIAL. |
| SSE states | backend/app/conversation_service.py:188–227 tạo STREAMING, :244–278 finalize meaningful content COMPLETED/PARTIAL/FAILED | Tool execution trong active turn trước final text; thất bại chưa có text → FAILED, có meaningful final text rồi fail → PARTIAL. Giữ nguyên emitted whitespace trong content, không cắt text để né C01. |
| SSE ordering | backend/app/api/chat.py:132–159 emit start rồi metadata; :190–253 deltas và một done/error terminal | prepare plan freeze sources; encoder vẫn start(1), metadata(2), final deltas nếu có, terminal duy nhất sequence kế tiếp. Tools route sources=[]; không tool_start/tool_result events, không thêm citation events. |
| Pre/post headers | backend/app/api/chat.py:472–501 pre-header mapping; :197–250 provider/finalization errors sau headers | Selector/schema/RAG preparation error trước headers theo current pre-header response; tool/final-generation error sau headers theo existing SSE error. Không ép emit start khi HTTP failure chưa bắt đầu response. |
| Paginated answer disclosure | Tool pagination metadata là internal contract đề xuất tại mục 5 | Cùng instructions mục 6 cho JSON/SSE: has_more=true luôn công bố chưa đầy đủ; giữ disclosure trong final text/history, không thêm pagination SSE event/DTO field hoặc tự fetch page tiếp. |
| History restoration | MessageRole chỉ USER/ASSISTANT; MessageRecord fields: backend/app/conversation_models.py:136–186; backend/app/history.py:106–139 lọc whole-turn completed | Persist final human-readable answer và aggregate usage; restore không cần tool protocol hoặc schema mới. Structured tool traces/re-execution không có; answer metadata ở quá khứ là kết quả query khi đó, không dữ liệu library hiện tại. |
| Sources/citations | backend/app/rag/pipeline.py:131–148, :312–323; backend/app/citation_mapping.py:12–56; backend/app/schemas.py:168–189 yêu cầu citation trỏ retrieved source | Count/list metadata không có chunk_id nên sources=[], citations=[]; không biến document ID/active pointer thành fabricated chunk citation. Ordinary RAG giữ ordered prompt-selected sources và mapping cũ. |
| Public model metadata | backend/app/schemas.py:69–74; SSEMetadataData ở backend/app/sse_schema.py:47–49 | Dùng cùng configured model cho selector/final để metadata.model tiếp tục có nghĩa; đổi provider/model cho selector là DEFER/owner decision mới. |

Trong SSE tools route, sources=[] đã biết trước execution nên có thể emit metadata trước khi đọc Documents; không cần giữ kết quả raw để phát event riêng. No-tool route phải chuẩn bị retrieval/source selection xong trước metadata. Không bổ sung sources sau delta, không lấy retrieved-but-unused sources gắn vào count/list answer.

Những trạng thái wire/history có thể bất đồng vì lỗi persistence vẫn phải báo đúng theo behavior hiện hữu, không tuyên bố “tool succeeded ⇒ persisted conversation succeeded”. Structured trace không được persist nên không khẳng định auditability/replay/exactly-once Tool Use.

### Failure boundaries và C05 risk acceptance đã chốt

**Giữ nguyên JSON/SSE conversation lifecycle. Owner chấp nhận C05 pre-guard preparation là known design risk, không phải issue đã resolved.** JSON vẫn acquire guard/create pair trước generate callback; SSE vẫn selector/preparation trước acquire, rồi tool execution sau begin_streaming_turn và iterator entry. Selection có thể tốn model cost trước khi SSE request bị conflict/reject và có thể dùng stale history. Không reorder guard hoặc sửa C01–C08 trong vòng này.

| Failure stage | JSON boundary | SSE boundary | Owner / giới hạn |
| --- | --- | --- | --- |
| Selector / plan validation / RAG preparation | Persistent: chạy trong generate callback sau guard/pair, dùng generation-failure path hiện có; stateless dùng existing HTTP/JSON error mapping. | Trước begin_streaming_turn và response headers: existing pre-header HTTP/JSON error mapping; chưa tạo pair mới cho request này. No-tool selection thành công đi tiếp RAG, không phải failure. | Shared orchestration phát hiện lỗi; không retry selector hoặc silent fallback khi provider lỗi. C05 cost/history risk được chấp nhận. |
| Tool execution | Persistent: sau guard/pair; lỗi được đưa về existing service generation-failure path. | Sau begin/iterator entry, start/metadata; chưa có final text thì existing error terminal FAILED, không fake empty success. | Executor dừng scheduling, Conversations sở hữu terminal write/release; không ghi messages từ tool. |
| Final generation | Non-stream failure/empty answer dùng existing JSON generation-error path; không coi tool success là completed answer. | Sau headers: meaningful final text đã emit thì PARTIAL khi lỗi, chưa có meaningful text thì FAILED; không restart answer/tool route. | API giữ wire semantics, Conversations giữ durable state; whitespace discrepancy C01 không được sửa hoặc che. |
| Persistence / guard release | Dùng existing persistence/error mapping; acknowledged message commit và guard release là các kết quả khác nhau, không replay whole turn. | Finalize trước done/error như hiện tại; finalization/release error dùng existing mapping, có thể bất đồng wire/history theo C03. | Tool success không bảo đảm persisted success. C02–C04/C06–C08 còn nguyên; không bảo đảm cleanup/terminal khi gặp C07 trước iterator entry. |

Flag mặc định disabled. Trước enablement phải có evidence của configured Groq model/SDK cho structured tool calling, call/result correlation, final non-stream JSON answer và final SSE text generation với policy tools-disabled như thiết kế. **NOT_VERIFIED:** chưa thực hiện capability verification; đây là implementation/enablement gate tương lai, không là action của vòng sửa documentation.

### Usage và latency accounting

CURRENT_IMPLEMENTATION: ProviderStreamChunk có usage (backend/app/rag/pipeline.py:57–61); encoder giữ giá trị usage cập nhật gần nhất (:181–183), không có ledger nhiều model calls. JSON chỉ lấy generation response usage (backend/app/rag/pipeline.py:185–188). RewriteMetrics tách provider/estimated (backend/app/query_rewriting.py:278–314); public ChatUsage/MessageUsage không có breakdown (backend/app/schemas.py:76–87; backend/app/conversation_models.py:122–133).

PROPOSED_DESIGN cho **tools-enabled requests**:

1. Facade giữ request-local ledger theo mỗi actual provider invocation: selector, final answer; nếu no-tool route có rewrite thì tính cả rewrite khi có evidence usage_source=provider. Query database không tự sinh token usage; serialized results đã được provider tính vào input của final model, không cộng hai lần.
2. Mỗi invocation nhận **một final normalized usage**; không cộng mọi cumulative usage snapshot trong stream. Aggregate input/output/total theo từng call. Không cộng token estimate vào provider totals. Nếu một invocation đã chạy nhưng không cung cấp complete actual usage, public usage=null; internal diagnostics có thể ghi known totals/coverage có giới hạn, không trình known partial như tổng đầy đủ. Failed/cancelled call thường làm coverage thiếu.
3. Trả aggregate cuối cùng qua cùng shape usage cho JSON; SSE giữ ledger đến terminal và đưa aggregate vào usage-bearing normalized chunk để encoder không overwrite bằng final-call-only usage. Persist đúng aggregate được publish. Không thêm public breakdown fields hoặc DB schema.
4. Gate off giữ nguyên accounting legacy, không dùng R1 để sửa usage baseline/evaluation. Với no-tool route có thêm selector, chi phí này phải được tính theo quy tắc trên; không gọi đó là zero overhead.
5. Tracker bắt đầu ở đầu handler như hiện tại (backend/app/api/chat.py:445; backend/app/stream_metrics.py:25–68), do đó first_event/first_content/total bao gồm selection/preparation/hidden tools theo vị trí thực. first content là final answer text, không selector/tool result. Optional bounded internal logs theo request_id cho stage latency/tool name/outcome, không raw args, filenames/content hoặc connection details. Không sửa StreamMetric/public DTO để thêm fields trong minimum scope.

### C01–C08 được giữ như known risks, không sửa ở R1

Nguồn: docs/audits/RAG-CONVERSATION-AUDIT-0B02.md:156–241 và docs/audits/RAG-CODEBASE-ASSESSMENT-0C.md:92–99. Các nhãn audit gốc được giữ, không coi là runtime reproduction mới.

| Risk | Source evidence hiện tại | Hệ quả cho thiết kế / disposition |
| --- | --- | --- |
| C01 — CONFIRMED_DEFECT | backend/app/sse_schema.py:186–194 dùng delta presence; backend/app/api/chat.py:209–244 và backend/app/conversation_service.py:244–250 dùng meaningful content | Whitespace-only tool final stream vẫn có thể gặp schema/runtime divergence. Không đổi whitespace/status rule trong R1; validation tương lai phải ghi rõ known exception, không claim toàn parity pass. |
| C02 — CONFIRMED_DEFECT | backend/app/conversation_service.py:214–229 pair inserted rồi mark STREAMING có thể fail, release nhưng không terminalize placeholder | Tool query phải bắt đầu sau setup thành công, nhưng không giải quyết pending placeholder setup failure. Defer riêng. |
| C03 — CONFIRMED_DEFECT | backend/app/conversation_service.py:274–278 terminal write rồi release; backend/app/api/chat.py:224–225 map persistence error | Tool/final model success không đồng nghĩa wire done hoặc guard cleanup. Không ghi lại terminal message để “sửa” ambiguity trong tool executor. |
| C04 — CONFIRMED_GAP | backend/app/conversation_repository.py:117–166; backend/app/main.py:21–38 không recovery abandoned guard | Bound tool loops không giải quyết process crash/stale guards. Không thêm TTL/lease/reconciler tự động. |
| C05 — DESIGN_RISK | backend/app/api/chat.py:453–470 vs backend/app/conversation_service.py:107–132 | Giữ pre-guard SSE planning có thể tốn selector cost và dùng stale history; không hứa guard serialize preparation. Documents reads chỉ sau acquire. Owner đã chấp nhận C05 là known design risk cho MVP; chưa resolved/fixed, không reorder lifecycle trong correction này. |
| C06 — DESIGN_RISK | backend/app/conversation_repository.py:117–220; service tạo new UUID mỗi submit | Một tool read side-effect-free không tạo exactly-once conversation; không auto-replay pair hoặc retry whole turn. |
| C07 — DESIGN_RISK | backend/app/api/chat.py:128–168, :256–312, :464–516 | Before-iterator-entry/generic encoder fault vẫn có thể mất cleanup/terminal; tool executor không nhận ownership thay API để che gap. Không chạy tool trong SSE pre-header setup nhằm tránh thêm query execution ngoài durable iterator. |
| C08 — DESIGN_RISK | backend/app/api/chat.py:169–223, :278–297 | Logical tool deadline không hard-bound existing provider close/persistence/guard release. Không thêm unbounded awaits ở new driver; không tuyên bố whole request <=120s. Existing cleanup policy là deferred finding. |

C05–C08 interleavings/timing/provider cancellation: NOT_VERIFIED. Owner có thể cho phép offline implementation với gate off và risk acceptance rõ ràng; không dùng R1 để ngầm phê duyệt live rollout hoặc chữa C01–C08.

## 8. Minimum Integration Change Matrix

Đây là **kế hoạch T0–T3 đề xuất theo prompt hiện tại** vì tooluse.md thiếu. Mọi file/action dưới là PROPOSED_DESIGN; không file nào được tạo/sửa trong R1 ngoài báo cáo. T0 = chốt contracts/capability gates; T1 = Documents reads; T2 = bounded Tool Use; T3 = shared orchestration/adapters + offline acceptance. Không khẳng định đó là tên phase roadmap gốc.

| Sequence | Classification | Proposed file(s) | Trách nhiệm/dependencies | Acceptance criteria cho implementation được duyệt sau |
| --- | --- | --- | --- | --- |
| T0.1 | REUSE_AS_IS | BACKEND-DEPENDENCY-ANALYSIS.md; real source interfaces | Giữ dependency/ownership baseline, ghi owner decisions mục 10 | Không relocation; chỉ hai read tools; giữ accepted global/deleted semantics và policy values. R1 APPROVE_WITH_CORRECTIONS; chờ owner duyệt bản hiệu chỉnh và explicit authorization R2. |
| T0.2 | MODIFY_EXISTING | backend/app/config.py; .env.example | Thêm một server-only enable gate default false; policy limits tập trung trong new executor/facade thay vì nhiều knobs | Off không provider selection/tool reads, không tác động đường RAG cũ. Không thêm package/dependency; enablement chưa được coi verified chỉ bằng config. Không sửa .env thật. |
| T1.1 | MODIFY_EXISTING | backend/app/document_repository.py | Hai proposed methods count_documents_for_tools/list_documents_for_tools; repository-owned predicate/sort/query max time | Exact count identity; cùng status predicate với list cũ; tie-break timestamps bằng _id; bounded fetch; safe RepositoryError. list_documents API cũ nguyên chữ ký/order. |
| T1.2 | NEW_MODULE | backend/app/document_queries.py | Documents read facade, inject existing repository; imports repository/models | No Qdrant/storage/ingestion dependency; projection/8KiB packing/sentinel pagination đúng, không len(page) count. Empty/deleted/same filename/multi-version cases rõ. |
| T2.1 | NEW_MODULE | backend/app/tool_use/contracts.py; backend/app/tool_use/__init__.py | Strict args/result/errors/invocation context; __init__ rỗng | Only count/list, strict types/unknown keys; stable envelope; không import executor/domain services ở contracts/init. |
| T2.2 | NEW_MODULE | backend/app/tool_use/document_tools.py | Hai handlers/tool descriptions, imports contracts và Documents query facade | Không collection query/predicate riêng; không clients/HTTP/pipeline; không mutate Documents. Tool output không chứa storage/source secrets. |
| T2.3 | NEW_MODULE | backend/app/tool_use/executor.py | Inject registry, validation/dispatch/deadline/round-call-size limits, imports contracts | 1 round/2 sequential calls; unknown/invalid/over-limit không query; no retry; cancellation dừng scheduling; query failures không giả thành empty success. |
| T3.1 | NEW_MODULE | backend/app/chat_orchestration.py | Shared plan/run facade; 11 allowed imports ở mục 4; provider protocol, usage/context budgets | JSON/SSE cùng LLM-first selector (1 non-stream request/turn), validation/executor policy; no-call → RAG; không hybrid/regex router; frozen sources; aggregate usage hoặc null khi thiếu; has_more=true phải công bố incomplete và hỗ trợ yêu cầu page sau ở turn kế; không auto full-library pagination hoặc reverse imports. |
| T3.2 | MODIFY_EXISTING | backend/app/api/chat.py | Đổi generation/preparation/iterator target sang facade; giữ HTTP/SSE/persistence adapter; truyền request deadline cho tools-on path | Routes/DTO fields/event names/order/IDs không đổi; JSON callback vẫn trong guard; SSE query sau begin/body; terminal finalize một lần theo path hiện hữu, không tool-owned writes. |
| T3.3 | REUSE_AS_IS | backend/app/rag/pipeline.py, rag/retriever.py, rag/prompt.py, citation_mapping.py | Legacy RAG preparation/generation/injection seams | RAG ordinary questions vẫn history-aware, active scope, ordered sources; pipeline không import orchestration/tool modules. Không đưa metadata results thành chunk citations. |
| T3.4 | REUSE_AS_IS | conversation_service.py, conversation_repository.py, conversation_models.py, conversation_schemas.py, history.py, schemas.py, sse_schema.py | Durable turn, restore và public contracts | Một logical pair; tool protocol ephemeral; history render final text như hiện tại; known C01–C08 ghi nhận không bị đánh dấu fixed. |
| T3.5 | REUSE_AS_IS | rag/llm.py, cloud_connections.py, main.py, stream_metrics.py, context_budget.py | Existing provider/client lifecycle, metric timing, ordinary context helpers | Không đổi cached base model/shared settings từ per-request binding; không clients riêng; native tool-message budgeting bổ sung ở facade, không giả existing helper đã xử lý mọi message. Provider acceptance NOT_VERIFIED tới khi kiểm chứng riêng. |
| T3.6 | MODIFY_EXISTING | backend/tests/test_chat_stream.py, test_chat_persistence.py và test_rag_integration.py | Future offline transport/service regression additions, không chạy ở R1 | Deterministic model/repository doubles, giữ lifecycle/DTO/source behavior cho tool success/error/no-call. Không cần cloud/provider để test policy. Không sửa expected results nhằm che C01–C08. |
| T1–T3 verification | NEW_MODULE | backend/tests/test_document_queries.py, test_tool_use.py, test_chat_orchestration.py | Future focused offline regressions cho query semantics/packing, policy và shared driver | Count != versions/chunks; deleted default; timestamp tie; empty/sentinel/byte cap; fail/cancel/limits; no reverse imports; tool-output/context budget và usage coverage. Đây là plan, không test files tạo trong R1. |
| Sau T3 / scope khác | DEFER | analyze_document, write/delete/update tools, UI/tool traces, RAG-as-tool, DB/SSE extensions, broad package migration | Không cần cho two metadata tools | Không đăng ký ngoài allowlist; không có placeholder capability. Future analyze_document chỉ cắm capability handler + contract được duyệt mới, không import API/pipeline ngược. |

Minimum application additions: **5 substantive modules + một package initializer rỗng**, không general registry framework, không tách thêm provider adapter file nếu facade nhỏ đủ rõ. Minimum application modifications: repository, chat API, config/example gate; các modules khác reuse. Test-file plan là verification sau authorization, không thay đổi read-only scope của R1.

Acceptance cross-cutting ở T3: kiểm tra static imports thực tế vẫn DAG, cả routes gọi cùng policy, call correlation đúng, tools-disabled legacy behavior giữ nguyên, byte bounds không phá pagination, tool errors không bị model bịa đáp án, và nguồn metadata không thành fabricated citations. Provider capability verification/live experiments cần scope được owner duyệt riêng; không lấy mocks làm bằng chứng Groq support.

## 9. Risks, Open Decisions & Deferred Scope

| Decision/risk | Recommendation PROPOSED_DESIGN | Trạng thái / blocker |
| --- | --- | --- |
| Hai tài liệu còn thiếu | Dùng scope count/list trong prompt này; đối chiếu lại roadmap nếu owner cung cấp sau | NOT_VERIFIED về R0 sơ bộ/T0–T6 gốc; không cản hoàn thành R1 nhưng không gán milestone gốc. |
| Library vs selected-session scope | Initial metadata tools library-wide; output ghi scope=library; session scope giữ cho content retrieval | Giữ accepted R1 semantics; nếu đổi selected scope phải thiết kế/duyệt predicates/args mới, không dùng active_version_ids làm count shortcut. |
| Deleted/status semantics | Mặc định status != DELETED, include_deleted explicit boolean; không mặc định INDEXED-only | Giữ accepted R1 business contract; data hiện có và count thực tế NOT_VERIFIED. |
| Query sufficiency | Hai read methods mới; stable tools-only sort, không thay list API cũ | Giữ accepted R1 query design; hiệu năng skip/sort/timeouts/index fit NOT_VERIFIED, không tạo index trong R1. |
| Routing policy | Đã chốt LLM-first: đúng 1 non-stream selector/tools-enabled turn; no tool → existing RAG; không hybrid/regex router | Chấp nhận additional model latency/token cost cho cả tool/RAG routes; không phải open routing decision còn lại. |
| Pagination/completeness | <=20 items/call; giữ returned_count/has_more/next_offset; has_more=true bắt buộc disclose incomplete theo instructions mục 6 | Người dùng yêu cầu page sau trong turn kế; không claim all documents khi range chưa complete. Automatic full-library pagination DEFER. |
| Provider capability | Flag default disabled; enablement cần verify configured Groq model/SDK hỗ trợ structured non-stream selection, matched tool-result messages và final JSON/SSE response generation | **Blocker enablement**, không blocker hoàn thành correction/design. Verification là future implementation gate, NOT_VERIFIED và không chạy trong vòng này; default model name/OpenAI compatibility không là evidence. |
| Single round và mixed requests | 1 round/2 calls; metadata route không làm content analysis; không auto paginate | Giữ accepted R1 limits; phần content/multi-step là DEFER, không chế agent loop để bù. |
| SSE pre-guard planning | Giữ current JSON/SSE lifecycle; query chỉ sau guard; owner đã chấp nhận selection cost/stale-history risk C05 | Known design risk được chấp nhận, chưa resolved/fixed; không còn yêu cầu quyết định reorder lifecycle cho MVP. Các failure boundaries tại mục 7 giữ audit risks hiện hữu. |
| Persistence failures | Không coi reads/model answer success là conversation success; giữ C02/C03/C04/C06/C07 | Owner quyết định risk acceptance/offline scope trước enablement; không ngầm fix hay waive findings. |
| Timeout/cancellation | Logical bounded additions, không hard-kill workers, no retry/no automatic new queries | C08/infrastructure behavior NOT_VERIFIED; output deadline khác cleanup deadline. |
| Accounting nhiều calls | Aggregate actual provider usage; thiếu coverage → null; bounded internal breakdown | Giữ accepted R1 accounting semantics cho tools-on và legacy off. Không đưa estimates vào totals hoặc thêm DB fields. |
| Context/token fidelity | Count schemas + native messages; preserve call/result protocol; prune history nguyên turn trước khi fail budget | SDK shape/token estimate NOT_VERIFIED; không cắt numeric count/result JSON để ép vừa. |
| Conversation history | Final text chỉ, không persist tool protocol/results/trace | Không có replay/audit trace; câu trả lời metadata cũ có thể stale theo thời gian, cần query mới khi hỏi current state. |

Deferred rõ ràng: analyze_document chi tiết, content retrieval tool, file parsing tools, status/name/date filters, cursor/snapshot pagination, full count/list snapshot transaction, tool mutation, autonomous planning/memory, LangGraph/MCP/broker/microservices, public tool SSE events/UI, new persistence schemas, multi-tenant auth redesign, fixes F/C/U và restructure toàn backend. Không thêm dependency hay requirement provider mới chỉ vì tên framework có sẵn.

## 10. Final Verdict & Owner Approval Gate

**Documentation verdict: READY_FOR_OWNER_APPROVAL.** Ba corrections đã nhất quán giữa routing, contracts, answer instructions, lifecycle/failure boundaries, risks và approval gate. R1 giữ các accepted boundaries/dependency decisions; không cần broad directory restructure, chưa implement hoặc chứng nhận runtime/provider compatibility.

Các quyết định kiến trúc R1 đã được chấp nhận giữ nguyên. Bản hiệu chỉnh ghi nhận ba quyết định cuối dưới đây trong baseline để owner duyệt documentation; không mở lại scope hoặc coi đó là authorization implementation:

1. Ownership/import rules và 5 substantive modules + empty initializer được đề xuất; repository/API/config là minimum modification set, không relocate source hiện tại.
2. Giữ library-wide count/list, status-based deleted default, count identities, stable created_at/_id order, offset/sentinel pagination, 20-item/8-KiB result cap và hai repository read additions. Correction completeness: bảo toàn returned_count/has_more/next_offset; has_more=true thì final answer bắt buộc nói chưa đầy đủ; chỉ claim all khi queried range đầy đủ theo mục 5–6. Page sau do người dùng yêu cầu ở turn kế; automatic full-library pagination DEFER. Đây là proposed implementation contracts, không interfaces đã tồn tại.
3. Correction routing: LLM-first với đúng một non-stream selector/tools-enabled chat turn; no tool → existing RAG; chấp nhận additional model latency/token cost; không hybrid/regex router. Giữ 1 round/2 sequential calls, final generation với tools disabled và no automatic fallback/retry khi tool/provider fail.
4. Logical deadlines, tool/message/token bounds, aggregate-actual-or-null usage, private ephemeral tool protocol; giữ routes, DTOs, SSE events và DB schema.
5. Correction lifecycle/gate: giữ current JSON/SSE conversation lifecycle; C05 pre-guard preparation là accepted known design risk, chưa resolved. Selector/tool/final-generation/persistence failures theo boundaries mục 7. Feature flag default disabled; phải verify configured Groq model structured tool calling và final JSON/SSE generation behavior trước enablement. Verification là future implementation gate, không thực hiện ở correction round. C01–C08 không được fix; audit fixes/lifecycle restructuring cần scope riêng.

### Remaining implementation blockers — tách khỏi documentation verdict

- Chưa có **explicit owner approval để bắt đầu R2/implementation**; READY_FOR_OWNER_APPROVAL chỉ là trạng thái tài liệu đã hiệu chỉnh nhất quán.
- Trước feature enablement, configured Groq model/SDK capability evidence vẫn thiếu (**NOT_VERIFIED**): structured tool calling/correlation và final JSON/SSE generation theo policy đã chốt. Việc kiểm chứng thuộc implementation gate tương lai; không thực hiện provider calls trong correction round.
- Implementation và acceptance checks đã đề xuất tại mục 8 chưa được thực hiện. C01–C08 vẫn tồn tại theo audit; riêng C05 đã được owner chấp nhận là known risk, không là yêu cầu sửa/reorder trước MVP. Không coi missing roadmap hoặc các scope DEFER là blocker mới cho documentation corrections.

### Verification record — R1 ban đầu, 2026-10-29

- **Deliverable/schema:** đúng 10 sections theo prompt; chỉ tạo BACKEND-MODULE-BOUNDARIES.md. Không tạo tool_use/, source module, placeholder, test file hoặc scanner script.
- **Dependency verification:** lấy 38 nodes/102 unique edges từ inventory R0-B được duyệt; additive graph thêm 5 substantive nodes/17 edges, topo-sort thành công 43/43 nodes và 119 edges. Empty proposed __init__ không thêm cạnh. Kết luận không new static cycle chỉ áp dụng cho danh sách imports được thiết kế; implementation chưa có, cần kiểm tra lại sau khi được duyệt.
- **Interface/source verification:** 85 source path/line references trong draft đã kiểm tra tồn tại và nằm trong file bounds; chữ ký thật và predicate/order được đọc trực tiếp ở document_repository.py:98–136, document_service.py:56–75. Hai for_tools methods được đánh dấu PROPOSED ONLY, không ghi là interface có sẵn. DocumentRepository giữ query semantics; facade/tools không sở hữu Mongo predicates.
- **Contract review:** không thêm public routes/DTO fields/SSE events hoặc persisted roles/schema. Một logical message pair, Conversations vẫn sở hữu guard/finalization. Source/citation identity không được tạo từ metadata tool results. C01–C08 được ghi rõ là inherited risks, không claim fixed hoặc unconditional JSON/SSE parity.
- **Provider/runtime:** structured selection, tool-result protocol, binding/streaming modes, token estimation/SDK timeout behavior và actual model deployment đều NOT_VERIFIED; không gọi Groq/Gemini/MongoDB/Qdrant để xác minh. Không dùng web/provider docs để biến source declaration thành runtime capability claim.
- **Integrity:** SHA-256 trước/sau không đổi cho 55 file snapshot: toàn bộ 38 Python application sources, sáu audit hiện hữu, R0-B report, hướng dẫn/README và các manifest/config templates đã đọc. File list backend/app không thêm/bớt. Tracked git diff giữ nguyên hai README edits đã có trước R1; R0-B report và docs/audits/ cũng giữ nguyên. Không source/config/dependency changes thuộc vòng này.
- **Execution:** chỉ filesystem/git/rg read-only inspection và Node built-ins để dựng/check design graph, fingerprint, validate source references và ghi báo cáo. Không Python/application imports; không tests, builds, servers, application scripts, package install/environment repair hoặc external service/network calls.
- **Approval tại thời điểm R1 ban đầu:** các decisions khi đó chờ owner review. Review sau đó là APPROVE_WITH_CORRECTIONS; bản ghi corrections 2026-10-30 dưới đây thay thế trạng thái approval cũ, không cấp authorization triển khai/R2.

### Documentation corrections verification — 2026-10-30

- Chỉ sửa BACKEND-MODULE-BOUNDARIES.md; giữ ownership, dependency graph, repository design và giới hạn execution đã được chấp nhận. Không tạo file/package/placeholder hoặc di chuyển module.
- Routing nhất quán ở mục 1, 6, 8–10: LLM-first, 1 non-stream selector/tools-enabled turn, no-tool → existing RAG, có latency/token overhead, không hybrid/regex router.
- Pagination nhất quán ở mục 1, 5–10: <=20 items/call; giữ returned_count/has_more/next_offset và byte-cap behavior; answer instructions bắt buộc incomplete disclosure khi has_more=true, không claim all khi range chưa complete, page sau ở subsequent turn; no automatic full-library pagination.
- Lifecycle/gate nhất quán ở mục 1, 6–10: giữ current JSON/SSE ordering/guard ownership; chấp nhận C05 như known design risk chưa resolved; nêu riêng selector/tool/final-generation/persistence failure boundaries; flag default disabled, provider verification là future implementation/enablement gate và vẫn NOT_VERIFIED.
- Documentation-only review; không tests, builds, application/verification scripts, source/config edits, external API/provider/database calls hoặc C01–C08 fixes. Documentation verdict: READY_FOR_OWNER_APPROVAL; dừng sau corrections, không bắt đầu R2.

**STOP AFTER R1.** Chưa có owner approval cho implementation/R2. Không tạo tool_use package, không viết query methods, không thay routes/lifecycle, không chạy verification suite/provider experiments và không sửa F/C/U findings.

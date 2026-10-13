# CURRENT_CHANGE — Nhật ký thực thi RAG V2

> **Vai trò:** Ghi ngắn gọn những gì Agent **thực sự đã làm** sau mỗi task, kèm file thay đổi, kiểm thử và công việc kế tiếp. Kế hoạch/checklist chính nằm tại [`PROJECT_LOG_V2.md`](./PROJECT_LOG_V2.md). Không tự nhận hoàn thành từ nội dung kế hoạch.

## 1. Trạng thái gần nhất

- **Giai đoạn:** Giai đoạn 5 — IN PROGRESS; `P5-01`…`P5-04` COMPLETED
- **Task vừa hoàn thành:** `P5-04` — RAG integration
- **Task tiếp theo:** `P5-05` chưa bắt đầu; chờ giao việc riêng
- **Blocker:** Không có blocker cho P5-04; M-06 còn chờ P5 evaluation
- **Lần cập nhật:** P5-04 focused 48/48, full 147/147, live scoped smoke và JSON/SSE transport PASS

> **Quyết định hạ tầng:** MongoDB Atlas cloud, không dùng MongoDB container; Qdrant Cloud (người dùng đã tạo cluster), không dùng Qdrant Docker; raw files lưu local. IP Access List Atlas hiện `0.0.0.0/0` theo xác nhận người dùng — chỉ phù hợp tạm cho development, cần thu hẹp khi có thể. Agent cần kiểm tra `QDRANT_URL` và `QDRANT_API_KEY` đã có trong `.env`, không in/copy giá trị vào log; `.env.example` chỉ dùng placeholder. Không lưu MongoDB URI/Qdrant URL thực/credentials trong file này. Đây là cập nhật tài liệu, **không phải bằng chứng P1-02 hoặc M-02 đã triển khai**.

## 2. Quy tắc ghi nhật ký dành cho Agent

1. Sau **mỗi task**, thêm đúng một mục nhật ký ở **đầu Mục 3** (mới nhất trên cùng); không ghi lại nguyên roadmap hoặc reasoning dài.
2. Ghi `Task ID`, thay đổi thực tế, những file đã sửa, lệnh kiểm thử + trạng thái **PASS / FAIL / NOT RUN**, vấn đề tồn đọng, task kế tiếp. Chỉ ghi PASS nếu đã thực sự chạy và xác minh.
3. Đồng bộ phần **Trạng thái gần nhất** ở trên với dashboard/checkbox của `PROJECT_LOG_V2.md`. Nếu task chưa nghiệm thu, ghi `IN PROGRESS` hoặc `BLOCKED`, không đánh dấu `[x]`.
4. **Không chép secrets, nội dung tài liệu nội bộ, stack trace chứa thông tin nhạy cảm** hay output quá dài vào log. Dùng đường dẫn file và tóm tắt ngắn.
5. Giữ khoảng **10–15 mục gần nhất** trong file này. Khi vượt ngưỡng, chuyển mục cũ nguyên vẹn sang `docs/changelog/phase-XX.md` (tạo thư mục nếu cần), thêm đường dẫn archive ở Mục 4. **Không xóa lịch sử nếu chưa archive thành công.**
6. Nếu có quyết định kiến trúc mới đã được duyệt, ghi tóm tắt quyết định vào Mục 12 của `PROJECT_LOG_V2.md`; entry ở đây chỉ ghi ảnh hưởng thực tế.

## 3. Nhật ký thay đổi (mới nhất ở trên)

<!-- Agent: chèn entry mới bên dưới dòng này. Không coi template hoặc ghi chú tạo file là bằng chứng triển khai. -->

### [2026-10-12] M-06 — Regression liên giai đoạn

- **Trạng thái:** COMPLETED; workstream migration M-01…M-06 và roadmap V2 hiện tại COMPLETED.
- **Đã thực hiện:** Audit coverage P2–P5 và bổ sung `verify_m06.py` làm gate xuyên giai đoạn trên FastAPI lifespan, MongoDB Atlas, Qdrant application collection và Gemini embedding thật. Verifier tạo đúng một session `SELECTED_DOCUMENTS` với whole-turn seed, dùng deterministic rewrite/generation để kiểm tra ổn định hai request `/chat` và `/chat/stream`: retrieval không thoát active version đã chọn, original query vẫn vào final prompt, JSON/SSE contract và usage đúng, SSE reconstruct đúng, sáu messages/request linkage/terminal status ổn định, JSON citation và terminal stream citation cùng truy ngược server source, guard được release. Script không sửa document/raw file/Qdrant point và cleanup session/messages chính xác. Thêm unit coverage cho SSE parser, scope và citation assertions; cập nhật README command/kết quả.
- **Files thay đổi:** `backend/scripts/verify_m06.py`, `backend/tests/test_m06_verification.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Live `verify_m06.py` — PASS 2 transports, 6 messages, 2 rewrite calls, 5 scoped sources mỗi transport, citation/persistence và cleanup; live read-only `smoke_provider_stream.py` — PASS 13 valid text deltas, usage present. Focused citation/scope/JSON/SSE/history tests PASS 42/42; toàn bộ unit/API/in-memory regression PASS 155/155; `compileall`, `pip check`, secret scan, README reference/fence check và `git diff --check` PASS. M-06 history retrieval eval với rewriter external thật — NOT RUN vì quyền chạy bị từ chối do nguy cơ gửi history/query payload sang provider; không tạo artifact và không đổi kết quả này thành PASS. Bằng chứng live P5-05 hiện có vẫn PASS 5/5.
- **Tồn đọng / quyết định:** Không phát hiện regression runtime nên không sửa production code. Integrated verifier cố ý deterministic ở rewrite/generation để tránh quota và dữ liệu đi ra provider; provider transport được smoke riêng bằng prompt không nhạy cảm. Các giới hạn đã chốt vẫn còn: thiếu auth/multi-tenant, approximate budget, conservative rewrite guard, stale generation guard sau hard crash, chưa realtime stream citations và eval corpus nhỏ.
- **Tiếp theo:** Không còn task chưa hoàn thành trong `PROJECT_LOG_V2.md`; chờ phạm vi mới được giao.

### [2026-10-12] P5-06 — Final docs

- **Trạng thái:** COMPLETED; Giai đoạn 5 COMPLETED.
- **Đã thực hiện:** Đối chiếu README với routes, Pydantic JSON/SSE contract, settings, history loader, context budget, query rewriter, shared RAG pipeline và evaluation runner hiện tại. Bổ sung luồng history-aware end-to-end từ MongoDB history/scope qua conditional rewrite, active-version Qdrant filter, budgeted prompt đến JSON/SSE/citation; thêm `/chat/stream` vào API table, `STREAM_TIMEOUT_SECONDS`, ví dụ persistent multi-turn, quy tắc server-owned history/scope, unit/focused/cloud smoke/evaluation commands và project tree P5. Làm rõ first-run/re-run/retrieval-only eval, quota behavior, external-provider data boundary và các giới hạn scale, detector/grounding, selected scope, version snapshot, realtime SSE citation, stale guard và heuristic eval. Không thay đổi runtime code hay API.
- **Files thay đổi:** `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** README validation — PASS: 34 code fences cân bằng, đủ 8 section/marker bắt buộc, 9/9 referenced P5 files tồn tại, không còn marker tài liệu cũ; toàn bộ unit/API/in-memory regression PASS 152/152; `compileall`, `pip check`, `git diff --check` PASS. Không chạy lại live cloud smoke vì task chỉ thay tài liệu; dùng đúng bằng chứng live P5-04/P5-05 đã lưu và không đổi code/config.
- **Tồn đọng / quyết định:** Giai đoạn 5 đã hoàn thành nhưng các giới hạn trong README vẫn áp dụng: token estimate xấp xỉ, lexical detector/guard bảo thủ, long-session loader chưa summary, public API chưa đổi `SELECTED_DOCUMENTS`, SSE chưa phát realtime verified citations, stale guard sau hard crash, thiếu auth/multi-tenant và eval corpus nhỏ. `M-06` vẫn IN PROGRESS; không tự động nghiệm thu trong task tài liệu này.
- **Tiếp theo:** `M-06` — chờ giao việc riêng để chạy/đối chiếu regression liên giai đoạn và quyết định trạng thái cuối.

### [2026-10-12] P5-05 — Evaluation

- **Trạng thái:** COMPLETED; Giai đoạn 5 IN PROGRESS.
- **Đã thực hiện:** Thêm golden set 5 nhóm pronoun/follow-up, topic switch, long session, out-of-document và cross-document; runner chạy paired baseline không history với history-aware trên collection Qdrant eval cô lập. Tách production pipeline thành shared component seam để evaluation dùng đúng budget/rewrite/retrieval/prompt/generation runtime. Báo cáo ghi retrieval hit/recall, fact coverage, faithfulness proxy, fallback/referent accuracy, budget, latency và rewrite/generation tokens. Provider lỗi có retry hữu hạn, chỉ lưu loại lỗi; `--retrieval-only` cho phép kiểm tra retrieval/budget/rewrite khi quota generation bị chặn. Dependent query phải gọi rewriter; grounding rejection/timeout được chấp nhận như safe fallback nhưng vẫn phải độc lập vượt retrieval/answer gates.
- **Files thay đổi:** `backend/app/rag/pipeline.py`, `backend/evaluation/history_golden_set.json`, `backend/evaluation/history_eval.py`, `backend/evaluation/results/p5_history_eval.json`, `backend/evaluation/results/p5_history_retrieval.json`, `backend/scripts/eval_history_cli.py`, `backend/tests/test_history_evaluation.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Focused evaluation/RAG/rewrite/budget PASS 25/25; toàn bộ unit/API/in-memory regression PASS 152/152. Live retrieval-only PASS 5/5 executions, retrieval hit/recall `1.0`, mọi budget hợp lệ; referent answer accuracy là `null` vì mode này không generation. Live paired generation PASS 5/5: baseline và history-aware retrieval hit/recall, answer relevance, faithfulness proxy, fallback accuracy đều `1.0`; referent accuracy `1.0`; history-aware delta trung bình `+5873.7 ms`, tổng `+4120` tokens. Long-session rewrite timeout và cross-document grounding rejection fallback nguyên query an toàn rồi vẫn PASS. Không re-index application collection, không ghi MongoDB và không in credentials/raw provider response.
- **Tồn đọng / quyết định:** Corpus chỉ có 5 history cases và metrics grounding/fact coverage là heuristic, không thay thế human/LLM judge. Baseline đã retrieval đúng toàn bộ in-document cases trên corpus nhỏ nên lần chạy này không cho thấy uplift retrieval; giá trị history được xác minh qua referent answer và behavior rewrite. Latency/token phụ thuộc provider và có thể biến động giữa runs. `M-06` giữ IN PROGRESS đến final cross-phase audit ở P5-06.
- **Tiếp theo:** `P5-06` — chưa bắt đầu; chờ giao việc riêng. Không tự động triển khai P5-06 hoặc hoàn tất M-06.

### [2026-10-12] P5-04 — RAG integration

- **Trạng thái:** COMPLETED; Giai đoạn 5 IN PROGRESS.
- **Đã thực hiện:** Thay hai nhánh dựng context riêng bằng shared `PreparedRagStream` builder cho `/chat` và `/chat/stream`. Với session, runtime tải default whole-turn history và scope từ MongoDB, resolve `ALL_ACTIVE`/`SELECTED_DOCUMENTS` thành snapshot active version IDs rồi filter Qdrant; document missing/deleted/inactive bị loại. Builder budget system/history/ranked chunk blocks/original query/output reserve; conditional rewriter chỉ đổi query gửi retrieval, generation luôn nhận original query. History được ghi rõ chỉ để resolve tham chiếu, không phải nguồn citation; ordinal của chunk sau budget vẫn khớp source metadata để map Qdrant chunk → Mongo active version. Non-stream chuẩn hóa usage provider giống stream.
- **Files thay đổi:** `backend/app/rag/prompt.py`, `backend/app/rag/pipeline.py`, `backend/app/api/chat.py`, `backend/tests/test_rag_integration.py`, `backend/tests/test_chat_persistence.py`, `backend/tests/test_chat_stream.py`, `backend/scripts/smoke_rag_integration.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Focused scope/budget/rewrite/retriever/JSON/SSE — PASS 48/48; toàn bộ unit/API/in-memory regression — PASS 147/147; `compileall`, Python 3.10.11 và `pip check` — PASS. Live Atlas/Qdrant scoped smoke — PASS 1 active version, 5 sources, 1 whole history turn, citation provenance và exact cleanup. Live `/chat` — PASS HTTP 200/COMPLETED/5 sources. Live `/chat/stream` lần đầu terminal `RAG_STREAM_ERROR` an toàn do provider tạm thời; retry hữu hạn PASS HTTP 200, 204 deltas, terminal `done`, 5 sources. Không in credential/raw provider response.
- **Tồn đọng / quyết định:** Context token count vẫn là xấp xỉ. Scope được snapshot theo active versions lúc prepare; version đổi giữa prepare và provider completion không làm nới scope nhưng có thể khiến response dựa trên version vừa hết active. Streaming realtime citations vẫn rỗng theo contract citation-before-delta hiện tại; terminal persistence recompute citations từ answer/source. Multi-turn quality/eval, topic switching và long-session comparison thuộc P5-05.
- **Tiếp theo:** `P5-05` — chưa bắt đầu; chờ giao việc riêng. Không tự động triển khai P5-05.

### [2026-10-12] P4-02 — Live Groq verification hoàn tất

- **Trạng thái:** COMPLETED; Giai đoạn 4 COMPLETED.
- **Đã thực hiện:** Xác minh secret-safe `.env` dùng `GROQ_API_KEY`, official Groq OpenAI-compatible base và `LLM_MODEL=openai/gpt-oss-120b`; không còn biến OpenRouter. Kiểm tra read-only Groq model catalog xác nhận authentication và model availability, sau đó chạy provider smoke qua đúng LangChain `ChatOpenAI.astream()` runtime path. Không thay đổi API, retrieval pipeline, MongoDB/Qdrant data hay P5 runtime.
- **Files thay đổi:** `.env` (người dùng đổi model), `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Groq `/models` — PASS auth HTTP 200 và configured model listed; live `smoke_provider_stream.py` — PASS 14 valid text deltas, usage metadata present; focused provider/stream/query/context — PASS 34/34; toàn bộ unit/API/in-memory regression — PASS 145/145; `compileall`, Python 3.10.11 và `pip check` — PASS. Không in credential hoặc raw provider response.
- **Tồn đọng / quyết định:** P4-02 không còn blocker. Model availability/quota vẫn là phụ thuộc vận hành bên ngoài và smoke script có thể dùng lại để kiểm tra. P5-04 vẫn chưa bắt đầu.
- **Tiếp theo:** `P5-04` — chỉ triển khai khi được giao riêng; `M-06` tiếp tục IN PROGRESS.

### [2026-10-12] P4-02 — Chuyển provider sang Groq (xác minh live)

- **Trạng thái:** BLOCKED — implementation, cấu hình và regression PASS; live text delta chưa phát được do model không khả dụng.
- **Đã thực hiện:** Thay OpenRouter adapter bằng LangChain `ChatOpenAI` trỏ tới Groq OpenAI-compatible API; dùng `GROQ_API_KEY` dạng `SecretStr`, `OPENAI_BASE_URL` được kiểm tra đúng HTTPS host/path Groq và `LLM_MODEL` qua environment settings. Thay dependency manifest bằng `langchain-openai`, cập nhật smoke/test/docs và sửa `.env` từ website root sang API base chính thức mà không đọc/in credential. Khôi phục đúng CPython 3.10.11 cho `.venv`. Không thay retrieval, MongoDB/Qdrant data hay API contract.
- **Files thay đổi:** `.env`, `.env.example`, `backend/requirements.txt`, `backend/app/config.py`, `backend/app/rag/llm.py`, `backend/app/rag/chain.py`, `backend/app/rag/pipeline.py`, `backend/scripts/smoke_provider_stream.py`, `backend/tests/test_llm.py`, `backend/tests/test_cloud_connections.py`, `backend/tests/test_context_budget.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Kiểm tra cấu hình secret-safe — PASS key/base/model present, official Groq API base, không còn biến OpenRouter; Python 3.10.11 và `pip check` — PASS; focused provider/stream/query/context — PASS 34/34; toàn bộ unit/API/in-memory regression — PASS 145/145; `compileall` — PASS. Groq `/models` read-only — auth PASS HTTP 200 nhưng configured model không listed. Live `smoke_provider_stream.py` — BLOCKED `OpenAIModelNotFoundError`, không in raw response/credential.
- **Tồn đọng / quyết định:** Giữ nguyên model người dùng chọn, không tự đổi model. `llama-3.3-70b-versatile` hiện không khả dụng cho API/tier này; cần đổi `LLM_MODEL` sang model đang listed (mặc định tài liệu mẫu là `openai/gpt-oss-120b`) rồi chạy lại live smoke. Chỉ tích P4-02 khi nhận được text delta thật. P5-04 vẫn tạm dừng.
- **Tiếp theo:** Người dùng chọn/cấu hình một Groq model khả dụng; chạy lại P4-02 live smoke và regression liên quan. Không tự động triển khai P5-04.

### [2026-10-12] P5-03 — Query rewriting

- **Trạng thái:** COMPLETED; Giai đoạn 5 IN PROGRESS. P4-02 tiếp tục tạm bỏ qua/BLOCKED.
- **Đã thực hiện:** Thêm lexical dependency detector chỉ gọi provider khi query có tham chiếu context và có selected whole-turn history. Thêm LangChain `ainvoke` adapter với prompt cấm answer/thêm fact, timeout riêng và output một dòng. Result luôn giữ `original_query` cho final generation, tách `retrieval_query`; candidate phải khác original, đúng giới hạn và pass lexical provenance guard từ original/history, đồng thời phải mang antecedent từ history. Entity/số/fact mới, multiline, unchanged, oversized, provider error/timeout đều fallback original an toàn. Metrics ghi provider call, added latency, input/output/total token cost và `usage_source=provider|estimated|none`; không suy đoán USD cost. Chưa nối vào `/chat` hoặc retriever.
- **Files thay đổi:** `.env.example`, `backend/app/config.py`, `backend/app/query_rewriting.py`, `backend/tests/test_query_rewriting.py`, `backend/tests/test_context_budget.py`, `backend/scripts/smoke_query_rewriting.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Focused rewrite/context/history/streaming — PASS 27/27; toàn bộ unit/API/in-memory regression — PASS 144/144; offline `smoke_query_rewriting.py` — PASS independent zero-call, dependent rewrite, original preservation, unsupported-fact rejection, safe fallback và token/latency metrics; `compileall`, `pip check`, `git diff --check` — PASS.
- **Tồn đọng / quyết định:** Lexical provenance ngăn token/entity/số mới nhưng không chứng minh semantic entailment hoàn hảo; prompt guard và fallback giảm rủi ro, evaluation tiếp tục ở P5-05. Detector bảo thủ có thể bỏ sót follow-up không có marker và khi đó dùng original query. Live OpenRouter không chạy vì P4-02 vẫn bị free-tier 429; logic provider được xác minh deterministic. Runtime dùng rewritten query cho retrieval và original query cho final prompt thuộc P5-04.
- **Tiếp theo:** `P5-04` — chưa bắt đầu; chờ giao việc riêng. Không tự động triển khai P5-04 hoặc quay lại P4-02.

### [2026-10-12] P5-02 — Context budget

- **Trạng thái:** COMPLETED; Giai đoạn 5 IN PROGRESS. P4-02 tiếp tục tạm bỏ qua/BLOCKED.
- **Đã thực hiện:** Thêm settings cho context window và allocation system/history/chunks/query/output reserve; startup validation chặn tổng vượt window. Thêm `ContextBudgetBuilder` dùng approximate counter sẵn có của `langchain-core` với hệ số chars/token cấu hình được. System instruction vượt allocation bị từ chối thay vì cắt. History chọn strict suffix các whole turns gần nhất và không cắt turn. Chunks giữ retrieval rank, prefix-truncate tối đa chunk cuối vừa budget rồi dừng. Query dùng deterministic head–tail marker; output reserve luôn được tính vào tổng. Contract trả usage từng phần, cờ truncate và số turn/chunk bị bỏ. Chưa nối vào `/chat`, prompt hoặc retriever.
- **Files thay đổi:** `.env.example`, `backend/app/config.py`, `backend/app/context_budget.py`, `backend/tests/test_context_budget.py`, `backend/scripts/smoke_context_budget.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused context/history/streaming — PASS 18/18; toàn bộ unit/API/in-memory regression — PASS 135/135; offline `smoke_context_budget.py` — PASS 5 allocations, total window, recent whole turns, query/chunk truncation; `compileall`, `pip check`, `git diff --check` — PASS.
- **Tồn đọng / quyết định:** Counter là xấp xỉ, mặc định bảo thủ hơn English ở 3 chars/token nhưng không bảo đảm khớp tokenizer riêng của mọi OpenRouter model. Strict recent suffix có thể trả history rỗng nếu turn mới nhất tự nó vượt allocation; không lùi qua turn đó để lấy turn cũ hơn. Chunk input phải được caller format kèm source header để header được tính; wiring thuộc P5-04. Query rewriting thuộc P5-03.
- **Tiếp theo:** `P5-03` — chưa bắt đầu; chờ giao việc riêng. Không tự động triển khai P5-03/P5-04 hoặc quay lại P4-02.

### [2026-10-12] P5-01 — History loader

- **Trạng thái:** COMPLETED; Giai đoạn 5 IN PROGRESS. P4-02 được tạm bỏ qua và vẫn BLOCKED, không tính là PASS.
- **Đã thực hiện:** Thêm `ConversationHistoryLoader` qua repository protocol, trả session record/retrieval scope cùng các `HistoryTurn` theo stable sequence. Loader phân trang toàn bộ message, ghép đúng hai record cùng `request_id`, yêu cầu user `COMPLETED` và assistant đứng ngay sequence kế tiếp. Mặc định chỉ assistant `COMPLETED` được nhận; `PARTIAL/FAILED/PENDING/STREAMING`, orphan, cross-session, group thừa hoặc pair không liên tiếp đều bị loại cả lượt. Diagnostic caller có thể opt-in terminal `PARTIAL/FAILED`; active messages luôn bị loại. Chưa thay prompt, retrieval hoặc `/chat`.
- **Files thay đổi:** `backend/app/history.py`, `backend/tests/test_history.py`, `backend/scripts/smoke_history_loader.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused history/models/session/persistence — PASS 35/35; toàn bộ unit/API/in-memory regression — PASS 126/126; live `smoke_history_loader.py` trên Atlas — PASS session identity, selected-document scope, stable order, multi-page load, default/diagnostic whole-turn filtering và exact cleanup; `compileall`, `pip check`, `git diff --check` — PASS.
- **Tồn đọng / quyết định:** Loader hiện đọc toàn bộ persisted history để giữ semantic đầy đủ; chưa chọn recent turns, tính token hay truncate — thuộc P5-02. Chưa dùng history cho query rewrite/prompt/retrieval/stream — thuộc P5-03/P5-04. Opt-in failed turn có thể chứa assistant content rỗng và chỉ dành cho diagnostic, không phải default generation context.
- **Tiếp theo:** `P5-02` — chưa bắt đầu; chờ giao việc riêng. Không tự động triển khai P5-02 hoặc quay lại P4-02.

### [2026-10-12] P4-05 — Metrics/tests

- **Trạng thái:** COMPLETED; Giai đoạn 4 vẫn IN PROGRESS vì P4-02 đang DEFERRED/BLOCKED.
- **Đã thực hiện:** Thêm monotonic one-shot tracker đo từ đầu request qua retrieval/persistence tới logical terminal: `first_event_ms`, nullable `first_content_ms`, `total_latency_ms`, `delta_count`, request ID, mode và safe outcome. Production ghi structured log không chứa question/answer/sources/credentials; lỗi metrics không ảnh hưởng response. Mở rộng endpoint tests cho success reconstruction, output rỗng, lỗi giữa stream, timeout, persistence failure, cancel/disconnect và durable lifecycle; metric chỉ ghi một lần ở success/error/cancel/pre-header failure.
- **Files thay đổi:** `backend/app/stream_metrics.py`, `backend/app/api/chat.py`, `backend/tests/test_stream_metrics.py`, `backend/tests/test_chat_stream.py`, `backend/scripts/smoke_stream_metrics.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused metrics/stream/lifecycle/SSE/provider — PASS 38/38; toàn bộ unit/API/in-memory regression — PASS 120/120; live `smoke_stream_metrics.py` — PASS first-event/first-content/total latency, success/empty/partial transcripts, client reconstruction, Atlas terminal states/guard release và exact cleanup; `compileall`, `pip check`, `git diff --check` — PASS.
- **Tồn đọng / quyết định:** Metric là structured application log, chưa có Prometheus/exporter/dashboard. Total latency kết thúc tại logical terminal trước khi terminal frame được network flush; đây là server-side processing metric, không phải browser-perceived latency. P4-02 giữ deferred cho tới khi người dùng yêu cầu chạy lại.
- **Tiếp theo:** `P5-01` — chưa bắt đầu; chờ giao việc riêng. Không tự động triển khai hoặc quay lại P4-02.

### [2026-10-12] P4-04 — Error/disconnect

- **Trạng thái:** COMPLETED; P4-02 giữ DEFERRED/BLOCKED theo quyết định người dùng.
- **Đã thực hiện:** Thêm deadline `STREAM_TIMEOUT_SECONDS` cho toàn provider stream. Lỗi provider/output rỗng/timeout/persistence sau headers phát đúng một terminal SSE `error` an toàn với `FAILED` hoặc `PARTIAL`; không retry sau output. Timeout và cancel đóng async iterator. Disconnect/cancel tại cả prefix hoặc delta yield cố finalize assistant bằng `RAG_STREAM_CANCELLED` rồi release generation guard; không phát terminal frame khi client đã rời kết nối. Lỗi dependency/retrieval/session trước headers tiếp tục trả HTTP phù hợp. Cập nhật cache headers thành `no-cache, no-transform`, giữ `X-Accel-Buffering: no`.
- **Files thay đổi:** `backend/app/api/chat.py`, `backend/app/config.py`, `.env.example`, `backend/tests/test_chat_stream.py`, `backend/scripts/smoke_stream_errors.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused stream/lifecycle/SSE/provider — PASS 33/33; toàn bộ unit/API/in-memory regression — PASS 115/115; live `smoke_stream_errors.py` — PASS provider partial error, timeout, Atlas `PARTIAL/FAILED`, guard release và exact cleanup; `compileall`, `pip check`, `git diff --check` — PASS.
- **Tồn đọng / quyết định:** Disconnect thực tế không thể gửi SSE terminal vì transport đã đóng; durable state vẫn được finalize best-effort. Nếu MongoDB cũng unavailable trong cleanup thì không có distributed recovery trong request; stale-guard reconciliation vẫn là giới hạn vận hành. Metrics first-event/first-content/total latency và reconstruction suite thuộc P4-05. P4-02 không được chạy lại cho tới khi người dùng yêu cầu.
- **Tiếp theo:** `P4-05` — chưa bắt đầu; chờ giao việc riêng. Không tự động quay lại P4-02.

### [2026-10-12] P4-03 — Lifecycle

- **Trạng thái:** COMPLETED; Giai đoạn 4 vẫn IN PROGRESS vì P4-02 còn BLOCKED.
- **Đã thực hiện:** Cho phép `/chat/stream` với `session_id`. Sau khi chuẩn bị retrieval/prompt và trước SSE headers, service atomically tạo user message, assistant `PENDING → STREAMING` và giữ guard. Stream tích lũy content/usage; thành công mới finalize `COMPLETED`, provider lỗi hoặc output rỗng ghi `PARTIAL`/`FAILED` đúng content đã phát, kèm error code an toàn và release guard. SSE `start` persistent mang đúng durable IDs; `/chat` JSON không đổi.
- **Files thay đổi:** `backend/app/api/chat.py`, `backend/app/conversation_service.py`, `backend/app/conversation_repository.py`, `backend/app/conversation_models.py`, `backend/tests/test_chat_stream.py`, `backend/tests/test_chat_persistence.py`, `backend/scripts/smoke_stream_lifecycle.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Focused lifecycle/provider/SSE — PASS 28/28; toàn bộ unit/API/in-memory regression — PASS 110/110; live `smoke_stream_lifecycle.py` — PASS Atlas persistent SSE, content/usage, terminal state, guard release và exact cleanup; `compileall`, `pip check`, `git diff --check` — PASS. Live `smoke_provider_stream.py` — BLOCKED: `TooManyRequestsResponseError`, không in credentials/raw response.
- **Tồn đọng / quyết định:** P4-03 dùng provider deterministic cho smoke persistence, không tiêu thụ quota hoặc ghi document data. P4-02 chỉ được đánh dấu COMPLETED sau live OpenRouter async smoke PASS. Cancel/disconnect, lỗi persistence sau headers, buffering/timeout thuộc P4-04.
- **Tiếp theo:** Xác minh lại `P4-02` khi provider khả dụng; P4-04 chưa bắt đầu và không tự động triển khai.

### [2026-10-12] P4-02 — Provider integration (xác minh lại)

- **Trạng thái:** BLOCKED — implementation và unit/mock verification PASS, nhưng live OpenRouter vẫn trả HTTP 429 sau khi người dùng thông báo đã reset limit.
- **Đã thực hiện:** Tách retrieval + prompt preparation khỏi provider stream; `/chat/stream` dùng LangChain/OpenRouter `astream()` sau headers. Chuẩn hóa content string/text block thành delta, bỏ qua control/empty/non-text chunk, chuẩn hóa `usage_metadata` hoặc OpenAI-style usage và giữ usage xuất hiện ở chunk không có text để đưa vào `done`. Giữ stateless, không persist message, không buffer answer để gắn citation sau delta và không xử lý exception sau headers — đúng ranh giới P4-03/P4-04.
- **Files thay đổi:** `backend/app/rag/pipeline.py`, `backend/app/api/chat.py`, `backend/tests/test_streaming_pipeline.py`, `backend/tests/test_chat_stream.py`, `backend/scripts/smoke_stream_endpoint.py`, `backend/scripts/smoke_provider_stream.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Xác minh cấu hình dưới dạng boolean — PASS cho API key/base URL/model; focused provider/endpoint/SSE/metrics — PASS 25/25; toàn bộ unit/API/in-memory regression — PASS 120/120; `compileall` và `pip check` — PASS. Key-management auth — PASS, key vẫn là free tier; configured model vẫn listed/free. Live `smoke_provider_stream.py` chạy hai lần hữu hạn, lần hai sau cửa sổ rate-limit 10 giây — BLOCKED `TooManyRequestsResponseError`. Request chẩn đoán tối thiểu xác nhận HTTP 429 thuộc nhóm free-tier limit/rate-limit/credit; không in credentials, model ID, endpoint cấu hình hay raw response.
- **Tồn đọng / quyết định:** Việc reset limit chưa tạo allowance dùng được cho API key hiện tại. Chỉ đánh dấu P4-02 COMPLETED khi live `astream()` phát được text delta thật. Không tự đổi sang model trả phí hoặc API key khác khi chưa có chỉ dẫn. Citation realtime cố ý rỗng vì contract bắt citation trước delta; lifecycle/error/metrics đã hoàn thành ở P4-03…P4-05.
- **Tiếp theo:** Người dùng cần nạp credit/đổi sang key có paid allowance, hoặc xác nhận model/key khác được phép dùng; sau đó chạy lại live smoke. Không tự động chuyển task.

### [2026-10-12] P4-01 — Endpoint

- **Trạng thái:** COMPLETED; Giai đoạn 4 IN PROGRESS; M-06 tiếp tục IN PROGRESS.
- **Đã thực hiện:** Thêm `POST /chat/stream` giữ nguyên `/chat` JSON. Endpoint stateless gọi RAG hiện có trước headers, sau đó phát typed SSE `start → metadata → citation* → delta → done` với `Content-Type: text/event-stream`, `Cache-Control: no-cache` và `X-Accel-Buffering: no`; transcript được xác minh bằng contract P3-03. Error trước headers trả JSON failure envelope an toàn HTTP 502. `session_id` trả HTTP 409 rõ ràng vì chưa có streaming lifecycle/persistence ở P4-03. P4-01 chỉ phát một delta từ answer hoàn tất; không tiêu thụ provider async stream, không persist streaming turn, không xử lý lỗi sau headers/disconnect.
- **Files thay đổi:** `backend/app/api/chat.py`, `backend/tests/test_chat_stream.py`, `backend/scripts/smoke_stream_endpoint.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused stream/SSE/chat — PASS 22/22; toàn bộ unit/API/in-memory regression — PASS 104/104; live `smoke_stream_endpoint.py` — PASS cloud readiness, typed event order/sequence và stateless POST SSE, không ghi dữ liệu; `compileall` và `pip check` — PASS.
- **Tồn đọng / quyết định:** Native `EventSource` không gửi POST body, README hướng dẫn `fetch`/`ReadableStream`. Async provider token deltas thuộc P4-02; persistent message lifecycle P4-03; post-header error, cancel/disconnect P4-04; metrics sâu P4-05.
- **Tiếp theo:** `P4-02` — chưa bắt đầu; chờ giao việc riêng. Không tự động chuyển task.

### [2026-10-12] P3-04 — Compatibility/tests

- **Trạng thái:** COMPLETED; Giai đoạn 3 COMPLETED; M-06 tiếp tục IN PROGRESS.
- **Đã thực hiện:** Giữ `/chat` tương thích additive và không đổi URL/version: request không có `session_id` vẫn stateless, client cũ tiếp tục đọc `answer`/`sources`. Generation failure stateless trả HTTP 502 với full logical `ChatResponse`; persistent failure dùng safe `ConversationGenerationError` để trả đúng durable request/user/assistant IDs của failed turn, `status=FAILED`, `answer=null`, arrays rỗng, `usage=null` và không lộ raw provider detail. Validation/session/concurrency/persistence error trước logical reply giữ status/`detail` cũ. Bổ sung coverage cho Pydantic validation, missing usage, no-result fallback, nhiều documents/citations và legacy projection. Khôi phục đúng CPython 3.10.11 mà `.venv` đang tham chiếu, không đổi dependencies.
- **Files thay đổi:** `backend/app/api/chat.py`, `backend/app/conversation_service.py`, `backend/tests/test_chat_persistence.py`, `backend/scripts/smoke_response_contract.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused schema/citation/persistence/concurrency — PASS 26/26; toàn bộ unit/API/in-memory regression — PASS 100/100. Live FastAPI lifespan + `/health/dependencies` + MongoDB Atlas/Qdrant Cloud compatibility lifecycle — PASS legacy projection, fallback, 2-document candidates/citations, `usage=null`, persistent forced failure/durable IDs và exact cleanup. `compileall`, `pip check`, secret scan và `git diff --check` — PASS.
- **Tồn đọng / quyết định:** Không triển khai `/chat/stream`; runtime streaming thuộc P4. Lỗi xảy ra trước khi có logical reply vẫn dùng FastAPI `detail`, tránh tạo persistent IDs giả. M-06 chưa hoàn tất cho tới runtime SSE/history-aware gates P4–P5; stale guard recovery và thu hẹp MongoDB role vẫn là giới hạn vận hành.
- **Tiếp theo:** `P4-01` — chưa bắt đầu; chờ giao việc riêng. Không tự động chuyển task.

## 4. Lưu trữ nhật ký cũ (archive)

- [Phase 1 + các entry M-03…M-06/P2-01 đã archive](./docs/changelog/phase-01.md)
- [Phase 2 — các entry P2 đã archive](./docs/changelog/phase-02.md)

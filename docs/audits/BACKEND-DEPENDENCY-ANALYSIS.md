# BACKEND-DEPENDENCY-ANALYSIS — R0-B

Ngày phân tích: 2026-10-29 (Asia/Bangkok). Phân tích source của working tree hiện tại, không giả định trùng HEAD. Deliverable duy nhất: báo cáo này tại repository root. Dừng sau R0-B.

## 1. Executive Summary

**Không có bằng chứng buộc phải tái cấu trúc thư mục backend trước Tool Use.** Đồ thị import nội bộ gồm **38 module, 102 cạnh có hướng duy nhất, 38 strongly connected components đơn**, không self-loop và không chu trình import tĩnh. Có **273 câu lệnh import**, tất cả absolute; không có relative import. Mọi đích module nội bộ và tên được import nội bộ đều có binding trong source được kiểm tra. Đây là kết quả STATIC_ANALYSIS_CONFIRMED cho phạm vi source đã quét, không phải kiểm chứng import/runtime của Python hoặc dependency bên thứ ba.

Các điểm cần owner quan tâm:

- **B01 — Điều phối tập trung nhưng chưa đủ bằng chứng gọi là god module:** api/chat và rag/pipeline cùng fan-out 11. API còn giữ transport, persistence lifecycle và provider stream trong một file; pipeline lắp history, scope, rewrite, budget, retrieval và generation. Việc nhét tool loop vào cả hai nơi có thể nhân đôi chính sách JSON/SSE. SOURCE_CONFIRMED: backend/app/api/chat.py:118, :333, :439; backend/app/rag/pipeline.py:64, :101, :175, :228. Rủi ro tăng trách nhiệm: POTENTIAL_RISK.
- **B02 — Coupling domain có thật, chưa phải cycle:** conversation_models import base record/helpers từ document_models; attachment_models cũng import UUID validator từ đó. SOURCE_CONFIRMED: backend/app/conversation_models.py:12–13; backend/app/attachment_models.py:4. Không cần di chuyển chỉ để chỉnh tên package.
- **B03 — Persistence/provider coupling hiện hữu:** pipeline import trực tiếp cả hai Mongo repositories; history có Protocol nhưng vẫn import concrete repository error; query rewriting import provider factory. SOURCE_CONFIRMED: backend/app/rag/pipeline.py:21–27; backend/app/history.py:20–30; backend/app/query_rewriting.py:22, :75–81. Các seam inject hiện có cho phép bổ sung Tool Use mà chưa cần thay toàn bộ backend.
- **B04 — Tool output chưa có contract:** pipeline chỉ chuẩn hóa text/usage, bỏ qua tool/control chunks theo trách nhiệm hiện tại. SOURCE_CONFIRMED: backend/app/rag/pipeline.py:56–61, :228–239, :265–279. Chỉ bind tools vào model rồi dùng stream hiện tại không đủ để biểu diễn tool execution. Cần owner chốt boundary và cách ánh xạ kết quả vào answer/sources/usage hiện hữu trước triển khai. Không thực hiện trong R0-B.

Không có CONFIRMED_CYCLE hoặc POTENTIAL_RUNTIME_CYCLE cụ thể được chứng minh trong source hiện tại. Rủi ro tạo cycle do một thiết kế Tool Use tương lai được ghi riêng, không gắn nhãn là lỗi hiện hữu. MongoDB, Qdrant, Groq, Gemini, ứng dụng, tests, builds và scripts dự án không được chạy.

## 2. Analysis Scope & Method

### Phạm vi và nguồn tham chiếu

Quét đệ quy toàn bộ backend/app/**/*.py: **27 file trực tiếp dưới app, 3 file api, 8 file rag = 38 file**. Không có __init__.py trong cây đã kiểm tra; app/api/rag được xử lý như các package namespace theo đường dẫn source, không import để xác minh. Mỗi file có một dòng inventory ở mục 3 và một owner ở mục 7. Imports từ backend/tests, backend/scripts và backend/evaluation chỉ được tìm kiếm văn bản để nhận diện tác động nếu đổi đường dẫn; không thuộc mẫu số fan-in/fan-out, không được chạy.

Đã tham khảo docs/audits/RAG-CODEBASE-ASSESSMENT-0C.md, đặc biệt các phần Current System Architecture, Architecture & Functional MVP Assessment và Known Limitations and Unverified Areas. Kết luận đồ thị được tính lại từ source, không lấy từ tài liệu này. **BACKEND-ARCHITECTURE-REVIEW.md và tooluse.md không tìm thấy trong danh sách file checkout, kể cả hidden files ngoài .git và thư mục dependencies/build đã loại trừ.** Nội dung R0 sơ bộ và roadmap Tool Use/P1–P8: NOT_VERIFIED. Không suy diễn nội dung của hai tài liệu thiếu này.

### Phương pháp có thể kiểm tra lại

1. Liệt kê file bằng rg --files backend/app và filesystem recursion; đọc UTF-8 toàn bộ 38 source files.
2. Dùng JavaScript/Node built-ins cho một bộ quét văn bản chỉ đọc: che comments/string literals, giữ newline, nhận diện import/from-import và ghép from-import nhiều dòng trong ngoặc. Đối chiếu lại tất cả dòng bắt đầu import/from trên source gốc: cùng **273 câu lệnh**. Không dùng parser AST Python: lệnh python không tồn tại trên PATH; không cài đặt/sửa môi trường hay thử chạy ứng dụng bằng interpreter khác.
3. Chuẩn hóa module từ đường dẫn. Với from app.api import chat, documents, sessions ở backend/app/main.py:13, phân giải thành ba module con thực tế. Với from module import symbol, chỉ tạo cạnh đến module chứa binding; không tạo node giả tên symbol. Kiểm tra các binding qua def/class, assignment và tên import/re-export trong target. Ví dụ new_uuid được re-export qua conversation_models.py:12, không phải module con.
4. Giữ line bắt đầu câu lệnh làm evidence. Dedupe theo (importer, target) để tính **102 cạnh**; nhiều symbol và nhiều câu lệnh cùng target không làm tăng degree. Bao gồm imports trong function, conditional và annotation imports nếu có; không chỉ tính những tên được gọi. Hai function-local imports được mô tả ở mục 3.
5. Chạy Tarjan trên đồ thị 38 node để tìm SCC/self-loop. Kiểm tra lần hai bằng loại dần node có in-degree 0: nếu loại hết 38 node thì đồ thị là DAG. Đối chiếu inventory cạnh với câu lệnh source và tìm các cơ chế dynamic loading/code execution.
6. Đọc trách nhiệm class/function và các call site quan trọng để tách import dependency khỏi runtime callback. Không resolve/exercise SDK internals, environment, database, provider hoặc HTTP routes bằng runtime.

Bộ quét phù hợp với cú pháp import thực tế đã đối chiếu của checkout này; không phải Python grammar validator hoặc resolver tổng quát. Không khẳng định chương trình hợp lệ khi chạy, mọi symbol external cài đúng version, hay không tồn tại cycle do import hooks/third-party code. Không thực thi application imports, kể cả config.py:245 vốn khởi tạo Settings và có thể đọc môi trường.

### Evidence classification

| Nhãn | Ý nghĩa trong báo cáo |
| --- | --- |
| SOURCE_CONFIRMED | Trách nhiệm, import hoặc call site hiện diện ở source/line được dẫn; không chứng nhận runtime thành công. |
| STATIC_ANALYSIS_CONFIRMED | Kết quả phân giải/count/graph được suy ra từ toàn bộ import statements đã đối chiếu trong phạm vi. |
| POTENTIAL_RISK | Hệ quả kiến trúc có điều kiện; chưa quan sát lỗi runtime hoặc chưa có thiết kế tương lai được duyệt. |
| NOT_VERIFIED | Thiếu reference, ngoài phạm vi hoặc cần thực thi mới xác minh được. |

## 3. Python Import Dependency Inventory

Toàn bộ bảng dưới là STATIC_ANALYSIS_CONFIRMED, với source evidence tại đúng đường dẫn và line của từng import. Cột internal ghi target tuyệt đối và line; cột external ghi nguyên module được import (bao gồm standard library và __future__, không mặc định tất cả là dependency cài ngoài). In/out chỉ tính **module nội bộ trực tiếp**, không tính transitive dependencies, runtime calls, packages namespace trung gian hoặc người dùng module ngoài app.

| Source module/file | Internal targets @ import line | External targets @ import line | In / Out |
| --- | --- | --- | --- |
| `backend/app/api/chat.py` | `app.attachments` @9; `app.document_repository` @10; `app.citation_mapping` @13; `app.config` @14; `app.conversation_models` @15; `app.conversation_repository` @16; `app.conversation_service` @22; `app.rag.pipeline` @28; `app.schemas` @34; `app.sse_schema` @44; `app.stream_metrics` @57 | `asyncio` @3; `uuid` @5; `fastapi` @7; `fastapi.concurrency` @8; `fastapi.responses` @11 | 1 / 11 |
| `backend/app/api/documents.py` | `app.document_repository` @9; `app.document_service` @14; `app.ingestion` @15; `app.rag.loader` @16; `app.attachments` @17; `app.document_repository` @18; `app.storage` @19; `app.excel` @20; `app.schemas` @21 | `pathlib` @3; `uuid` @4; `fastapi` @6; `fastapi.concurrency` @7 | 1 / 8 |
| `backend/app/api/sessions.py` | `app.conversation_models` @8; `app.conversation_repository` @9; `app.conversation_schemas` @15; `app.conversation_service` @27 | `uuid` @3; `fastapi` @5; `fastapi.concurrency` @6 | 1 / 4 |
| `backend/app/attachment_models.py` | `app.document_models` @4 | `pydantic` @3 | 5 / 1 |
| `backend/app/attachments.py` | `app.attachment_models` @5; `app.document_models` @6; `app.document_repository` @7; `app.excel` @8 | `pathlib` @3; `codecs` @59 | 2 / 4 |
| `backend/app/citation_mapping.py` | — | `__future__` @3; `re` @5; `typing` @6; `uuid` @7 | 2 / 0 |
| `backend/app/cloud_connections.py` | `app.config` @22 | `__future__` @6; `dataclasses` @8; `typing` @9; `pymongo` @11; `pymongo.errors` @12; `qdrant_client` @19; `qdrant_client.http.exceptions` @20 | 1 / 1 |
| `backend/app/config.py` | — | `functools` @9; `pathlib` @10; `re` @11; `urllib.parse` @12; `pydantic` @14; `pydantic_settings` @15 | 11 / 0 |
| `backend/app/context_budget.py` | `app.history` @17 | `__future__` @9; `dataclasses` @11; `typing` @12; `langchain_core.messages` @14; `langchain_core.messages.utils` @15 | 2 / 1 |
| `backend/app/conversation_indexes.py` | — | `collections.abc` @3; `typing` @4; `pymongo` @6 | 2 / 0 |
| `backend/app/conversation_models.py` | `app.document_models` @12; `app.attachment_models` @13 | `datetime` @7; `enum` @8; `pydantic` @10 | 7 / 2 |
| `backend/app/conversation_repository.py` | `app.conversation_indexes` @11; `app.conversation_models` @12 | `__future__` @3; `dataclasses` @5; `typing` @6; `pymongo` @8; `pymongo.errors` @9 | 5 / 2 |
| `backend/app/conversation_schemas.py` | `app.conversation_models` @7; `app.attachment_models` @8 | `datetime` @3; `pydantic` @5 | 1 / 2 |
| `backend/app/conversation_service.py` | `app.citation_mapping` @8; `app.attachment_models` @9; `app.conversation_models` @10; `app.conversation_repository` @19 | `dataclasses` @3; `asyncio` @4; `collections.abc` @5; `typing` @6 | 2 / 4 |
| `backend/app/data_migration.py` | `app.document_models` @12; `app.document_repository` @13; `app.ingestion` @14; `app.storage` @15; `app.vector_index` @16 | `__future__` @3; `hashlib` @5; `dataclasses` @6; `pathlib` @7; `typing` @8; `langchain_core.embeddings` @10 | 0 / 5 |
| `backend/app/document_indexes.py` | — | `collections.abc` @3; `typing` @4; `pymongo` @6 | 2 / 0 |
| `backend/app/document_models.py` | — | `datetime` @7; `enum` @8; `typing` @9; `uuid` @10; `pydantic` @12 | 9 / 0 |
| `backend/app/document_repository.py` | `app.document_indexes` @10; `app.document_models` @15 | `__future__` @3; `typing` @5; `pymongo` @7; `pymongo.errors` @8 | 8 / 2 |
| `backend/app/document_service.py` | `app.config` @8; `app.document_models` @9; `app.document_repository` @10; `app.ingestion` @11; `app.qdrant_ingestion` @16; `app.storage` @17; `app.vector_index` @18 | `__future__` @3; `dataclasses` @5; `typing` @6 | 1 / 7 |
| `backend/app/excel.py` | — | `datetime` @3; `io` @4; `math` @5; `zipfile` @6; `langchain_core.documents` @8; `openpyxl` @9 | 3 / 0 |
| `backend/app/history.py` | `app.conversation_models` @13; `app.conversation_repository` @20 | `__future__` @8; `dataclasses` @10; `typing` @11 | 3 / 2 |
| `backend/app/ingestion.py` | `app.config` @14; `app.document_models` @15; `app.document_repository` @21; `app.qdrant_ingestion` @26; `app.rag.embeddings` @27; `app.rag.loader` @28; `app.rag.splitter` @29; `app.storage` @30; `app.vector_index` @36 | `__future__` @3; `shutil` @5; `tempfile` @6; `dataclasses` @7; `pathlib` @8; `typing` @9; `langchain_core.documents` @11; `langchain_core.embeddings` @12 | 3 / 9 |
| `backend/app/main.py` | `app.api.chat` @13; `app.api.documents` @13; `app.api.sessions` @13; `app.cloud_connections` @14; `app.config` @15; `app.conversation_indexes` @16; `app.document_indexes` @17 | `contextlib` @6; `fastapi` @8; `fastapi.concurrency` @9; `fastapi.middleware.cors` @10; `fastapi.responses` @11 | 0 / 7 |
| `backend/app/qdrant_ingestion.py` | `app.vector_index` @19 | `__future__` @3; `math` @5; `typing` @6; `qdrant_client.http.models` @8 | 3 / 1 |
| `backend/app/query_rewriting.py` | `app.context_budget` @20; `app.history` @21; `app.rag.llm` @22 | `__future__` @8; `asyncio` @10; `dataclasses` @11; `enum` @12; `re` @13; `time` @14; `collections.abc` @15; `typing` @16; `langchain_core.messages` @18 | 1 / 3 |
| `backend/app/rag/chain.py` | `app.rag.llm` @14; `app.rag.prompt` @15 | `langchain_core.language_models.chat_models` @3; `langchain_core.output_parsers` @4; `langchain_core.prompts` @5; `langchain_core.retrievers` @6; `langchain_core.runnables` @7 | 0 / 2 |
| `backend/app/rag/embeddings.py` | `app.config` @11 | `functools` @7; `langchain_core.embeddings` @9; `langchain_google_genai` @31 | 2 / 1 |
| `backend/app/rag/llm.py` | `app.config` @11 | `functools` @6; `langchain_core.language_models.chat_models` @8; `langchain_openai` @9 | 3 / 1 |
| `backend/app/rag/loader.py` | `app.excel` @11 | `pathlib` @7; `langchain_community.document_loaders` @9; `langchain_core.documents` @10 | 2 / 1 |
| `backend/app/rag/pipeline.py` | `app.config` @14; `app.context_budget` @15; `app.conversation_models` @20; `app.conversation_repository` @21; `app.document_models` @22; `app.document_repository` @23; `app.history` @27; `app.query_rewriting` @28; `app.rag.llm` @32; `app.rag.prompt` @33; `app.rag.retriever` @39 | `__future__` @3; `asyncio` @5; `collections.abc` @6; `dataclasses` @7; `typing` @8; `langchain_core.documents` @10; `langchain_core.language_models.chat_models` @11; `langchain_core.prompt_values` @12 | 1 / 11 |
| `backend/app/rag/prompt.py` | — | `langchain_core.documents` @3; `langchain_core.prompts` @4 | 2 / 0 |
| `backend/app/rag/retriever.py` | `app.config` @13; `app.document_repository` @14; `app.qdrant_ingestion` @15; `app.rag.embeddings` @16; `app.vector_index` @17 | `__future__` @3; `typing` @5; `langchain_core.callbacks` @7; `langchain_core.documents` @8; `langchain_core.embeddings` @9; `langchain_core.retrievers` @10; `pydantic` @11 | 1 / 5 |
| `backend/app/rag/splitter.py` | `app.config` @10 | `langchain_core.documents` @7; `langchain_text_splitters` @8 | 1 / 1 |
| `backend/app/schemas.py` | `app.document_models` @10; `app.attachment_models` @11 | `datetime` @3; `enum` @4; `typing` @5; `uuid` @6; `pydantic` @8 | 3 / 2 |
| `backend/app/sse_schema.py` | `app.schemas` @14 | `__future__` @7; `typing` @9; `uuid` @10; `pydantic` @12 | 1 / 1 |
| `backend/app/storage.py` | `app.config` @19 | `__future__` @7; `hashlib` @9; `os` @10; `tempfile` @11; `abc` @12; `contextlib` @13; `dataclasses` @14; `pathlib` @15; `typing` @16; `uuid` @17 | 4 / 1 |
| `backend/app/stream_metrics.py` | — | `__future__` @3; `dataclasses` @5; `logging` @6; `time` @7; `collections.abc` @8 | 1 / 0 |
| `backend/app/vector_index.py` | — | `__future__` @3; `math` @5; `abc` @6; `dataclasses` @7; `uuid` @8 | 5 / 0 |

### Absolute, relative, lazy, dynamic và unresolved references

- **Absolute imports: 273; relative imports: 0.** Không có from . / from .. trong source đã quét. 271 câu lệnh ở module level; hai câu lệnh còn lại là function-local imports dưới đây. STATIC_ANALYSIS_CONFIRMED.
- backend/app/attachments.py:59: import codecs trong preview_version, chỉ ở nhánh text; standard-library dependency khai báo tĩnh và load trễ, không phải dynamic target. SOURCE_CONFIRMED.
- backend/app/rag/embeddings.py:29–35: from langchain_google_genai import GoogleGenerativeAIEmbeddings chỉ chạy khi provider alias phù hợp. Đây là conditional/lazy **static import có target xác định**, không phải importlib động. Provider được chọn bằng config; việc SDK tồn tại và khởi tạo thành công: NOT_VERIFIED.
- Không tìm thấy importlib/import_module, __import__, exec, eval, find_spec, reload, thay đổi sys.path/sys.modules hoặc module-level __getattr__ trong mã đã bỏ comments/strings. Không phát hiện aliased loader imports trong inventory. STATIC_ANALYSIS_CONFIRMED trong 38 file; không phủ định cơ chế import nội bộ của SDK.
- **Unresolved internal module targets: 0; unresolved internal imported bindings: 0** theo kiểm tra source. Các target external chỉ được inventory, không import/resolve qua môi trường: NOT_VERIFIED về availability/version/native libraries. LangChain loaders còn có thể cần parser dependencies gián tiếp; ví dụ PyPDFLoader/TextLoader ở backend/app/rag/loader.py:9.
- getattr ở backend/app/api/chat.py:202 và backend/app/rag/pipeline.py:267, :284–285 lấy thuộc tính stream/provider, không nạp module. Những tham chiếu qua Any, repository injection, retriever.invoke, callback generate hoặc LCEL runnable không thể phân giải thành toàn bộ runtime call graph bằng import inventory này.

### Import dependency khác runtime call

| Tình huống | Import graph thực tế | Runtime call trong source; giới hạn |
| --- | --- | --- |
| JSON persistent turn | api.chat → conversation_service và rag.pipeline | api/chat.py:354–368 tạo closure generate gọi answer_question và truyền vào service; conversation_service.py:102, :132 gọi callback. Không có import conversation_service → rag.pipeline. |
| SSE persistent turn | api.chat → rag.pipeline, conversation_service | api/chat.py:168 gọi astream_rag_answer; :216–223 gọi service.finalize_streaming_turn; :453–470 chuẩn bị RAG rồi begin turn. Các call không thêm cạnh ngược vào API. |
| History read | rag.pipeline → history và conversation_repository | rag/pipeline.py:76–80 inject concrete repository vào ConversationHistoryLoader; history.py:23–30 khai báo Protocol; :79–80, :92–94 gọi repository. Không có import repository → history. |
| Ingest dependencies | ingestion → rag.loader, rag.splitter, rag.embeddings | ingestion.py:63–80 nhận injected loader/splitter/embeddings; :177–178 gọi injected functions; :198–200 dùng provider fallback. Không thể suy ra provider thực tế chỉ từ import. |
| Baseline LCEL | rag.chain → rag.llm, rag.prompt | rag/chain.py:26–53 nhận retriever và nối runnable. Không có cạnh pipeline → chain hoặc API → chain. Script consumer xác nhận bằng văn bản: backend/scripts/eval_cli.py:35. Fan-in 0 trong app không có nghĩa dead code. |

## 4. Dependency Graph (Mermaid)

Mũi tên **importer → imported module group**. Nhóm dùng đúng ownership ở mục 7, không dựa riêng vào vị trí thư mục; ví dụ rag/pipeline.py thuộc Chat Orchestration, rag/embeddings.py thuộc Infrastructure, rag/loader.py thuộc Ingestion. Diagram gộp các cạnh giữa nhóm, bỏ cạnh nội bộ cùng nhóm; inventory mục 3 là đồ thị module-level đầy đủ.

~~~mermaid
flowchart TD
  A[API] --> C[Chat Orchestration]
  A --> V[Conversations]
  A --> D[Documents]
  A --> I[Ingestion]
  A --> R[RAG]
  A --> F[Infrastructure]
  A --> S[Shared/Core]
  C --> V
  C --> D
  C --> R
  C --> F
  C --> S
  V --> D
  V --> R
  D --> V
  D --> I
  D --> F
  D --> S
  I --> D
  I --> F
  I --> S
  R --> D
  R --> F
  R --> S
  F --> S
~~~

**Các vòng nhìn thấy sau khi gộp nhóm không phải module import cycles.** Ví dụ Documents → Conversations là attachments.py:5 → attachment_models; Conversations → Documents là attachment_models.py:4 → document_models. Chuỗi module dừng ở document_models, không quay về attachments. Tương tự document_service.py:11 → ingestion.py và ingestion.py:15, :21 → document_models/document_repository tạo hướng hai chiều giữa nhóm Documents/Ingestion, nhưng không có ingestion → document_service. Đây là SOURCE_CONFIRMED về cạnh và STATIC_ANALYSIS_CONFIRMED về việc không có vòng module.

Hướng chính API → use cases/orchestration → repositories/adapters/models vẫn rõ. Các cross-module dependencies đáng chú ý:

| Evidence | Ý nghĩa kiến trúc |
| --- | --- |
| backend/app/api/chat.py:9–10, :315–325; backend/app/api/documents.py:17–20, :139–145 | API dựng document repository/storage trực tiếp cho attachment/preview bên cạnh service path. SOURCE_CONFIRMED; chấp nhận trong MVP, chỉ gom thành facade nếu adapter logic tiếp tục tăng. |
| backend/app/rag/pipeline.py:20–27, :72–98 | RAG request orchestration phụ thuộc cả Documents và Conversations. SOURCE_CONFIRMED; không nên gọi file này là retrieval thuần hoặc cho tool adapter import ngược toàn bộ pipeline. |
| backend/app/history.py:20, :23–30, :100–102 | Protocol persistence đã có nhưng error contract vẫn kéo concrete Mongo repository và PyMongo vào import closure. SOURCE_CONFIRMED; tác động là reuse history không hoàn toàn độc lập SDK. |
| backend/app/conversation_models.py:12–13; backend/app/attachment_models.py:4 | Shared helpers nằm trong Documents và attachment DTO nằm trong Conversations tạo domain coupling, không tạo vòng. SOURCE_CONFIRMED. |
| backend/app/rag/retriever.py:15; backend/app/qdrant_ingestion.py:156–205 | Retrieval tái sử dụng QdrantVectorIndex query implementation trong file tên ingestion. SOURCE_CONFIRMED; tên file hẹp hơn trách nhiệm, không phải retrieval thực hiện ingestion. |

## 5. Circular Dependency Findings

**CONFIRMED_CYCLE: 0.** Tarjan trả về 38 SCC, mỗi SCC một module, không self-loop. Kết quả kiểm tra DAG độc lập bằng in-degree elimination được ghi trong verification cuối báo cáo. STATIC_ANALYSIS_CONFIRMED cho tất cả 102 cạnh nội bộ ở mục 3, bao gồm imports ở function/conditional; không chỉ đồ thị rút gọn Mermaid.

Không có exact circular import chain/source lines để liệt kê vì không có cycle được phát hiện. Những chuỗi sau minh họa các trường hợp dễ đọc nhầm:

| Chuỗi có thật và line | Phân loại và kết luận |
| --- | --- |
| api.chat → conversation_service (api/chat.py:22) → citation_mapping (conversation_service.py:8) | SOURCE_CONFIRMED; citation_mapping chỉ import standard library, không quay về service/API. Không cycle. |
| conversation_models → attachment_models (conversation_models.py:13) → document_models (attachment_models.py:4), đồng thời conversation_models → document_models (:12) | SOURCE_CONFIRMED; diamond dependency, không cycle. document_models không import ngược Conversations. |
| document_service → ingestion (document_service.py:11) → document_repository (ingestion.py:21) → document_models (document_repository.py:15) | SOURCE_CONFIRMED; không có document_repository → document_service/ingestion. Không cycle. |
| query_rewriting → context_budget (query_rewriting.py:20) → history (context_budget.py:17) → conversation_repository (history.py:20) | SOURCE_CONFIRMED; repository không import query rewriting/history/budget. Không cycle. |

**POTENTIAL_RUNTIME_CYCLE: không có trường hợp cụ thể được xác lập.** Callback generate tạo lời gọi từ service đến một closure gọi pipeline; đó không phải import ngược, và callback hiện tại không gọi lại answer_with_persistence. Việc callback/injection *có thể* trỏ đến code khác nói chung không đủ để báo một cycle hiện hữu. Runtime recursion, SDK import cycles, plugin loading ngoài app và import hooks môi trường: NOT_VERIFIED.

**Rủi ro tương lai, chưa có trong source — POTENTIAL_RISK:** nếu pipeline import tool_use, còn tool_use import pipeline để gọi retrieval, sẽ hình thành pipeline → tool_use → pipeline. Nếu tool adapter import api.chat để tái dùng lifecycle thì cũng dễ tạo vòng API → orchestration → tool → API. Cách ngăn: tool nhận retrieval callable/contract qua injection; composition nằm ở orchestration/entrypoint; tool không import ngược transport/orchestrator. Không xử lý bằng lazy import để che cycle. Không có file/line cho các cạnh tương lai vì chúng chưa tồn tại.

## 6. Module Coupling Assessment

Degree dưới đây là số **module nội bộ trực tiếp duy nhất**, không tính số symbol hoặc external packages. Không đặt ngưỡng tự động để gắn lỗi.

| Module | In / Out | Đánh giá tác động và evidence |
| --- | --- | --- |
| api.chat | 1 / 11 | Fan-out cao hợp lý ở transport composition, nhưng 516 dòng nội dung chứa JSON, provider iteration, timeout/cancellation, persistence finalize và SSE encoding. SOURCE_CONFIRMED: backend/app/api/chat.py:118–312, :333–435, :439–516. POTENTIAL_RISK nếu tool loop được thêm cả JSON và SSE; chỉ tách orchestration khi phần mới thật sự vượt seam hiện có. |
| rag.pipeline | 1 / 11 | Hub chủ đích cho preparation chung, tránh drift JSON/SSE; factory/persistence/provider nằm cùng orchestration. SOURCE_CONFIRMED: backend/app/rag/pipeline.py:64–155, :175–239. prepare_rag_request_from_components nhận injected retriever/query_rewriter/budget_builder (:101–109), là seam hiện hữu. Không coi fan-out tự thân là defect. |
| ingestion | 3 / 9 | Workflow đa bước bắt buộc chạm metadata/storage/parsing/vector/embedding; injection đã có. SOURCE_CONFIRMED: backend/app/ingestion.py:63–80, :189–278. Tool Use cho chat không có lý do nhập ingestion toàn bộ. Publication/reconciliation chỉ có một owner; không tách tùy tiện theo counts. |
| api.documents | 1 / 8 | Ngoài service còn preview/storage/XLSX validation, SOURCE_CONFIRMED: backend/app/api/documents.py:125–153. Nếu dùng lại bởi tool, gọi capability service/adapter được inject, tránh gọi HTTP handler. |
| document_service; main | 1 / 7; 0 / 7 | Factory composition giải thích dependencies cụ thể: backend/app/document_service.py:131–146; backend/app/main.py:13–17, :21–38. Không cần container DI hoặc di chuyển factory ở R0-B. |
| config | 11 / 0 | Fan-in lớn đúng vai trò settings; không import business modules. SOURCE_CONFIRMED: backend/app/config.py:9–15, :235–245. Import-time Settings validation có thể ảnh hưởng reuse; môi trường hợp lệ NOT_VERIFIED. Không thêm tool registry/service imports vào config. |
| document_models | 9 / 0 | Central domain records cộng helper dùng ngoài Documents; coupling đáng quan tâm khi domain mở rộng. SOURCE_CONFIRMED: backend/app/document_models.py:15–51; backend/app/conversation_models.py:12; backend/app/attachment_models.py:4. Chỉ extract helper/base khi có thay đổi domain thực tế; giữ serialization contract. |
| document_repository | 8 / 2 | Nhiều consumers nhưng gồm factories, migration và exception imports, không phải cả tám cùng truy cập Mongo trong business path. SOURCE_CONFIRMED: imports mục 3; ví dụ attachments.py:7 chỉ import error, pipeline.py:72 thực sự dựng repository. Reuse lớn làm relocation/renaming tốn nhiều caller updates. |
| conversation_models | 7 / 2 | Domain types dùng trong service/history/DTO/pipeline là hợp lý; base/helper coupling đã mô tả ở B02. SOURCE_CONFIRMED: backend/app/conversation_models.py:12–13. |
| conversation_repository; vector_index | 5 / 2; 5 / 0 | Repository tập trung persistence và guard; vector_index là adapter contract dùng chung ingest/retrieval, không SDK dependency. SOURCE_CONFIRMED: backend/app/conversation_repository.py:117–220; backend/app/vector_index.py:147–176. Giữ các boundary này. |

**Infrastructure trong business logic:** DocumentService và IngestionService đã nhận FileStorage/VectorIndex, nhưng imports/factory vẫn kéo concrete Mongo/Qdrant adapters; ConversationService constructor gắn kiểu MongoConversationRepository; pipeline dựng concrete repositories. SOURCE_CONFIRMED: backend/app/document_service.py:43–54, :131–146; backend/app/ingestion.py:63–80, :340–353; backend/app/conversation_service.py:69–70, :299–300; backend/app/rag/pipeline.py:72–80. Đây là coupling có thể kiểm soát, chưa chứng minh cần kiến trúc ports/adapters cho toàn bộ backend. SDK dependencies thực tế có thể đi vào import closure ngay cả khi runtime function chỉ dùng Protocol/error.

Không module dưới app import ngược api/main từ repositories/adapters. STATIC_ANALYSIS_CONFIRMED theo inventory. Fan-in 0 của data_migration và rag.chain chỉ có nghĩa không được module app khác import; consumers bên scripts có thật (backend/scripts/migrate_demo_corpus.py:20, backend/scripts/eval_cli.py:35), không đề xuất xóa.

## 7. Module Ownership Matrix

Mỗi module có **một primary owner về trách nhiệm**, không đồng nghĩa đề nghị chuyển file ngay. Repositories/indexes có Mongo mechanics nhưng thuộc owner domain quản lý schema/lifecycle; infrastructure chỉ chứa adapters/contracts/provider/client lifecycle dùng chung. Attachment DTOs thuộc Conversations, document-version resolution/preview thuộc Documents. HTTP DTOs thuộc API dù tên file có conversation. Tất cả dòng có classification SOURCE_CONFIRMED cho trách nhiệm hiện tại; lựa chọn owner là đề xuất suy ra từ trách nhiệm đó, không khẳng định package mới đã tồn tại.

| Current module | Primary owner | Trách nhiệm và source evidence |
| --- | --- | --- |
| `app.api.chat` | API | HTTP/JSON/SSE adapter và điều phối turn hiện nằm chung — `backend/app/api/chat.py:118`. |
| `app.api.documents` | API | Document HTTP, upload validation và preview adapter — `backend/app/api/documents.py:125`. |
| `app.api.sessions` | API | Session/message HTTP và DTO mapping — `backend/app/api/sessions.py:32`. |
| `app.attachment_models` | Conversations | AttachmentReference và MessageAttachment dùng trong request/message — `backend/app/attachment_models.py:7`. |
| `app.attachments` | Documents | Xác thực document/version và đọc preview; không quản lý session scope — `backend/app/attachments.py:17`. |
| `app.citation_mapping` | RAG | Pure source-provenance mapping từ ordinal sang identity — `backend/app/citation_mapping.py:12`. |
| `app.cloud_connections` | Infrastructure | Lifecycle MongoDB/Qdrant clients — `backend/app/cloud_connections.py:38`. |
| `app.config` | Shared/Core | Settings và cấu hình dùng chung — `backend/app/config.py:23`. |
| `app.context_budget` | Chat Orchestration | Phân bổ budget cho system/history/chunks/query — `backend/app/context_budget.py:134`. |
| `app.conversation_indexes` | Conversations | Mongo indexes thuộc domain conversations — `backend/app/conversation_indexes.py:53`. |
| `app.conversation_models` | Conversations | Session scope, message state, citation/usage records — `backend/app/conversation_models.py:16`. |
| `app.conversation_repository` | Conversations | Mongo persistence, session guard/sequence, message lifecycle — `backend/app/conversation_repository.py:117`. |
| `app.conversation_schemas` | API | Session/message HTTP DTOs; domain vocabulary từ Conversations — `backend/app/conversation_schemas.py:11`. |
| `app.conversation_service` | Conversations | Session CRUD và durable turn lifecycle; nhận generation callback — `backend/app/conversation_service.py:97`. |
| `app.data_migration` | Ingestion | Điều phối migrate corpus và xác minh dữ liệu; không phải startup — `backend/app/data_migration.py:68`. |
| `app.document_indexes` | Documents | Mongo indexes thuộc domain documents — `backend/app/document_indexes.py:69`. |
| `app.document_models` | Documents | Document/version/job records; đang chứa cả base record và UUID/time helpers — `backend/app/document_models.py:15`. |
| `app.document_repository` | Documents | Mongo document/version/job persistence và publication — `backend/app/document_repository.py:37`. |
| `app.document_service` | Documents | Document lifecycle/use cases và composition factory — `backend/app/document_service.py:42`. |
| `app.excel` | Ingestion | Bounded workbook parser, LangChain Document projection và preview projection — `backend/app/excel.py:43`. |
| `app.history` | Conversations | Tải persisted session và lọc whole-turn history; không retrieve/generate — `backend/app/history.py:23`. |
| `app.ingestion` | Ingestion | Raw file → parse/split/embed/index → publication/reconciliation — `backend/app/ingestion.py:62`. |
| `app.main` | API | Composition root: router, lifecycle, index initialization — `backend/app/main.py:21`. |
| `app.qdrant_ingestion` | Infrastructure | Qdrant implementation của VectorIndex, có query/count/delete — `backend/app/qdrant_ingestion.py:30`. |
| `app.query_rewriting` | Chat Orchestration | Quyết định/guard rewrite, gọi provider, giữ query gốc — `backend/app/query_rewriting.py:102`. |
| `app.rag.chain` | RAG | LCEL baseline chain riêng; không phải pipeline HTTP hiện tại — `backend/app/rag/chain.py:26`. |
| `app.rag.embeddings` | Infrastructure | Gemini/LangChain embedding provider factory — `backend/app/rag/embeddings.py:17`. |
| `app.rag.llm` | Infrastructure | Groq/OpenAI-compatible chat-model factory — `backend/app/rag/llm.py:15`. |
| `app.rag.loader` | Ingestion | File-format parsing facade, có XLSX qua excel — `backend/app/rag/loader.py:15`. |
| `app.rag.pipeline` | Chat Orchestration | History/scope/rewrite/retrieval/budget và generation chung JSON/SSE — `backend/app/rag/pipeline.py:64`. |
| `app.rag.prompt` | RAG | Prompt và format context/history; không truy cập persistence — `backend/app/rag/prompt.py:25`. |
| `app.rag.retriever` | RAG | Active-version filtered retrieval; factory lắp adapters — `backend/app/rag/retriever.py:38`. |
| `app.rag.splitter` | Ingestion | Text splitting và giữ provenance — `backend/app/rag/splitter.py:13`. |
| `app.schemas` | API | HTTP chat/document DTOs; không phải domain core tổng quát — `backend/app/schemas.py:14`. |
| `app.sse_schema` | API | SSE DTOs, transcript validation và encoding — `backend/app/sse_schema.py:23`. |
| `app.storage` | Infrastructure | FileStorage contract và LocalFileStorage implementation — `backend/app/storage.py:47`. |
| `app.stream_metrics` | Chat Orchestration | Theo dõi thời gian stream và ghi metric qua logging — `backend/app/stream_metrics.py:25`. |
| `app.vector_index` | Infrastructure | Vector contract, filters, records và errors dùng chung ingest/retrieval — `backend/app/vector_index.py:147`. |

### Các module dễ nhầm ownership

- **history.py → Conversations.** Load persisted session/scope và whole completed turns, dùng HistoryRepository Protocol; không dựng prompt, không rewrite hoặc retrieve. backend/app/history.py:23–30, :57–86, :106–139. RAG/chat orchestration là consumer; chuyển sang rag/ chỉ vì pipeline dùng nó sẽ làm nghĩa ownership sai.
- **attachments.py → Documents.** resolve_version kiểm tra version thuộc document và document chưa deleted; resolve_attachments tạo metadata server-owned, preview_version đọc raw bytes/Excel projection. backend/app/attachments.py:17–38, :41–65. Việc trả MessageAttachment tạo cạnh Documents → Conversations, nhưng không làm module thành session orchestrator. Không đổi session retrieval scope. Không cần tách file chỉ vì cạnh này; chỉ tách resolution và preview nếu các use cases phát triển độc lập.
- **excel.py → Ingestion, capability parsing tái dùng bởi Documents preview.** read_workbook giới hạn workbook, workbook_documents dựng LangChain Documents, workbook_preview tạo projection cho API. backend/app/excel.py:43–94, :97–112, :115–138. Không phải Shared/Core trung tính vì import langchain_core.documents và openpyxl (:8–9). Optional separation parser/projections chỉ đáng làm nếu thêm tool xử lý bảng và cần reuse parser không kéo LangChain.
- **citation_mapping.py → RAG.** Pure provenance utility, nhận answer + ordered sources; xác thực identities/ordinal, không persistence/transport/provider. backend/app/citation_mapping.py:12–30, :33–56. Conversations dùng nó để finalize citations, API dùng cho response. Không đặt trong Conversations chỉ vì dữ liệu cuối cùng được persist. Không coi UUID hợp lệ là chứng minh factual grounding.
- **rag/pipeline.py, context_budget.py, query_rewriting.py → Chat Orchestration.** Kết hợp history, original/retrieval query và generation policy; retrieval capability riêng ở rag/retriever.py. Source: backend/app/rag/pipeline.py:64–155; backend/app/context_budget.py:134–192; backend/app/query_rewriting.py:170–241. Owner khác vị trí hiện tại là đủ, chưa cần move.

### Minimal boundary cho tool_use/ tương lai

Proposed boundary, chưa tồn tại: orchestration gọi capability Tool Use và inject các adapters/callables cần thiết; tool_use giữ tool definitions, argument/result contract, registry/dispatch và giới hạn execution do owner duyệt. Module này không sở hữu session guard/message persistence, HTTP/SSE encoding, document publication, hay cloud-client lifecycle. Tool cần retrieval nhận active-version scope đã giải quyết hoặc scoped retrieval callable; không import rag.pipeline/api.chat và không tự mở cloud connections. SOURCE_CONFIRMED cho seam nền: backend/app/rag/pipeline.py:101–109; backend/app/conversation_service.py:97–105; backend/app/rag/retriever.py:71–102. Lựa chọn boundary tương lai: POTENTIAL_RISK nếu bị vi phạm, chưa phải missing implementation defect trong R0-B.

## 8. Refactor Impact & Current-to-Proposed Mapping

**CURRENT → PROPOSED giữ nguyên physical import paths cho toàn bộ 38 module.** Owner có thể chấp nhận mapping logic ở mục 7 mà không sửa code. Bảng dưới là đề xuất, không phải thay đổi đã áp dụng.

- KEEP: giữ module/path/contract hiện tại.
- MOVE_LATER: chỉ di chuyển khi có lợi ích cụ thể; **không có relocation nào được đề nghị trong vòng này**.
- REFACTOR_LATER: có lựa chọn extract/separate trách nhiệm khi trigger thực tế xuất hiện; vẫn giữ public path/facade nếu làm.
- REQUIRED_BEFORE_TOOL_USE: boundary/contract phải chốt trước triển khai tool execution; **không có module hiện hữu nào bị yêu cầu move/refactor chỉ để qua R0-B**. Các quyết định bắt buộc được tách ở mục 9, không ngụy tạo một source file cần sửa ngay.

| CURRENT → PROPOSED import path | Classification | Proposed treatment |
| --- | --- | --- |
| `app.api.chat` → `app.api.chat` | REFACTOR_LATER | Nếu thêm tool loop: giữ HTTP/SSE adapter ở đây, gom execution policy tại seam dùng chung; giữ router/DTO/event contracts. |
| `app.api.documents` → `app.api.documents` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.api.sessions` → `app.api.sessions` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.attachment_models` → `app.attachment_models` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.attachments` → `app.attachments` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.citation_mapping` → `app.citation_mapping` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.cloud_connections` → `app.cloud_connections` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.config` → `app.config` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.context_budget` → `app.context_budget` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.conversation_indexes` → `app.conversation_indexes` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.conversation_models` → `app.conversation_models` | REFACTOR_LATER | Chỉ đổi helper imports nếu extract base/UUID/time helpers; giữ model fields, aliases, validators và enums. |
| `app.conversation_repository` → `app.conversation_repository` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.conversation_schemas` → `app.conversation_schemas` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.conversation_service` → `app.conversation_service` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.data_migration` → `app.data_migration` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.document_indexes` → `app.document_indexes` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.document_models` → `app.document_models` | REFACTOR_LATER | Có thể extract base/UUID/time helpers vào Shared/Core khi cần reuse độc lập domain; giữ re-export để bảo toàn callers. |
| `app.document_repository` → `app.document_repository` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.document_service` → `app.document_service` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.excel` → `app.excel` | REFACTOR_LATER | Chỉ tách parser khỏi LangChain/preview projections nếu tool reuse đòi hỏi; giữ các hàm facade hiện có. |
| `app.history` → `app.history` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.ingestion` → `app.ingestion` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.main` → `app.main` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.qdrant_ingestion` → `app.qdrant_ingestion` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.query_rewriting` → `app.query_rewriting` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.rag.chain` → `app.rag.chain` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.rag.embeddings` → `app.rag.embeddings` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.rag.llm` → `app.rag.llm` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.rag.loader` → `app.rag.loader` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.rag.pipeline` → `app.rag.pipeline` | REFACTOR_LATER | Nếu triển khai tools: giữ facade chuẩn bị/generate hiện tại; extract execution seam chỉ khi cần, tránh import ngược từ tool adapter. |
| `app.rag.prompt` → `app.rag.prompt` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.rag.retriever` → `app.rag.retriever` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.rag.splitter` → `app.rag.splitter` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.schemas` → `app.schemas` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.sse_schema` → `app.sse_schema` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.storage` → `app.storage` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.stream_metrics` → `app.stream_metrics` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |
| `app.vector_index` → `app.vector_index` | KEEP | Giữ trách nhiệm và import path; owner như mục 7. |

### Import paths bị tác động nếu owner duyệt refactor về sau

Không có import path nào thay đổi trong R0-B. Dưới đây là **toàn bộ importer trực tiếp trong app** của các module REFACTOR_LATER, tính từ inventory, để phân biệt impact thực tế với khuyến nghị mơ hồ. Giữ facade/re-export thì callers không buộc đổi.

| Target có thể refactor | Importers hiện tại @ source line | Hợp đồng phải giữ |
| --- | --- | --- |
| `app.api.chat` | `backend/app/main.py:13` | router, handlers và SSE lifecycle adapter |
| `app.rag.pipeline` | `backend/app/api/chat.py:28` | PreparedRagStream, ProviderStreamChunk, answer_question/prepare_rag_stream/astream_rag_answer và async helpers |
| `app.conversation_models` | `backend/app/api/chat.py:15`; `backend/app/api/sessions.py:8`; `backend/app/conversation_repository.py:12`; `backend/app/conversation_schemas.py:7`; `backend/app/conversation_service.py:10`; `backend/app/history.py:13`; `backend/app/rag/pipeline.py:20` | Session/Message records, enums, scope và helper re-exports |
| `app.document_models` | `backend/app/attachment_models.py:4`; `backend/app/attachments.py:6`; `backend/app/conversation_models.py:12`; `backend/app/data_migration.py:12`; `backend/app/document_repository.py:15`; `backend/app/document_service.py:9`; `backend/app/ingestion.py:15`; `backend/app/rag/pipeline.py:22`; `backend/app/schemas.py:10` | MongoRecord, UUID/time helpers và document/version/job models |
| `app.excel` | `backend/app/api/documents.py:20`; `backend/app/attachments.py:8`; `backend/app/rag/loader.py:11` | WorkbookError, limits, read_workbook/workbook_documents/workbook_preview |

Import impact ngoài app cần review riêng nếu đổi path: backend/evaluation/history_eval.py:11 import HistoryTurn; backend/scripts/eval_history_cli.py:24 import pipeline helpers; backend/scripts/eval_cli.py:35 dùng baseline chain; backend/tests/test_message_attachments_excel.py:255, :280 patch string app.excel.*, và backend/tests/test_multi_session_isolation.py:177–180 patch app.rag.pipeline.*. SOURCE_CONFIRMED bằng tìm kiếm văn bản; không chạy các consumers này. Một lần grep caller đầy đủ vẫn cần tại thời điểm refactor vì báo cáo không đóng băng workspace tương lai.

### Circular-dependency impact và stable contracts

Nếu extract shared base/helpers: core phải không import lại document/conversation models; document_models có thể re-export helper để tương thích. Nếu đưa tool execution seam vào pipeline: tool adapters không import pipeline, API hoặc concrete conversation service; inject retrieval capability để giữ DAG. Nếu tách Excel parser: lớp parser không import ngược preview/tool orchestration. Tất cả là POTENTIAL_RISK của phương án tương lai, không phải cycles hiện có.

Giữ các contracts sau:

| Contract | Evidence và ràng buộc |
| --- | --- |
| HTTP DTOs/routes | backend/app/schemas.py:98–150, :213–266; backend/app/conversation_schemas.py:11–104; backend/app/main.py:50–52. Không thêm route/DTO/tool payload trong R0-B. |
| SSE | backend/app/sse_schema.py:23–105, :205–207; backend/app/api/chat.py:132–159, :190–253. Giữ start/metadata/delta/done/error behavior, sequence, IDs và terminal semantics; không tự đưa raw tool/control chunks lên SSE. |
| Persisted turn lifecycle | backend/app/conversation_service.py:97–186, :188–278; backend/app/conversation_repository.py:117–220. Session guard và finalization thuộc Conversations; tool adapter không tự tạo/finalize message. |
| Retrieval scope/provenance | backend/app/rag/pipeline.py:242–262, :312–323; backend/app/rag/retriever.py:31–50; backend/app/citation_mapping.py:12–56. Giữ empty-scope behavior, active-version filtering, source order và identity mapping. |
| Storage/vector seams | backend/app/storage.py:47–68; backend/app/vector_index.py:147–176; backend/app/rag/retriever.py:71–102. Dùng injection hiện có, không tạo client/service locator mới chỉ để tools gọi retrieval. |
| DB serialization/schema | backend/app/document_models.py:46–51, :54–157; backend/app/conversation_models.py:59–186; backend/app/document_indexes.py:69–74; backend/app/conversation_indexes.py:53–58. Không đổi collections, indexes, fields/aliases hay schema trong vòng này. |

## 9. Minimum Changes Before Tool Use

**Số thay đổi cấu trúc bắt buộc trong backend hiện tại theo bằng chứng R0-B: 0.** Không có cycle cần phá và không có relocation bắt buộc. Tách owner logic và dùng seam injection hiện hữu đủ làm nền; lựa chọn cụ thể còn phụ thuộc tooluse.md chưa có. Không khẳng định mọi tool tương lai đều triển khai được mà không thay code.

Các mục sau là **REQUIRED_BEFORE_TOOL_USE — owner/design gate cho vòng triển khai được duyệt sau**, không phải lệnh sửa application trong audit:

| Gate | Minimum decision/change khi triển khai | Evidence hiện tại / classification |
| --- | --- | --- |
| T1 — Ownership/dependency direction | Chọn một nơi điều phối tool execution dùng chung cho JSON/SSE; tool_use không import API/pipeline/conversation persistence ngược; registry/dispatch nhận capabilities được inject. Không cần chuyển các file hiện tại để làm điều này. | backend/app/api/chat.py:333–368, :453–470; backend/app/rag/pipeline.py:101–109. SOURCE_CONFIRMED cho seams; nguy cơ nhân đôi/cycle là POTENTIAL_RISK. |
| T2 — Input/output contract | Chốt tool set thực sự, validated args, normalized result/error và cách chuyển tool result thành answer/sources/usage hiện tại. Chỉ dùng text normalization hiện tại không xử lý tool-call lifecycle; cần execution seam riêng hoặc adapter mapping rõ ràng. | backend/app/rag/pipeline.py:56–61, :175–188, :228–239, :265–279. SOURCE_CONFIRMED. Khả năng model/provider hỗ trợ tool calls: NOT_VERIFIED; không gọi provider để kiểm tra. |
| T3 — Lifecycle và bounds | Chốt timeout/cancellation/max-step behavior ở tool executor và một owner finalization; tool errors phải đi qua behavior hiện có của JSON/SSE/persistence. Không nhân tool loop thành nhiều durable user/assistant turns hoặc raw protocol messages khi DB/DTO chưa được duyệt đổi. | backend/app/api/chat.py:170–223, :278–303; backend/app/conversation_service.py:97–105, :232–278. SOURCE_CONFIRMED nền lifecycle; chính sách tool cụ thể chưa có: NOT_VERIFIED. |
| T4 — Scope và source contract | Retrieval tool phải nhận scope phía server và trả provenance/order phù hợp. Không dùng attachment references để ngầm thay retrieval scope; không gọi loader/ingestion hoặc mở search unfiltered như shortcut. | backend/app/attachments.py:1, :30–38; backend/app/rag/pipeline.py:75–98, :242–262; backend/app/rag/retriever.py:44–50. SOURCE_CONFIRMED. |

Không đặt thêm requirements auth/RBAC, schema mới, general agent framework, DI container, message bus hoặc full domain package migration vào minimum scope. Những yêu cầu đó không được chứng minh cần thiết cho R0-B. Không sửa F/C/U findings; các audit cũ giữ nguyên và không được nâng thành runtime-confirmed bằng kết quả import graph.

## 10. Final Verdict & Owner Decision Gate

**R0-B verdict: đồ thị import nội bộ hiện tại là DAG; đủ cơ sở tiếp tục thiết kế Tool Use có giới hạn, chưa cần restructuring toàn backend.** SOURCE_CONFIRMED cho boundaries và seams; STATIC_ANALYSIS_CONFIRMED cho 38 module/102 cạnh/không cycle. Đây là architecture decision support, không chứng nhận backend chạy được, provider tool support, JSON/SSE parity qua runtime, hay production readiness.

Owner có thể duyệt giữ nguyên layout hiện tại và dùng ownership ở mục 7; chỉ cân nhắc các REFACTOR_LATER khi tool execution thực tế yêu cầu. Trước implementation cần cung cấp/duyệt roadmap tool set và các gate T1–T4, đặc biệt text/tool-result mapping và một owner cho durable turn. Hai reference còn thiếu giới hạn việc đối chiếu với kế hoạch R0/Tool Use gốc; không cản kết luận về import graph hiện tại.

### Final verification record

- **Coverage — STATIC_ANALYSIS_CONFIRMED:** 38/38 Python files; file list trước/sau giống nhau; 38 inventory rows, 38 ownership rows, 38 current-to-proposed rows. Source-line import scan độc lập và scanner sau che comments/strings cùng 273 câu lệnh, không thiếu/thừa import line.
- **Edges/bindings — STATIC_ANALYSIS_CONFIRMED:** 102 unique internal edges, mọi edge truy lại được câu lệnh source ở line ghi trong inventory; 0 unresolved module targets, 0 imported bindings không tìm thấy trong target source. Absolute 273, relative 0; hai lazy/conditional imports đã tách riêng. External availability không được xác minh.
- **Cycles — STATIC_ANALYSIS_CONFIRMED:** Tarjan có 38 singleton SCC, 0 self-loop; Kahn/in-degree elimination xử lý hết 38 node. Không đánh đồng vòng giữa nhóm trong Mermaid hoặc lời gọi callback với module import cycle.
- **Ownership consistency:** diagram, matrix và mapping cùng dùng một primary owner cho mỗi module; ownership không đồng nghĩa physical relocation. Không có MOVE_LATER hoặc source refactor nào bắt buộc trước Tool Use.
- **Read-only application boundary:** SHA-256 trước/sau không đổi cho toàn bộ 38 Python source files và 16 file đã snapshot bổ sung (hướng dẫn repository/frontend, hai README, requirements/Dockerfile, package manifests/lockfile, .env.example templates và sáu audit hiện hữu). Không chỉnh source, cấu hình, audit cũ hoặc README. Chỉ ghi mới BACKEND-DEPENDENCY-ANALYSIS.md theo yêu cầu explicit về output; không tạo scanner/script/artifact phụ.
- **Execution boundary:** không chạy backend/server, tests, build, lint, scripts dự án, import application modules, dependency install/repair hoặc network/service calls. Chỉ thực hiện filesystem/git/rg inspection và Node built-in static analysis/report writing. Lệnh python -B - cho bộ phân tích AST inline không chạy được vì shell không tìm thấy python; không có Python/application execution phát sinh từ lần thử đó.
- **Existing working tree:** trước audit đã có README.md và frontend/README.md modified, docs/audits/ untracked. Giữ nguyên các thay đổi này; chúng không phải sản phẩm của R0-B. Không reset/clean/commit.
- **Restructuring decision:** không có bằng chứng restructuring là điều kiện tiên quyết; Tool Use design/implementation và các claims runtime vẫn chưa được phê duyệt/xác minh trong vòng này.

**Dừng tại R0-B.** Không tiến hành R1, relocation/refactor, triển khai Tool Use hoặc sửa findings F/C/U. Mọi bước tiếp theo cần owner phê duyệt phạm vi riêng; báo cáo này không phải approval triển khai.

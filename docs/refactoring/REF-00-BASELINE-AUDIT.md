# REF-00 — Baseline Audit & Safety Snapshot

## 1. Git & Working Tree State

- **Branch:** `master`
- **HEAD Commit:** `dee65aeb07a5a6bb6e0363d21bda1497118824b6` (`feat(rag): integrate document inventory tool calling`)
- **`backend/` Status at Baseline:** Clean (`0` modified, `0` staged, `0` untracked files inside `backend/`).
- **Pre-existing Non-Backend Working Tree Entries (Preserved Untouched):**
  - Modified: `.gitignore`
  - Untracked: `BACKEND-DEPENDENCY-ANALYSIS.md`, `BACKEND-MODULE-BOUNDARIES.md`, `R2-01-IMPLEMENTATION-REPORT.md`, `R2-02-IMPLEMENTATION-REPORT.md`, `R2-03-IMPLEMENTATION-REPORT.md`, `R2-04-IMPLEMENTATION-REPORT.md`, `R2-05-IMPLEMENTATION-REPORT.md`, `R2-06-ACCEPTANCE-REPORT.md`, `R2-06B-LIVE-SMOKE-REPORT.md`, `docs/audits/` (`10` audit files).

---

## 2. Python 3.12.10 Environment Verification

- **Explicit Interpreter:** `C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe` (`Python 3.12.10`)
- **Project Virtual Environment:** `d:\Project\rag-demo\.venv` recreated with Python `3.12.10` (`.\.venv\Scripts\python.exe --version` → `Python 3.12.10`)
- **Manifest Compatibility:** `backend/requirements.txt` (`20` requirement specifications; no conflicting Python version lock; all packages installed cleanly on Python `3.12.10` without modifying `backend/requirements.txt`).
- **Dependency Integrity (`pip check`):** `No broken requirements found.`
- **Key Dependency Import Verification:** `fastapi`, `uvicorn`, `pydantic`, `pydantic_settings`, `langchain_core`, `langchain_openai`, `langchain_google_genai`, `langchain_text_splitters`, `langchain_community`, `pypdf`, `chardet`, `pymongo`, `dns`, `qdrant_client`, `unstructured`, `openpyxl`, `defusedxml`, `networkx`, `pandas` → `ALL_IMPORTS_OK`.

---

## 3. Baseline Test Execution

- **Command:** `.\.venv\Scripts\python.exe -B -c "import os, sys, unittest; os.chdir('backend'); sys.path.insert(0, os.getcwd()); result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests')); sys.exit(not result.wasSuccessful())"`
- **Total Tests Executed:** `384`
- **PASS:** `384`
- **FAIL:** `0`
- **ERROR:** `0`
- **SKIP:** `0`
- **Execution Time:** `5.132s`
- **External Network / Cloud Calls:** `0` (all tests run offline against in-memory fakes/mocks).

---

## 4. Complete Backend Module Inventory (`116` Python Files)

### 4.1. `backend/app/` (`44` files)

1. `backend/app/main.py`
2. `backend/app/attachment_models.py`
3. `backend/app/attachments.py`
4. `backend/app/chat_orchestration.py`
5. `backend/app/citation_mapping.py`
6. `backend/app/cloud_connections.py`
7. `backend/app/config.py`
8. `backend/app/context_budget.py`
9. `backend/app/conversation_indexes.py`
10. `backend/app/conversation_models.py`
11. `backend/app/conversation_repository.py`
12. `backend/app/conversation_schemas.py`
13. `backend/app/conversation_service.py`
14. `backend/app/data_migration.py`
15. `backend/app/document_indexes.py`
16. `backend/app/document_models.py`
17. `backend/app/document_queries.py`
18. `backend/app/document_repository.py`
19. `backend/app/document_service.py`
20. `backend/app/excel.py`
21. `backend/app/history.py`
22. `backend/app/ingestion.py`
23. `backend/app/qdrant_ingestion.py`
24. `backend/app/query_rewriting.py`
25. `backend/app/schemas.py`
26. `backend/app/sse_schema.py`
27. `backend/app/storage.py`
28. `backend/app/stream_metrics.py`
29. `backend/app/vector_index.py`
30. `backend/app/api/chat.py`
31. `backend/app/api/documents.py`
32. `backend/app/api/sessions.py`
33. `backend/app/rag/chain.py`
34. `backend/app/rag/embeddings.py`
35. `backend/app/rag/llm.py`
36. `backend/app/rag/loader.py`
37. `backend/app/rag/pipeline.py`
38. `backend/app/rag/prompt.py`
39. `backend/app/rag/retriever.py`
40. `backend/app/rag/splitter.py`
41. `backend/app/tool_use/__init__.py`
42. `backend/app/tool_use/contracts.py`
43. `backend/app/tool_use/document_tools.py`
44. `backend/app/tool_use/executor.py`

### 4.2. `backend/evaluation/` (`2` Python files + datasets & results)

- Python modules (`2`):
  1. `backend/evaluation/history_eval.py`
  2. `backend/evaluation/metrics.py`
- Datasets & artifacts:
  - `backend/evaluation/golden_set.json`
  - `backend/evaluation/history_golden_set.json`
  - `backend/evaluation/corpus/01_architecture_overview.md`
  - `backend/evaluation/corpus/02_chunking_and_metadata.md`
  - `backend/evaluation/corpus/03_operations_and_limitations.md`
  - `backend/evaluation/results/` (`5` JSON result snapshots + `.gitkeep`)

### 4.3. `backend/scripts/` (`35` files)

1. `backend/scripts/check_cloud_connections.py`
2. `backend/scripts/controlled_live_e2e.py`
3. `backend/scripts/eval_cli.py`
4. `backend/scripts/eval_history_cli.py`
5. `backend/scripts/init_mongodb_indexes.py`
6. `backend/scripts/migrate_demo_corpus.py`
7. `backend/scripts/reconcile_ingestion.py`
8. `backend/scripts/smoke_citation_mapping.py`
9. `backend/scripts/smoke_context_budget.py`
10. `backend/scripts/smoke_conversation_models.py`
11. `backend/scripts/smoke_document_api.py`
12. `backend/scripts/smoke_history_loader.py`
13. `backend/scripts/smoke_ingestion.py`
14. `backend/scripts/smoke_message_persistence.py`
15. `backend/scripts/smoke_provider_stream.py`
16. `backend/scripts/smoke_qdrant_ingestion.py`
17. `backend/scripts/smoke_query_rewriting.py`
18. `backend/scripts/smoke_rag_integration.py`
19. `backend/scripts/smoke_response_contract.py`
20. `backend/scripts/smoke_session_api.py`
21. `backend/scripts/smoke_session_concurrency.py`
22. `backend/scripts/smoke_sse_schema.py`
23. `backend/scripts/smoke_stream_endpoint.py`
24. `backend/scripts/smoke_stream_errors.py`
25. `backend/scripts/smoke_stream_lifecycle.py`
26. `backend/scripts/smoke_stream_metrics.py`
27. `backend/scripts/smoke_vector_adapter.py`
28. `backend/scripts/try_step.py`
29. `backend/scripts/verify_cutover.py`
30. `backend/scripts/verify_frontend_functional_qa.py`
31. `backend/scripts/verify_m06.py`
32. `backend/scripts/verify_multi_session_isolation.py`
33. `backend/scripts/verify_phase1.py`
34. `backend/scripts/verify_phase2.py`
35. `backend/scripts/verify_ui_S1_S7.py`

### 4.4. `backend/tests/` (`35` files)

1. `backend/tests/test_chat_json_tools.py`
2. `backend/tests/test_chat_orchestration.py`
3. `backend/tests/test_chat_persistence.py`
4. `backend/tests/test_chat_response_schema.py`
5. `backend/tests/test_chat_stream.py`
6. `backend/tests/test_chat_stream_tools.py`
7. `backend/tests/test_citation_mapping.py`
8. `backend/tests/test_cloud_connections.py`
9. `backend/tests/test_context_budget.py`
10. `backend/tests/test_controlled_live_guards.py`
11. `backend/tests/test_conversation_concurrency.py`
12. `backend/tests/test_conversation_models.py`
13. `backend/tests/test_cors.py`
14. `backend/tests/test_document_models.py`
15. `backend/tests/test_document_queries.py`
16. `backend/tests/test_documents_api.py`
17. `backend/tests/test_evaluation_metrics.py`
18. `backend/tests/test_history.py`
19. `backend/tests/test_history_evaluation.py`
20. `backend/tests/test_ingestion.py`
21. `backend/tests/test_llm.py`
22. `backend/tests/test_m06_verification.py`
23. `backend/tests/test_message_attachments_excel.py`
24. `backend/tests/test_multi_session_isolation.py`
25. `backend/tests/test_query_rewriting.py`
26. `backend/tests/test_rag_integration.py`
27. `backend/tests/test_retriever.py`
28. `backend/tests/test_session_actions.py`
29. `backend/tests/test_sessions_api.py`
30. `backend/tests/test_sse_schema.py`
31. `backend/tests/test_storage.py`
32. `backend/tests/test_stream_metrics.py`
33. `backend/tests/test_stream_terminal_parity.py`
34. `backend/tests/test_streaming_pipeline.py`
35. `backend/tests/test_tool_use.py`
36. `backend/tests/test_vector_index.py`
37. `backend/tests/test_xlsx_loader.py`

*(Note: 35 test `.py` files in `backend/tests/`; `test_chat_json_tools.py` and `test_chat_stream_tools.py` also import test helpers from sibling test modules during discovery.)*

---

## 5. Baseline Dependency & Import Graph Analysis

- **Total `app` Modules:** `44` (`43` non-empty modules + `1` empty `app.tool_use.__init__`)
- **Total AST Import Statements:** `323` (`0` relative imports)
- **Unique Directed Internal Edges:** `120`
- **Strongly Connected Components (SCCs):** `44` singleton SCCs
- **Circular Dependencies:** `0`

| Module | Fan-in | Fan-out | Internal Dependencies | External Packages |
| --- | ---: | ---: | --- | --- |
| `app.api.chat` | 1 | 13 | `app.attachments`, `app.chat_orchestration`, `app.citation_mapping`, `app.config`, `app.conversation_models`, `app.conversation_repository`, `app.conversation_service`, `app.document_queries`, `app.document_repository`, `app.rag.pipeline`, `app.schemas`, `app.sse_schema`, `app.stream_metrics` | `anyio`, `asyncio`, `concurrent`, `fastapi`, `time`, `typing`, `uuid` |
| `app.api.documents` | 1 | 8 | `app.attachments`, `app.document_repository`, `app.document_service`, `app.excel`, `app.ingestion`, `app.rag.loader`, `app.schemas`, `app.storage` | `fastapi`, `pathlib`, `uuid` |
| `app.api.sessions` | 1 | 4 | `app.conversation_models`, `app.conversation_repository`, `app.conversation_schemas`, `app.conversation_service` | `fastapi`, `uuid` |
| `app.attachment_models` | 5 | 1 | `app.document_models` | `pydantic` |
| `app.attachments` | 2 | 4 | `app.attachment_models`, `app.document_models`, `app.document_repository`, `app.excel` | `codecs`, `pathlib` |
| `app.chat_orchestration` | 1 | 10 | `app.config`, `app.context_budget`, `app.conversation_repository`, `app.document_queries`, `app.history`, `app.rag.llm`, `app.rag.pipeline`, `app.tool_use.contracts`, `app.tool_use.document_tools`, `app.tool_use.executor` | `asyncio`, `collections`, `dataclasses`, `json`, `langchain_core`, `math`, `time`, `typing` |
| `app.citation_mapping` | 2 | 0 | — | `re`, `typing`, `uuid` |
| `app.cloud_connections` | 1 | 1 | `app.config` | `dataclasses`, `pymongo`, `qdrant_client`, `typing` |
| `app.config` | 12 | 0 | — | `functools`, `pathlib`, `pydantic`, `pydantic_settings`, `re`, `urllib` |
| `app.context_budget` | 3 | 1 | `app.history` | `dataclasses`, `langchain_core`, `typing` |
| `app.conversation_indexes` | 2 | 0 | — | `collections`, `pymongo`, `typing` |
| `app.conversation_models` | 7 | 2 | `app.attachment_models`, `app.document_models` | `datetime`, `enum`, `pydantic` |
| `app.conversation_repository` | 6 | 2 | `app.conversation_indexes`, `app.conversation_models` | `dataclasses`, `pymongo`, `typing` |
| `app.conversation_schemas` | 1 | 2 | `app.attachment_models`, `app.conversation_models` | `datetime`, `pydantic` |
| `app.conversation_service` | 2 | 4 | `app.attachment_models`, `app.citation_mapping`, `app.conversation_models`, `app.conversation_repository` | `asyncio`, `collections`, `dataclasses`, `typing` |
| `app.data_migration` | 0 | 5 | `app.document_models`, `app.document_repository`, `app.ingestion`, `app.storage`, `app.vector_index` | `dataclasses`, `hashlib`, `langchain_core`, `pathlib`, `typing` |
| `app.document_indexes` | 2 | 0 | — | `collections`, `pymongo`, `typing` |
| `app.document_models` | 10 | 0 | — | `datetime`, `enum`, `pydantic`, `typing`, `uuid` |
| `app.document_queries` | 3 | 2 | `app.document_models`, `app.document_repository` | `json`, `typing` |
| `app.document_repository` | 10 | 2 | `app.document_indexes`, `app.document_models` | `pydantic`, `pymongo`, `typing` |
| `app.document_service` | 1 | 7 | `app.config`, `app.document_models`, `app.document_repository`, `app.ingestion`, `app.qdrant_ingestion`, `app.storage`, `app.vector_index` | `dataclasses`, `typing` |
| `app.excel` | 3 | 0 | — | `datetime`, `io`, `langchain_core`, `math`, `openpyxl`, `zipfile` |
| `app.history` | 4 | 2 | `app.conversation_models`, `app.conversation_repository` | `dataclasses`, `typing` |
| `app.ingestion` | 3 | 9 | `app.config`, `app.document_models`, `app.document_repository`, `app.qdrant_ingestion`, `app.rag.embeddings`, `app.rag.loader`, `app.rag.splitter`, `app.storage`, `app.vector_index` | `dataclasses`, `langchain_core`, `pathlib`, `shutil`, `tempfile`, `typing` |
| `app.main` | 0 | 7 | `app.api.chat`, `app.api.documents`, `app.api.sessions`, `app.cloud_connections`, `app.config`, `app.conversation_indexes`, `app.document_indexes` | `contextlib`, `fastapi` |
| `app.qdrant_ingestion` | 3 | 1 | `app.vector_index` | `math`, `qdrant_client`, `typing` |
| `app.query_rewriting` | 1 | 3 | `app.context_budget`, `app.history`, `app.rag.llm` | `asyncio`, `collections`, `dataclasses`, `enum`, `langchain_core`, `re`, `time`, `typing` |
| `app.rag.chain` | 0 | 2 | `app.rag.llm`, `app.rag.prompt` | `langchain_core` |
| `app.rag.embeddings` | 2 | 1 | `app.config` | `functools`, `langchain_core`, `langchain_google_genai` |
| `app.rag.llm` | 4 | 1 | `app.config` | `functools`, `langchain_core`, `langchain_openai` |
| `app.rag.loader` | 2 | 1 | `app.excel` | `langchain_community`, `langchain_core`, `pathlib` |
| `app.rag.pipeline` | 2 | 11 | `app.config`, `app.context_budget`, `app.conversation_models`, `app.conversation_repository`, `app.document_models`, `app.document_repository`, `app.history`, `app.query_rewriting`, `app.rag.llm`, `app.rag.prompt`, `app.rag.retriever` | `asyncio`, `collections`, `dataclasses`, `langchain_core`, `typing` |
| `app.rag.prompt` | 2 | 0 | — | `langchain_core` |
| `app.rag.retriever` | 1 | 5 | `app.config`, `app.document_repository`, `app.qdrant_ingestion`, `app.rag.embeddings`, `app.vector_index` | `langchain_core`, `pydantic`, `typing` |
| `app.rag.splitter` | 1 | 1 | `app.config` | `langchain_core`, `langchain_text_splitters` |
| `app.schemas` | 3 | 2 | `app.attachment_models`, `app.document_models` | `datetime`, `enum`, `pydantic`, `typing`, `uuid` |
| `app.sse_schema` | 1 | 1 | `app.schemas` | `pydantic`, `typing`, `uuid` |
| `app.storage` | 4 | 1 | `app.config` | `abc`, `contextlib`, `dataclasses`, `hashlib`, `os`, `pathlib`, `tempfile`, `typing`, `uuid` |
| `app.stream_metrics` | 1 | 0 | — | `collections`, `dataclasses`, `logging`, `time` |
| `app.tool_use` | 0 | 0 | — | — |
| `app.tool_use.contracts` | 3 | 0 | — | `dataclasses`, `json`, `pydantic`, `typing` |
| `app.tool_use.document_tools` | 1 | 3 | `app.document_queries`, `app.document_repository`, `app.tool_use.contracts` | `functools` |
| `app.tool_use.executor` | 1 | 1 | `app.tool_use.contracts` | `asyncio`, `collections`, `inspect`, `math`, `time`, `types` |
| `app.vector_index` | 5 | 0 | — | `abc`, `dataclasses`, `math`, `uuid` |

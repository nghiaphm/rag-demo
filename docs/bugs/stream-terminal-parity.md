# BUG-STREAM-001 — Whitespace-only error terminal differs from history

Detected by F7-03-05 on 2026-10-15. **FIXED in the explicitly user-authorized F7-03-05 continuation.** Original reproduction and equality assertion retained; no skip/xfail/waiver. Other QA/manual/security gates are separate.

Reproduce from project root using the existing Python environment. The guarded runner sets the backend import path and runs all selected suites, including the focused parity test:

```powershell
.venv/Scripts/python.exe backend/scripts/verify_frontend_functional_qa.py
```

The provider is a deterministic async fixture, repository is in memory, and the guarded runner rejects external TCP. No live Groq/Gemini, database or cloud ingestion is involved.

1. Begin a persistent turn with the real ConversationService.
2. The fixture yields one delta containing exactly `" \n\t "`, then raises a synthetic provider error.
3. The real SSE encoder finalizes the turn through the real service.
4. Compare terminal SSE status with the stored assistant record for the same IDs/content/error code.

Actual: SSE `error.status=PARTIAL`; persisted `MessageStatus.FAILED`. Exact content and error code agree, generation guard is released. Controls pass: non-whitespace content+error is PARTIAL in both; no delta+error is FAILED in both. The equality assertion is intentionally left **failing**, without skip/xfail or a changed expectation.

Cause: `backend/app/api/chat.py` selects PARTIAL using `emitted_delta`; `backend/app/conversation_service.py:finalize_streaming_turn` tests `content.strip()` when error_code is present. Transport and persistence disagree about a whitespace-only output.

Frontend impact: existing persisted-history verification detects the mismatch, preserves streamed whitespace and PARTIAL status, shows the recovery warning, releases loading and avoids automatic replay/canonical URL replacement. After an explicit history reload, the backend FAILED record is shown. This safe behavior is covered by `frontend/tests/functional-regression.test.mjs`; it does not resolve the server disagreement.

The paragraphs above record the original failing behavior. The original plan required a separately assigned bugfix; the user explicitly approved including the minimal fix and before/after regression in this QA continuation.

## Resolution and actual evidence

Existing `MessageRecord` validation permits PARTIAL/COMPLETED only with meaningful text (`content.strip()` nonempty). Keep that model/schema/persistence rule. In `backend/app/api/chat.py`, the encoder now classifies error status from the same meaningful-content rule instead of delta count. Normal provider completion with only whitespace is RAG_STREAM_EMPTY/FAILED before persistence. All emitted/stored characters, IDs, sequence, error code/usage and guard release are preserved; no database schema, REST/SSE shape or RAG retrieval/generation changes.

The frontend transcript validator previously inferred PARTIAL from any delta. It now permits FAILED after whitespace-only deltas, while still rejecting FAILED with meaningful text or PARTIAL before any delta. Its whitespace predicate is checked against the existing Python interpreter's complete `str.isspace()` set; NEL is whitespace, BOM remains content. The original legacy PARTIAL/history FAILED mismatch fixture still warns and does not replay/canonicalize. A matching FAILED/history FAILED fixture verifies exact text and canonical recovery without replay.

Before: baseline81 tests had1 parity failure; expanded84-test run had failing whitespace equality and normal-completion regressions. A first attempt to change persistence classification failed model validation and was fully reverted; `conversation_service.py` and models remain unchanged. Final encoder-side fix: **84/84 guarded backend tests PASS**, plus **67/67 guarded isolation/concurrency tests PASS**. These suites overlap and are not151 unique tests. Frontend **198/198 PASS**, including the unchanged original mismatch warning test and new matching-state/Unicode checks. No live provider calls.

The parity test now includes the original three cases and Unicode-whitespace, disconnect/cancel, and whitespace-only normal completion (6 test methods; Unicode subtests). It asserts exact content, terminal status/code, IDs, usage, sequence and guard release where applicable. The source equality assertion was not weakened.

# BUG-STREAM-001 — Whitespace-only error terminal differs from history

Detected by F7-03-05 on 2026-10-15. **OPEN / blocks the functional QA gate.** No application/backend fix or risk waiver has been applied.

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

Follow-up task: **BUGFIX — Stream terminal/persistence parity**, NOT STARTED. Choose one consistent rule compatible with the SSE contract; preserve exact content, IDs, usage/error and session-guard semantics. Do not trim deltas or special-case the frontend to conceal drift. Acceptance: all three parity cases and selected backend suites pass, frontend recovery/SSE/multi-turn regression remains green, and the known failure is removed by an implementation fix. F7-03-05 explicitly restricts backend semantic fixes to a separately assigned bugfix; no business logic is changed in this QA task.

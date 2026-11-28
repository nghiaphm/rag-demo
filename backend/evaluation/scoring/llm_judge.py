"""Custom LLM-as-a-Judge for RAGAS-inspired RAG evaluation metrics.

IMPORTANT TRANSPARENCY NOTE:
- This module implements a **RAGAS-inspired Custom LLM-as-a-Judge** (`CustomLlmJudge`).
- It does **NOT** wrap or claim to be the official `ragas` PyPI package.
- When a judge call fails or returns malformed JSON after `max_retries`, this judge
  raises `LlmJudgeError` explicitly so the caller records `score = None` (`judge_errors`)
  and NEVER silently backfills deterministic heuristic scores into an LLM-judge table.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from langchain_core.messages import HumanMessage, SystemMessage

if TYPE_CHECKING:
    from evaluation.scoring.ragas_metrics import RagasSample, RagasScore


_REQUIRED_METRIC_KEYS: tuple[str, ...] = (
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_relevancy",
)

_IN_SCOPE_SYSTEM_PROMPT = (
    "You are an objective evaluation judge for RAGAS-inspired custom metrics. "
    "Evaluate the assistant's answer strictly against the question, ground truth, and retrieved contexts. "
    "Return ONLY a valid JSON object with four float keys in [0.0, 1.0]: "
    '{"context_precision": 0.0, "context_recall": 0.0, "faithfulness": 0.0, "answer_relevancy": 0.0}.'
)

_REFUSAL_SYSTEM_PROMPT = (
    "You are an objective refusal evaluation judge for out-of-scope RAG questions. "
    "Determine whether the assistant properly stated that the uploaded documents do not contain "
    "the requested information WITHOUT fabricating unsupported external facts. "
    'Return ONLY a valid JSON object: {"correct_refusal": true} or {"correct_refusal": false}.'
)


class LlmJudgeError(RuntimeError):
    """Raised when CustomLlmJudge cannot obtain or parse a valid LLM judgment."""


def _extract_json_dict(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        raise LlmJudgeError("Empty response from CustomLlmJudge.")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LlmJudgeError("CustomLlmJudge response did not contain a JSON object.")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LlmJudgeError(f"Invalid JSON from CustomLlmJudge: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LlmJudgeError("CustomLlmJudge JSON root must be an object.")
    return parsed


def _parse_unit_float(payload: dict[str, Any], key: str) -> float:
    if key not in payload:
        raise LlmJudgeError(f"Missing required metric key '{key}' in CustomLlmJudge output.")
    raw_val = payload[key]
    if isinstance(raw_val, bool) or not isinstance(raw_val, (int, float)):
        raise LlmJudgeError(f"Metric '{key}' must be numeric, got {type(raw_val).__name__}.")
    val = float(raw_val)
    if val < 0.0 or val > 1.0:
        raise LlmJudgeError(f"Metric '{key}'={val} is outside [0.0, 1.0].")
    return round(val, 4)


class CustomLlmJudge:
    """RAGAS-inspired Custom LLM-as-a-Judge (never falls back to heuristics)."""

    scoring_method: str = "custom_llm_judge"

    def __init__(
        self,
        *,
        invoke_fn: Callable[[str], Any] | None = None,
        llm: Any = None,
        max_retries: int = 1,
    ) -> None:
        if invoke_fn is None and llm is None:
            raise ValueError("CustomLlmJudge requires either invoke_fn or llm.")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0.")
        self._invoke_fn = invoke_fn
        self._llm = llm
        self._max_retries = int(max_retries)

    def _call_model(self, system_prompt: str, user_prompt: str) -> str:
        if self._invoke_fn is not None:
            response = self._invoke_fn(f"{system_prompt}\n\n{user_prompt}")
        else:
            response = self._llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
        if isinstance(response, str):
            return response
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        return str(response)

    def score_sample(self, sample: RagasSample) -> RagasScore:
        """Judge an in-scope RAG sample; raises LlmJudgeError after retries."""
        from evaluation.scoring.ragas_metrics import RagasScore

        contexts_block = "\n---\n".join(sample.contexts) if sample.contexts else "(no retrieved context)"
        user_prompt = (
            f"Question: {sample.question}\n"
            f"Ground Truth: {sample.ground_truth or '(not provided)'}\n"
            f"Expected Facts: {list(sample.expected_facts)}\n"
            f"Retrieved Sources: {list(sample.retrieved_sources)}\n"
            f"Expected Sources: {list(sample.expected_sources)}\n"
            f"Retrieved Contexts:\n{contexts_block}\n\n"
            f"Generated Answer:\n{sample.answer}"
        )

        last_exc: Exception | None = None
        for _attempt in range(self._max_retries + 1):
            try:
                raw_text = self._call_model(_IN_SCOPE_SYSTEM_PROMPT, user_prompt)
                parsed = _extract_json_dict(raw_text)
                scores = {key: _parse_unit_float(parsed, key) for key in _REQUIRED_METRIC_KEYS}
                return RagasScore(
                    context_precision=scores["context_precision"],
                    context_recall=scores["context_recall"],
                    faithfulness=scores["faithfulness"],
                    answer_relevancy=scores["answer_relevancy"],
                )
            except Exception as exc:
                last_exc = exc

        raise LlmJudgeError(f"CustomLlmJudge failed after {self._max_retries + 1} attempt(s): {last_exc}") from last_exc

    def score_refusal(self, sample: RagasSample) -> bool:
        """Judge whether an out-of-scope sample was properly refused without hallucination."""
        user_prompt = (
            f"Out-of-scope Question: {sample.question}\n"
            f"Expected Behavior: {sample.ground_truth or 'Refuse because out of document scope.'}\n"
            f"Generated Answer:\n{sample.answer}"
        )

        last_exc: Exception | None = None
        for _attempt in range(self._max_retries + 1):
            try:
                raw_text = self._call_model(_REFUSAL_SYSTEM_PROMPT, user_prompt)
                parsed = _extract_json_dict(raw_text)
                verdict = parsed.get("correct_refusal")
                if not isinstance(verdict, bool):
                    raise LlmJudgeError("'correct_refusal' must be a boolean.")
                return verdict
            except Exception as exc:
                last_exc = exc

        raise LlmJudgeError(
            f"CustomLlmJudge refusal check failed after {self._max_retries + 1} attempt(s): {last_exc}"
        ) from last_exc

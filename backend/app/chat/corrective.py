"""Self-corrective Retrieval (Corrective RAG): Grading, Query Correction, Fallback & Evidence Evaluation."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from time import monotonic
from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage

from app.rag.web_search import WebSearchProvider
from app.shared.observability import NoOpTrace, TraceContext


_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+", flags=re.UNICODE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "are", "was", "were", "what", "when",
        "where", "which", "who", "how", "is", "in", "on", "at", "to", "of", "a", "an",
        "cua", "của", "va", "và", "la", "là", "cho", "trong", "duoc", "được", "mot", "một",
        "cac", "các", "voi", "với", "khi", "thi", "thì", "nay", "này", "do", "đó", "theo",
        "tu", "từ", "ra", "vao", "vào", "bao", "nhieu", "nhiêu", "gi", "gì", "nao", "nào",
        "dung", "dùng", "se", "sẽ", "de", "để", "tren", "trên", "hay", "khong", "không",
        "phai", "phải", "co", "có", "nhu", "như", "the", "thế", "tai", "tại", "sao",
    }
)


def _content_tokens(text: str) -> set[str]:
    return {
        tok
        for tok in _TOKEN_RE.findall((text or "").lower())
        if len(tok) > 1 and tok not in _STOPWORDS
    }


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


class RelevanceGrade(str, Enum):
    """Relevance assessment for retrieved candidate chunks."""

    RELEVANT = "RELEVANT"
    AMBIGUOUS = "AMBIGUOUS"
    IRRELEVANT = "IRRELEVANT"


@dataclass(frozen=True)
class RetrievalGradeResult:
    """Output of RetrievalGrader."""

    grade: RelevanceGrade
    relevant_indices: tuple[int, ...]
    reason: str
    confidence: float = 1.0


@dataclass(frozen=True)
class QueryCorrectionResult:
    """Output of QueryCorrector."""

    corrected_query: str
    reason: str


@dataclass(frozen=True)
class EvidenceEvaluationResult:
    """Output of post-generation EvidenceEvaluator."""

    grounded: bool
    support_ratio: float
    reason: str


@dataclass(frozen=True)
class CorrectiveOutcome:
    """Final result of running the self-corrective retrieval loop."""

    documents: list[Document]
    final_query: str
    grade: RelevanceGrade
    retries_used: int
    used_web_fallback: bool
    strict_fallback_triggered: bool
    tried_queries: tuple[str, ...]


class RetrievalGrader:
    """Grades whether retrieved documents are relevant to the user question."""

    def __init__(self, *, llm: Any = None, timeout_seconds: float = 8.0) -> None:
        self._llm = llm
        self._timeout_seconds = timeout_seconds

    def _heuristic_grade(
        self,
        question: str,
        documents: Sequence[Document],
    ) -> RetrievalGradeResult:
        if not documents:
            return RetrievalGradeResult(
                grade=RelevanceGrade.IRRELEVANT,
                relevant_indices=(),
                reason="No candidate documents retrieved.",
                confidence=1.0,
            )

        q_tokens = _content_tokens(question)
        if not q_tokens:
            return RetrievalGradeResult(
                grade=RelevanceGrade.AMBIGUOUS,
                relevant_indices=tuple(range(len(documents))),
                reason="Question has no distinctive content tokens.",
                confidence=0.5,
            )

        relevant_indices: list[int] = []
        best_ratio = 0.0
        for idx, doc in enumerate(documents):
            doc_tokens = _content_tokens(doc.page_content)
            overlap = len(q_tokens & doc_tokens)
            ratio = overlap / len(q_tokens)
            if ratio > best_ratio:
                best_ratio = ratio
            if overlap >= 2 or ratio >= 0.35:
                relevant_indices.append(idx)

        if relevant_indices:
            return RetrievalGradeResult(
                grade=RelevanceGrade.RELEVANT,
                relevant_indices=tuple(relevant_indices),
                reason=f"Matched {len(relevant_indices)} document(s) with overlap ratio {best_ratio:.2f}.",
                confidence=min(1.0, best_ratio),
            )
        if best_ratio > 0.0:
            return RetrievalGradeResult(
                grade=RelevanceGrade.AMBIGUOUS,
                relevant_indices=(0,),
                reason=f"Weak lexical overlap ({best_ratio:.2f}); treating as ambiguous.",
                confidence=best_ratio,
            )
        return RetrievalGradeResult(
            grade=RelevanceGrade.IRRELEVANT,
            relevant_indices=(),
            reason="Zero content overlap between question and retrieved documents.",
            confidence=0.9,
        )

    async def grade(
        self,
        question: str,
        documents: Sequence[Document],
    ) -> RetrievalGradeResult:
        """Assess document relevance using LLM if configured, else deterministic heuristic."""
        if not documents:
            return self._heuristic_grade(question, documents)

        if self._llm is None:
            return self._heuristic_grade(question, documents)

        snippets = "\n".join(
            f"[{idx}] {doc.page_content[:400]}"
            for idx, doc in enumerate(documents[:5])
        )
        messages = [
            SystemMessage(
                content=(
                    "You are a strict retrieval relevance grader. "
                    "Return JSON only: "
                    '{"grade":"RELEVANT|AMBIGUOUS|IRRELEVANT","relevant_indices":[0],"reason":"short reason"}.'
                )
            ),
            HumanMessage(content=f"Question: {question}\n\nDocuments:\n{snippets}"),
        ]
        try:
            response = await asyncio.wait_for(
                self._llm.ainvoke(messages),
                timeout=self._timeout_seconds,
            )
            raw = getattr(response, "content", "")
            parsed = _extract_json_object(raw if isinstance(raw, str) else str(raw))
            if parsed and str(parsed.get("grade", "")).upper() in RelevanceGrade.__members__:
                grade = RelevanceGrade[str(parsed["grade"]).upper()]
                indices_raw = parsed.get("relevant_indices") or []
                indices = tuple(
                    i for i in indices_raw if isinstance(i, int) and 0 <= i < len(documents)
                )
                return RetrievalGradeResult(
                    grade=grade,
                    relevant_indices=indices,
                    reason=str(parsed.get("reason") or "LLM graded"),
                    confidence=0.9,
                )
        except Exception:
            pass

        return self._heuristic_grade(question, documents)


class QueryCorrector:
    """Rewrites an unsuccessful retrieval query while avoiding previously tried queries."""

    def __init__(self, *, llm: Any = None, timeout_seconds: float = 8.0) -> None:
        self._llm = llm
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _normalize(query: str) -> str:
        return " ".join((query or "").lower().split())

    def _heuristic_correct(
        self,
        original_query: str,
        tried_queries: Sequence[str],
    ) -> QueryCorrectionResult:
        tried_norm = {self._normalize(q) for q in tried_queries}
        tokens = [
            tok
            for tok in _TOKEN_RE.findall((original_query or "").lower())
            if tok not in _STOPWORDS
        ]
        candidate = " ".join(dict.fromkeys(tokens)) if tokens else original_query.strip()
        if not candidate or self._normalize(candidate) in tried_norm:
            candidate = f"{candidate} details specification".strip()
        return QueryCorrectionResult(
            corrected_query=candidate,
            reason="Extracted key content terms for retry retrieval.",
        )

    async def correct(
        self,
        original_query: str,
        tried_queries: Sequence[str],
        *,
        reason: str = "",
    ) -> QueryCorrectionResult:
        """Produce a novel, refined retrieval query."""
        tried_norm = {self._normalize(q) for q in tried_queries}
        if self._llm is not None:
            messages = [
                SystemMessage(
                    content=(
                        "Rewrite the user query into a concise keyword-rich search query "
                        "to improve document retrieval. Do not repeat any previously tried query. "
                        "Return only the rewritten query text."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Original question: {original_query}\n"
                        f"Previously tried queries: {list(tried_queries)}\n"
                        f"Failure reason: {reason}"
                    )
                ),
            ]
            try:
                response = await asyncio.wait_for(
                    self._llm.ainvoke(messages),
                    timeout=self._timeout_seconds,
                )
                raw = getattr(response, "content", "")
                rewritten = (raw if isinstance(raw, str) else str(raw)).strip()
                if rewritten and self._normalize(rewritten) not in tried_norm:
                    return QueryCorrectionResult(
                        corrected_query=rewritten,
                        reason="LLM-refined query for corrective retrieval.",
                    )
            except Exception:
                pass

        return self._heuristic_correct(original_query, tried_queries)


class EvidenceEvaluator:
    """Post-generation groundedness check against retrieved context documents."""

    def __init__(self, *, llm: Any = None, timeout_seconds: float = 8.0) -> None:
        self._llm = llm
        self._timeout_seconds = timeout_seconds

    def _heuristic_evaluate(
        self,
        answer: str,
        documents: Sequence[Document],
    ) -> EvidenceEvaluationResult:
        claims = [c.strip() for c in _SENTENCE_SPLIT_RE.split(answer or "") if c.strip()]
        if not claims:
            return EvidenceEvaluationResult(grounded=False, support_ratio=0.0, reason="Empty answer.")
        if not documents:
            return EvidenceEvaluationResult(
                grounded=False,
                support_ratio=0.0,
                reason="No supporting documents available.",
            )

        ctx_tokens = _content_tokens(" ".join(doc.page_content for doc in documents))
        if not ctx_tokens:
            return EvidenceEvaluationResult(
                grounded=False,
                support_ratio=0.0,
                reason="Supporting documents contain no indexable tokens.",
            )

        supported = 0
        for claim in claims:
            claim_tokens = _content_tokens(claim)
            if not claim_tokens:
                supported += 1
                continue
            if (len(claim_tokens & ctx_tokens) / len(claim_tokens)) >= 0.4:
                supported += 1

        ratio = round(supported / len(claims), 4)
        return EvidenceEvaluationResult(
            grounded=ratio >= 0.5,
            support_ratio=ratio,
            reason=f"{supported}/{len(claims)} answer claim(s) grounded in context.",
        )

    async def evaluate(
        self,
        question: str,
        answer: str,
        documents: Sequence[Document],
    ) -> EvidenceEvaluationResult:
        """Verify whether the generated answer is supported by retrieved documents."""
        if self._llm is None:
            return self._heuristic_evaluate(answer, documents)

        ctx = "\n".join(doc.page_content[:400] for doc in documents[:5])
        messages = [
            SystemMessage(
                content=(
                    "Check if the answer is fully supported by the context. "
                    'Return JSON only: {"grounded": true, "support_ratio": 1.0, "reason": "..."}.'
                )
            ),
            HumanMessage(content=f"Question: {question}\nContext:\n{ctx}\nAnswer:\n{answer}"),
        ]
        try:
            response = await asyncio.wait_for(
                self._llm.ainvoke(messages),
                timeout=self._timeout_seconds,
            )
            raw = getattr(response, "content", "")
            parsed = _extract_json_object(raw if isinstance(raw, str) else str(raw))
            if parsed and isinstance(parsed.get("grounded"), bool):
                return EvidenceEvaluationResult(
                    grounded=bool(parsed["grounded"]),
                    support_ratio=float(parsed.get("support_ratio", 1.0 if parsed["grounded"] else 0.0)),
                    reason=str(parsed.get("reason") or "LLM evidence evaluation"),
                )
        except Exception:
            pass

        return self._heuristic_evaluate(answer, documents)


class CorrectiveRagRunner:
    """Executes grade -> correct -> re-retrieve -> fallback loop within retry/deadline bounds."""

    def __init__(
        self,
        *,
        grader: RetrievalGrader | None = None,
        corrector: QueryCorrector | None = None,
        web_search_provider: WebSearchProvider | None = None,
        max_retries: int = 1,
    ) -> None:
        self.grader = grader or RetrievalGrader()
        self.corrector = corrector or QueryCorrector()
        self.web_search_provider = web_search_provider
        self.max_retries = max(0, max_retries)

    async def run(
        self,
        *,
        question: str,
        initial_query: str,
        initial_documents: list[Document],
        retrieve_and_rerank: Callable[[str], Awaitable[list[Document]]],
        trace: TraceContext | None = None,
        deadline: float | None = None,
        on_status: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> CorrectiveOutcome:
        active_trace = trace or NoOpTrace()
        tried_queries: list[str] = [initial_query]
        current_query = initial_query
        current_docs = list(initial_documents)
        retries_used = 0

        if on_status is not None:
            await on_status("retrieval_grade", "Đang đánh giá độ phù hợp của tài liệu...")

        with active_trace.span("retrieval_grade", input={"query": current_query, "doc_count": len(current_docs)}) as span:
            grade_result = await self.grader.grade(question, current_docs)
            span.set_output({"grade": grade_result.grade.value, "reason": grade_result.reason})

        while (
            grade_result.grade is RelevanceGrade.IRRELEVANT
            and retries_used < self.max_retries
            and (deadline is None or monotonic() < deadline)
        ):
            if on_status is not None:
                await on_status("query_correction", "Tài liệu chưa sát câu hỏi, đang tối ưu lại truy vấn...")

            with active_trace.span("query_correction", input={"tried": list(tried_queries)}) as span:
                correction = await self.corrector.correct(
                    question,
                    tried_queries,
                    reason=grade_result.reason,
                )
                span.set_output({"corrected_query": correction.corrected_query})

            if correction.corrected_query.strip().lower() in {q.strip().lower() for q in tried_queries}:
                break

            retries_used += 1
            current_query = correction.corrected_query
            tried_queries.append(current_query)

            current_docs = await retrieve_and_rerank(current_query)
            with active_trace.span(
                "retrieval_grade_retry",
                input={"attempt": retries_used, "query": current_query, "doc_count": len(current_docs)},
            ) as span:
                grade_result = await self.grader.grade(question, current_docs)
                span.set_output({"grade": grade_result.grade.value, "reason": grade_result.reason})

        if grade_result.grade is RelevanceGrade.RELEVANT and grade_result.relevant_indices:
            filtered = [current_docs[i] for i in grade_result.relevant_indices if i < len(current_docs)]
            if filtered:
                current_docs = filtered

        used_web_fallback = False
        strict_fallback_triggered = False
        if grade_result.grade is RelevanceGrade.IRRELEVANT or not current_docs:
            if self.web_search_provider is not None and (deadline is None or monotonic() < deadline):
                if on_status is not None:
                    await on_status("web_fallback", "Đang tìm kiếm bổ sung từ nguồn web...")
                with active_trace.span("web_search_fallback", input={"query": current_query}) as span:
                    web_docs = await self.web_search_provider.search(current_query)
                    span.set_output({"web_doc_count": len(web_docs)})
                if web_docs:
                    current_docs = web_docs
                    used_web_fallback = True
                else:
                    current_docs = []
                    strict_fallback_triggered = True
            else:
                current_docs = []
                strict_fallback_triggered = True

        return CorrectiveOutcome(
            documents=current_docs,
            final_query=current_query,
            grade=grade_result.grade,
            retries_used=retries_used,
            used_web_fallback=used_web_fallback,
            strict_fallback_triggered=strict_fallback_triggered,
            tried_queries=tuple(tried_queries),
        )

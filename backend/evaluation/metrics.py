"""Metric deterministic cho evaluation RAG (không gọi API, reproducible).

Đây là các heuristic đơn giản:
- retrieval: so khớp source file_name retrieve được với expected source;
- answer: coverage của expected facts trong câu trả lời;
- faithfulness: tỉ lệ token nội dung của answer xuất hiện trong retrieved context.

Không phải ground-truth tuyệt đối; dùng làm baseline để so sánh cấu hình.
"""

import re

_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "are", "was", "were",
        "cua", "của", "va", "và", "la", "là", "cho", "trong", "duoc", "được",
        "mot", "một", "cac", "các", "voi", "với", "khi", "thi", "thì", "nay",
        "này", "do", "đó", "theo", "tu", "từ", "ra", "vao", "vào", "bao",
        "nhieu", "nhiêu", "gi", "gì", "nao", "nào", "dung", "dùng", "se", "sẽ",
        "de", "để", "tren", "trên", "hay", "hoac", "hoặc", "khong", "không",
        "phai", "phải", "co", "có", "nhat", "nhất", "dong", "đồng", "binh",
        "thuong", "thường",
    }
)

_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+", flags=re.UNICODE)


def fact_present(fact: str, text: str) -> bool:
    """Kiểm tra `fact` xuất hiện trong `text` như một token/mệnh đề độc lập.

    Dùng word-boundary để `50` không khớp nhầm trong `500`.
    """
    pattern = r"(?<!\w)" + re.escape(fact) + r"(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def answer_fact_coverage(answer: str, expected_facts: list[str]) -> float:
    """Tỉ lệ expected facts có mặt trong answer (1.0 nếu không yêu cầu fact nào)."""
    if not expected_facts:
        return 1.0
    hits = sum(1 for fact in expected_facts if fact_present(fact, answer))
    return hits / len(expected_facts)


def retrieval_metrics(
    retrieved_sources: list[str | None],
    expected_sources: list[str],
) -> dict:
    """Đo retrieval dựa trên tập source file_name.

    Returns:
        dict gồm `retrieval_hit` (bool | None) và `retrieval_recall` (float | None).
        None nếu case không có expected source (case ngoài tài liệu).
    """
    expected = {source for source in expected_sources if source}
    if not expected:
        return {"retrieval_hit": None, "retrieval_recall": None}

    retrieved = {source for source in retrieved_sources if source}
    matched = retrieved & expected
    return {
        "retrieval_hit": len(matched) > 0,
        "retrieval_recall": len(matched) / len(expected),
    }


def _content_tokens(text: str) -> set[str]:
    """Tách token để đo overlap: giữ mọi số (16, 50, 0.8.6) và từ dài >= 4 ký tự."""
    tokens: set[str] = set()
    for raw in _TOKEN_RE.findall(text.lower()):
        if any(char.isdigit() for char in raw):
            tokens.add(raw)
        elif len(raw) >= 4 and raw not in _STOPWORDS:
            tokens.add(raw)
    return tokens


def faithfulness_ratio(answer: str, context: str) -> float:
    """Tỉ lệ token nội dung của answer xuất hiện trong retrieved context.

    Nếu answer không có token nội dung nào (ví dụ chỉ gồm từ ngắn) thì trả 1.0
    thay vì 0.0 để tránh đánh giá sai các câu trả lời ngắn nhưng hợp lệ.
    """
    answer_tokens = _content_tokens(answer)
    if not answer_tokens:
        return 1.0
    context_tokens = _content_tokens(context)
    return len(answer_tokens & context_tokens) / len(answer_tokens)

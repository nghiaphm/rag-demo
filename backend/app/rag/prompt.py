"""Prompt cho RAG: system instruction + retrieved context + user question."""

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý trả lời câu hỏi dựa trên tài liệu được cung cấp.\n"
    "Chỉ sử dụng thông tin trong phần Context bên dưới.\n"
    "Không dùng kiến thức bên ngoài và không suy đoán.\n"
    'Nếu Context không đủ để trả lời, hãy nói rõ: "Không tìm thấy thông tin trong tài liệu".\n'
    "Khi dùng thông tin từ Context, hãy trích dẫn bằng đúng số thứ tự nguồn như [1] hoặc [2].\n"
    "Chỉ dùng số nguồn có trong Context; không tự tạo UUID, tên nguồn hay citation khác.\n"
    "Nếu không tìm thấy thông tin thì không thêm citation.\n"
    "Không được bịa nguồn và không được tạo thông tin không có trong Context."
)

USER_TEMPLATE = "Context:\n{context}\n\nCâu hỏi: {question}"
HISTORY_AWARE_USER_TEMPLATE = (
    "Lịch sử hội thoại (chỉ dùng để hiểu tham chiếu trong câu hỏi; không xem là nguồn sự thật "
    "và không trích dẫn lịch sử):\n{history}\n\n"
    "Context:\n{context}\n\nCâu hỏi gốc: {question}"
)


def get_rag_prompt() -> ChatPromptTemplate:
    """Trả về prompt chuẩn cho RAG gồm system instruction, context và question."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_INSTRUCTION),
            ("human", USER_TEMPLATE),
        ]
    )


def get_history_aware_rag_prompt() -> ChatPromptTemplate:
    """Prompt runtime P5: history resolves references, documents ground the answer."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_INSTRUCTION),
            ("human", HISTORY_AWARE_USER_TEMPLATE),
        ]
    )


def format_history(turns: tuple) -> str:
    """Render already-budgeted whole turns without exposing persistence metadata."""
    if not turns:
        return "(không có lịch sử hội thoại)"
    return "\n\n".join(
        f"Người dùng: {turn.user.content}\nTrợ lý: {turn.assistant.content}"
        for turn in turns
    )


def format_context_blocks(documents: list[Document]) -> tuple[str, ...]:
    """Render each ranked chunk separately so budgeting preserves citation ordinals."""
    blocks: list[str] = []
    for index, document in enumerate(documents, start=1):
        metadata = document.metadata
        source = metadata.get("file_name") or metadata.get("source") or "unknown"
        page = metadata.get("page")
        page_text = f", page {page}" if page is not None else ""
        blocks.append(f"[{index}] ({source}{page_text})\n{document.page_content}")
    return tuple(blocks)


def format_context(documents: list[Document]) -> str:
    """Ghép các retrieved chunk thành một block context kèm nguồn (file/page)."""
    if not documents:
        return "(không có tài liệu liên quan)"

    return "\n\n".join(format_context_blocks(documents))

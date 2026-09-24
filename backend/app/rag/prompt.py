"""Prompt cho RAG: system instruction + retrieved context + user question."""

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý trả lời câu hỏi dựa trên tài liệu được cung cấp.\n"
    "Chỉ sử dụng thông tin trong phần Context bên dưới.\n"
    "Không dùng kiến thức bên ngoài và không suy đoán.\n"
    'Nếu Context không đủ để trả lời, hãy nói rõ: "Không tìm thấy thông tin trong tài liệu".\n'
    "Không được bịa nguồn và không được tạo thông tin không có trong Context."
)

USER_TEMPLATE = "Context:\n{context}\n\nCâu hỏi: {question}"


def get_rag_prompt() -> ChatPromptTemplate:
    """Trả về prompt chuẩn cho RAG gồm system instruction, context và question."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_INSTRUCTION),
            ("human", USER_TEMPLATE),
        ]
    )


def format_context(documents: list[Document]) -> str:
    """Ghép các retrieved chunk thành một block context kèm nguồn (file/page)."""
    if not documents:
        return "(không có tài liệu liên quan)"

    blocks: list[str] = []
    for index, document in enumerate(documents, start=1):
        metadata = document.metadata
        source = metadata.get("file_name") or metadata.get("source") or "unknown"
        page = metadata.get("page")
        page_text = f", page {page}" if page is not None else ""
        blocks.append(f"[{index}] ({source}{page_text})\n{document.page_content}")
    return "\n\n".join(blocks)

"""RAG chain: question -> retrieve top-k -> prompt -> configured Groq LLM -> answer."""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import (
    Runnable,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)

from app.rag.llm import get_llm
from app.rag.prompt import format_context, get_rag_prompt


def _to_prompt_inputs(payload: dict) -> dict:
    """Chuyển payload {question, documents} thành input cho prompt {context, question}."""
    return {
        "context": format_context(payload["documents"]),
        "question": payload["question"],
    }


def build_rag_chain(
    retriever: BaseRetriever,
    llm: BaseChatModel | None = None,
    prompt: ChatPromptTemplate | None = None,
) -> Runnable:
    """Build RAG chain bằng LCEL.

    Input: câu hỏi dạng `str`.

    Output: `dict` gồm:
        - `question`: câu hỏi gốc
        - `documents`: danh sách `Document` đã retrieve (source cho Phase 4)
        - `answer`: câu trả lời của LLM
    """
    resolved_llm = llm if llm is not None else get_llm()
    resolved_prompt = prompt if prompt is not None else get_rag_prompt()

    answer_chain = (
        RunnableLambda(_to_prompt_inputs)
        | resolved_prompt
        | resolved_llm
        | StrOutputParser()
    )

    return RunnableParallel(
        documents=retriever,
        question=RunnablePassthrough(),
    ) | RunnablePassthrough.assign(answer=answer_chain)

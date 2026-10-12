"""Read-only P4-02 Groq async-stream smoke without retrieval or persistence writes."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.rag.pipeline import PreparedRagStream, astream_rag_answer
from app.rag.prompt import get_rag_prompt


async def _run() -> tuple[int, bool]:
    prompt_value = get_rag_prompt().invoke(
        {
            "context": "[1] (smoke.md)\nP4-02 async streaming is enabled.",
            "question": "Trả lời ngắn gọn bằng một câu tiếng Việt.",
        }
    )
    prepared = PreparedRagStream(prompt_value=prompt_value, sources=[])
    text_parts: list[str] = []
    usage_available = False
    async for chunk in astream_rag_answer(prepared):
        if chunk.content is not None:
            text_parts.append(chunk.content)
        usage_available = usage_available or chunk.usage is not None
    if not "".join(text_parts).strip():
        raise RuntimeError("provider emitted no valid text delta")
    return len(text_parts), usage_available


def main() -> int:
    try:
        count, usage_available = asyncio.run(asyncio.wait_for(_run(), timeout=60))
    except Exception as exc:  # noqa: BLE001 - do not expose provider response or credentials
        print(f"BLOCKED: Groq async stream unavailable ({type(exc).__name__}); secrets không được in.")
        return 2
    print(
        "PASS: Groq/LangChain async stream emitted "
        f"{count} valid text delta(s); usage_metadata={'present' if usage_available else 'absent'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

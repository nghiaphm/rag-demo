"""P4-02 LangChain provider chunk normalization tests."""

import asyncio
import unittest
from types import SimpleNamespace

from app.rag.pipeline import (
    PreparedRagStream,
    ProviderStreamChunk,
    _text_delta,
    _usage_from_chunk,
    astream_rag_answer,
)


class FakeStreamingModel:
    def __init__(self, chunks):
        self.chunks = chunks
        self.inputs = []

    async def astream(self, prompt_value):
        self.inputs.append(prompt_value)
        for chunk in self.chunks:
            yield chunk


class StreamingPipelineTests(unittest.TestCase):
    def test_text_normalizer_ignores_non_text_and_keeps_text_blocks(self):
        self.assertEqual(_text_delta(SimpleNamespace(content="Xin")), "Xin")
        self.assertEqual(
            _text_delta(
                SimpleNamespace(
                    content=[{"type": "text", "text": "Xin "}, {"text": "chào"}]
                )
            ),
            "Xin chào",
        )
        self.assertIsNone(_text_delta(SimpleNamespace(content=[])))
        self.assertIsNone(_text_delta(SimpleNamespace(content={"tool_call": "x"})))
        self.assertIsNone(_text_delta(SimpleNamespace(content="")))

    def test_usage_normalizer_supports_langchain_and_openai_names(self):
        self.assertEqual(
            _usage_from_chunk(
                SimpleNamespace(
                    usage_metadata={
                        "input_tokens": 4,
                        "output_tokens": 2,
                        "total_tokens": 6,
                    },
                    response_metadata={},
                )
            ),
            {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
        )
        self.assertEqual(
            _usage_from_chunk(
                SimpleNamespace(
                    usage_metadata=None,
                    response_metadata={
                        "usage": {"prompt_tokens": 5, "completion_tokens": 3}
                    },
                )
            ),
            {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
        )
        self.assertIsNone(
            _usage_from_chunk(
                SimpleNamespace(usage_metadata={"input_tokens": -1}, response_metadata={})
            )
        )

    def test_astream_preserves_usage_on_textless_final_chunk(self):
        prompt = object()
        model = FakeStreamingModel(
            [
                SimpleNamespace(content="Xin ", usage_metadata=None, response_metadata={}),
                SimpleNamespace(content=[], usage_metadata=None, response_metadata={}),
                SimpleNamespace(
                    content="chào",
                    usage_metadata={
                        "input_tokens": 5,
                        "output_tokens": 2,
                        "total_tokens": 7,
                    },
                    response_metadata={},
                ),
            ]
        )
        prepared = PreparedRagStream(prompt_value=prompt, sources=[])

        async def collect() -> list[ProviderStreamChunk]:
            return [chunk async for chunk in astream_rag_answer(prepared, llm=model)]

        chunks = asyncio.run(collect())
        self.assertEqual(model.inputs, [prompt])
        self.assertEqual([chunk.content for chunk in chunks], ["Xin ", None, "chào"])
        self.assertEqual(chunks[-1].usage["total_tokens"], 7)


if __name__ == "__main__":
    unittest.main()

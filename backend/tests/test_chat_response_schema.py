"""P3-01 tests for the provider/transport-neutral JSON response contract."""

import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.schemas import (
    Citation,
    ChatError,
    ChatResponse,
    ChatResponseMetadata,
    ChatResponseMode,
    ChatResponseStatus,
    ChatUsage,
)


class ChatResponseSchemaTests(unittest.TestCase):
    @staticmethod
    def stateless_values() -> dict:
        return {
            "request_id": uuid4(),
            "session_id": None,
            "user_message_id": None,
            "assistant_message_id": None,
            "answer": "Grounded answer",
            "sources": [],
            "citations": [],
            "metadata": ChatResponseMetadata(
                mode=ChatResponseMode.STATELESS,
                model=None,
            ),
            "usage": None,
            "status": ChatResponseStatus.COMPLETED,
            "error": None,
        }

    def test_all_top_level_fields_are_required_even_when_nullable(self):
        schema = ChatResponse.model_json_schema()
        self.assertEqual(
            set(schema["required"]),
            {
                "request_id",
                "session_id",
                "user_message_id",
                "assistant_message_id",
                "answer",
                "sources",
                "citations",
                "metadata",
                "usage",
                "status",
                "error",
            },
        )

    def test_stateless_completed_serializes_explicit_nulls_and_empty_arrays(self):
        payload = ChatResponse(**self.stateless_values()).model_dump(mode="json")
        self.assertIsNone(payload["session_id"])
        self.assertIsNone(payload["user_message_id"])
        self.assertIsNone(payload["assistant_message_id"])
        self.assertIsNone(payload["usage"])
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["sources"], [])
        self.assertEqual(payload["citations"], [])

    def test_persistent_response_requires_session_and_both_message_ids(self):
        values = self.stateless_values()
        values["metadata"] = ChatResponseMetadata(
            mode=ChatResponseMode.PERSISTENT,
            model="provider/model",
        )
        with self.assertRaises(ValidationError):
            ChatResponse(**values)

        values.update(
            session_id=uuid4(),
            user_message_id=uuid4(),
            assistant_message_id=uuid4(),
        )
        response = ChatResponse(**values)
        self.assertEqual(response.status, ChatResponseStatus.COMPLETED)

    def test_completed_requires_answer_and_null_error(self):
        for answer, error in (
            (None, None),
            ("   ", None),
            ("answer", ChatError(code="UNEXPECTED", message="safe")),
        ):
            values = self.stateless_values()
            values.update(answer=answer, error=error)
            with self.assertRaises(ValidationError):
                ChatResponse(**values)

    def test_failed_requires_safe_error(self):
        values = self.stateless_values()
        values.update(answer=None, status=ChatResponseStatus.FAILED)
        with self.assertRaises(ValidationError):
            ChatResponse(**values)

        values["error"] = ChatError(
            code="RAG_PIPELINE_ERROR",
            message="Không thể tạo câu trả lời.",
            retryable=True,
        )
        failed = ChatResponse(**values)
        self.assertIsNone(failed.answer)
        self.assertEqual(failed.error.code, "RAG_PIPELINE_ERROR")

    def test_usage_is_nullable_but_validated_when_present(self):
        values = self.stateless_values()
        values["usage"] = ChatUsage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )
        self.assertEqual(ChatResponse(**values).usage.total_tokens, 15)
        with self.assertRaises(ValidationError):
            ChatUsage(input_tokens=10, output_tokens=5, total_tokens=14)

    def test_citation_must_be_a_member_of_retrieved_sources(self):
        values = self.stateless_values()
        citation = Citation(
            chunk_id=uuid4(),
            document_id=uuid4(),
            version_id=uuid4(),
            page=2,
        )
        values["citations"] = [citation]
        with self.assertRaises(ValidationError):
            ChatResponse(**values)

        values["sources"] = [
            {
                "chunk_id": str(citation.chunk_id),
                "document_id": str(citation.document_id),
                "version_id": str(citation.version_id),
                "page": 2,
            }
        ]
        self.assertEqual(len(ChatResponse(**values).citations), 1)


if __name__ == "__main__":
    unittest.main()

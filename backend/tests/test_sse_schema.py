"""P3-03 SSE event schema, ordering, terminal and reconstruction tests."""

import json
import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.schemas import ChatError, ChatResponseMode, Citation
from app.sse_schema import (
    SSECitationData,
    SSECitationEvent,
    SSEDeltaData,
    SSEDeltaEvent,
    SSEDoneData,
    SSEDoneEvent,
    SSEErrorData,
    SSEErrorEvent,
    SSEMetadataData,
    SSEMetadataEvent,
    SSEStartData,
    SSEStartEvent,
    SSETranscript,
    encode_sse_event,
)


class SSESchemaTests(unittest.TestCase):
    def setUp(self):
        self.session_id = uuid4()
        self.user_message_id = uuid4()
        self.assistant_message_id = uuid4()
        self.request_id = uuid4()
        self.citation = Citation(
            chunk_id=uuid4(),
            document_id=uuid4(),
            version_id=uuid4(),
            file_name="guide.md",
            page=2,
        )
        self.source = {
            "chunk_id": str(self.citation.chunk_id),
            "document_id": str(self.citation.document_id),
            "version_id": str(self.citation.version_id),
            "file_name": "guide.md",
            "page": 2,
        }

    def start(self, sequence=1):
        return SSEStartEvent(
            data=SSEStartData(
                sequence=sequence,
                request_id=self.request_id,
                session_id=self.session_id,
                user_message_id=self.user_message_id,
                assistant_message_id=self.assistant_message_id,
                mode=ChatResponseMode.PERSISTENT,
            )
        )

    def metadata(self, sequence=2):
        return SSEMetadataEvent(
            data=SSEMetadataData(
                sequence=sequence,
                model="provider/model",
                sources=[self.source],
            )
        )

    def citation_event(self, sequence=3, citation=None):
        return SSECitationEvent(
            data=SSECitationData(
                sequence=sequence,
                citation=citation or self.citation,
            )
        )

    @staticmethod
    def delta(sequence, content):
        return SSEDeltaEvent(data=SSEDeltaData(sequence=sequence, content=content))

    @staticmethod
    def done(sequence):
        return SSEDoneEvent(data=SSEDoneData(sequence=sequence, usage=None))

    @staticmethod
    def error(sequence, status):
        return SSEErrorEvent(
            data=SSEErrorData(
                sequence=sequence,
                status=status,
                error=ChatError(code="PROVIDER_ERROR", message="Safe error"),
                usage=None,
            )
        )

    def test_valid_success_order_and_client_reconstruction(self):
        transcript = SSETranscript(
            events=[
                self.start(),
                self.metadata(),
                self.citation_event(),
                self.delta(4, "Xin "),
                self.delta(5, "chào"),
                self.done(6),
            ]
        )
        self.assertEqual(transcript.reconstructed_answer, "Xin chào")
        start = transcript.events[0].data
        self.assertEqual(start.assistant_message_id, self.assistant_message_id)

    def test_stateless_start_requires_explicit_null_ids(self):
        start = SSEStartData(
            sequence=1,
            request_id=uuid4(),
            session_id=None,
            user_message_id=None,
            assistant_message_id=None,
            mode=ChatResponseMode.STATELESS,
        )
        self.assertIsNone(start.assistant_message_id)
        with self.assertRaises(ValidationError):
            SSEStartData(
                sequence=1,
                request_id=uuid4(),
                session_id=uuid4(),
                user_message_id=None,
                assistant_message_id=None,
                mode=ChatResponseMode.STATELESS,
            )

    def test_failure_before_metadata_and_partial_after_delta(self):
        failed = SSETranscript(events=[self.start(), self.error(2, "FAILED")])
        self.assertEqual(failed.reconstructed_answer, "")
        partial = SSETranscript(
            events=[
                self.start(),
                self.metadata(),
                self.delta(3, "partial"),
                self.error(4, "PARTIAL"),
            ]
        )
        self.assertEqual(partial.reconstructed_answer, "partial")

    def test_terminal_status_must_match_delta_presence(self):
        with self.assertRaises(ValidationError):
            SSETranscript(events=[self.start(), self.error(2, "PARTIAL")])
        with self.assertRaises(ValidationError):
            SSETranscript(
                events=[
                    self.start(),
                    self.metadata(),
                    self.delta(3, "partial"),
                    self.error(4, "FAILED"),
                ]
            )
        with self.assertRaises(ValidationError):
            SSETranscript(events=[self.start(), self.metadata(), self.done(3)])

    def test_order_sequence_and_single_terminal_are_enforced(self):
        invalid_transcripts = [
            [self.metadata(1), self.start(2), self.done(3)],
            [self.start(), self.metadata(3), self.delta(4, "x"), self.done(5)],
            [self.start(), self.metadata(), self.delta(3, "x")],
            [self.start(), self.metadata(), self.delta(3, "x"), self.done(4), self.error(5, "PARTIAL")],
            [self.start(), self.metadata(), self.delta(3, "x"), self.citation_event(4), self.done(5)],
        ]
        for events in invalid_transcripts:
            with self.subTest(events=[event.event for event in events]):
                with self.assertRaises(ValidationError):
                    SSETranscript(events=events)

    def test_citation_must_match_metadata_source_and_be_unique(self):
        other = Citation(
            chunk_id=uuid4(),
            document_id=uuid4(),
            version_id=uuid4(),
            page=0,
        )
        with self.assertRaises(ValidationError):
            SSETranscript(
                events=[
                    self.start(),
                    self.metadata(),
                    self.citation_event(citation=other),
                    self.delta(4, "answer"),
                    self.done(5),
                ]
            )
        with self.assertRaises(ValidationError):
            SSETranscript(
                events=[
                    self.start(),
                    self.metadata(),
                    self.citation_event(),
                    self.citation_event(sequence=4),
                    self.delta(5, "answer"),
                    self.done(6),
                ]
            )

    def test_wire_encoding_uses_event_and_json_data_frames(self):
        encoded = encode_sse_event(self.start())
        self.assertTrue(encoded.startswith("event: start\ndata: "))
        self.assertTrue(encoded.endswith("\n\n"))
        data_line = encoded.splitlines()[1]
        payload = json.loads(data_line.removeprefix("data: "))
        self.assertEqual(payload["sequence"], 1)
        self.assertEqual(payload["assistant_message_id"], str(self.assistant_message_id))


if __name__ == "__main__":
    unittest.main()

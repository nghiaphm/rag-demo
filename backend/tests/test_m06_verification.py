"""Deterministic tests for the M-06 live verifier's contract assertions."""

import json
import unittest
from uuid import uuid4

from scripts.verify_m06 import (
    _assert_citation,
    _assert_scoped_sources,
    _events,
)


class M06VerificationTests(unittest.TestCase):
    def setUp(self):
        self.document_id = str(uuid4())
        self.version_id = str(uuid4())
        self.source = {
            "chunk_id": str(uuid4()),
            "document_id": self.document_id,
            "version_id": self.version_id,
            "page": 2,
        }

    def test_sse_parser_preserves_event_names_and_json_data(self):
        body = (
            'event: start\ndata: {"sequence":1}\n\n'
            'event: done\ndata: {"sequence":2,"status":"COMPLETED"}\n\n'
        )
        self.assertEqual(
            _events(body),
            [
                ("start", {"sequence": 1}),
                ("done", {"sequence": 2, "status": "COMPLETED"}),
            ],
        )
        with self.assertRaises((RuntimeError, json.JSONDecodeError)):
            _events("event: delta\ndata: not-json")

    def test_scope_assertion_rejects_wrong_document_or_version(self):
        _assert_scoped_sources(
            [self.source],
            document_id=self.document_id,
            version_id=self.version_id,
        )
        wrong = {**self.source, "document_id": str(uuid4())}
        with self.assertRaises(RuntimeError):
            _assert_scoped_sources(
                [wrong],
                document_id=self.document_id,
                version_id=self.version_id,
            )

    def test_citation_assertion_requires_exact_server_source_provenance(self):
        citation = {
            field: self.source[field]
            for field in ("chunk_id", "document_id", "version_id", "page")
        }
        _assert_citation([citation], self.source)
        with self.assertRaises(RuntimeError):
            _assert_citation([{**citation, "page": 3}], self.source)


if __name__ == "__main__":
    unittest.main()

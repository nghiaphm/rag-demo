"""Unit tests cho P1-03 models và MongoDB index contract."""

import unittest
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError

from app.document_indexes import (
    DOCUMENT_INDEXES,
    DOCUMENT_VERSION_INDEXES,
    INDEX_DEFINITIONS,
    initialize_document_indexes,
)
from app.document_models import (
    DocumentRecord,
    DocumentStatus,
    DocumentVersionRecord,
    IngestionJobRecord,
)

VALID_CHECKSUM = "a" * 64


class DocumentModelTests(unittest.TestCase):
    def test_ids_are_independent_uuid4_values_even_for_same_filename(self):
        first = DocumentRecord(file_name="same.pdf")
        second = DocumentRecord(file_name="same.pdf")
        self.assertNotEqual(first.document_id, second.document_id)
        self.assertEqual(UUID(first.document_id).version, 4)
        self.assertEqual(UUID(second.document_id).version, 4)

    def test_active_version_defaults_to_none(self):
        self.assertIsNone(DocumentRecord(file_name="document.md").active_version_id)

    def test_status_validation_rejects_unknown_value(self):
        with self.assertRaises(ValidationError):
            DocumentRecord(file_name="document.md", status="UNKNOWN")

    def test_datetime_must_be_timezone_aware(self):
        with self.assertRaises(ValidationError):
            DocumentRecord(file_name="document.md", created_at=datetime(2026, 1, 1))

    def test_checksum_is_normalized_and_validated(self):
        version = DocumentVersionRecord(
            document_id=DocumentRecord(file_name="document.md").document_id,
            version=1,
            file_name="document.md",
            checksum_sha256="A" * 64,
            size_bytes=10,
        )
        self.assertEqual(version.checksum_sha256, VALID_CHECKSUM)
        with self.assertRaises(ValidationError):
            DocumentVersionRecord(
                document_id=version.document_id,
                version=2,
                file_name="document.md",
                checksum_sha256="not-a-sha256",
                size_bytes=10,
            )

    def test_models_serialize_mongo_id_alias(self):
        document = DocumentRecord(file_name="document.md", status=DocumentStatus.UPLOADED)
        job = IngestionJobRecord(
            document_id=document.document_id,
            version_id=str(UUID(int=1)),
        )
        self.assertEqual(document.to_mongo()["_id"], document.document_id)
        self.assertEqual(job.to_mongo()["_id"], job.job_id)


class FakeCollection:
    def __init__(self):
        self.calls: list[list] = []

    def create_indexes(self, indexes):
        self.calls.append(indexes)
        return [index.document["name"] for index in indexes]


class FakeDatabase:
    def __init__(self):
        self.collections = {name: FakeCollection() for name in INDEX_DEFINITIONS}

    def __getitem__(self, name):
        return self.collections[name]


class DocumentIndexTests(unittest.TestCase):
    def test_duplicate_document_id_and_version_is_rejected_by_unique_spec(self):
        unique_indexes = [
            index.document
            for indexes in INDEX_DEFINITIONS.values()
            for index in indexes
            if index.document.get("unique") is True
        ]
        self.assertEqual(len(unique_indexes), 1)
        self.assertEqual(
            list(unique_indexes[0]["key"].items()),
            [("document_id", 1), ("version", 1)],
        )

    def test_filename_and_checksum_indexes_are_not_unique(self):
        filename = next(index.document for index in DOCUMENT_INDEXES if "file_name" in index.document["key"])
        checksum = next(
            index.document
            for index in DOCUMENT_VERSION_INDEXES
            if "checksum_sha256" in index.document["key"]
        )
        self.assertIsNot(filename.get("unique", False), True)
        self.assertIsNot(checksum.get("unique", False), True)

    def test_index_initialization_is_idempotent_for_unchanged_specs(self):
        database = FakeDatabase()
        first = initialize_document_indexes(database)
        second = initialize_document_indexes(database)
        self.assertEqual(first, second)
        self.assertTrue(all(len(collection.calls) == 2 for collection in database.collections.values()))


if __name__ == "__main__":
    unittest.main()

"""API regression cho document lifecycle mà không gọi cloud thật."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.documents import router
from app.document_models import DocumentRecord, DocumentStatus, DocumentVersionRecord
from app.document_repository import RepositoryNotFoundError
from app.document_service import DeleteResult, DocumentDetail, DocumentSummary
from app.ingestion import IngestionResult

DOCUMENT_ID = "8a424056-e6cb-4a7f-8163-a20d3fbc3590"
VERSION_ID = "30731462-aa86-47ee-985a-73b077e96da9"
JOB_ID = "b0aeccaa-3cef-4df0-9dbf-a75b76ff9815"


class FakeDocumentService:
    def __init__(self):
        self.ingestion = self
        self.document = DocumentRecord(
            _id=DOCUMENT_ID,
            file_name="guide.md",
            active_version_id=VERSION_ID,
            status=DocumentStatus.INDEXED,
        )
        self.version = DocumentVersionRecord(
            _id=VERSION_ID,
            document_id=DOCUMENT_ID,
            version=1,
            file_name="guide.md",
            checksum_sha256="a" * 64,
            size_bytes=7,
            storage_key=f"documents/{DOCUMENT_ID}/{VERSION_ID}/original",
            chunk_count=2,
            status=DocumentStatus.INDEXED,
        )

    @staticmethod
    def _result(file_name="guide.md"):
        return IngestionResult(
            document_id=DOCUMENT_ID,
            version_id=VERSION_ID,
            job_id=JOB_ID,
            file_name=file_name,
            num_chunks=2,
            activated=True,
        )

    def ingest(self, *, file_name, content):
        if content != b"content":
            raise AssertionError("API không truyền content đã validate")
        return self._result(file_name)

    def list_documents(self, **kwargs):
        return [DocumentSummary(self.document, self.version, 1)]

    def get_document(self, document_id):
        if document_id != DOCUMENT_ID:
            raise RepositoryNotFoundError()
        return DocumentDetail(self.document, [self.version])

    def update(self, document_id, *, file_name, content):
        if document_id != DOCUMENT_ID or content != b"content-v2":
            raise AssertionError("API không truyền update input")
        return self._result(file_name)

    def reindex(self, document_id):
        if document_id != DOCUMENT_ID:
            raise AssertionError("API không truyền document ID")
        return self._result()

    def delete(self, document_id):
        if document_id != DOCUMENT_ID:
            raise AssertionError("API không truyền document ID")
        return DeleteResult(document_id, 2, 1, False)


class CleanupPendingService(FakeDocumentService):
    def delete(self, document_id):
        return DeleteResult(document_id, 0, 1, True)


class DocumentApiTests(unittest.TestCase):
    @staticmethod
    def make_app(database=object(), qdrant_client=object()):
        app = FastAPI()
        app.include_router(router)
        app.state.cloud_connections = SimpleNamespace(
            mongodb=SimpleNamespace(database=database),
            qdrant=SimpleNamespace(client=qdrant_client),
        )
        return app

    def test_document_lifecycle_routes(self):
        app = self.make_app()
        fake = FakeDocumentService()
        with patch("app.api.documents.create_document_service", return_value=fake):
            client = TestClient(app)
            upload = client.post(
                "/documents/upload",
                files={"file": ("guide.md", b"content", "text/markdown")},
            )
            listed = client.get("/documents")
            detail = client.get(f"/documents/{DOCUMENT_ID}")
            update = client.put(
                f"/documents/{DOCUMENT_ID}",
                files={"file": ("guide-v2.md", b"content-v2", "text/markdown")},
            )
            reindex = client.post(f"/documents/{DOCUMENT_ID}/re-index")
            deleted = client.delete(f"/documents/{DOCUMENT_ID}")

        self.assertEqual(upload.status_code, 201)
        self.assertEqual(upload.json()["version_id"], VERSION_ID)
        self.assertEqual(upload.json()["status"], "INDEXED")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["active_version_id"], VERSION_ID)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["versions"][0]["checksum_sha256"], "a" * 64)
        self.assertEqual(update.status_code, 201)
        self.assertEqual(update.json()["file_name"], "guide-v2.md")
        self.assertEqual(reindex.status_code, 201)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["raw_file_policy"], "retained")
        self.assertFalse(deleted.json()["retrieval_eligible"])

    def test_returns_503_without_exposing_dependency_details(self):
        response = TestClient(self.make_app(database=None)).get("/documents")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("mongodb", response.text.lower())

    def test_invalid_document_id_is_422(self):
        response = TestClient(self.make_app()).get("/documents/not-a-uuid")
        self.assertEqual(response.status_code, 422)

    def test_delete_returns_202_when_cleanup_must_be_retried(self):
        with patch(
            "app.api.documents.create_document_service",
            return_value=CleanupPendingService(),
        ):
            response = TestClient(self.make_app()).delete(f"/documents/{DOCUMENT_ID}")
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["cleanup_pending"])
        self.assertFalse(response.json()["retrieval_eligible"])


if __name__ == "__main__":
    unittest.main()

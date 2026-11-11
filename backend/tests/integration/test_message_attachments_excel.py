"""Offline API, persistence, XLSX ingestion and Qdrant retrieval regression."""

from io import BytesIO
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from pydantic import ValidationError
from qdrant_client import QdrantClient

from app.api.routes.documents import router as documents_router
from app.api.routes.chat import router as chat_router
from app.api.routes.sessions import _message_response
from app.documents.attachment_models import AttachmentReference
from app.documents.attachments import AttachmentUnavailableError, preview_version, resolve_attachments
from app.conversations.models import MessageRecord, SessionRecord
from app.conversations.repository import MongoConversationRepository
from app.conversations.service import ConversationService
from app.documents.service import DocumentService
from app.documents.models import DocumentStatus
from app.documents.excel.validation import WorkbookError, read_workbook
from app.rag.loaders.excel import workbook_documents
from app.documents.excel.preview import workbook_preview
from app.documents.ingestion import IngestionService
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.chat.pipeline import ProviderStreamChunk
from app.chat.pipeline import _to_source
from app.rag.retriever import get_retriever
from app.api.schemas.chat_documents import ChatRequest
from app.infrastructure.storage import LocalFileStorage
from tests.integration.test_ingestion import MemoryRepository, DeterministicEmbeddings
from tests.integration.test_chat_persistence import FakeMessageRepository


def workbook_bytes(*, empty=False, formula=False):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Vehicles"
    if not empty:
        sheet.append(["Name", "Speed"])
        sheet.append(["Airplane", 900])
        sheet.append(["Bus", 80])
        if formula:
            sheet.append(["=WEBSERVICE(\"https://example.invalid\")", "=1+2"])
        other = workbook.create_sheet("Policies")
        other.append(["Topic", "Rule"])
        other.append(["License", "A valid license is required"])
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


class KeywordEmbeddings(DeterministicEmbeddings):
    def embed_documents(self, texts):
        return [[float("airplane" in text.lower()), float("license" in text.lower()), 0.01] for text in texts]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


class ExcelAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = LocalFileStorage(Path(self.temporary.name))
        self.repository = MemoryRepository()
        self.qdrant = QdrantClient(":memory:")
        self.index = QdrantVectorIndex(self.qdrant, "excel_offline")
        self.embeddings = KeywordEmbeddings()
        self.ingestion = IngestionService(repository=self.repository, storage=self.storage,
                                         vector_index=self.index, embeddings=self.embeddings,
                                         embedding_model="offline-keywords")
        self.service = DocumentService(repository=self.repository, storage=self.storage,
                                       vector_index=self.index, ingestion=self.ingestion)
        self.app = FastAPI()
        self.app.include_router(documents_router)
        self.app.include_router(chat_router)
        self.app.state.cloud_connections = SimpleNamespace(mongodb=SimpleNamespace(database=object()),
                                                          qdrant=SimpleNamespace(client=object()))

    def tearDown(self):
        self.qdrant.close()
        self.temporary.cleanup()

    def upload(self, name="vehicles.xlsx", content=None, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
        with patch("app.api.routes.documents.create_document_service", return_value=self.service):
            return TestClient(self.app).post("/documents/upload", files={"file": (name, content or workbook_bytes(), mime)})

    def test_real_multisheet_upload_indexes_and_retrieves_correct_row_and_metadata(self):
        original_connect = socket.socket.connect

        def local_only(connection, address):
            if address[0] in {"127.0.0.1", "::1"}:
                return original_connect(connection, address)
            raise AssertionError("No external network")

        with patch.object(socket.socket, "connect", new=local_only):
            response = self.upload()
            self.assertEqual(response.status_code, 201, response.text)
            result = response.json()
            self.assertTrue(result["activated"])
            retriever = get_retriever(vector_index=self.index, embeddings=self.embeddings,
                                      active_version_ids=(result["version_id"],), top_k=1)
            plane = retriever.invoke("Airplane speed")[0]
            self.assertIn("900", plane.page_content)
            self.assertEqual(plane.metadata["sheet_name"], "Vehicles")
            self.assertEqual(plane.metadata["row_index"], 2)
            self.assertEqual(plane.metadata["version_id"], result["version_id"])
            self.assertEqual(_to_source(plane)["sheet_name"], "Vehicles")
            self.assertEqual(_to_source(plane)["row_index"], 2)
            policy = retriever.invoke("License rule")[0]
            self.assertEqual(policy.metadata["sheet_name"], "Policies")
            self.assertIn("valid license", policy.page_content)

    def test_versioned_preview_survives_new_active_version_and_has_readonly_tables(self):
        result = self.upload().json()
        self.service.update(result["document_id"], file_name="replacement.txt", content=b"Replacement text")
        with patch("app.api.routes.documents.create_document_service", return_value=self.service):
            response = TestClient(self.app).get(f"/documents/{result['document_id']}/versions/{result['version_id']}/preview")
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json()
        self.assertEqual(preview["sheets"][0]["name"], "Vehicles")
        self.assertEqual(preview["sheets"][0]["columns"], ["Name", "Speed"])
        self.assertEqual(preview["sheets"][0]["rows"][0], ["Airplane", "900"])
        self.assertEqual(resolve_attachments(self.repository, [AttachmentReference(**{key: result[key] for key in ("document_id", "version_id")})])[0].file_name, "vehicles.xlsx")

    def test_txt_preview_is_versioned_and_plain_text(self):
        text = "Phương tiện\r\nXe máy\n<script>unsafe()</script>"
        result = self.upload("phuongtien.txt", text.encode(), "text/plain").json()
        preview = preview_version(self.repository, self.storage, result["document_id"], result["version_id"])
        self.assertEqual(preview["text"], text)
        self.assertEqual(preview["kind"], "text")

    def test_real_pdf_upload_still_parses_indexes_and_preserves_zero_based_page(self):
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 20 250 Td (PDF transport fixture) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        content = BytesIO()
        writer.write(content)
        response = self.upload("fixture.pdf", content.getvalue(), "application/pdf")
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        matches = get_retriever(vector_index=self.index, embeddings=self.embeddings,
                                active_version_ids=(result["version_id"],), top_k=1).invoke("PDF fixture")
        self.assertIn("PDF transport fixture", matches[0].page_content)
        self.assertEqual(matches[0].metadata["page"], 0)

    def test_unindexed_reference_is_rejected_before_rag_preparation(self):
        result = self.upload().json()
        version = self.repository.versions[result["version_id"]]
        self.repository.versions[version.version_id] = version.model_copy(update={"status": DocumentStatus.FAILED})
        with patch("app.api.routes.chat.MongoDocumentRepository", return_value=self.repository), \
             patch("app.api.routes.chat.prepare_rag_stream") as prepare:
            response = TestClient(self.app).post("/chat/stream", json={"question": "Question", "session_id": str(uuid4()),
                "attachments": [{key: result[key] for key in ("document_id", "version_id")}]})
        self.assertEqual(response.status_code, 409)
        prepare.assert_not_called()

    def test_json_and_sse_user_messages_persist_only_validated_attachment_references(self):
        result = self.upload().json()
        references = [{key: result[key] for key in ("document_id", "version_id")}]

        async def stream(_prepared):
            yield ProviderStreamChunk(content="Answer", usage=None)

        for path in ("/chat", "/chat/stream"):
            with self.subTest(path=path):
                messages = FakeMessageRepository()
                service = ConversationService(messages)
                with patch("app.api.routes.chat.MongoDocumentRepository", return_value=self.repository), \
                     patch("app.api.routes.chat.create_conversation_service", return_value=service), \
                     patch("app.api.routes.chat.answer_question", return_value={"answer": "Answer", "sources": []}), \
                     patch("app.api.routes.chat.prepare_rag_stream", return_value=SimpleNamespace(sources=[])), \
                     patch("app.api.routes.chat.astream_rag_answer", stream):
                    response = TestClient(self.app).post(path, json={"question": "Explain", "session_id": str(uuid4()), "attachments": references})
                self.assertEqual(response.status_code, 200, response.text)
                user, assistant = messages.pair
                restored = MessageRecord.model_validate(user.to_mongo())
                public = _message_response(restored).model_dump(mode="json")
                self.assertEqual(public["attachments"][0], {**references[0], "file_name": "vehicles.xlsx"})
                self.assertNotIn("content", public["attachments"][0])
                self.assertEqual(assistant.attachments, [])

    def test_old_message_defaults_and_attachment_contract_reject_duplicates_and_stateless(self):
        reference = {"document_id": str(uuid4()), "version_id": str(uuid4())}
        for values in ({"attachments": [reference]}, {"session_id": str(uuid4()), "attachments": [reference, reference]}):
            with self.assertRaises(ValidationError):
                ChatRequest(question="Question", **values)
        repository = FakeMessageRepository()
        ConversationService(repository).begin_streaming_turn(session_id=str(uuid4()), question="Legacy", model="offline")
        document = repository.pair[0].to_mongo()
        document.pop("attachments")
        self.assertEqual(MessageRecord.model_validate(document).attachments, [])

    def test_real_mongo_repository_serializes_and_restores_attachment_references(self):
        result = self.upload().json()
        attachments = resolve_attachments(self.repository, [AttachmentReference(**{key: result[key] for key in ("document_id", "version_id")})])
        session_id = str(uuid4())
        turn = ConversationService(FakeMessageRepository()).begin_streaming_turn(
            session_id=session_id, question="Question", model="offline", attachments=attachments)
        sessions, messages = MagicMock(), MagicMock()
        database = {"sessions": sessions, "messages": messages}
        repository = MongoConversationRepository(database)
        repository.create_message_pair(turn.user_message, turn.assistant_message)
        stored = messages.insert_many.call_args.args[0]
        self.assertEqual(set(stored[0]["attachments"][0]), {"document_id", "version_id", "file_name"})
        sessions.find_one.return_value = SessionRecord(session_id=session_id).to_mongo()
        messages.count_documents.return_value = 2
        messages.find.return_value.sort.return_value.skip.return_value.limit.return_value = stored
        restored, total = MongoConversationRepository(database).list_messages(session_id)
        self.assertEqual(total, 2)
        self.assertEqual(_message_response(restored[0]).attachments, attachments)

    def test_wrong_version_and_deleted_documents_are_unavailable(self):
        first = self.upload().json()
        other = self.upload("other.xlsx").json()
        with self.assertRaises(AttachmentUnavailableError):
            resolve_attachments(self.repository, [AttachmentReference(document_id=first["document_id"], version_id=other["version_id"])])
        self.repository.unpublish(first["document_id"])
        with self.assertRaises(AttachmentUnavailableError) as caught:
            preview_version(self.repository, self.storage, first["document_id"], first["version_id"])
        self.assertEqual(caught.exception.status, 410)

    def test_upload_rejects_mime_and_invalid_workbook_before_creating_documents(self):
        for content, mime in ((b"not a workbook", "application/octet-stream"), (workbook_bytes(), "text/plain"), (workbook_bytes(empty=True), "application/octet-stream")):
            response = self.upload(content=content, mime=mime)
            self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.repository.documents, {})


class WorkbookValidationTests(unittest.TestCase):
    def test_formulas_remain_literal_and_parser_never_connects(self):
        with patch.object(socket.socket, "connect", side_effect=AssertionError("No external links")):
            documents = workbook_documents(workbook_bytes(formula=True))
        self.assertTrue(any("=WEBSERVICE" in doc.page_content and "=1+2" in doc.page_content for doc in documents))

    def test_empty_corrupt_macro_size_row_sheet_and_cell_limits(self):
        for content in (b"", b"invalid", workbook_bytes(empty=True)):
            with self.assertRaises(WorkbookError):
                read_workbook(content)
        for name, limit in (("MAX_XLSX_BYTES", 1), ("MAX_SHEETS", 1), ("MAX_ROWS", 2), ("MAX_CELLS", 1), ("MAX_XLSX_EXPANDED_BYTES", 1)):
            with self.subTest(limit=name), patch(f"app.documents.excel.validation.{name}", limit), self.assertRaises(WorkbookError):
                read_workbook(workbook_bytes())
        stream = BytesIO(workbook_bytes())
        with ZipFile(stream, "a") as archive:
            archive.writestr("xl/vbaProject.bin", b"macro")
        with self.assertRaises(WorkbookError):
            read_workbook(stream.getvalue())

    def test_preview_is_bounded_and_preserves_sheet_headers_and_rows(self):
        preview = workbook_preview(workbook_bytes())
        self.assertEqual(preview["sheets"][0]["columns"], ["Name", "Speed"])
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Title"])
        for row in range(100):
            sheet.append([f"Value {row}"])
        stream = BytesIO()
        workbook.save(stream)
        workbook.close()
        preview = workbook_preview(stream.getvalue())
        self.assertEqual(len(preview["sheets"][0]["rows"]), 50)
        self.assertTrue(preview["truncated"])

    def test_repeated_headers_cannot_amplify_ingestion_beyond_text_limits(self):
        for name in ("MAX_INGEST_CHARS", "MAX_ROW_CHARS"):
            with self.subTest(limit=name), patch(f"app.rag.loaders.excel.{name}", 1), self.assertRaises(WorkbookError):
                workbook_documents(workbook_bytes())

"""MongoDB repository cho document ingestion lifecycle."""

from __future__ import annotations

from typing import Any

from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.document_indexes import (
    DOCUMENTS_COLLECTION,
    DOCUMENT_VERSIONS_COLLECTION,
    INGESTION_JOBS_COLLECTION,
)
from app.document_models import (
    DocumentRecord,
    DocumentStatus,
    DocumentVersionRecord,
    IngestionJobRecord,
    IngestionJobStatus,
    utc_now,
)


class RepositoryError(Exception):
    """Lỗi persistence an toàn, không làm lộ MongoDB details."""


class RepositoryConflictError(RepositoryError):
    pass


class RepositoryNotFoundError(RepositoryError):
    pass


class MongoDocumentRepository:
    def __init__(self, database: Any):
        if database is None:
            raise RepositoryError("MongoDB chưa kết nối")
        self.documents = database[DOCUMENTS_COLLECTION]
        self.versions = database[DOCUMENT_VERSIONS_COLLECTION]
        self.jobs = database[INGESTION_JOBS_COLLECTION]

    def create_upload(
        self,
        document: DocumentRecord,
        version: DocumentVersionRecord,
        job: IngestionJobRecord,
    ) -> None:
        inserted: list[tuple[Any, str]] = []
        try:
            self.documents.insert_one(document.to_mongo())
            inserted.append((self.documents, document.document_id))
            self.versions.insert_one(version.to_mongo())
            inserted.append((self.versions, version.version_id))
            self.jobs.insert_one(job.to_mongo())
        except DuplicateKeyError as exc:
            self._cleanup_inserts(inserted)
            raise RepositoryConflictError("Document/version đã tồn tại") from exc
        except PyMongoError as exc:
            self._cleanup_inserts(inserted)
            raise RepositoryError("Không thể tạo metadata upload") from exc

    @staticmethod
    def _cleanup_inserts(inserted: list[tuple[Any, str]]) -> None:
        for collection, record_id in reversed(inserted):
            try:
                collection.delete_one({"_id": record_id})
            except PyMongoError:
                pass

    def get_document(self, document_id: str) -> DocumentRecord:
        try:
            value = self.documents.find_one({"_id": document_id})
        except PyMongoError as exc:
            raise RepositoryError("Không thể đọc document metadata") from exc
        if value is None:
            raise RepositoryNotFoundError("Document không tồn tại")
        return DocumentRecord.model_validate(value)

    def find_document_by_source_key(self, source_key: str) -> DocumentRecord | None:
        try:
            value = self.documents.find_one({"source_key": source_key})
        except PyMongoError as exc:
            raise RepositoryError("Không thể đọc migration source metadata") from exc
        return None if value is None else DocumentRecord.model_validate(value)

    def get_version(self, version_id: str) -> DocumentVersionRecord:
        try:
            value = self.versions.find_one({"_id": version_id})
        except PyMongoError as exc:
            raise RepositoryError("Không thể đọc document version") from exc
        if value is None:
            raise RepositoryNotFoundError("Document version không tồn tại")
        return DocumentVersionRecord.model_validate(value)

    def list_documents(
        self,
        *,
        include_deleted: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[DocumentRecord]:
        query = {} if include_deleted else {"status": {"$ne": DocumentStatus.DELETED.value}}
        try:
            values = (
                self.documents.find(query)
                .sort("created_at", DESCENDING)
                .skip(offset)
                .limit(limit)
            )
            return [DocumentRecord.model_validate(value) for value in values]
        except PyMongoError as exc:
            raise RepositoryError("Không thể liệt kê documents") from exc

    def list_versions(self, document_id: str) -> list[DocumentVersionRecord]:
        try:
            values = self.versions.find({"document_id": document_id}).sort("version", DESCENDING)
            return [DocumentVersionRecord.model_validate(value) for value in values]
        except PyMongoError as exc:
            raise RepositoryError("Không thể liệt kê document versions") from exc

    def list_active_version_ids(self) -> list[str]:
        """Danh sách version được phép retrieval tại thời điểm query."""
        try:
            values = self.documents.find(
                {
                    "status": DocumentStatus.INDEXED.value,
                    "active_version_id": {"$type": "string"},
                },
                {"active_version_id": 1},
            )
            return [str(value["active_version_id"]) for value in values]
        except PyMongoError as exc:
            raise RepositoryError("Không thể đọc active retrieval scope") from exc

    def next_version_number(self, document_id: str) -> int:
        try:
            latest = self.versions.find_one(
                {"document_id": document_id},
                sort=[("version", DESCENDING)],
                projection={"version": 1},
            )
        except PyMongoError as exc:
            raise RepositoryError("Không thể cấp số document version") from exc
        return 1 if latest is None else int(latest["version"]) + 1

    def create_version_upload(
        self,
        version: DocumentVersionRecord,
        job: IngestionJobRecord,
    ) -> None:
        inserted_version = False
        try:
            if self.documents.count_documents(
                {
                    "_id": version.document_id,
                    "status": {"$ne": DocumentStatus.DELETED.value},
                },
                limit=1,
            ) != 1:
                raise RepositoryNotFoundError("Document không tồn tại")
            self.versions.insert_one(version.to_mongo())
            inserted_version = True
            self.jobs.insert_one(job.to_mongo())
        except RepositoryNotFoundError:
            raise
        except DuplicateKeyError as exc:
            raise RepositoryConflictError("Document version đã tồn tại") from exc
        except PyMongoError as exc:
            raise RepositoryError("Không thể tạo metadata version") from exc
        finally:
            if inserted_version:
                try:
                    if self.jobs.count_documents({"_id": job.job_id}, limit=1) == 0:
                        self.versions.delete_one({"_id": version.version_id})
                except PyMongoError:
                    pass

    def create_retry_job(self, version: DocumentVersionRecord) -> IngestionJobRecord:
        try:
            latest = self.jobs.find_one(
                {"version_id": version.version_id},
                sort=[("attempt", DESCENDING)],
                projection={"attempt": 1},
            )
            attempt = 1 if latest is None else int(latest["attempt"]) + 1
            job = IngestionJobRecord(
                document_id=version.document_id,
                version_id=version.version_id,
                attempt=attempt,
            )
            self.jobs.insert_one(job.to_mongo())
            return job
        except PyMongoError as exc:
            raise RepositoryError("Không thể tạo retry job") from exc

    def mark_processing(self, document_id: str, version_id: str, job_id: str) -> None:
        now = utc_now()
        try:
            job_result = self.jobs.update_one(
                {"_id": job_id, "status": IngestionJobStatus.PENDING.value},
                {"$set": {
                    "status": IngestionJobStatus.PROCESSING.value,
                    "started_at": now,
                    "updated_at": now,
                    "error_code": None,
                    "error_message": None,
                }},
            )
            version_result = self.versions.update_one(
                {"_id": version_id, "document_id": document_id},
                {"$set": {"status": DocumentStatus.PROCESSING.value, "updated_at": now}},
            )
            if job_result.matched_count != 1 or version_result.matched_count != 1:
                raise RepositoryConflictError("Ingestion state không hợp lệ")
            self.documents.update_one(
                {
                    "_id": document_id,
                    "active_version_id": None,
                    "status": {"$ne": DocumentStatus.DELETED.value},
                },
                {"$set": {"status": DocumentStatus.PROCESSING.value, "updated_at": now}},
            )
        except RepositoryError:
            raise
        except PyMongoError as exc:
            raise RepositoryError("Không thể chuyển ingestion sang PROCESSING") from exc

    def set_chunk_plan(
        self,
        version_id: str,
        *,
        chunk_count: int,
        embedding_model: str,
        vector_collection: str,
    ) -> None:
        try:
            result = self.versions.update_one(
                {"_id": version_id, "status": DocumentStatus.PROCESSING.value},
                {"$set": {
                    "chunk_count": chunk_count,
                    "embedding_model": embedding_model,
                    "vector_collection": vector_collection,
                    "updated_at": utc_now(),
                }},
            )
            if result.matched_count != 1:
                raise RepositoryConflictError("Version không ở trạng thái PROCESSING")
        except RepositoryError:
            raise
        except PyMongoError as exc:
            raise RepositoryError("Không thể lưu chunk plan") from exc

    def complete_and_activate(self, version_id: str, job_id: str) -> bool:
        """Mark indexed và chỉ activate nếu không có version mới hơn đang active."""
        version = self.get_version(version_id)
        now = utc_now()
        try:
            self.versions.update_one(
                {"_id": version_id},
                {"$set": {
                    "status": DocumentStatus.INDEXED.value,
                    "indexed_at": now,
                    "updated_at": now,
                }},
            )

            activated = False
            for _ in range(5):
                document = self.documents.find_one({"_id": version.document_id})
                if document is None:
                    raise RepositoryNotFoundError("Document không tồn tại")
                if document.get("status") == DocumentStatus.DELETED.value:
                    raise RepositoryConflictError("Document đã bị xóa")
                current_id = document.get("active_version_id")
                if current_id == version_id:
                    activated = True
                    break
                if current_id is not None:
                    current = self.versions.find_one({"_id": current_id}, {"version": 1})
                    if current is not None and int(current["version"]) >= version.version:
                        break
                result = self.documents.update_one(
                    {
                        "_id": version.document_id,
                        "active_version_id": current_id,
                        "status": {"$ne": DocumentStatus.DELETED.value},
                    },
                    {"$set": {
                        "active_version_id": version_id,
                        "file_name": version.file_name,
                        "status": DocumentStatus.INDEXED.value,
                        "updated_at": now,
                    }},
                )
                if result.modified_count == 1:
                    activated = True
                    break
            else:
                raise RepositoryConflictError("Không thể activate version do concurrent update")

            job_result = self.jobs.update_one(
                {"_id": job_id},
                {"$set": {
                    "status": IngestionJobStatus.COMPLETED.value,
                    "completed_at": now,
                    "updated_at": now,
                }},
            )
            if job_result.matched_count != 1:
                raise RepositoryNotFoundError("Ingestion job không tồn tại")
            return activated
        except RepositoryError:
            raise
        except PyMongoError as exc:
            raise RepositoryError("Không thể hoàn tất ingestion metadata") from exc

    def mark_failed(self, document_id: str, version_id: str, job_id: str, error_code: str) -> None:
        now = utc_now()
        try:
            self.versions.update_one(
                {"_id": version_id},
                {"$set": {"status": DocumentStatus.FAILED.value, "updated_at": now}},
            )
            self.jobs.update_one(
                {"_id": job_id},
                {"$set": {
                    "status": IngestionJobStatus.FAILED.value,
                    "error_code": error_code,
                    "error_message": "Ingestion thất bại; xem server diagnostics.",
                    "completed_at": now,
                    "updated_at": now,
                }},
            )
            # Chỉ document chưa từng có active version mới chuyển FAILED.
            self.documents.update_one(
                {
                    "_id": document_id,
                    "active_version_id": None,
                    "status": {"$ne": DocumentStatus.DELETED.value},
                },
                {"$set": {"status": DocumentStatus.FAILED.value, "updated_at": now}},
            )
        except PyMongoError as exc:
            raise RepositoryError("Không thể ghi nhận ingestion failure") from exc

    def latest_processing_job(self, version_id: str) -> IngestionJobRecord:
        try:
            value = self.jobs.find_one(
                {"version_id": version_id, "status": IngestionJobStatus.PROCESSING.value},
                sort=[("attempt", DESCENDING)],
            )
        except PyMongoError as exc:
            raise RepositoryError("Không thể đọc processing job") from exc
        if value is None:
            raise RepositoryNotFoundError("Không có processing job")
        return IngestionJobRecord.model_validate(value)

    def is_active_version(self, document_id: str, version_id: str) -> bool:
        try:
            return self.documents.count_documents(
                {"_id": document_id, "active_version_id": version_id}, limit=1
            ) == 1
        except PyMongoError as exc:
            raise RepositoryError("Không thể xác minh active version") from exc

    def is_document_deleted(self, document_id: str) -> bool:
        try:
            return self.documents.count_documents(
                {"_id": document_id, "status": DocumentStatus.DELETED.value}, limit=1
            ) == 1
        except PyMongoError as exc:
            raise RepositoryError("Không thể xác minh document deletion state") from exc

    def unpublish(self, document_id: str) -> DocumentRecord:
        now = utc_now()
        try:
            result = self.documents.update_one(
                {"_id": document_id, "status": {"$ne": DocumentStatus.DELETED.value}},
                {
                    "$set": {
                        "status": DocumentStatus.DELETED.value,
                        "active_version_id": None,
                        "cleanup_pending": True,
                        "deleted_at": now,
                        "updated_at": now,
                    }
                },
            )
            if result.matched_count != 1:
                # DELETE lặp lại chỉ mở lại cleanup; giữ nguyên deleted_at ban đầu.
                result = self.documents.update_one(
                    {"_id": document_id, "status": DocumentStatus.DELETED.value},
                    {"$set": {"cleanup_pending": True, "updated_at": now}},
                )
                if result.matched_count != 1:
                    raise RepositoryNotFoundError("Document không tồn tại")
            return self.get_document(document_id)
        except RepositoryError:
            raise
        except PyMongoError as exc:
            raise RepositoryError("Không thể unpublish document") from exc

    def mark_cleanup_complete(self, document_id: str) -> None:
        try:
            result = self.documents.update_one(
                {"_id": document_id, "status": DocumentStatus.DELETED.value},
                {"$set": {"cleanup_pending": False, "updated_at": utc_now()}},
            )
            if result.matched_count != 1:
                raise RepositoryNotFoundError("Document đã xóa không tồn tại")
        except RepositoryError:
            raise
        except PyMongoError as exc:
            raise RepositoryError("Không thể hoàn tất cleanup metadata") from exc

    def list_processing_versions(self, limit: int = 100) -> list[DocumentVersionRecord]:
        try:
            jobs = list(
                self.jobs.find(
                    {"status": IngestionJobStatus.PROCESSING.value},
                    {"version_id": 1},
                ).sort("updated_at", 1).limit(limit)
            )
            version_ids = [job["version_id"] for job in jobs]
            if not version_ids:
                return []
            values = self.versions.find(
                {
                    "_id": {"$in": version_ids},
                    "status": {"$in": [DocumentStatus.PROCESSING.value, DocumentStatus.INDEXED.value]},
                    "chunk_count": {"$gt": 0},
                }
            ).sort("updated_at", 1)
            return [DocumentVersionRecord.model_validate(value) for value in values]
        except PyMongoError as exc:
            raise RepositoryError("Không thể liệt kê version cần reconciliation") from exc

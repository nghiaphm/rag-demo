"""Unit tests cho Giai đoạn 1: StorageBackend Protocol, Local/S3 adapters và versioned key builder."""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from pydantic import SecretStr

from app.documents.models import DocumentRecord, DocumentVersionRecord
from app.documents.ports import (
    InvalidStorageKeyError,
    StorageAlreadyExistsError,
    StorageBackend,
    StorageError,
    StorageNotFoundError,
    build_versioned_storage_key,
)
from app.infrastructure.s3_storage import S3FileStorage
from app.infrastructure.storage import LocalFileStorage, create_file_storage
from app.shared.auth import UserContext, create_access_token, decode_token


class FakeS3ClientError(Exception):
    """Giả lập botocore ClientError không cần phụ thuộc mạng."""

    def __init__(self, code: str, status_code: int, message: str = "S3 error") -> None:
        super().__init__(message)
        self.response = {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        }


class StubS3Client:
    """In-memory S3 client stub kiểm thử conditional put, head, get, list và delete_objects."""

    def __init__(self, *, page_size: int = 2) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str | None] = {}
        self.put_calls: list[dict] = []
        self.head_calls: list[str] = []
        self.page_size = page_size
        self.fail_on_op: str | None = None
        self.fail_exception: Exception | None = None

    def _check_fail(self, op: str) -> None:
        if self.fail_on_op == op and self.fail_exception is not None:
            raise self.fail_exception

    def put_object(self, **kwargs):
        self._check_fail("put_object")
        self.put_calls.append(dict(kwargs))
        key = kwargs["Key"]
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise FakeS3ClientError(
                "PreconditionFailed",
                412,
                "At least one of the pre-conditions you specified did not hold",
            )
        body = kwargs["Body"]
        self.objects[key] = bytes(body) if isinstance(body, (bytes, bytearray)) else body.read()
        self.content_types[key] = kwargs.get("ContentType")
        return {"ETag": '"stub-etag"'}

    def head_object(self, *, Bucket: str, Key: str):
        _ = Bucket
        self._check_fail("head_object")
        self.head_calls.append(Key)
        if Key not in self.objects:
            raise FakeS3ClientError("404", 404, "Not Found")
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, *, Bucket: str, Key: str):
        _ = Bucket
        self._check_fail("get_object")
        if Key not in self.objects:
            raise FakeS3ClientError("NoSuchKey", 404, "The specified key does not exist.")
        return {"Body": io.BytesIO(self.objects[Key])}

    def delete_object(self, *, Bucket: str, Key: str):
        _ = Bucket
        self._check_fail("delete_object")
        self.objects.pop(Key, None)
        return {}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str | None = None):
        _ = Bucket
        self._check_fail("list_objects_v2")
        matching = sorted(
            k
            for k in self.objects
            if k.startswith(Prefix) and (ContinuationToken is None or k > ContinuationToken)
        )
        slice_keys = matching[: self.page_size]
        is_truncated = len(matching) > self.page_size
        result = {
            "Contents": [{"Key": k} for k in slice_keys],
            "IsTruncated": is_truncated,
        }
        if is_truncated and slice_keys:
            result["NextContinuationToken"] = slice_keys[-1]
        return result

    def delete_objects(self, *, Bucket: str, Delete: dict):
        _ = Bucket
        self._check_fail("delete_objects")
        deleted = []
        for item in Delete.get("Objects", []):
            key = item["Key"]
            self.objects.pop(key, None)
            deleted.append({"Key": key})
        return {"Deleted": deleted}


class StorageBackendUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_versioned_storage_key_format_and_validation(self) -> None:
        doc_id = str(uuid4())
        key_xlsx = build_versioned_storage_key("default", doc_id, 1, "hr_employees.XLSX")
        self.assertEqual(key_xlsx, f"default/{doc_id}/v1/original.xlsx")

        key_pdf = build_versioned_storage_key("tenant_a", doc_id, 3, "policy.pdf")
        self.assertEqual(key_pdf, f"tenant_a/{doc_id}/v3/original.pdf")

        key_no_ext = build_versioned_storage_key("default", doc_id, 2, "")
        self.assertEqual(key_no_ext, f"default/{doc_id}/v2/original")

        with self.assertRaises(InvalidStorageKeyError):
            build_versioned_storage_key("../evil", doc_id, 1, "a.xlsx")
        with self.assertRaises(InvalidStorageKeyError):
            build_versioned_storage_key("default", "not-a-uuid", 1, "a.xlsx")
        with self.assertRaises(InvalidStorageKeyError):
            build_versioned_storage_key("default", doc_id, 0, "a.xlsx")
        with self.assertRaises(InvalidStorageKeyError):
            build_versioned_storage_key("default", doc_id, True, "a.xlsx")

    def test_local_and_s3_satisfy_storage_backend_protocol(self) -> None:
        local = LocalFileStorage(self.root)
        s3 = S3FileStorage(bucket="rag-test-bucket", client=StubS3Client())
        self.assertIsInstance(local, StorageBackend)
        self.assertIsInstance(s3, StorageBackend)
        self.assertEqual(local.backend_name, "local")
        self.assertEqual(s3.backend_name, "s3")

    def test_local_delete_prefix_removes_matching_subtree_safely(self) -> None:
        local = LocalFileStorage(self.root)
        doc_id = str(uuid4())
        v1_orig = f"default/{doc_id}/v1/original.xlsx"
        v1_t1 = f"default/{doc_id}/v1/tables/nhan_su.parquet"
        v1_t2 = f"default/{doc_id}/v1/tables/phong_ban.parquet"
        v2_orig = f"default/{doc_id}/v2/original.xlsx"

        for key in (v1_orig, v1_t1, v1_t2, v2_orig):
            (self.root / key).parent.mkdir(parents=True, exist_ok=True)
            (self.root / key).write_bytes(b"data")

        deleted_tables = local.delete_prefix(f"default/{doc_id}/v1/tables/")
        self.assertEqual(deleted_tables, 2)
        self.assertFalse(local.exists(v1_t1))
        self.assertFalse(local.exists(v1_t2))
        self.assertTrue(local.exists(v1_orig))
        self.assertTrue(local.exists(v2_orig))

        self.assertEqual(local.delete_prefix(f"default/{doc_id}/v99/tables/"), 0)
        with self.assertRaises(InvalidStorageKeyError):
            local.delete_prefix("../escape")

    def test_s3_conditional_put_uses_if_none_match_when_enabled(self) -> None:
        stub = StubS3Client()
        storage = S3FileStorage(
            bucket="rag-test-bucket",
            use_if_none_match=True,
            client=stub,
        )
        key = build_versioned_storage_key("default", str(uuid4()), 1, "report.xlsx")
        payload = b"excel-binary-content"

        stored = storage.put(key, payload, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertEqual(stored.storage_key, key)
        self.assertEqual(stored.size_bytes, len(payload))
        self.assertEqual(stored.checksum_sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(stub.put_calls[0].get("IfNoneMatch"), "*")
        self.assertEqual(stub.head_calls, [])

        self.assertTrue(storage.exists(key))
        self.assertEqual(storage.get(key), payload)
        with storage.open(key) as stream:
            self.assertEqual(stream.read(), payload)

        with self.assertRaises(StorageAlreadyExistsError):
            storage.put(key, b"overwrite-attempt")
        self.assertEqual(storage.get(key), payload)

    def test_s3_conditional_put_falls_back_to_head_object_when_disabled(self) -> None:
        stub = StubS3Client()
        storage = S3FileStorage(
            bucket="minio-compatible-bucket",
            use_if_none_match=False,
            client=stub,
        )
        key = build_versioned_storage_key("default", str(uuid4()), 1, "report.xlsx")

        storage.put(key, io.BytesIO(b"first-version"))
        self.assertNotIn("IfNoneMatch", stub.put_calls[0])
        self.assertEqual(stub.head_calls, [key])

        with self.assertRaises(StorageAlreadyExistsError):
            storage.put(key, b"second-overwrite")
        self.assertEqual(len(stub.put_calls), 1)
        self.assertEqual(storage.get(key), b"first-version")

    def test_s3_delete_and_paginated_delete_prefix(self) -> None:
        stub = StubS3Client(page_size=2)
        storage = S3FileStorage(bucket="rag-test-bucket", client=stub)
        doc_id = str(uuid4())
        keys = [
            f"default/{doc_id}/v1/tables/t1.parquet",
            f"default/{doc_id}/v1/tables/t2.parquet",
            f"default/{doc_id}/v1/tables/t3.parquet",
            f"default/{doc_id}/v1/original.xlsx",
        ]
        for key in keys:
            storage.put(key, b"bytes")

        removed = storage.delete_prefix(f"default/{doc_id}/v1/tables/")
        self.assertEqual(removed, 3)
        self.assertTrue(storage.exists(f"default/{doc_id}/v1/original.xlsx"))
        self.assertFalse(storage.exists(f"default/{doc_id}/v1/tables/t1.parquet"))

        self.assertTrue(storage.delete(f"default/{doc_id}/v1/original.xlsx"))
        self.assertFalse(storage.delete(f"default/{doc_id}/v1/original.xlsx"))
        with self.assertRaises(StorageNotFoundError):
            storage.get(f"default/{doc_id}/v1/original.xlsx")

    def test_s3_errors_never_leak_credentials_or_endpoints(self) -> None:
        stub = StubS3Client()
        secret_msg = (
            "Endpoint https://s3.internal.corp failed with "
            "aws_access_key_id=AKIAIOSFODNN7EXAMPLE "
            "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        )
        stub.fail_on_op = "put_object"
        stub.fail_exception = RuntimeError(secret_msg)
        storage = S3FileStorage(bucket="rag-test-bucket", client=stub)
        key = build_versioned_storage_key("default", str(uuid4()), 1, "test.xlsx")

        with self.assertRaises(StorageError) as ctx:
            storage.put(key, b"data")
        err_text = str(ctx.exception)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", err_text)
        self.assertNotIn("wJalrXUtnFEMI", err_text)
        self.assertNotIn("s3.internal.corp", err_text)
        self.assertIsNone(ctx.exception.__cause__)

    def test_factory_creates_s3_storage_from_config(self) -> None:
        stub = StubS3Client()

        class S3Config:
            storage_backend = "s3"
            s3_bucket = "rag-prod-bucket"
            s3_region = "ap-southeast-1"
            s3_endpoint_url = "https://s3.ap-southeast-1.amazonaws.com"
            s3_ingest_access_key_id = SecretStr("AKIA_TEST")
            s3_ingest_secret_access_key = SecretStr("SECRET_TEST")
            s3_use_if_none_match = False

        created = create_file_storage(S3Config(), s3_client=stub)
        self.assertIsInstance(created, S3FileStorage)
        self.assertEqual(created.backend_name, "s3")
        self.assertFalse(created.use_if_none_match)

    def test_legacy_version_record_defaults_storage_backend_to_local_and_user_context_has_tenant(self) -> None:
        doc_id = str(uuid4())
        ver_id = str(uuid4())
        legacy_mongo_doc = {
            "_id": doc_id,
            "file_name": "old.xlsx",
            "status": "INDEXED",
        }
        legacy_mongo_ver = {
            "_id": ver_id,
            "document_id": doc_id,
            "version": 1,
            "file_name": "old.xlsx",
            "checksum_sha256": "a" * 64,
            "size_bytes": 128,
            "storage_key": f"documents/{doc_id}/{ver_id}/original",
            "status": "INDEXED",
        }
        doc = DocumentRecord.model_validate(legacy_mongo_doc)
        ver = DocumentVersionRecord.model_validate(legacy_mongo_ver)
        self.assertEqual(doc.tenant_id, "default")
        self.assertEqual(ver.storage_backend, "local")

        token = create_access_token(
            user_id="u-1",
            username="alice",
            roles=("viewer",),
            secret="test-secret-key",
        )
        user_ctx = decode_token(token, secret="test-secret-key")
        self.assertIsInstance(user_ctx, UserContext)
        self.assertEqual(user_ctx.tenant_id, "default")


if __name__ == "__main__":
    unittest.main()

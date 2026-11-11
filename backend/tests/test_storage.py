"""Unit tests cho P1-04 local file storage; chỉ dùng temporary directory."""

import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from app.documents.ports import FileStorage, InvalidStorageKeyError, StorageAlreadyExistsError, StorageError, build_document_storage_key
from app.infrastructure.storage import LocalFileStorage, create_file_storage


class FailingStream(io.BytesIO):
    def __init__(self):
        super().__init__(b"partial-data")
        self._reads = 0

    def read(self, size=-1):
        self._reads += 1
        if self._reads > 1:
            raise OSError("simulated read failure")
        return super().read(7)


class LocalFileStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.storage = LocalFileStorage(self.root)

    def tearDown(self):
        self.temporary_directory.cleanup()

    @staticmethod
    def make_key(document_id=None, version_id=None):
        return build_document_storage_key(
            str(document_id or uuid4()),
            str(version_id or uuid4()),
        )

    def test_implements_file_storage_contract_and_crud(self):
        self.assertIsInstance(self.storage, FileStorage)
        key = self.make_key()
        result = self.storage.save(key, b"raw document")

        self.assertEqual(result.storage_key, key)
        self.assertTrue(self.storage.exists(key))
        self.assertEqual(self.storage.read(key), b"raw document")
        with self.storage.open(key) as stream:
            self.assertEqual(stream.read(), b"raw document")
        self.assertTrue(self.storage.delete(key))
        self.assertFalse(self.storage.exists(key))
        self.assertFalse(self.storage.delete(key))

    def test_same_user_filename_cannot_collide_across_documents(self):
        # Filename không phải input của key builder; cùng tên upload vẫn có key khác.
        first = self.make_key()
        second = self.make_key()
        self.assertNotEqual(first, second)
        self.storage.save(first, b"first same.pdf")
        self.storage.save(second, b"second same.pdf")
        self.assertEqual(self.storage.read(first), b"first same.pdf")
        self.assertEqual(self.storage.read(second), b"second same.pdf")

    def test_versions_of_same_document_have_distinct_keys(self):
        document_id = uuid4()
        first = self.make_key(document_id=document_id)
        second = self.make_key(document_id=document_id)
        self.assertNotEqual(first, second)

    def test_sha256_is_computed_while_saving(self):
        content = b"checksum content"
        result = self.storage.save(self.make_key(), io.BytesIO(content))
        self.assertEqual(result.checksum_sha256, hashlib.sha256(content).hexdigest())
        self.assertEqual(result.size_bytes, len(content))

    def test_path_traversal_and_noncanonical_keys_are_rejected(self):
        invalid_keys = (
            "../outside",
            "documents/../../outside",
            "/absolute/path",
            "documents\\outside",
            "C:/outside",
        )
        for key in invalid_keys:
            with self.subTest(key=key), self.assertRaises(InvalidStorageKeyError):
                self.storage.exists(key)

    def test_existing_version_is_never_overwritten(self):
        key = self.make_key()
        self.storage.save(key, b"immutable")
        with self.assertRaises(StorageAlreadyExistsError):
            self.storage.save(key, b"replacement")
        self.assertEqual(self.storage.read(key), b"immutable")

    def test_failed_write_leaves_no_target_or_temporary_file(self):
        key = self.make_key()
        with self.assertRaises(StorageError):
            self.storage.save(key, FailingStream())
        self.assertFalse(self.storage.exists(key))
        self.assertEqual(list(self.root.rglob(".storage-*.tmp")), [])

    def test_key_builder_requires_uuid_ids(self):
        with self.assertRaises(InvalidStorageKeyError):
            build_document_storage_key("../../document", str(uuid4()))

    def test_factory_uses_configured_local_backend_and_documents_dir(self):
        class Config:
            storage_backend = "local"
            documents_dir = str(self.root / "configured")

        configured = create_file_storage(Config())
        self.assertIsInstance(configured, LocalFileStorage)
        self.assertEqual(configured.root, (self.root / "configured").resolve())

    def test_factory_rejects_unimplemented_backend(self):
        class Config:
            storage_backend = "s3"
            documents_dir = str(self.root)

        with self.assertRaises(StorageError):
            create_file_storage(Config())


if __name__ == "__main__":
    unittest.main()

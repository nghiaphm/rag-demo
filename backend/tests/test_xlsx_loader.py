"""Exercise the real optional XLSX parser without cloud/provider access."""

import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from app.rag.loaders.files import load_document


class XlsxLoaderTests(unittest.TestCase):
    def test_xlsx_optional_dependencies_parse_workbook_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Knowledge"
            sheet.append(["Topic", "Description"])
            sheet.append(["Access", "Request access through the service desk."])
            sheet.append(["Backup", "Backups run every evening."])
            workbook.save(path)
            workbook.close()

            with patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")):
                documents = load_document(path)

            self.assertTrue(documents)
            self.assertIn("service desk", "\n".join(document.page_content for document in documents))
            for document in documents:
                self.assertEqual(document.metadata["file_name"], path.name)
                self.assertEqual(document.metadata["source"], str(path))


if __name__ == "__main__":
    unittest.main()

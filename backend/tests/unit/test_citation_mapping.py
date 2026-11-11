"""P3-02 server-side citation eligibility and mapping tests."""

import unittest
from uuid import uuid4

from langchain_core.documents import Document

from app.chat.citation_mapping import map_verified_citations
from app.rag.prompt import SYSTEM_INSTRUCTION, format_context


class CitationMappingTests(unittest.TestCase):
    @staticmethod
    def source(*, page=0, **overrides) -> dict:
        value = {
            "chunk_id": str(uuid4()),
            "document_id": str(uuid4()),
            "version_id": str(uuid4()),
            "file_name": "guide.md",
            "page": page,
        }
        value.update(overrides)
        return value

    def test_sources_are_candidates_but_only_referenced_ordinals_are_citations(self):
        first = self.source(page=1)
        second = self.source(page=2)
        third = self.source(page=3)
        citations = map_verified_citations(
            "Dùng nguồn thứ hai [2], rồi nguồn đầu [1].",
            [first, second, third],
        )
        self.assertEqual(
            [item["chunk_id"] for item in citations],
            [second["chunk_id"], first["chunk_id"]],
        )
        self.assertNotIn(third["chunk_id"], {item["chunk_id"] for item in citations})

    def test_duplicate_out_of_range_and_zero_ordinals_are_ignored(self):
        source = self.source()
        citations = map_verified_citations("[0] [1] [1] [2]", [source])
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["chunk_id"], source["chunk_id"])

    def test_invalid_ids_or_page_are_not_eligible(self):
        invalid_id = self.source(chunk_id="model-invented-id")
        invalid_page = self.source(page=-1)
        self.assertEqual(
            map_verified_citations("[1] [2]", [invalid_id, invalid_page]),
            [],
        )

    def test_uuid_text_or_model_supplied_citation_object_is_never_trusted(self):
        source = self.source()
        invented = str(uuid4())
        answer = f"Model says citation_id={invented} without a source ordinal."
        self.assertEqual(map_verified_citations(answer, [source]), [])

    def test_no_marker_and_fallback_have_no_citations(self):
        source = self.source()
        self.assertEqual(map_verified_citations("Không tìm thấy thông tin trong tài liệu", [source]), [])

    def test_context_ordinals_are_stable_and_prompt_forbids_invented_ids(self):
        context = format_context(
            [
                Document(page_content="first", metadata={"file_name": "a.md"}),
                Document(page_content="second", metadata={"file_name": "b.md"}),
            ]
        )
        self.assertLess(context.index("[1]"), context.index("[2]"))
        self.assertIn("đúng số thứ tự nguồn", SYSTEM_INSTRUCTION)
        self.assertIn("không tự tạo UUID", SYSTEM_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()

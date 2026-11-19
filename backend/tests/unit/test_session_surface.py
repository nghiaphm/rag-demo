"""Offline tests for session surface defaulting, legacy migration compatibility, and repository filtering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.conversations.models import SessionRecord, SessionSurface  # noqa: E402
from app.conversations.repository import MongoConversationRepository  # noqa: E402
from app.conversations.service import ConversationService  # noqa: E402


class _Cursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, *_args):
        return self

    def skip(self, offset: int):
        self._docs = self._docs[offset:]
        return self

    def limit(self, limit: int):
        self._docs = self._docs[:limit]
        return self

    def __iter__(self):
        return iter(self._docs)


def _matches_clause(doc: dict, clause: dict) -> bool:
    for key, expected in clause.items():
        if key == "$or":
            if not any(_matches_clause(doc, branch) for branch in expected):
                return False
        elif isinstance(expected, dict) and "$exists" in expected:
            exists = key in doc
            if exists != bool(expected["$exists"]):
                return False
        else:
            if doc.get(key) != expected:
                return False
    return True


class _FakeSessionCollection:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs

    def insert_one(self, doc: dict) -> None:
        self.docs.append(dict(doc))

    def count_documents(self, query: dict) -> int:
        return sum(1 for doc in self.docs if _matches_clause(doc, query))

    def find(self, query: dict) -> _Cursor:
        matched = [dict(doc) for doc in self.docs if _matches_clause(doc, query)]
        return _Cursor(matched)


class SessionSurfaceTests(unittest.TestCase):
    def test_legacy_session_without_or_null_surface_defaults_to_workspace(self) -> None:
        legacy = SessionRecord(title="Legacy chat")
        self.assertEqual(legacy.surface, SessionSurface.WORKSPACE)

        raw_missing = legacy.to_mongo()
        raw_missing.pop("surface", None)
        validated_missing = SessionRecord.model_validate(raw_missing)
        self.assertEqual(validated_missing.surface, SessionSurface.WORKSPACE)

        raw_null = legacy.to_mongo()
        raw_null["surface"] = None
        validated_null = SessionRecord.model_validate(raw_null)
        self.assertEqual(validated_null.surface, SessionSurface.WORKSPACE)

    def test_repository_filters_hr_and_workspace_including_legacy_records(self) -> None:
        ws = SessionRecord(title="Workspace session", surface=SessionSurface.WORKSPACE).to_mongo()
        hr = SessionRecord(title="HR session", surface=SessionSurface.HR).to_mongo()
        legacy = SessionRecord(title="Legacy without surface").to_mongo()
        legacy.pop("surface", None)
        null_surface = SessionRecord(title="Legacy null surface").to_mongo()
        null_surface["surface"] = None
        deleted_hr = SessionRecord(title="Deleted HR", surface=SessionSurface.HR).to_mongo()
        deleted_hr["deleted_at"] = ws["created_at"]

        sessions_col = _FakeSessionCollection([ws, hr, legacy, null_surface, deleted_hr])
        repo = MongoConversationRepository({"sessions": sessions_col, "messages": _FakeSessionCollection([])})
        service = ConversationService(repo)

        hr_page = service.list_sessions(surface=SessionSurface.HR)
        self.assertEqual(hr_page.total, 1)
        self.assertEqual([item.title for item in hr_page.items], ["HR session"])

        ws_page = service.list_sessions(surface=SessionSurface.WORKSPACE)
        self.assertEqual(ws_page.total, 3)
        self.assertEqual(
            {item.title for item in ws_page.items},
            {"Workspace session", "Legacy without surface", "Legacy null surface"},
        )

        created_hr = service.create_session(title="New HR chat", surface=SessionSurface.HR)
        self.assertEqual(created_hr.surface, SessionSurface.HR)
        self.assertEqual(service.list_sessions(surface=SessionSurface.HR).total, 2)


if __name__ == "__main__":
    unittest.main()

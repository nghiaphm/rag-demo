"""Concurrency policy tests cho one active generation per session."""

import asyncio
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from app.conversations.repository import SessionGenerationConflictError
from app.conversations.service import ConversationService


class AtomicGuardRepository:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_request_id = None
        self.next_sequence = 1
        self.pairs = []
        self.finalized = []

    def begin_generation(self, session_id, request_id):
        with self.lock:
            if self.active_request_id is not None:
                raise SessionGenerationConflictError()
            self.active_request_id = request_id
            first = self.next_sequence
            self.next_sequence += 2
            return first, first + 1

    def release_generation(self, session_id, request_id):
        with self.lock:
            if self.active_request_id != request_id:
                raise AssertionError("non-owner released guard")
            self.active_request_id = None

    def create_message_pair(self, user, assistant):
        self.pairs.append((user, assistant))

    def finalize_assistant_message(self, message):
        self.finalized.append(message)
        return message


class ConversationConcurrencyTests(unittest.TestCase):
    def test_two_simultaneous_requests_allow_only_one_generation(self):
        repository = AtomicGuardRepository()
        service = ConversationService(repository)
        started = threading.Event()
        finish = threading.Event()

        def slow_generate():
            started.set()
            if not finish.wait(timeout=5):
                raise TimeoutError("test generation did not resume")
            return {"answer": "first", "sources": []}

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(
                service.answer_with_persistence,
                session_id="8a424056-e6cb-4a7f-8163-a20d3fbc3590",
                question="first",
                generate=slow_generate,
                model="test/model",
            )
            self.assertTrue(started.wait(timeout=5))
            second = executor.submit(
                service.answer_with_persistence,
                session_id="8a424056-e6cb-4a7f-8163-a20d3fbc3590",
                question="second",
                generate=lambda: {"answer": "second", "sources": []},
                model="test/model",
            )
            with self.assertRaises(SessionGenerationConflictError):
                second.result(timeout=5)
            finish.set()
            self.assertEqual(first.result(timeout=5)["answer"], "first")

        self.assertIsNone(repository.active_request_id)
        self.assertEqual(len(repository.pairs), 1)

        result = service.answer_with_persistence(
            session_id="8a424056-e6cb-4a7f-8163-a20d3fbc3590",
            question="third",
            generate=lambda: {"answer": "third", "sources": []},
            model="test/model",
        )
        self.assertEqual(result["answer"], "third")
        self.assertEqual([pair[0].sequence for pair in repository.pairs], [1, 3])

    def test_cancelled_generation_releases_guard(self):
        repository = AtomicGuardRepository()
        service = ConversationService(repository)

        with self.assertRaises(asyncio.CancelledError):
            service.answer_with_persistence(
                session_id="8a424056-e6cb-4a7f-8163-a20d3fbc3590",
                question="cancel",
                generate=lambda: (_ for _ in ()).throw(asyncio.CancelledError()),
                model="test/model",
            )

        self.assertIsNone(repository.active_request_id)
        self.assertEqual(repository.finalized[-1].error_code, "GENERATION_CANCELLED")


if __name__ == "__main__":
    unittest.main()

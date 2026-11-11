"""Overlapped real API/pipeline/rewrite/retriever/persistence with fake I/O only."""
import asyncio
import json
from copy import deepcopy
from threading import Barrier, RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi import FastAPI
from langchain_core.messages import AIMessageChunk
from pymongo import ReturnDocument

from app.api.routes.chat import router
from app.conversations.models import SessionRecord
from app.conversations.repository import MongoConversationRepository
from app.conversations.service import ConversationService
from app.chat.query_rewriting import ProviderRewrite, QueryRewriter
from app.rag.retriever import get_retriever
from app.api.streaming.sse_schema import SSETranscript
from app.rag.vector_index import VectorSearchResult


class Cursor(list):
    def sort(self, keys):
        for key, order in reversed(keys):
            super().sort(key=lambda value: value[key], reverse=order < 0)
        return self

    def skip(self, count):
        return Cursor(self[count:])

    def limit(self, count):
        return Cursor(self[:count])


class Collection:
    """Thread-safe fake storage; production repository still builds all queries."""
    def __init__(self):
        self.values = []
        self.lock = RLock()

    @staticmethod
    def matches(value, query):
        return all(value.get(k) in v["$in"] if isinstance(v, dict) and "$in" in v
                   else value.get(k) == v for k, v in query.items())

    def insert_one(self, value):
        with self.lock:
            assert not any(v["_id"] == value["_id"] for v in self.values)
            self.values.append(deepcopy(value))

    def insert_many(self, values, **_kwargs):
        for value in values:
            self.insert_one(value)

    def find(self, query):
        with self.lock:
            return Cursor(deepcopy([v for v in self.values if self.matches(v, query)]))

    def find_one(self, query):
        return next(iter(self.find(query)), None)

    def count_documents(self, query):
        return len(self.find(query))

    def find_one_and_update(self, query, update, **kwargs):
        with self.lock:
            for value in self.values:
                if self.matches(value, query):
                    before = deepcopy(value)
                    value.update(update.get("$set", {}))
                    for key, amount in update.get("$inc", {}).items():
                        value[key] = value.get(key, 0) + amount
                    for key in update.get("$unset", {}):
                        value.pop(key, None)
                    return deepcopy(value) if kwargs.get("return_document") == ReturnDocument.AFTER else before
        return None

    def update_one(self, query, update):
        result = self.find_one_and_update(query, update)
        return SimpleNamespace(matched_count=int(result is not None))

    def replace_one(self, query, replacement):
        with self.lock:
            for i, value in enumerate(self.values):
                if self.matches(value, query):
                    self.values[i] = deepcopy(replacement)
                    return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


class MultiSessionIsolationTests(unittest.TestCase):
    def run_pair(self, *, same=True, failure=None, independent=False):
        # Resolve actual collection names rather than assume storage naming.
        from app.conversations.indexes import SESSIONS_COLLECTION, MESSAGES_COLLECTION
        database = {SESSIONS_COLLECTION: Collection(), MESSAGES_COLLECTION: Collection()}
        repository = MongoConversationRepository(database)
        service = ConversationService(repository)
        sessions = [repository.create_session(SessionRecord()) for _ in range(2)]
        tags = ("Alpha", "Beta")
        versions = {tag: str(uuid4()) for tag in tags}
        documents = {tag: str(uuid4()) for tag in tags}
        chunks = {tag: str(uuid4()) for tag in tags}
        for session, tag in zip(sessions, tags):
            service.answer_with_persistence(session_id=session.session_id,
                question=f"Tell me {tag} policy", model="qa/mock",
                generate=lambda tag=tag: {"answer": f"{tag} policy history", "sources": []})

        rewrite_barrier, embedding_barrier = Barrier(2), Barrier(2)
        observations = {"rewrite": [], "embedding": [], "retrieval": [], "prompts": [], "stream_peak": 0}
        lock = RLock()

        class RewriteProvider:
            async def rewrite(self, prompt):
                tag = "Alpha" if "Alpha" in prompt else "Beta"
                with lock:
                    observations["rewrite"].append((tag, prompt))
                await asyncio.to_thread(rewrite_barrier.wait, 5)
                if failure == "rewrite" and tag == "Beta":
                    raise TimeoutError("synthetic rewrite unavailable")
                return ProviderRewrite(content=f"{tag} policy")

        class Embeddings:
            def embed_query(self, query):
                with lock:
                    observations["embedding"].append(query)
                embedding_barrier.wait(5)
                if failure == "embedding" and "Beta" in query:
                    raise TimeoutError("synthetic embedding timeout")
                return [1.0 if "Alpha" in query else 2.0 if "Beta" in query else 0.0]

        class Index:
            def query(self, vector, *, limit, filters):
                tag = "Alpha" if vector[0] == 1 else "Beta" if vector[0] == 2 else "Common"
                with lock:
                    observations["retrieval"].append((tag, filters.version_ids))
                if failure == "vector" and tag == "Beta":
                    raise TimeoutError("synthetic Qdrant timeout")
                if (failure == "empty" and tag == "Beta") or (failure == "rewrite" and tag == "Common"):
                    return []
                source_tag = "Alpha" if tag == "Common" else tag
                return [VectorSearchResult(point_id=chunks[source_tag], document_id=documents[source_tag],
                    version_id=versions[source_tag], chunk_index=0, file_name=f"{tag}.txt",
                    chunk_text=f"CONTEXT_{tag}", score=1.0, page=0)]

        async def exercise():
            opened = asyncio.Event()
            count = 0
            expected = 1 if failure in {"embedding", "vector"} else 2

            class LLM:
                async def astream(self, prompt):
                    nonlocal count
                    human = prompt.to_messages()[-1].content
                    tag = "Alpha" if "Alpha policy history" in human else "Beta"
                    observations["prompts"].append((tag, human))
                    count += 1
                    observations["stream_peak"] = max(observations["stream_peak"], count)
                    if count == expected:
                        opened.set()
                    await asyncio.wait_for(opened.wait(), 5)
                    if failure == "llm_pre" and tag == "Beta":
                        raise RuntimeError("synthetic provider rate limit before content")
                    context = human.split("Context:\n", 1)[1].split("\n\nCâu hỏi gốc:", 1)[0]
                    answer = "Không tìm thấy thông tin trong tài liệu." if "(không có tài liệu liên quan)" in context else f"{tag}: {context.splitlines()[-1]} [1]"
                    yield AIMessageChunk(content=answer)
                    if failure == "llm" and tag == "Beta":
                        raise RuntimeError("synthetic provider rate limit")

            llm, embeddings, index = LLM(), Embeddings(), Index()
            app = FastAPI()
            app.include_router(router)
            app.state.cloud_connections = SimpleNamespace(mongodb=SimpleNamespace(database=database), qdrant=SimpleNamespace(client=object()))
            with patch("app.chat.pipeline.MongoDocumentRepository", return_value=SimpleNamespace(list_active_version_ids=lambda: list(versions.values()))), \
                patch("app.chat.pipeline.create_query_rewriter", side_effect=lambda _settings: QueryRewriter(RewriteProvider(), timeout_seconds=10, max_chars=200)), \
                patch("app.chat.pipeline.get_retriever", side_effect=lambda **kwargs: get_retriever(embeddings=embeddings, vector_index=index, active_version_ids=kwargs["active_version_ids"])), \
                patch("app.chat.pipeline.get_llm", return_value=llm):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://offline.test") as client:
                    questions = ["Explain common policy"] * 2 if independent else ["What about it?", "What about it?" if same else "How about that policy?"]
                    return await asyncio.gather(*(client.post("/chat/stream", json={"question": q, "session_id": s.session_id}) for q, s in zip(questions, sessions)))

        responses = asyncio.run(exercise())
        self.assertEqual(len(observations["embedding"]), 2)
        self.assertEqual(observations["stream_peak"], 1 if failure in {"embedding", "vector"} else 2)
        self.assertEqual(len(observations["rewrite"]), 0 if independent else 2)
        for tag, prompt in observations["rewrite"]:
            self.assertNotIn("Beta" if tag == "Alpha" else "Alpha", prompt)
        for tag, prompt in observations["prompts"]:
            self.assertNotIn(f"{'Beta' if tag == 'Alpha' else 'Alpha'} policy history", prompt)
        for _tag, allowed in observations["retrieval"]:
            self.assertEqual(set(allowed), set(versions.values()))
        seed = [message for session in sessions for message in repository.list_messages(session.session_id)[0][:2]]
        all_ids = {message.message_id for message in seed}
        requests = {message.request_id for message in seed}
        for i, (response, session, tag) in enumerate(zip(responses, sessions, tags)):
            persisted, total = repository.list_messages(session.session_id)
            self.assertTrue(all(m.session_id == session.session_id for m in persisted))
            self.assertIsNone(repository.get_session(session.session_id).active_generation_id)
            if i == 1 and failure in {"embedding", "vector"}:
                self.assertEqual(response.status_code, 502)
                self.assertNotIn("Không tìm thấy", response.text)
                self.assertEqual(total, 2)
                continue
            self.assertEqual(response.status_code, 200)
            frames = [(frame.splitlines()[0][7:], json.loads(frame.split("data: ", 1)[1])) for frame in response.text.strip().split("\n\n")]
            transcript = SSETranscript.model_validate({"events": [{"event": event, "data": data} for event, data in frames]})
            start, metadata, terminal = frames[0][1], frames[1][1], frames[-1]
            self.assertEqual([event for event, _ in frames[:3]], ["start", "metadata", "error" if failure == "llm_pre" and i == 1 else "delta"])
            self.assertEqual(start["session_id"], session.session_id)
            self.assertNotIn(start["request_id"], requests)
            requests.add(start["request_id"])
            for key in ("user_message_id", "assistant_message_id"):
                self.assertNotIn(start[key], all_ids)
                all_ids.add(start[key])
            self.assertEqual(total, 4)
            user, assistant = persisted[-2:]
            self.assertEqual((user.message_id, assistant.message_id), (start["user_message_id"], start["assistant_message_id"]))
            self.assertEqual(user.request_id, start["request_id"])
            self.assertEqual(assistant.request_id, start["request_id"])
            self.assertEqual(assistant.content, transcript.reconstructed_answer)
            self.assertEqual(assistant.status.value, terminal[1]["status"])
            self.assertEqual(terminal[0], "error" if failure in {"llm", "llm_pre"} and i == 1 else "done")
            if terminal[0] == "error":
                self.assertEqual(terminal[1]["error"]["code"], "RAG_STREAM_ERROR")
                self.assertEqual(assistant.error_code, "RAG_STREAM_ERROR")
                self.assertNotIn("synthetic", response.text)
            empty = i == 1 and failure in {"empty", "rewrite"}
            if failure == "llm_pre" and i == 1:
                self.assertEqual(assistant.content, "")
                self.assertEqual(assistant.status.value, "FAILED")
            elif empty:
                self.assertEqual(metadata["sources"], [])
                self.assertEqual(assistant.content, "Không tìm thấy thông tin trong tài liệu.")
            else:
                self.assertEqual(len(metadata["sources"]), 1)
                self.assertIn(f"{tag}: CONTEXT_{'Common' if independent else tag}", assistant.content)
                source_tag = "Alpha" if independent else tag
                self.assertEqual(metadata["sources"][0]["chunk_id"], chunks[source_tag])
                self.assertEqual(metadata["sources"][0]["document_id"], documents[source_tag])
                self.assertEqual(metadata["sources"][0]["version_id"], versions[source_tag])
                self.assertNotIn(f"CONTEXT_{'Beta' if tag == 'Alpha' else 'Alpha'}", assistant.content)
        return observations

    def test_same_followup_distinct_histories_overlap_without_contamination(self):
        self.run_pair()

    def test_different_followups_overlap_without_contamination(self):
        self.run_pair(same=False)

    def test_same_independent_query_can_share_all_active_documents(self):
        self.run_pair(independent=True)

    def test_one_llm_error_does_not_fail_other_session(self):
        self.run_pair(failure="llm")

    def test_embedding_timeout_is_http_error_not_no_information_answer(self):
        self.run_pair(failure="embedding")

    def test_provider_error_before_content_is_failed_not_no_information_answer(self):
        self.run_pair(failure="llm_pre")

    def test_vector_timeout_is_http_error_not_no_information_answer(self):
        self.run_pair(failure="vector")

    def test_empty_retrieval_can_produce_prompt_refusal_without_collision(self):
        self.run_pair(failure="empty")

    def test_rewrite_provider_failure_falls_back_to_original_query(self):
        observed = self.run_pair(failure="rewrite")
        self.assertIn("What about it?", observed["embedding"])

    def test_missing_qdrant_collection_returns_empty_results(self):
        from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
        client = SimpleNamespace(collection_exists=lambda _name: False,
                                 query_points=lambda **_kwargs: self.fail("Missing collection must not query points"))
        index = QdrantVectorIndex(client, "offline-fixture")
        self.assertEqual(index.query([1.0], limit=5), [])

    def test_no_active_versions_skips_embedding_and_vector_query(self):
        retriever = get_retriever(active_version_ids=(),
            embeddings=SimpleNamespace(embed_query=lambda _q: self.fail("No active versions must skip embedding")),
            vector_index=SimpleNamespace(query=lambda *_args, **_kwargs: self.fail("No active versions must skip vector query")))
        self.assertEqual(retriever.invoke("fixture"), [])

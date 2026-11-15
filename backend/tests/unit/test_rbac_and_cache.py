"""Offline unit tests for Phase 4 Auth/RBAC, Access-aware VectorFilter, Semantic Cache, and Rate Limiting."""

from __future__ import annotations

import unittest
from uuid import uuid4

from app.chat.context_budget import ContextBudgetConfig
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.infrastructure.semantic_cache import RedisRateLimiter, RedisSemanticCache
from app.rag.vector_index import VectorFilter, VectorRecord
from app.shared.auth import (
    AuthTokenError,
    UserContext,
    UserRole,
    can_access_resource,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.shared.cache import build_permission_scope, build_version_snapshot


class TestAuthAndRbac(unittest.TestCase):
    def test_password_hashing_and_verification(self) -> None:
        hashed = hash_password("super-secret-123")
        self.assertTrue(verify_password("super-secret-123", hashed))
        self.assertFalse(verify_password("wrong-password", hashed))

    def test_jwt_create_decode_and_tamper_rejection(self) -> None:
        secret = "unit-test-secret-key"
        access = create_access_token(
            user_id="u-1",
            username="alice",
            roles=[UserRole.EDITOR.value],
            secret=secret,
            expires_minutes=15,
        )
        user = decode_token(access, secret=secret, expected_type="access")
        self.assertEqual(user.user_id, "u-1")
        self.assertEqual(user.username, "alice")
        self.assertEqual(user.roles, ("editor",))

        with self.assertRaises(AuthTokenError):
            decode_token(access, secret="wrong-secret", expected_type="access")

        refresh = create_refresh_token(
            user_id="u-1",
            username="alice",
            roles=[UserRole.EDITOR.value],
            secret=secret,
        )
        with self.assertRaises(AuthTokenError):
            decode_token(refresh, secret=secret, expected_type="access")

    def test_rbac_can_access_resource_prevents_idor(self) -> None:
        viewer = UserContext(user_id="u-viewer", username="bob", roles=("viewer",))
        editor = UserContext(user_id="u-editor", username="carol", roles=("editor",))
        admin = UserContext(user_id="u-admin", username="root", roles=("admin",))

        # Owner can always access
        self.assertTrue(can_access_resource(user=viewer, owner_id="u-viewer", allowed_roles=["admin"]))
        # Matching role can access
        self.assertTrue(can_access_resource(user=editor, owner_id="other", allowed_roles=["editor", "admin"]))
        # Cross-role IDOR denied
        self.assertFalse(can_access_resource(user=viewer, owner_id="other", allowed_roles=["editor", "admin"]))
        # Admin can access any resource
        self.assertTrue(can_access_resource(user=admin, owner_id="other", allowed_roles=["editor"]))
        # Anonymous (AUTH_ENABLED=false) is allowed
        self.assertTrue(can_access_resource(user=None, owner_id="other", allowed_roles=["admin"]))

    def test_access_aware_vector_filter_and_payload(self) -> None:
        doc_id = str(uuid4())
        ver_id = str(uuid4())
        point_id = str(uuid4())
        record = VectorRecord(
            point_id=point_id,
            document_id=doc_id,
            version_id=ver_id,
            chunk_index=0,
            file_name="secret.pdf",
            chunk_text="Confidential Q3 report",
            vector=(0.1, 0.2, 0.3),
            owner_id="u-owner",
            allowed_roles=("editor", "admin"),
        )
        payload = record.payload()
        self.assertEqual(payload["owner_id"], "u-owner")
        self.assertEqual(payload["allowed_roles"], ["editor", "admin"])

        vf = VectorFilter(
            version_ids=(ver_id,),
            owner_id="u-viewer",
            allowed_roles=("viewer",),
        )
        qdrant_filter = QdrantVectorIndex._to_qdrant_filter(vf)
        self.assertIsNotNone(qdrant_filter)
        self.assertEqual(len(qdrant_filter.must), 2)

    def test_context_budget_enforces_max_tokens_per_turn(self) -> None:
        with self.assertRaises(ValueError):
            ContextBudgetConfig(
                context_window_tokens=8192,
                system_max_tokens=1024,
                history_max_tokens=2048,
                chunks_max_tokens=3584,
                query_max_tokens=512,
                output_reserve_tokens=1024,
                max_tokens_per_turn=4096,
            )


class TestSemanticCacheAndRateLimiter(unittest.IsolatedAsyncioTestCase):
    async def test_semantic_cache_hits_above_threshold_and_isolates_rbac_scopes(self) -> None:
        cache = RedisSemanticCache()
        viewer = UserContext(user_id="u-1", username="v", roles=("viewer",))
        admin = UserContext(user_id="u-2", username="a", roles=("admin",))

        viewer_scope = build_permission_scope(viewer)
        admin_scope = build_permission_scope(admin)
        snapshot = build_version_snapshot(["v1", "v2"])

        await cache.set(
            query="What is Qdrant?",
            query_vector=[1.0, 0.0, 0.0],
            answer="Qdrant is a vector database.",
            sources=[{"file_name": "qdrant.md"}],
            permission_scope=admin_scope,
            active_version_snapshot=snapshot,
        )

        # Same scope + high cosine similarity (>= 0.95) -> HIT
        hit = await cache.get(
            query_vector=[0.99, 0.05, 0.0],
            permission_scope=admin_scope,
            active_version_snapshot=snapshot,
            threshold=0.95,
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit.answer, "Qdrant is a vector database.")

        # Different RBAC permission scope -> MUST MISS (no cache poisoning!)
        cross_scope = await cache.get(
            query_vector=[1.0, 0.0, 0.0],
            permission_scope=viewer_scope,
            active_version_snapshot=snapshot,
            threshold=0.95,
        )
        self.assertIsNone(cross_scope)

        # Different document version snapshot -> MUST MISS
        stale = await cache.get(
            query_vector=[1.0, 0.0, 0.0],
            permission_scope=admin_scope,
            active_version_snapshot=build_version_snapshot(["v1", "v3"]),
            threshold=0.95,
        )
        self.assertIsNone(stale)

        # Explicit invalidation -> MUST MISS
        await cache.invalidate_all()
        after_invalidation = await cache.get(
            query_vector=[1.0, 0.0, 0.0],
            permission_scope=admin_scope,
            active_version_snapshot=snapshot,
            threshold=0.95,
        )
        self.assertIsNone(after_invalidation)

    async def test_rate_limiter_enforces_per_user_limit(self) -> None:
        limiter = RedisRateLimiter()
        self.assertTrue(await limiter.allow("u-1", limit=2, window_seconds=60))
        self.assertTrue(await limiter.allow("u-1", limit=2, window_seconds=60))
        self.assertFalse(await limiter.allow("u-1", limit=2, window_seconds=60))
        # Different user still has independent quota
        self.assertTrue(await limiter.allow("u-2", limit=2, window_seconds=60))


if __name__ == "__main__":
    unittest.main()

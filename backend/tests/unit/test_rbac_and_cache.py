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

    async def test_redis_rate_limiter_atomic_lua_and_bounded_fallback_when_redis_fails(self) -> None:
        class _EvalThenDownRedis:
            def __init__(self) -> None:
                self.eval_calls: list[tuple[str, int, str, int]] = []
                self.fail = False
                self._counts: dict[str, int] = {}

            async def eval(self, script: str, numkeys: int, key: str, window: int) -> int:
                if self.fail:
                    raise ConnectionError("redis://:secret-pass@10.0.0.9:6379 connection reset")
                self.eval_calls.append((script, numkeys, key, window))
                self._counts[key] = self._counts.get(key, 0) + 1
                return self._counts[key]

        fake_redis = _EvalThenDownRedis()
        limiter = RedisRateLimiter(redis_client=fake_redis, max_memory_keys=3)

        # Normal path uses atomic Lua script with EXPIRE/TTL guard
        self.assertTrue(await limiter.allow("u-lua", limit=2, window_seconds=60))
        self.assertEqual(len(fake_redis.eval_calls), 1)
        self.assertIn("EXPIRE", fake_redis.eval_calls[0][0])
        self.assertIn("TTL", fake_redis.eval_calls[0][0])

        # Redis crashes mid-flight -> must NOT fail-open unconditionally or raise 500;
        # must enforce limit via bounded local memory and never leak Redis secret in logs!
        fake_redis.fail = True
        with self.assertLogs("app.infrastructure.semantic_cache", level="WARNING") as captured:
            self.assertTrue(await limiter.allow("u-down", limit=2, window_seconds=60))
            self.assertTrue(await limiter.allow("u-down", limit=2, window_seconds=60))
            self.assertFalse(await limiter.allow("u-down", limit=2, window_seconds=60))

        joined_logs = "\n".join(captured.output)
        self.assertNotIn("secret-pass", joined_logs)

        # Memory fallback stays strictly bounded at max_memory_keys=3
        for idx in range(10):
            await limiter.allow(f"flood-{idx}", limit=5, window_seconds=60)
        self.assertLessEqual(len(limiter._memory), 3)

    def test_resolve_client_ip_ignores_spoofed_xff_unless_from_trusted_proxy(self) -> None:
        from types import SimpleNamespace
        from app.api.dependencies.client_ip import resolve_client_ip

        def _req(direct_host: str | None, xff: str | None = None):
            headers = {"x-forwarded-for": xff} if xff is not None else {}
            client = SimpleNamespace(host=direct_host) if direct_host is not None else None
            return SimpleNamespace(client=client, headers=headers)

        # Untrusted direct client trying to spoof X-Forwarded-For -> ignored
        self.assertEqual(
            resolve_client_ip(_req("203.0.113.50", "198.51.100.77"), trusted_proxy_ips=()),
            "203.0.113.50",
        )
        self.assertEqual(
            resolve_client_ip(_req("203.0.113.50", "198.51.100.77"), trusted_proxy_ips=("10.0.0.1",)),
            "203.0.113.50",
        )

        # Trusted reverse proxy (exact IP or CIDR) -> extracts first valid client IP
        self.assertEqual(
            resolve_client_ip(_req("10.0.0.5", "198.51.100.88, 10.0.0.5"), trusted_proxy_ips=("10.0.0.0/8",)),
            "198.51.100.88",
        )
        self.assertEqual(
            resolve_client_ip(_req("127.0.0.1", "203.0.113.9"), trusted_proxy_ips=("127.0.0.1",)),
            "203.0.113.9",
        )

        # Malformed X-Forwarded-For from trusted proxy -> safely falls back to direct host
        self.assertEqual(
            resolve_client_ip(_req("127.0.0.1", "not-an-ip\r\ninjected"), trusted_proxy_ips=("127.0.0.1",)),
            "127.0.0.1",
        )


if __name__ == "__main__":
    unittest.main()

"""Provider-neutral construction tests for the Groq OpenAI-compatible LLM."""

import unittest
from unittest.mock import patch

from app.rag import llm


class LLMFactoryTests(unittest.TestCase):
    def tearDown(self) -> None:
        llm.get_llm.cache_clear()
        if hasattr(llm, "get_grader_llm"):
            llm.get_grader_llm.cache_clear()

    def test_factory_uses_groq_key_base_url_configured_model_timeout_and_retries(self):
        sentinel = object()
        llm.get_llm.cache_clear()
        with patch("app.rag.llm.ChatOpenAI", return_value=sentinel) as constructor:
            self.assertIs(llm.get_llm(), sentinel)
            self.assertIs(llm.get_llm(), sentinel)

        constructor.assert_called_once_with(
            model=llm.settings.llm_model,
            api_key=llm.settings.groq_api_key.get_secret_value(),
            base_url=llm.settings.openai_base_url,
            timeout=llm.settings.llm_request_timeout_seconds,
            max_retries=llm.settings.llm_max_retries,
        )

    def test_grader_llm_and_embeddings_use_secret_str_and_timeouts(self):
        from pydantic import SecretStr
        from app.rag import embeddings
        from app.shared.config import Settings

        cfg = Settings(
            _env_file=None,
            groq_api_key="gsk_placeholder_secret",  # pragma: allowlist secret
            embedding_api_key="AIza_placeholder_secret",  # pragma: allowlist secret
        )
        self.assertIsInstance(cfg.embedding_api_key, SecretStr)
        self.assertNotIn("AIza_placeholder_secret", repr(cfg))
        self.assertNotIn("AIza_placeholder_secret", str(cfg.model_dump()))

        embeddings.get_embeddings.cache_clear()
        sentinel_emb = object()
        with patch(
            "langchain_google_genai.GoogleGenerativeAIEmbeddings",
            return_value=sentinel_emb,
        ) as emb_cls:
            self.assertIs(embeddings.get_embeddings(), sentinel_emb)

        emb_cls.assert_called_once_with(
            model=embeddings.settings.embedding_model,
            google_api_key=embeddings.settings.embedding_api_key.get_secret_value(),
            request_options={"timeout": embeddings.settings.embedding_timeout_seconds},
        )
        embeddings.get_embeddings.cache_clear()

    def test_startup_guard_rejects_weak_default_jwt_secret_when_auth_enabled(self):
        from pydantic import ValidationError
        from app.shared.config import Settings

        for weak_secret in (
            "dev-insecure-secret-change-in-production",
            "replace-with-strong-random-secret",
            "changeme",
            "short-secret",
        ):
            with self.subTest(secret=weak_secret), self.assertRaises(ValidationError):
                Settings(
                    _env_file=None,
                    groq_api_key="gsk_placeholder_test",  # pragma: allowlist secret
                    embedding_api_key="AIza_placeholder_test",  # pragma: allowlist secret
                    auth_enabled=True,
                    jwt_secret_key=weak_secret,  # pragma: allowlist secret
                )

        valid_cfg = Settings(
            _env_file=None,
            groq_api_key="gsk_placeholder_test",  # pragma: allowlist secret
            embedding_api_key="AIza_placeholder_test",  # pragma: allowlist secret
            auth_enabled=True,
            jwt_secret_key="strong-production-jwt-signing-key-at-least-32-chars",  # pragma: allowlist secret
        )
        self.assertTrue(valid_cfg.auth_enabled)


if __name__ == "__main__":
    unittest.main()

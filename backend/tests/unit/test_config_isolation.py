"""Unit tests verifying unittest-compatible test config isolation from local .env."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import app.shared.config as config_mod
from app.shared.config import Settings, settings
from tests._test_env import install_test_environment, override_settings


class TestConfigIsolation(unittest.TestCase):
    def test_settings_ignore_local_dotenv_feature_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            noisy_dotenv = Path(tmpdir) / ".env"
            noisy_dotenv.write_text(
                "\n".join(
                    [
                        "GROQ_API_KEY=gsk_placeholder_noisy_dotenv_123",  # pragma: allowlist secret
                        "EMBEDDING_API_KEY=AIza_placeholder_noisy_dotenv_123",  # pragma: allowlist secret
                        "TOOL_USE_ENABLED=true",
                        "AGENTIC_MODE_ENABLED=true",
                        "STORAGE_BACKEND=s3",
                        "S3_BUCKET=noisy-local-bucket",
                        "EXCEL_PARQUET_INGESTION_ENABLED=true",
                        "EXCEL_SQL_ENABLED=true",
                        "CORRECTIVE_RAG_ENABLED=true",
                    ]
                ),
                encoding="utf-8",
            )
            install_test_environment(dotenv_path_for_check=noisy_dotenv, force=True)

            self.assertFalse(settings.tool_use_enabled)
            self.assertFalse(settings.agentic_mode_enabled)
            self.assertFalse(settings.excel_sql_enabled)
            self.assertFalse(settings.excel_parquet_ingestion_enabled)
            self.assertFalse(settings.corrective_rag_enabled)
            self.assertEqual(settings.storage_backend, "local")

            fresh = Settings(langfuse_enabled=False)
            self.assertFalse(fresh.agentic_mode_enabled)
            self.assertEqual(fresh.storage_backend, "local")
            self.assertIs(config_mod.get_settings(), settings)

    def test_override_settings_applies_and_restores_on_exception(self) -> None:
        original_top_k = settings.top_k
        original_agentic = settings.agentic_mode_enabled

        with self.assertRaises(RuntimeError):
            with override_settings(top_k=12, agentic_mode_enabled=True):
                self.assertEqual(settings.top_k, 12)
                self.assertTrue(settings.agentic_mode_enabled)
                raise RuntimeError("boom")

        self.assertEqual(settings.top_k, original_top_k)
        self.assertEqual(settings.agentic_mode_enabled, original_agentic)


if __name__ == "__main__":
    unittest.main()

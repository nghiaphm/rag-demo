"""Deterministic offline test configuration isolation compatible with Python unittest.

Prevents developer-local `.env` feature flags (e.g. AGENTIC_MODE_ENABLED,
EXCEL_SQL_ENABLED, STORAGE_BACKEND=s3) from leaking into unit and integration
suites while keeping explicit process environment overrides functional for CI.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import sys
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_INSTALLED = False

_REQUIRED_FALLBACK_ENV: dict[str, str] = {
    "GROQ_API_KEY": "gsk_offline_unittest_placeholder_key",
    "EMBEDDING_API_KEY": "AIza_offline_unittest_placeholder_key",
}


def install_test_environment(
    *,
    dotenv_path_for_check: Path | None = None,
    force: bool = False,
) -> None:
    """Isolate `app.shared.config.settings` and `Settings` from `.env` files on disk."""
    global _INSTALLED  # noqa: PLW0603
    if _INSTALLED and not force:
        return

    for env_key, placeholder in _REQUIRED_FALLBACK_ENV.items():
        if not os.environ.get(env_key, "").strip():
            os.environ[env_key] = placeholder

    import app.shared.config as config_mod

    if dotenv_path_for_check is not None:
        # Simulate a noisy .env path first, then neutralize env_file loading.
        config_mod.Settings.model_config["env_file"] = dotenv_path_for_check

    config_mod.Settings.model_config["env_file"] = None
    clean_settings = config_mod.Settings(_env_file=None)

    target = config_mod.settings
    for field_name in config_mod.Settings.model_fields:
        object.__setattr__(target, field_name, getattr(clean_settings, field_name))

    _clear_cached_providers()
    _INSTALLED = True


def _clear_cached_providers() -> None:
    for mod_name, fn_name in (
        ("app.rag.llm", "get_llm"),
        ("app.rag.llm", "get_grader_llm"),
        ("app.rag.embeddings", "get_embeddings"),
    ):
        mod = sys.modules.get(mod_name)
        fn = getattr(mod, fn_name, None) if mod is not None else None
        cache_clear = getattr(fn, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


@contextmanager
def override_settings(**overrides: Any) -> Iterator[Any]:
    """Temporarily override fields on `app.shared.config.settings` and restore in finally."""
    install_test_environment()
    import app.shared.config as config_mod

    target = config_mod.settings
    unknown = set(overrides) - set(config_mod.Settings.model_fields)
    if unknown:
        raise KeyError(f"Unknown Settings field(s): {sorted(unknown)}")

    previous = {key: getattr(target, key) for key in overrides}
    try:
        for key, value in overrides.items():
            object.__setattr__(target, key, value)
        _clear_cached_providers()
        yield target
    finally:
        for key, value in previous.items():
            object.__setattr__(target, key, value)
        _clear_cached_providers()

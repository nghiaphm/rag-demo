"""Domain/application events do Chat phát ra; không biết gì về SSE hay HTTP."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderStreamChunk:
    """Normalized provider output; usage can arrive in a textless final chunk."""

    content: str | None
    usage: dict[str, int] | None

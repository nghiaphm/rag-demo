"""Kết quả health-check dùng chung cho các cloud connection adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ConnectionStatus:
    """Kết quả công khai; không chứa URI, API key hoặc raw exception."""

    service: str
    ok: bool
    code: str
    message: str

    def to_dict(self) -> dict[str, str | bool]:
        return asdict(self)

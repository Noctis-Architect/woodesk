from __future__ import annotations

from dataclasses import dataclass, field

from ..api.http import ApiError


@dataclass
class AIResult:
    text: str
    usage: dict = field(default_factory=dict)
    remaining: int | None = None


class QuotaExceeded(ApiError):
    pass


class AIClient:
    def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: int | None = None) -> AIResult:
        raise NotImplementedError

    def list_models(self) -> list[str]:
        raise NotImplementedError

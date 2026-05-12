from __future__ import annotations

import asyncio
import time


class ProviderCooldownRegistry:
    """Skip providers that failed recently (circuit-breaker-lite)."""

    def __init__(self, cooldown_seconds: float = 60.0) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._until: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def should_skip(self, provider: str) -> bool:
        until = self._until.get(provider, 0.0)
        return time.monotonic() < until

    async def note_failure(self, provider: str) -> None:
        async with self._lock:
            self._until[provider] = time.monotonic() + self.cooldown_seconds

    async def note_success(self, provider: str) -> None:
        async with self._lock:
            self._until.pop(provider, None)

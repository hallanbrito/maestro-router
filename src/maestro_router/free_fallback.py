"""Experimental 0800 fallback and in-process quota reservations (NOT billing proof)."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class Limits:
    requests_per_minute: int
    requests_per_day: int
    tokens_per_minute: int
    tokens_per_day: int

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in (
            self.requests_per_minute, self.requests_per_day,
            self.tokens_per_minute, self.tokens_per_day,
        )):
            raise ValueError("Quota limits must be positive integers")


@dataclass(frozen=True)
class FreeRoute:
    id: str
    provider: str
    model: str
    scope: str
    limits: Limits
    verified_free_by_operator: bool = False


@dataclass(frozen=True)
class Outcome:
    status: str
    route: str | None
    answer: str | None
    attempts: tuple[tuple[str, str], ...]


class RejectedBeforeGeneration(Exception):
    """A provider conclusively rejects the request with HTTP 429."""


class TextAdapter(Protocol):
    async def execute(self, route: FreeRoute, prompt: str, max_output_tokens: int) -> str: ...


class SlidingQuota:
    """Single-process conservative sliding minute and 24h quotas, no refunds.

    Not actual provider balance: restarts, other clients and shared limits are
    not observed. Never run multi-worker with this ledger.
    """
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = asyncio.Lock()
        self._minute: dict[str, deque[tuple[float, int]]] = defaultdict(deque)
        self._day: dict[str, deque[tuple[float, int]]] = defaultdict(deque)

    async def reserve(self, scope: str, limits: Limits, token_reservation: int) -> bool:
        if not scope.strip() or type(token_reservation) is not int or token_reservation < 0:
            raise ValueError("Invalid quota reservation")
        async with self._lock:
            now = self._clock()
            minute, day = self._minute[scope], self._day[scope]
            while minute and now - minute[0][0] >= 60:
                minute.popleft()
            while day and now - day[0][0] >= 86400:
                day.popleft()
            if (len(minute) + 1 > limits.requests_per_minute
                or len(day) + 1 > limits.requests_per_day
                or sum(x[1] for x in minute) + token_reservation > limits.tokens_per_minute
                or sum(x[1] for x in day) + token_reservation > limits.tokens_per_day):
                return False
            minute.append((now, token_reservation))
            day.append((now, token_reservation))
            return True


class FreeOrchestrator:
    """Only operator-confirmed free routes; fallback only on explicit 429.

    Any ambiguous outcome (network, timeout, 5xx, partial output) stops replay.
    """
    def __init__(self, routes: tuple[FreeRoute, ...], adapters: dict[str, TextAdapter],
                 quota: SlidingQuota, *, max_attempts: int = 3,
                 max_output_tokens: int = 512):
        if not 1 <= max_attempts <= 3 or not 1 <= max_output_tokens <= 2048:
            raise ValueError("Invalid attempt or output budget")
        if len({r.id for r in routes}) != len(routes):
            raise ValueError("Duplicate route id")
        self.routes = routes
        self.adapters = dict(adapters)
        self.quota = quota
        self.max_attempts = max_attempts
        self.max_output_tokens = max_output_tokens

    async def run(self, prompt: str, *, live_allowed: bool) -> Outcome:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 6000:
            return Outcome("invalid_request", None, None, ())
        if not live_allowed:
            return Outcome("disabled", None, None, ())
        attempts: list[tuple[str, str]] = []
        outbound = 0
        # Conservative estimate, NOT a provider-proven upper bound for every tokenizer.
        reservation = len(prompt.encode("utf-8")) + 128 + self.max_output_tokens
        for route in self.routes:
            if outbound >= self.max_attempts:
                break
            if not route.verified_free_by_operator or route.provider not in self.adapters:
                continue
            if not await self.quota.reserve(route.scope, route.limits, reservation):
                attempts.append((route.id, "local_quota_exhausted"))
                continue
            outbound += 1
            try:
                answer = await self.adapters[route.provider].execute(
                    route, prompt, self.max_output_tokens
                )
                if not isinstance(answer, str) or not answer.strip():
                    attempts.append((route.id, "invalid_provider_output"))
                    return Outcome("indeterminate", None, None, tuple(attempts))
                attempts.append((route.id, "success"))
                return Outcome("completed", route.id, answer, tuple(attempts))
            except RejectedBeforeGeneration:
                attempts.append((route.id, "http_429"))
            except Exception:
                attempts.append((route.id, "indeterminate"))
                return Outcome("indeterminate", None, None, tuple(attempts))
        return Outcome("blocked", None, None, tuple(attempts))

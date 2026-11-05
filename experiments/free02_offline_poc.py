"""Offline-only free-preferred fallback experiment (not Maestro runtime code).

All adapters are deterministic in-memory fakes. This module performs zero network,
filesystem, authentication, provider, or billing operations. Estimates are NOT bills.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from time import monotonic
from typing import Callable, Literal


ErrorCode = Literal["rate_limit", "unavailable", "authentication", "partial", "indeterminate"]
OfferKind = Literal["free_declared", "paid_known"]


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant", "tool"]
    content: str


@dataclass(frozen=True)
class Route:
    id: str
    offer: OfferKind
    estimate_brl: Decimal
    capabilities: frozenset[str] = frozenset()
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip() or not self.estimate_brl.is_finite() or self.estimate_brl < 0:
            raise ValueError("invalid route")
        if self.offer not in ("free_declared", "paid_known"):
            raise ValueError("invalid offer")


@dataclass(frozen=True)
class Consent:
    risk_acknowledged: bool
    allowed_route_ids: frozenset[str]
    paid_fallback_authorized: bool = False
    max_estimated_brl: Decimal = Decimal("0")
    cancelled: bool = False

    def __post_init__(self) -> None:
        if not self.max_estimated_brl.is_finite() or self.max_estimated_brl < 0:
            raise ValueError("invalid estimated ceiling")


class FakeFailure(Exception):
    def __init__(
        self,
        code: ErrorCode,
        *,
        content_started: bool = False,
        side_effect_uncertain: bool = False,
    ) -> None:
        if code not in ("rate_limit", "unavailable", "authentication", "partial", "indeterminate"):
            raise ValueError("invalid fake failure")
        super().__init__(code)
        self.code = code
        self.content_started = content_started
        self.side_effect_uncertain = side_effect_uncertain


class FakeAdapter:
    """Deterministic local stub: stores only in-memory synthetic test messages."""

    def __init__(self, outcome: str | FakeFailure) -> None:
        self.outcome = outcome
        self.calls: list[tuple[Message, ...]] = []

    def execute(self, history: tuple[Message, ...]) -> str:
        self.calls.append(history)
        if isinstance(self.outcome, FakeFailure):
            raise self.outcome
        return self.outcome


@dataclass(frozen=True)
class Attempt:
    route_id: str
    outcome: str


@dataclass(frozen=True)
class Result:
    state: Literal["completed", "blocked", "indeterminate"]
    route_id: str | None
    answer: str | None
    attempts: tuple[Attempt, ...]
    estimated_attempt_brl: Decimal
    billing_actual: Literal["UNKNOWN"] = "UNKNOWN"


def simulate(
    routes: tuple[Route, ...],
    adapters: dict[str, FakeAdapter],
    history: tuple[Message, ...],
    consent_now: Callable[[], Consent],
    *,
    required_capabilities: frozenset[str] = frozenset(),
    max_attempts: int = 2,
    timeout_seconds: float = 10.0,
    clock: Callable[[], float] = monotonic,
) -> Result:
    """Run a bounded mock-only fallback, rechecking consent before each attempt.

    A declared free offer still carries a real-world billing risk. Explicit risk
    acknowledgement enables experimentation; known paid routes additionally need
    separate payment permission and an estimated ceiling. Neither guarantees bill.
    """
    if (not 1 <= max_attempts <= 2 or isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not isfinite(timeout_seconds) or timeout_seconds <= 0):
        raise ValueError("invalid global limits")
    if len({r.id for r in routes}) != len(routes):
        raise ValueError("duplicate route id")
    if any(not isinstance(m, Message) for m in history):
        raise ValueError("untrusted context type")

    start = clock()
    attempted: set[str] = set()
    evidence: list[Attempt] = []
    estimated_total = Decimal("0")

    def finish(state: Literal["completed", "blocked", "indeterminate"], route: str | None = None, answer: str | None = None) -> Result:
        return Result(state, route, answer, tuple(evidence), estimated_total)

    for _ in range(max_attempts):
        permission = consent_now()
        if permission.cancelled or not permission.risk_acknowledged or clock() - start >= timeout_seconds:
            return finish("blocked")

        eligible = sorted(
            (
                r for r in routes
                if r.id not in attempted and r.id in permission.allowed_route_ids
                and r.enabled and required_capabilities <= r.capabilities
                and ((r.offer == "free_declared" and r.estimate_brl == 0)
                     or (permission.paid_fallback_authorized and permission.max_estimated_brl > 0))
                and estimated_total + r.estimate_brl <= permission.max_estimated_brl
            ),
            key=lambda r: (r.offer != "free_declared", r.estimate_brl, r.id),
        )
        if not eligible:
            return finish("blocked")
        route = eligible[0]
        adapter = adapters.get(route.id)
        if adapter is None or not isinstance(adapter, FakeAdapter):
            return finish("blocked")
        attempted.add(route.id)
        estimated_total += route.estimate_brl
        try:
            answer = adapter.execute(history)
            if clock() - start >= timeout_seconds:
                evidence.append(Attempt(route.id, "deadline_exceeded"))
                return finish("indeterminate")
            evidence.append(Attempt(route.id, "success"))
            return finish("completed", route.id, answer)
        except FakeFailure as failure:
            evidence.append(Attempt(route.id, failure.code))
            if failure.content_started or failure.side_effect_uncertain or failure.code in ("partial", "indeterminate"):
                return finish("indeterminate")
            if failure.code not in ("rate_limit", "unavailable"):
                return finish("blocked")
        except Exception:
            evidence.append(Attempt(route.id, "unexpected_error"))
            return finish("indeterminate")
    return finish("blocked")

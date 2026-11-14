"""FREE-LAB tests: deterministic fakes; zero external API calls."""
import asyncio

from maestro_router.free_fallback import (
    FreeOrchestrator, FreeRoute, Limits, RejectedBeforeGeneration, SlidingQuota,
)

CAP = Limits(2, 3, 2000, 4000)
ROUTES = tuple(
    FreeRoute(name, name, name, name, CAP, True)
    for name in ("groq", "gemini", "cerebras")
)


class Fake:
    def __init__(self, value):
        self.value = value
        self.calls = []

    async def execute(self, route, prompt, max_output_tokens):
        self.calls.append((route.id, prompt, max_output_tokens))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def run(coro):
    return asyncio.run(coro)


def test_three_provider_handoff_for_two_429s():
    adapters = {
        "groq": Fake(RejectedBeforeGeneration()),
        "gemini": Fake(RejectedBeforeGeneration()),
        "cerebras": Fake("ok"),
    }
    result = run(FreeOrchestrator(ROUTES, adapters, SlidingQuota())
                 .run("Explique SQL", live_allowed=True))
    assert result.status == "completed" and result.route == "cerebras"
    assert [status for _, status in result.attempts] == [
        "http_429", "http_429", "success",
    ]
    assert all(fake.calls[0][1] == "Explique SQL" for fake in adapters.values())


def test_default_disabled_no_external_calls():
    fake = Fake("ok")
    engine = FreeOrchestrator(ROUTES, {"groq": fake}, SlidingQuota())
    result = run(engine.run("a", live_allowed=False))
    assert result.status == "disabled" and not fake.calls


def test_uncertain_failure_stops_replay():
    b = Fake("success")
    adapters = {"groq": Fake(TimeoutError("secret maybe billed")), "gemini": b}
    result = run(FreeOrchestrator(ROUTES, adapters, SlidingQuota())
                 .run("x", live_allowed=True))
    assert result.status == "indeterminate" and not b.calls
    assert "secret maybe billed" not in repr(result)


def test_atomic_local_quota_reservation_and_reset():
    now = [0.0]
    quota = SlidingQuota(clock=lambda: now[0])

    async def scenario():
        results = await asyncio.gather(*(
            quota.reserve("same-org", CAP, 100) for _ in range(9)
        ))
        assert sum(results) == 2
        now[0] = 61
        assert await quota.reserve("same-org", CAP, 100)
        assert not await quota.reserve("same-org", CAP, 100)
        now[0] = 86401
        assert await quota.reserve("same-org", CAP, 100)
    run(scenario())


def test_unconfirmed_free_route_is_never_called():
    routes = (
        FreeRoute("a", "groq", "model", "shared", CAP, False),
        ROUTES[1],
    )
    f = Fake("ok")
    result = run(FreeOrchestrator(routes, {"groq": Fake("no"), "gemini": f},
                                  SlidingQuota()).run("x", live_allowed=True))
    assert result.route == "gemini" and len(f.calls) == 1


def test_ambiguous_500_or_401_never_triggers_fallback():
    for failure in (RuntimeError("500"), PermissionError("401")):
        b = Fake("ok")
        result = run(FreeOrchestrator(
            ROUTES, {"groq": Fake(failure), "gemini": b}, SlidingQuota()
        ).run("x", live_allowed=True))
        assert result.status == "indeterminate" and b.calls == []


def test_local_quota_exhaustion_skips_route():
    limits = Limits(1, 1, 800, 800)
    routes = (
        FreeRoute("a", "groq", "model", "scope", limits, True),
        FreeRoute("b", "gemini", "model", "other", limits, True),
    )
    adapters = {"groq": Fake("first"), "gemini": Fake("second")}
    engine = FreeOrchestrator(
        routes, adapters, SlidingQuota(), max_output_tokens=100
    )
    assert run(engine.run("x", live_allowed=True)).route == "a"
    assert run(engine.run("x", live_allowed=True)).route == "b"


def test_invalid_request_never_dispatches():
    fake = Fake("ok")
    engine = FreeOrchestrator(ROUTES, {"groq": fake}, SlidingQuota())
    assert run(engine.run("  ", live_allowed=True)).status == "invalid_request"
    assert fake.calls == []

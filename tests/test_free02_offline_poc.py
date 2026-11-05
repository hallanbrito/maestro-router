"""F02-01..18: offline-only contract checks; never contact a provider."""
from decimal import Decimal

import pytest

from experiments.free02_offline_poc import Consent, FakeAdapter, FakeFailure, Message, Route, simulate


HISTORY = (Message("user", "Explique a etapa 1"), Message("assistant", "Etapa 1 registrada"))
A = Route("a", "free_declared", Decimal("0"), frozenset({"text"}))
B = Route("b", "free_declared", Decimal("0"), frozenset({"text"}))
PAID = Route("b", "paid_known", Decimal("0.05"), frozenset({"text"}))


def policy(*, allowed=("a", "b"), risk=True, paid=False, budget="0", cancel=False):
    return Consent(risk, frozenset(allowed), paid, Decimal(budget), cancel)


def attempt(a="rate_limit", b="success", *, route_b=B, consent=None, **kwargs):
    first = FakeAdapter(FakeFailure(a)) if a != "success" else FakeAdapter("first answer")
    second = FakeAdapter(FakeFailure(b)) if b != "success" else FakeAdapter("second answer")
    permission = consent or (lambda: policy())
    result = simulate((A, route_b), {"a": first, "b": second}, HISTORY, permission, **kwargs)
    return result, first, second


def test_f02_01_first_free_route_success():
    r, a, b = attempt(a="success")
    assert r.state == "completed" and r.route_id == "a"
    assert len(a.calls) == 1 and not b.calls and len(r.attempts) == 1


def test_f02_02_429_falls_back_once():
    r, a, b = attempt()
    assert r.state == "completed" and r.route_id == "b"
    assert [x.outcome for x in r.attempts] == ["rate_limit", "success"]
    assert len(a.calls) == len(b.calls) == 1


def test_f02_03_forbidden_route_never_invoked():
    r, _, b = attempt(consent=lambda: policy(allowed=("a",)))
    assert r.state == "blocked" and not b.calls


def test_f02_04_paid_route_not_automatically_used():
    r, _, b = attempt(route_b=PAID)
    assert r.state == "blocked" and not b.calls


def test_f02_05_risk_ack_not_financial_permission():
    r, _, b = attempt(route_b=PAID, consent=lambda: policy(budget="1"))
    assert r.state == "blocked" and not b.calls


def test_f02_06_estimated_budget_prevents_paid_fallback():
    r, _, b = attempt(route_b=PAID, consent=lambda: policy(paid=True, budget="0.01"))
    assert r.state == "blocked" and not b.calls


def test_f02_07_partial_output_never_repeated():
    a = FakeAdapter(FakeFailure("unavailable", content_started=True))
    b = FakeAdapter("answer")
    r = simulate((A, B), {"a": a, "b": b}, HISTORY, lambda: policy())
    assert r.state == "indeterminate" and not b.calls


def test_f02_08_unknown_outcome_never_repeated():
    r, _, b = attempt(a="indeterminate")
    assert r.state == "indeterminate" and not b.calls


def test_f02_09_handoff_preserves_exact_history():
    r, a, b = attempt()
    assert r.state == "completed" and a.calls == [HISTORY] and b.calls == [HISTORY]


def test_f02_10_no_hidden_context_added():
    _, _, b = attempt()
    assert b.calls[0] == HISTORY and len(b.calls[0]) == 2


def test_f02_11_cancel_before_fallback():
    policies = iter((policy(), policy(cancel=True)))
    r, _, b = attempt(consent=lambda: next(policies))
    assert r.state == "blocked" and not b.calls


def test_f02_12_all_routes_exhausted():
    r, a, b = attempt(a="rate_limit", b="unavailable")
    assert r.state == "blocked" and len(a.calls) == len(b.calls) == 1


def test_f02_13_auth_failure_not_sent_to_other_provider():
    r, _, b = attempt(a="authentication")
    assert r.state == "blocked" and not b.calls


def test_f02_14_consent_revoked_before_fallback():
    policies = iter((policy(), policy(risk=False)))
    r, _, b = attempt(consent=lambda: next(policies))
    assert r.state == "blocked" and not b.calls


def test_f02_15_uncertain_tool_effect_never_repeated():
    a = FakeAdapter(FakeFailure("rate_limit", side_effect_uncertain=True))
    b = FakeAdapter("answer")
    r = simulate((A, B), {"a": a, "b": b}, HISTORY, lambda: policy())
    assert r.state == "indeterminate" and not b.calls


def test_f02_16_usage_cannot_be_called_actual_billing():
    r, _, _ = attempt(a="success")
    assert r.billing_actual == "UNKNOWN" and r.estimated_attempt_brl == Decimal("0")


def test_f02_17_capability_mismatch_excludes_candidate():
    r, a, b = attempt(required_capabilities=frozenset({"vision"}))
    assert r.state == "blocked" and not a.calls and not b.calls


def test_f02_18_paid_fallback_with_explicit_limit():
    r, a, b = attempt(route_b=PAID, consent=lambda: policy(paid=True, budget="0.05"))
    assert r.state == "completed" and r.route_id == "b"
    assert r.estimated_attempt_brl == Decimal("0.05") and r.billing_actual == "UNKNOWN"
    assert len(a.calls) == len(b.calls) == 1


def test_no_risk_ack_blocks_even_declared_free():
    r, a, b = attempt(consent=lambda: policy(risk=False))
    assert r.state == "blocked" and not a.calls and not b.calls


def test_no_over_retry_after_limit():
    r, a, b = attempt(max_attempts=1)
    assert r.state == "blocked" and len(a.calls) == 1 and not b.calls


def test_global_deadline_blocks_before_call():
    ticks = iter((0.0, 20.0))
    r, a, b = attempt(clock=lambda: next(ticks), timeout_seconds=10.0)
    assert r.state == "blocked" and not a.calls and not b.calls


def test_duplicate_route_id_rejected():
    import pytest
    with pytest.raises(ValueError, match="duplicate"):
        simulate((A, A), {"a": FakeAdapter("ok")}, HISTORY, lambda: policy())


def test_declared_free_with_positive_estimate_requires_financial_opt_in():
    misleading_free = Route("b", "free_declared", Decimal("0.05"), frozenset({"text"}))
    r, _, b = attempt(route_b=misleading_free, consent=lambda: policy(budget="1"))
    assert r.state == "blocked" and not b.calls


def test_invalid_infinite_ceiling_rejected():
    import pytest
    with pytest.raises(ValueError, match="invalid estimated ceiling"):
        policy(budget="Infinity")


def test_response_after_global_deadline_is_not_completed():
    now = [0.0]

    class SlowAdapter(FakeAdapter):
        def execute(self, history):
            answer = super().execute(history)
            now[0] = 60.0
            return answer

    first = SlowAdapter("late answer")
    second = FakeAdapter("fallback answer")
    result = simulate((A, B), {"a": first, "b": second}, HISTORY,
                      lambda: policy(), timeout_seconds=10.0, clock=lambda: now[0])
    assert result.state == "indeterminate"
    assert result.answer is None and result.route_id is None
    assert [(item.route_id, item.outcome) for item in result.attempts] == [("a", "deadline_exceeded")]
    assert first.calls == [HISTORY] and not second.calls


def test_unexpected_adapter_exception_is_sanitized_and_stops_fallback():
    class UnexpectedAdapter(FakeAdapter):
        def execute(self, history):
            self.calls.append(history)
            raise RuntimeError("opaque failure")

    first = UnexpectedAdapter("unused")
    second = FakeAdapter("fallback answer")
    result = simulate((A, B), {"a": first, "b": second}, HISTORY, lambda: policy())
    assert result.state == "indeterminate"
    assert result.answer is None and result.route_id is None
    assert [(item.route_id, item.outcome) for item in result.attempts] == [("a", "unexpected_error")]
    assert "opaque failure" not in repr(result)
    assert first.calls == [HISTORY] and not second.calls


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0])
def test_nonpositive_or_nonfinite_timeout_rejected(timeout):
    with pytest.raises(ValueError, match="invalid global limits"):
        attempt(a="success", timeout_seconds=timeout)


@pytest.mark.parametrize("route_id", [3, "", "  \t"])
def test_invalid_route_id_rejected(route_id):
    with pytest.raises(ValueError, match="invalid route"):
        Route(route_id, "free_declared", Decimal("0"))

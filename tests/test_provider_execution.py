from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient

import maestro_router.api as api_module
from maestro_router.api import create_app
from maestro_router.execution import (
    ExecutionFailedError,
    ExecutionRoute,
    ExecutionTimeoutError,
    ExecutionUnavailableError,
    TextExecutionRequest,
    TextExecutionResult,
)
from maestro_router.routing import (
    EconomicEstimate,
    InvalidDecisionError,
    Route,
    RouteCatalog,
)


class ControlledAdapter:
    def __init__(
        self,
        *,
        content: str = "controlled result",
        error: Exception | None = None,
    ) -> None:
        self.content = content
        self.error = error
        self.calls: list[tuple[TextExecutionRequest, ExecutionRoute]] = []

    async def execute(
        self, request: TextExecutionRequest, route: ExecutionRoute
    ) -> TextExecutionResult:
        self.calls.append((request, route))
        if self.error is not None:
            raise self.error
        return TextExecutionResult(content=self.content)


class InvalidSynchronousAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request: object, route: object) -> TextExecutionResult:
        self.calls += 1
        return TextExecutionResult(content="must not be called")


class InvalidResultAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: object, route: object) -> object:
        self.calls += 1
        return {"provider_payload": "must not be published"}


def available(amount: str, reference: str) -> EconomicEstimate:
    return EconomicEstimate(
        status="available",
        amount=amount,
        currency="USD",
        price_reference=reference,
        assumptions=("Estimativa controlada para o teste.",),
    )


def uncertain() -> EconomicEstimate:
    return EconomicEstimate(
        status="uncertain",
        amount="0.015",
        currency="USD",
        price_reference="pricing-uncertain",
        assumptions=("O volume de saída é aproximado.",),
        reason="O volume de saída não pode ser determinado com precisão.",
    )


def unavailable() -> EconomicEstimate:
    return EconomicEstimate(
        status="unavailable",
        reason="Não há informação suficiente para estimar a execução.",
    )


def route(
    route_id: str,
    amount: str,
    *,
    adapter_id: str | None = None,
) -> Route:
    return Route(
        id=route_id,
        provider=f"provider-{route_id}",
        model=f"model-{route_id}",
        adapter_id=adapter_id or f"adapter-{route_id}",
        estimate=available(amount, f"pricing-{route_id}"),
    )


@pytest.mark.parametrize("field", ["provider", "model", "adapter_id"])
def test_execution_route_identity_fields_must_be_non_blank(field: str) -> None:
    values = {
        "id": "route-a",
        "provider": "provider-a",
        "model": "model-a",
        "adapter_id": "adapter-a",
    }
    values[field] = "   "

    with pytest.raises(ValueError, match="non-whitespace"):
        Route(**values)


def client_for(
    routes: tuple[Route, ...], adapters: Mapping[str, object]
) -> TestClient:
    return TestClient(create_app(RouteCatalog(routes), adapters))


def test_success_executes_only_selected_adapter_once_and_matches_closed_schema() -> None:
    selected = ControlledAdapter(content="content returned by the adapter")
    unselected = ControlledAdapter(content="wrong content")
    selected_route = route("route-a", "0.0100")
    unselected_route = route("route-b", "0.0200")
    client = client_for(
        (unselected_route, selected_route),
        {
            unselected_route.adapter_id: unselected,
            selected_route.adapter_id: selected,
        },
    )

    response = client.post(
        "/v1/executions",
        json={"task": "Execute exactly.", "context": "Keep this context."},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"result", "decision", "economics"}
    assert set(body["result"]) == {"content"}
    assert body["result"]["content"] == "content returned by the adapter"
    assert set(body["decision"]) == {
        "outcome",
        "route",
        "strategy",
        "applied_constraints",
        "reason",
        "factors",
    }
    assert body["decision"]["route"] == {
        "id": "route-a",
        "provider": "provider-route-a",
        "model": "model-route-a",
    }
    assert body["decision"]["strategy"] == {
        "id": "lowest-estimated-cost",
        "applied": True,
    }
    assert body["economics"]["estimate"] == {
        "status": "available",
        "amount": "0.0100",
        "currency": "USD",
        "price_reference": "pricing-route-a",
        "assumptions": ["Estimativa controlada para o teste."],
    }
    for field in ("usage", "calculated_cost"):
        assert set(body["economics"][field]) == {"status", "reason"}
        assert body["economics"][field]["status"] == "unavailable"
        assert body["economics"][field]["reason"].strip()
        assert 0 not in body["economics"][field].values()
        assert None not in body["economics"][field].values()

    assert len(selected.calls) == 1
    assert unselected.calls == []
    adapter_request, adapter_route = selected.calls[0]
    assert adapter_request == TextExecutionRequest(
        task="Execute exactly.", context="Keep this context."
    )
    assert adapter_route == ExecutionRoute(
        id="route-a",
        provider="provider-route-a",
        model="model-route-a",
    )


@pytest.mark.parametrize("invalid_adapter", [None, InvalidSynchronousAdapter()])
def test_missing_or_invalid_selected_adapter_is_invalid_configuration(
    invalid_adapter: InvalidSynchronousAdapter | None,
) -> None:
    unrelated = ControlledAdapter()
    selected_route = route("route-a", "0.01", adapter_id="selected-adapter")
    adapters: dict[str, object] = {"unrelated-adapter": unrelated}
    if invalid_adapter is not None:
        adapters["selected-adapter"] = invalid_adapter

    response = client_for((selected_route,), adapters).post(
        "/v1/executions", json={"task": "Execute."}
    )

    assert response.status_code == 500
    assert set(response.json()) == {"error"}
    assert response.json()["error"]["code"] == "INVALID_CONFIGURATION"
    assert response.json()["error"]["issues"]
    assert unrelated.calls == []
    if invalid_adapter is not None:
        assert invalid_adapter.calls == 0


def test_invalid_cheapest_route_is_excluded_before_economic_comparison() -> None:
    invalid = InvalidSynchronousAdapter()
    valid = ControlledAdapter(content="valid route result")
    invalid_route = route(
        "route-a", "0.01", adapter_id="secret-internal-adapter-id"
    )
    valid_route = route("route-b", "0.02")

    response = client_for(
        (invalid_route, valid_route),
        {
            invalid_route.adapter_id: invalid,
            valid_route.adapter_id: valid,
        },
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["route"]["id"] == "route-b"
    assert body["economics"]["estimate"]["amount"] == "0.02"
    assert body["result"]["content"] == "valid route result"
    configuration_factors = [
        factor
        for factor in body["decision"]["factors"]
        if factor["category"] == "configuration"
    ]
    assert len(configuration_factors) == 1
    assert "route-a" in configuration_factors[0]["description"]
    assert any(
        constraint["source"] == "configuration"
        and constraint["category"] == "route"
        and "route-a" in constraint["description"]
        for constraint in body["decision"]["applied_constraints"]
    )
    assert "secret-internal-adapter-id" not in response.text
    assert "InvalidSynchronousAdapter" not in response.text
    assert invalid.calls == 0
    assert len(valid.calls) == 1


def test_all_enabled_routes_with_invalid_associations_are_invalid_configuration() -> None:
    invalid = InvalidSynchronousAdapter()
    route_a = route("route-a", "0.01")
    route_b = route("route-b", "0.02")

    response = client_for(
        (route_a, route_b), {route_a.adapter_id: invalid}
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 500
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "INVALID_CONFIGURATION"
    assert "decision" not in body
    assert "economics" not in body
    assert "result" not in body
    assert invalid.calls == 0


def test_disabled_route_without_adapter_remains_no_eligible_route() -> None:
    unrelated = ControlledAdapter()
    disabled = Route(
        id="route-disabled",
        provider="provider-disabled",
        model="model-disabled",
        adapter_id="missing-adapter",
        enabled=False,
        estimate=available("0.01", "pricing-disabled"),
    )

    response = client_for((disabled,), {"unrelated-adapter": unrelated}).post(
        "/v1/executions", json={"task": "Execute."}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_ELIGIBLE_ROUTE"
    assert unrelated.calls == []


def test_request_uses_same_adapter_snapshot_for_routing_and_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ControlledAdapter(content="snapshot result")
    replacement = ControlledAdapter(content="mutated mapping result")
    selected_route = route("route-a", "0.01")
    adapters: dict[str, object] = {selected_route.adapter_id: original}
    original_route_request = api_module.route_request

    def mutate_after_snapshot(*args: object, **kwargs: object) -> object:
        adapters[selected_route.adapter_id] = replacement
        return original_route_request(*args, **kwargs)

    monkeypatch.setattr(api_module, "route_request", mutate_after_snapshot)
    response = client_for((selected_route,), adapters).post(
        "/v1/executions", json={"task": "Execute."}
    )

    assert response.status_code == 200
    assert response.json()["result"]["content"] == "snapshot result"
    assert len(original.calls) == 1
    assert replacement.calls == []


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (ExecutionFailedError("external general details"), 502, "EXECUTION_FAILED"),
        (
            ExecutionUnavailableError("external availability details"),
            503,
            "EXECUTION_UNAVAILABLE",
        ),
        (ExecutionTimeoutError("external timeout details"), 504, "EXECUTION_TIMEOUT"),
    ],
)
def test_typed_execution_errors_are_normalized_after_one_call(
    error: Exception, status_code: int, code: str
) -> None:
    adapter = ControlledAdapter(error=error)
    selected_route = route("route-a", "0.01")

    response = client_for(
        (selected_route,), {selected_route.adapter_id: adapter}
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error", "decision", "economics"}
    assert body["error"]["code"] == code
    assert "result" not in body
    assert body["decision"]["outcome"] == "selected"
    assert body["economics"]["estimate"]["amount"] == "0.01"
    assert len(adapter.calls) == 1


def test_unexpected_adapter_error_is_sanitized() -> None:
    secret = "secret endpoint payload and credential"
    adapter = ControlledAdapter(error=RuntimeError(secret))
    selected_route = route("route-a", "0.01")

    response = client_for(
        (selected_route,), {selected_route.adapter_id: adapter}
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EXECUTION_FAILED"
    assert secret not in response.text
    assert len(adapter.calls) == 1


@pytest.mark.parametrize(
    ("estimate", "expected"),
    [
        (
            uncertain(),
            {
                "status": "uncertain",
                "amount": "0.015",
                "currency": "USD",
                "price_reference": "pricing-uncertain",
                "assumptions": ["O volume de saída é aproximado."],
                "reason": "O volume de saída não pode ser determinado com precisão.",
            },
        ),
        (
            unavailable(),
            {
                "status": "unavailable",
                "reason": "Não há informação suficiente para estimar a execução.",
            },
        ),
    ],
)
def test_single_route_success_preserves_non_available_estimate(
    estimate: EconomicEstimate, expected: dict[str, object]
) -> None:
    adapter = ControlledAdapter()
    selected_route = Route(
        id="route-a",
        provider="provider-a",
        model="model-a",
        adapter_id="adapter-a",
        estimate=estimate,
    )

    response = client_for(
        (selected_route,), {selected_route.adapter_id: adapter}
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 200
    assert response.json()["economics"]["estimate"] == expected
    assert len(adapter.calls) == 1


def test_invalid_adapter_result_is_sanitized_execution_failure() -> None:
    adapter = InvalidResultAdapter()
    selected_route = route("route-a", "0.01")

    response = client_for(
        (selected_route,), {selected_route.adapter_id: adapter}
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EXECUTION_FAILED"
    assert "provider_payload" not in response.text
    assert "must not be published" not in response.text
    assert adapter.calls == 1


@pytest.mark.parametrize(
    ("routes", "expected_code"),
    [
        ((route("route-a", "0.01"),), "NO_ELIGIBLE_ROUTE"),
        (
            (
                Route(
                    id="route-a",
                    provider="provider-a",
                    model="model-a",
                    adapter_id="adapter-a",
                ),
                Route(
                    id="route-b",
                    provider="provider-b",
                    model="model-b",
                    adapter_id="adapter-b",
                ),
            ),
            "INSUFFICIENT_ECONOMIC_INFORMATION",
        ),
    ],
)
def test_routing_refusals_never_call_adapters(
    routes: tuple[Route, ...], expected_code: str
) -> None:
    adapters = {item.adapter_id: ControlledAdapter() for item in routes}
    payload = (
        {
            "task": "Execute.",
            "constraints": {"required_capabilities": ["missing-capability"]},
        }
        if expected_code == "NO_ELIGIBLE_ROUTE"
        else {"task": "Execute."}
    )

    response = client_for(routes, adapters).post("/v1/executions", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == expected_code
    assert all(adapter.calls == [] for adapter in adapters.values())


def test_invalid_decision_is_sanitized_and_prevents_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = ControlledAdapter()
    selected_route = route("route-a", "0.01")

    def reject_decision(*args: object, **kwargs: object) -> object:
        raise InvalidDecisionError("internal route and invariant details")

    monkeypatch.setattr(api_module, "route_request", reject_decision)
    response = client_for(
        (selected_route,), {selected_route.adapter_id: adapter}
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 500
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "INVALID_DECISION"
    assert body["error"]["issues"]
    assert "internal route and invariant details" not in response.text
    assert adapter.calls == []


def test_catalog_and_adapter_registry_order_do_not_influence_selection() -> None:
    route_a = route("route-a", "0.01")
    route_b = route("route-b", "0.02")

    first_a = ControlledAdapter(content="first-a")
    first_b = ControlledAdapter(content="first-b")
    first = client_for(
        (route_b, route_a),
        {route_b.adapter_id: first_b, route_a.adapter_id: first_a},
    ).post("/v1/executions", json={"task": "Execute."})

    second_a = ControlledAdapter(content="second-a")
    second_b = ControlledAdapter(content="second-b")
    second = client_for(
        (route_a, route_b),
        {route_a.adapter_id: second_a, route_b.adapter_id: second_b},
    ).post("/v1/executions", json={"task": "Execute."})

    assert first.json()["decision"]["route"]["id"] == "route-a"
    assert second.json()["decision"]["route"]["id"] == "route-a"
    assert len(first_a.calls) == len(second_a.calls) == 1
    assert first_b.calls == second_b.calls == []

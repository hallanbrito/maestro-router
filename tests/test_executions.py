from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from maestro_router.api import create_app
from maestro_router.contracts import ExecutionRequest
from maestro_router.execution import TextExecutionResult
from maestro_router.routing import (
    EconomicEstimate,
    Route,
    RouteCatalog,
    SelectedDecision,
    _selection_context,
    _validate_selection,
    route_request,
)


def available(
    amount: str, currency: str = "USD", reference: str = "pricing-test"
) -> EconomicEstimate:
    return EconomicEstimate(
        status="available",
        amount=amount,
        currency=currency,
        price_reference=reference,
        assumptions=(),
    )


def uncertain(amount: str = "0.01") -> EconomicEstimate:
    return EconomicEstimate(
        status="uncertain",
        amount=amount,
        currency="USD",
        price_reference="pricing-uncertain",
        assumptions=("O volume de saída é aproximado.",),
        reason="O volume de saída não pode ser determinado com precisão.",
    )


def configured_route(route_id: str, **changes: Any) -> Route:
    return Route(
        id=route_id,
        provider=f"provider-{route_id}",
        model=f"model-{route_id}",
        adapter_id=f"adapter-{route_id}",
        **changes,
    )


class UnexpectedCallAdapter:
    async def execute(self, request: object, route: object) -> TextExecutionResult:
        raise AssertionError("Routing refusal must not execute an adapter.")


def client_for(*routes: Route) -> TestClient:
    adapters = {route.adapter_id: UnexpectedCallAdapter() for route in routes}
    return TestClient(create_app(RouteCatalog(routes), adapters))


def test_structurally_valid_request_reaches_routing() -> None:
    response = client_for().post(
        "/v1/executions",
        json={"task": "Analise o documento.", "constraints": {}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_ELIGIBLE_ROUTE"


@pytest.mark.parametrize(
    ("payload", "path"),
    [
        ({}, "/task"),
        ({"task": "   "}, "/task"),
        ({"task": "ok", "context": None}, "/context"),
        (
            {"task": "ok", "constraints": {"required_capabilities": []}},
            "/constraints/required_capabilities",
        ),
        (
            {
                "task": "ok",
                "constraints": {
                    "max_estimated_cost": {"amount": 0.01, "currency": "usd"}
                },
            },
            "/constraints/max_estimated_cost/amount",
        ),
    ],
)
def test_invalid_payload_uses_normative_error(payload: object, path: str) -> None:
    response = client_for().post("/v1/executions", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert path in {issue.get("path") for issue in body["error"]["issues"]}


@pytest.mark.parametrize(
    "payload",
    [
        {"task": "ok", "metadata": {}},
        {"task": "ok", "constraints": {"preferred_provider": "provider-a"}},
        {
            "task": "ok",
            "constraints": {
                "max_estimated_cost": {
                    "amount": "0.01",
                    "currency": "USD",
                    "rounding": "up",
                }
            },
        },
    ],
)
def test_closed_request_objects_reject_additional_fields(payload: object) -> None:
    response = client_for().post("/v1/executions", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_empty_catalog_produces_explainable_refusal() -> None:
    response = client_for().post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 422
    body = response.json()
    assert body["decision"]["factors"] == [
        {
            "category": "route",
            "description": "O catálogo não continha rotas configuradas.",
        }
    ]


def test_all_routes_are_eliminated_by_normative_filter_order() -> None:
    routes = (
        configured_route("route-a", enabled=False),
        configured_route("route-b", capabilities=frozenset({"text_generation"})),
        configured_route(
            "route-c",
            capabilities=frozenset({"document_analysis"}),
            quality_criteria=frozenset(),
        ),
        configured_route(
            "route-d",
            capabilities=frozenset({"document_analysis"}),
            quality_criteria=frozenset({"quality-accepted"}),
            known_unavailable=True,
        ),
        configured_route(
            "route-z",
            capabilities=frozenset({"document_analysis"}),
            quality_criteria=frozenset({"quality-accepted"}),
        ),
    )
    response = client_for(*routes).post(
        "/v1/executions",
        json={
            "task": "Analise.",
            "constraints": {
                "allowed_route_ids": ["route-a", "route-b", "route-c", "route-d"],
                "required_capabilities": ["document_analysis"],
                "required_quality_criteria": ["quality-accepted"],
            },
        },
    )

    assert response.status_code == 422
    factors = response.json()["decision"]["factors"]
    assert [factor["category"] for factor in factors] == [
        "route",
        "capability",
        "quality",
        "availability",
        "route",
    ]
    assert [factor["description"].split()[0] for factor in factors] == [
        "route-a",
        "route-b",
        "route-c",
        "route-d",
        "route-z",
    ]


def test_no_eligible_route_response_matches_public_contract() -> None:
    response = client_for(
        configured_route("route-text-a", capabilities=frozenset({"text_generation"}))
    ).post(
        "/v1/executions",
        json={
            "task": "Analise o documento.",
            "constraints": {"required_capabilities": ["document_analysis"]},
        },
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert set(body) == {"error", "decision"}
    assert body["error"] == {
        "code": "NO_ELIGIBLE_ROUTE",
        "message": (
            "Nenhuma rota configurada, habilitada e válida satisfaz "
            "as restrições aplicáveis."
        ),
    }
    assert body["decision"]["outcome"] == "refused"
    assert body["decision"]["strategy"] == {
        "id": "lowest-estimated-cost",
        "applied": False,
    }
    assert "route" not in body["decision"]
    assert "economics" not in body
    assert body["decision"]["applied_constraints"]
    assert body["decision"]["reason"].strip()
    assert body["decision"]["factors"]


def test_decision_is_deterministic_for_same_request_and_catalog() -> None:
    routes = [
        configured_route("route-b", capabilities=frozenset({"text_generation"})),
        configured_route("route-a", known_unavailable=True),
    ]
    payload = {
        "task": "Analise.",
        "constraints": {"required_capabilities": ["document_analysis"]},
    }

    first = client_for(*routes).post("/v1/executions", json=payload)
    second = client_for(*reversed(routes)).post("/v1/executions", json=payload)

    assert first.status_code == second.status_code == 422
    assert first.json() == second.json()


def test_surviving_route_is_selected_internally() -> None:
    request = ExecutionRequest(task="Execute a tarefa.")
    route = configured_route("route-a")

    decision = route_request(request, RouteCatalog([route]))

    assert isinstance(decision, SelectedDecision)
    assert decision.route is route
    assert decision.strategy_id == "lowest-estimated-cost"
    assert decision.strategy_applied is True
    assert "única rota elegível" in decision.reason
    assert decision.compared_routes == ()


@pytest.mark.parametrize(
    "estimate",
    [
        EconomicEstimate(
            status="unavailable",
            reason="Não há preço suficiente para estimar a execução.",
        ),
        uncertain(),
    ],
)
def test_ceiling_with_indeterminate_estimate_refuses_economically(
    estimate: EconomicEstimate,
) -> None:
    response = client_for(configured_route("route-a", estimate=estimate)).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {
                "max_estimated_cost": {"amount": "0.01", "currency": "USD"}
            },
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INSUFFICIENT_ECONOMIC_INFORMATION"
    assert body["decision"]["outcome"] == "refused"
    assert body["decision"]["strategy"] == {
        "id": "lowest-estimated-cost",
        "applied": False,
    }
    assert estimate.status in body["decision"]["factors"][0]["description"]


def test_ceiling_with_available_estimate_above_limit_has_no_eligible_route() -> None:
    response = client_for(
        configured_route("route-a", estimate=available("0.0100000000000001"))
    ).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {
                "max_estimated_cost": {"amount": "0.01", "currency": "USD"}
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_ELIGIBLE_ROUTE"


def test_ceiling_with_available_estimate_within_limit_reaches_selection() -> None:
    request = ExecutionRequest.model_validate(
        {
            "task": "Execute.",
            "constraints": {
                "max_estimated_cost": {"amount": "0.1", "currency": "USD"}
            },
        }
    )
    route = configured_route("route-a", estimate=available("0.100000000000000000"))

    decision = route_request(request, RouteCatalog([route]))

    assert isinstance(decision, SelectedDecision)
    assert decision.route is route
    assert decision.evaluated_estimates == ((route.id, route.estimate),)
    assert decision.factors[0].references == ["pricing-test"]


def test_multiple_routes_without_available_estimate_refuse_economically() -> None:
    response = client_for(
        configured_route("route-a"),
        configured_route("route-b", estimate=uncertain()),
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_ECONOMIC_INFORMATION"


def test_available_but_non_comparable_estimates_do_not_reach_selection() -> None:
    non_comparable = EconomicEstimate(
        status="available",
        amount="0.01",
        currency="USD",
        price_reference="pricing-partial",
        assumptions=("A estimativa cobre somente uma parcela da execução.",),
        comparable=False,
        non_comparability_reason="Não representa o custo total da execução.",
    )
    response = client_for(
        configured_route("route-a", estimate=non_comparable),
        configured_route("route-b"),
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_ECONOMIC_INFORMATION"


def test_multiple_available_currencies_refuse_without_conversion() -> None:
    response = client_for(
        configured_route(
            "route-a", estimate=available("0.01", "USD", "pricing-usd")
        ),
        configured_route(
            "route-b", estimate=available("0.01", "EUR", "pricing-eur")
        ),
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_ECONOMIC_INFORMATION"


def test_single_route_without_ceiling_does_not_require_cost() -> None:
    route = configured_route("route-a")

    decision = route_request(
        ExecutionRequest(task="Execute."), RouteCatalog([route])
    )

    assert isinstance(decision, SelectedDecision)
    assert decision.route is route


def test_only_routes_with_proven_ceiling_compliance_reach_selection() -> None:
    request = ExecutionRequest.model_validate(
        {
            "task": "Execute.",
            "constraints": {
                "max_estimated_cost": {"amount": "0.01", "currency": "USD"}
            },
        }
    )
    valid = configured_route(
        "route-valid", estimate=available("0.01", reference="pricing-valid")
    )
    expensive = configured_route(
        "route-expensive", estimate=available("0.02", reference="pricing-expensive")
    )

    decision = route_request(request, RouteCatalog([expensive, valid]))

    assert isinstance(decision, SelectedDecision)
    assert decision.selectable_routes == (valid,)
    assert decision.route is valid


def test_economic_evaluation_is_deterministic_across_catalog_order() -> None:
    routes = [
        configured_route("route-b", estimate=uncertain("0.02")),
        configured_route("route-a"),
    ]
    payload = {"task": "Execute."}

    first = client_for(*routes).post("/v1/executions", json=payload)
    second = client_for(*reversed(routes)).post("/v1/executions", json=payload)

    assert first.status_code == second.status_code == 422
    assert first.json() == second.json()


@pytest.mark.parametrize(
    "estimate",
    [
        available("0.01"),
        uncertain("0.01"),
        EconomicEstimate(
            status="unavailable",
            reason="Não há preço suficiente para estimar a execução.",
        ),
    ],
)
def test_single_candidate_without_ceiling_accepts_every_estimate_status(
    estimate: EconomicEstimate,
) -> None:
    route = configured_route("route-only", estimate=estimate)

    decision = route_request(
        ExecutionRequest(task="Execute."), RouteCatalog([route])
    )

    assert isinstance(decision, SelectedDecision)
    assert decision.route is route
    assert decision.strategy_applied is True
    assert decision.evaluated_estimates == ((route.id, estimate),)
    assert "única rota elegível" in decision.reason
    assert all(factor.category != "tie_breaker" for factor in decision.factors)


def test_multiple_routes_select_unique_lowest_decimal_estimate() -> None:
    cheaper = configured_route(
        "route-b", estimate=available("0.0100000000000000001")
    )
    expensive = configured_route(
        "route-a", estimate=available("0.0100000000000000002")
    )

    decision = route_request(
        ExecutionRequest(task="Execute."),
        RouteCatalog([expensive, cheaper]),
    )

    assert isinstance(decision, SelectedDecision)
    assert decision.route is cheaper
    assert decision.compared_routes == (cheaper, expensive)


def test_numeric_tie_uses_smallest_route_id_and_records_tie_breaker() -> None:
    route_b = configured_route(
        "route-b", estimate=available("0.1", reference="pricing-b")
    )
    route_a = configured_route(
        "route-a", estimate=available("0.10", reference="pricing-a")
    )

    decision = route_request(
        ExecutionRequest(task="Execute."),
        RouteCatalog([route_b, route_a]),
    )

    assert isinstance(decision, SelectedDecision)
    assert decision.route is route_a
    tie_factors = [
        factor for factor in decision.factors if factor.category == "tie_breaker"
    ]
    assert len(tie_factors) == 1
    assert "route-a" in tie_factors[0].description


def test_non_comparable_routes_remain_explainable_after_selection() -> None:
    uncertain_route = configured_route("route-b", estimate=uncertain())
    unavailable_route = configured_route(
        "route-c",
        estimate=EconomicEstimate(
            status="unavailable",
            reason="A referência econômica não estava disponível.",
        ),
    )
    comparable_route = configured_route("route-a", estimate=available("0.02"))

    decision = route_request(
        ExecutionRequest(task="Execute."),
        RouteCatalog([uncertain_route, unavailable_route, comparable_route]),
    )

    assert isinstance(decision, SelectedDecision)
    assert decision.route is comparable_route
    assert decision.compared_routes == (comparable_route,)
    descriptions = " ".join(factor.description for factor in decision.factors)
    assert "route-b" in descriptions
    assert "uncertain" in descriptions
    assert uncertain_route.estimate.reason in descriptions
    assert "route-c" in descriptions
    assert "unavailable" in descriptions
    assert unavailable_route.estimate.reason in descriptions
    assert "economicamente comparáveis" in decision.reason


def test_selection_is_deterministic_across_catalog_order() -> None:
    routes = [
        configured_route(
            "route-b", estimate=available("0.1", reference="pricing-b")
        ),
        configured_route(
            "route-a", estimate=available("0.10", reference="pricing-a")
        ),
        configured_route("route-c", estimate=uncertain()),
    ]
    request = ExecutionRequest(task="Execute.")

    first = route_request(request, RouteCatalog(routes))
    second = route_request(request, RouteCatalog(reversed(routes)))

    assert isinstance(first, SelectedDecision)
    assert isinstance(second, SelectedDecision)
    assert first == second


def test_incoherent_selection_cannot_pass_validation() -> None:
    route_a = configured_route("route-a", estimate=available("0.01"))
    route_b = configured_route("route-b", estimate=available("0.02"))
    request = ExecutionRequest(task="Execute.")
    decision = route_request(request, RouteCatalog([route_a, route_b]))
    assert isinstance(decision, SelectedDecision)
    context = _selection_context(
        request,
        [route_a, route_b],
        [],
    )

    incoherent = replace(
        decision,
        selected_routes=(route_b,),
        selectable_routes=(route_b,),
        compared_routes=(route_b,),
        evaluated_estimates=((route_b.id, route_b.estimate),),
    )

    with pytest.raises(ValueError, match="authoritative selectable set"):
        _validate_selection(context, incoherent)


def test_ceiling_selects_comparable_route_and_preserves_indeterminate_route() -> None:
    request = ExecutionRequest.model_validate(
        {
            "task": "Execute.",
            "constraints": {
                "max_estimated_cost": {"amount": "0.02", "currency": "USD"}
            },
        }
    )
    admissible = configured_route("route-a", estimate=available("0.01"))
    indeterminate = configured_route("route-b", estimate=uncertain("0.015"))

    decision = route_request(
        request, RouteCatalog([indeterminate, admissible])
    )

    assert isinstance(decision, SelectedDecision)
    assert decision.route is admissible
    assert decision.selectable_routes == (admissible,)
    assert decision.evaluated_estimates == (
        (admissible.id, admissible.estimate),
        (indeterminate.id, indeterminate.estimate),
    )
    descriptions = " ".join(factor.description for factor in decision.factors)
    assert "route-b" in descriptions
    assert "uncertain" in descriptions


def test_multiple_routes_within_ceiling_select_cheapest_in_economic_order() -> None:
    request = ExecutionRequest.model_validate(
        {
            "task": "Execute.",
            "constraints": {
                "max_estimated_cost": {"amount": "0.03", "currency": "USD"}
            },
        }
    )
    expensive = configured_route("route-a", estimate=available("0.02"))
    cheaper = configured_route("route-z", estimate=available("0.01"))

    decision = route_request(request, RouteCatalog([expensive, cheaper]))

    assert isinstance(decision, SelectedDecision)
    assert decision.route is cheaper
    assert decision.compared_routes == (cheaper, expensive)


def test_available_non_comparable_route_is_excluded_when_another_is_comparable() -> None:
    non_comparable = configured_route(
        "route-a",
        estimate=EconomicEstimate(
            status="available",
            amount="0.001",
            currency="USD",
            price_reference="pricing-partial",
            assumptions=("Cobre somente uma parcela da execução.",),
            comparable=False,
            non_comparability_reason="Não representa o custo total.",
        ),
    )
    comparable = configured_route("route-b", estimate=available("0.02"))

    decision = route_request(
        ExecutionRequest(task="Execute."),
        RouteCatalog([non_comparable, comparable]),
    )

    assert isinstance(decision, SelectedDecision)
    assert decision.route is comparable
    assert decision.selectable_routes == (comparable,)
    assert decision.compared_routes == (comparable,)
    descriptions = " ".join(factor.description for factor in decision.factors)
    assert "route-a" in descriptions
    assert "Não representa o custo total." in descriptions


def test_valid_selection_without_adapter_is_invalid_configuration() -> None:
    route = configured_route("route-a", estimate=available("0.01"))
    client = TestClient(create_app(RouteCatalog([route])))

    response = client.post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INVALID_CONFIGURATION"


def test_duplicate_json_member_is_rejected() -> None:
    response = client_for().post(
        "/v1/executions",
        content='{"task":"first","task":"second"}',
        headers={"content-type": "application/json; charset=UTF-8"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_non_json_media_type_is_rejected() -> None:
    response = client_for().post(
        "/v1/executions",
        content=json.dumps({"task": "ok"}),
        headers={"content-type": "text/plain"},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_fastapi_does_not_publish_auxiliary_endpoints() -> None:
    client = client_for()

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404

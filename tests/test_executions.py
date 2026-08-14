from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from maestro_router.api import create_app
from maestro_router.contracts import ExecutionRequest
from maestro_router.routing import (
    EconomicEstimate,
    Route,
    RouteCatalog,
    RoutingNotImplementedError,
    refuse_when_no_route,
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


def client_for(*routes: Route) -> TestClient:
    return TestClient(create_app(RouteCatalog(routes)))


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
        Route("route-a", enabled=False),
        Route("route-b", capabilities=frozenset({"text_generation"})),
        Route(
            "route-c",
            capabilities=frozenset({"document_analysis"}),
            quality_criteria=frozenset(),
        ),
        Route(
            "route-d",
            capabilities=frozenset({"document_analysis"}),
            quality_criteria=frozenset({"quality-accepted"}),
            known_unavailable=True,
        ),
        Route(
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
        Route("route-text-a", capabilities=frozenset({"text_generation"}))
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
        Route("route-b", capabilities=frozenset({"text_generation"})),
        Route("route-a", known_unavailable=True),
    ]
    payload = {
        "task": "Analise.",
        "constraints": {"required_capabilities": ["document_analysis"]},
    }

    first = client_for(*routes).post("/v1/executions", json=payload)
    second = client_for(*reversed(routes)).post("/v1/executions", json=payload)

    assert first.status_code == second.status_code == 422
    assert first.json() == second.json()


def test_surviving_route_stops_at_the_current_slice_boundary() -> None:
    request = ExecutionRequest(task="Execute a tarefa.")
    catalog = RouteCatalog([Route("route-a")])

    with pytest.raises(
        RoutingNotImplementedError,
        match="Deterministic selection",
    ):
        refuse_when_no_route(request, catalog)


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
    response = client_for(Route("route-a", estimate=estimate)).post(
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
        Route("route-a", estimate=available("0.0100000000000001"))
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
    route = Route("route-a", estimate=available("0.100000000000000000"))

    with pytest.raises(RoutingNotImplementedError) as error:
        refuse_when_no_route(request, RouteCatalog([route]))

    assert error.value.candidates == (route,)


def test_multiple_routes_without_available_estimate_refuse_economically() -> None:
    response = client_for(
        Route("route-a"),
        Route("route-b", estimate=uncertain()),
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
        Route("route-a", estimate=non_comparable),
        Route("route-b"),
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_ECONOMIC_INFORMATION"


def test_multiple_available_currencies_refuse_without_conversion() -> None:
    response = client_for(
        Route("route-a", estimate=available("0.01", "USD", "pricing-usd")),
        Route("route-b", estimate=available("0.01", "EUR", "pricing-eur")),
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_ECONOMIC_INFORMATION"


def test_single_route_without_ceiling_does_not_require_cost() -> None:
    route = Route("route-a")

    with pytest.raises(RoutingNotImplementedError) as error:
        refuse_when_no_route(
            ExecutionRequest(task="Execute."), RouteCatalog([route])
        )

    assert error.value.candidates == (route,)


def test_only_routes_with_proven_ceiling_compliance_reach_selection() -> None:
    request = ExecutionRequest.model_validate(
        {
            "task": "Execute.",
            "constraints": {
                "max_estimated_cost": {"amount": "0.01", "currency": "USD"}
            },
        }
    )
    valid = Route("route-valid", estimate=available("0.01", reference="pricing-valid"))
    expensive = Route(
        "route-expensive", estimate=available("0.02", reference="pricing-expensive")
    )

    with pytest.raises(RoutingNotImplementedError) as error:
        refuse_when_no_route(request, RouteCatalog([expensive, valid]))

    assert error.value.candidates == (valid,)


def test_economic_evaluation_is_deterministic_across_catalog_order() -> None:
    routes = [
        Route("route-b", estimate=uncertain("0.02")),
        Route("route-a"),
    ]
    payload = {"task": "Execute."}

    first = client_for(*routes).post("/v1/executions", json=payload)
    second = client_for(*reversed(routes)).post("/v1/executions", json=payload)

    assert first.status_code == second.status_code == 422
    assert first.json() == second.json()


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

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from maestro_router.api import create_app
from maestro_router.contracts import ExecutionRequest
from maestro_router.routing import (
    Route,
    RouteCatalog,
    RoutingNotImplementedError,
    refuse_when_no_route,
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
        match="Selection, economic evaluation, and execution",
    ):
        refuse_when_no_route(request, catalog)


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

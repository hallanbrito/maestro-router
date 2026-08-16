from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import maestro_router.bootstrap as bootstrap_module
from maestro_router.adapters import OpenAIResponsesAdapter
from maestro_router.api import app as default_app
from maestro_router.api import create_app
from maestro_router.bootstrap import (
    InvalidRuntimeConfigurationError,
    create_openai_app,
)
from maestro_router.routing import RouteCatalog


CONTROLLED_KEY = "controlled-key-input"
CONTROLLED_MODEL = "controlled-model"
CONTROLLED_ROUTE_ID = "controlled-route"
UNAVAILABLE_ESTIMATE_REASON = (
    "Não há preço nem método de estimativa aprovados para esta rota."
)


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        text_part = SimpleNamespace(type="output_text", text="controlled result")
        message = SimpleNamespace(type="message", content=[text_part])
        return SimpleNamespace(
            status="completed",
            output=[message],
            output_text="controlled result",
        )


class FakeAsyncOpenAI:
    def __init__(self) -> None:
        self.responses = FakeResponses()
        self.option_calls: list[dict[str, Any]] = []

    def with_options(self, **kwargs: Any) -> FakeAsyncOpenAI:
        self.option_calls.append(kwargs)
        return self


class ControlledClientFactory:
    def __init__(self) -> None:
        self.client: FakeAsyncOpenAI | None = None
        self.calls: list[dict[str, str]] = []

    def __call__(self, **kwargs: str) -> FakeAsyncOpenAI:
        self.calls.append(kwargs)
        self.client = FakeAsyncOpenAI()
        return self.client


def controlled_configuration() -> dict[str, str]:
    return {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_MODEL": CONTROLLED_MODEL,
        "MAESTRO_OPENAI_ROUTE_ID": CONTROLLED_ROUTE_ID,
    }


@pytest.mark.parametrize(
    ("variable_name", "invalid_value"),
    [
        ("OPENAI_API_KEY", None),
        ("OPENAI_API_KEY", ""),
        ("OPENAI_API_KEY", "   "),
        ("MAESTRO_OPENAI_MODEL", None),
        ("MAESTRO_OPENAI_MODEL", ""),
        ("MAESTRO_OPENAI_MODEL", "   "),
        ("MAESTRO_OPENAI_ROUTE_ID", None),
        ("MAESTRO_OPENAI_ROUTE_ID", ""),
        ("MAESTRO_OPENAI_ROUTE_ID", "   "),
    ],
)
def test_invalid_configuration_prevents_client_construction(
    variable_name: str,
    invalid_value: str | None,
) -> None:
    configuration = controlled_configuration()
    if invalid_value is None:
        del configuration[variable_name]
    else:
        configuration[variable_name] = invalid_value
    factory = ControlledClientFactory()

    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(configuration, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == variable_name
    assert str(caught.value) == (
        f"{variable_name} é obrigatória e deve conter valor não branco."
    )
    assert CONTROLLED_KEY not in str(caught.value)
    assert CONTROLLED_MODEL not in str(caught.value)
    assert CONTROLLED_ROUTE_ID not in str(caught.value)
    assert factory.calls == []
    assert factory.client is None


def test_composition_builds_only_the_approved_route_and_association(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def capture_create_app(
        catalog: RouteCatalog,
        adapters: dict[str, OpenAIResponsesAdapter],
    ) -> FastAPI:
        captured["catalog"] = catalog
        captured["adapters"] = adapters
        return FastAPI()

    monkeypatch.setattr(bootstrap_module, "create_app", capture_create_app)
    factory = ControlledClientFactory()

    create_openai_app(controlled_configuration(), client_factory=factory)  # type: ignore[arg-type]

    catalog = captured["catalog"]
    assert isinstance(catalog, RouteCatalog)
    routes = catalog.snapshot()
    assert len(routes) == 1
    route = routes[0]
    assert route.id == CONTROLLED_ROUTE_ID
    assert route.provider == "openai"
    assert route.model == CONTROLLED_MODEL
    assert route.adapter_id == "openai-responses"
    assert route.enabled is True
    assert route.capabilities == frozenset()
    assert route.quality_criteria == frozenset()
    assert route.known_unavailable is False
    assert route.estimate.status == "unavailable"
    assert route.estimate.reason == UNAVAILABLE_ESTIMATE_REASON
    adapters = captured["adapters"]
    assert isinstance(adapters, dict)
    assert set(adapters) == {"openai-responses"}
    assert isinstance(adapters["openai-responses"], OpenAIResponsesAdapter)
    assert factory.calls == [{"api_key": CONTROLLED_KEY}]


def test_valid_composition_executes_once_and_preserves_unavailable_economics() -> None:
    factory = ControlledClientFactory()
    app = create_openai_app(
        controlled_configuration(), client_factory=factory  # type: ignore[arg-type]
    )
    assert factory.client is not None

    response = TestClient(app).post(
        "/v1/executions", json={"task": "Execute."}
    )

    assert response.status_code == 200
    assert response.json()["result"] == {"content": "controlled result"}
    assert response.json()["decision"]["route"] == {
        "id": CONTROLLED_ROUTE_ID,
        "provider": "openai",
        "model": CONTROLLED_MODEL,
    }
    economics = response.json()["economics"]
    assert economics["estimate"]["status"] == "unavailable"
    assert economics["estimate"]["reason"] == UNAVAILABLE_ESTIMATE_REASON
    assert economics["usage"]["status"] == "unavailable"
    assert economics["calculated_cost"]["status"] == "unavailable"
    assert len(factory.client.responses.calls) == 1
    assert factory.client.responses.calls[0]["model"] == CONTROLLED_MODEL
    assert CONTROLLED_KEY not in response.text


def test_undeclared_capability_refuses_without_external_call() -> None:
    factory = ControlledClientFactory()
    app = create_openai_app(
        controlled_configuration(), client_factory=factory  # type: ignore[arg-type]
    )
    assert factory.client is not None

    response = TestClient(app).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {"required_capabilities": ["document_analysis"]},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_ELIGIBLE_ROUTE"
    assert factory.client.responses.calls == []


def test_economic_ceiling_refuses_without_external_call() -> None:
    factory = ControlledClientFactory()
    app = create_openai_app(
        controlled_configuration(), client_factory=factory  # type: ignore[arg-type]
    )
    assert factory.client is not None

    response = TestClient(app).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {
                "max_estimated_cost": {"amount": "0.01", "currency": "USD"}
            },
        },
    )

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_ECONOMIC_INFORMATION"
    )
    assert factory.client.responses.calls == []


def test_configuration_is_snapshotted_during_composition() -> None:
    configuration = controlled_configuration()
    factory = ControlledClientFactory()
    app = create_openai_app(
        configuration, client_factory=factory  # type: ignore[arg-type]
    )
    assert factory.client is not None

    configuration.update(
        {
            "OPENAI_API_KEY": "later-key-input",
            "MAESTRO_OPENAI_MODEL": "later-model",
            "MAESTRO_OPENAI_ROUTE_ID": "later-route",
        }
    )
    response = TestClient(app).post(
        "/v1/executions", json={"task": "Execute."}
    )

    assert response.status_code == 200
    assert response.json()["decision"]["route"]["id"] == CONTROLLED_ROUTE_ID
    assert response.json()["decision"]["route"]["model"] == CONTROLLED_MODEL
    assert factory.calls == [{"api_key": CONTROLLED_KEY}]
    assert factory.client.responses.calls[0]["model"] == CONTROLLED_MODEL
    assert "later-key-input" not in response.text


def test_non_blank_values_are_preserved_without_normalization() -> None:
    configuration = {
        "OPENAI_API_KEY": "  controlled-key-input  ",
        "MAESTRO_OPENAI_MODEL": "  controlled-model  ",
        "MAESTRO_OPENAI_ROUTE_ID": "  controlled-route  ",
    }
    factory = ControlledClientFactory()
    app = create_openai_app(
        configuration, client_factory=factory  # type: ignore[arg-type]
    )
    assert factory.client is not None

    response = TestClient(app).post(
        "/v1/executions", json={"task": "Execute."}
    )

    assert response.status_code == 200
    assert factory.calls == [{"api_key": "  controlled-key-input  "}]
    assert response.json()["decision"]["route"]["id"] == "  controlled-route  "
    assert response.json()["decision"]["route"]["model"] == "  controlled-model  "
    assert factory.client.responses.calls[0]["model"] == "  controlled-model  "


def test_default_application_remains_neutral() -> None:
    for application in (create_app(), default_app):
        response = TestClient(application).post(
            "/v1/executions", json={"task": "Execute."}
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "NO_ELIGIBLE_ROUTE"

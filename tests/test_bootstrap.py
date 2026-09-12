from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from threading import Barrier, Lock
from types import SimpleNamespace
from typing import Any

import pytest
import httpx2
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import AsyncOpenAI, Omit, omit

import maestro_router.bootstrap as bootstrap_module
from maestro_router.adapters import OpenAIResponsesAdapter
from maestro_router.api import app as default_app
from maestro_router.api import create_app
from maestro_router.bootstrap import (
    InvalidRuntimeConfigurationError,
    create_openai_app,
    create_openai_app_from_env,
)
from maestro_router.routing import Route, RouteCatalog

CONTROLLED_KEY = "controlled-key-input"
CONTROLLED_MODEL = "controlled-model"
CONTROLLED_ROUTE_ID = "controlled-route"
PRICE_REFERENCE_VARIABLE = "MAESTRO_OPENAI_PRICE_REFERENCE_JSON"
ESTIMATED_USAGE_VARIABLE = "MAESTRO_OPENAI_ESTIMATED_USAGE_JSON"
CONTROLLED_PRICE_ID = "controlled-pricing-reference"
SENSITIVE_SENTINELS = (
    CONTROLLED_KEY,
    CONTROLLED_MODEL,
    CONTROLLED_ROUTE_ID,
    "sensitive-rate-17",
    "sensitive-source-23",
    "sensitive-condition-29",
)
UNAVAILABLE_ESTIMATE_REASON = (
    "Não há preço nem método de estimativa aprovados para esta rota."
)
PRICE_ONLY_UNAVAILABLE_ESTIMATE_REASON = (
    "Não há previsão de uso configurada para estimar esta rota."
)
APPROVED_CLIENT_OPTIONS = {
    "admin_api_key": "",
    "organization": "",
    "project": "",
    "webhook_secret": "",
    "base_url": "https://api.openai.com/v1",
    "max_retries": 0,
    "default_headers": {
        "OpenAI-Organization": omit,
        "OpenAI-Project": omit,
    },
    "default_query": {},
}
CONTROLLED_ESTIMATE_ASSUMPTIONS = [
    "A estimativa considera 300 unidades de input_token configuradas pelo operador.",
    "A estimativa considera 500 unidades de output_token configuradas pelo operador.",
]


class FakeResponses:
    def __init__(
        self,
        usage: object | None = None,
        observed_model: str | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.usage = usage
        self.observed_model = observed_model

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        text_part = SimpleNamespace(type="output_text", text="controlled result")
        message = SimpleNamespace(type="message", content=[text_part])
        response = SimpleNamespace(
            status="completed",
            output=[message],
            output_text="controlled result",
            model=self.observed_model or kwargs["model"],
        )
        if self.usage is not None:
            response.usage = self.usage
        return response


class FakeAsyncOpenAI:
    def __init__(self, usage: object | None = None) -> None:
        self.responses = FakeResponses(usage)
        self.option_calls: list[dict[str, Any]] = []

    def with_options(self, **kwargs: Any) -> FakeAsyncOpenAI:
        self.option_calls.append(kwargs)
        return self


class ControlledClientFactory:
    def __init__(
        self,
        usage: object | None = None,
        observed_model: str | None = None,
    ) -> None:
        self.client: FakeAsyncOpenAI | None = None
        self.calls: list[dict[str, str]] = []
        self.usage = usage
        self.observed_model = observed_model

    def __call__(self, **kwargs: str) -> FakeAsyncOpenAI:
        self.calls.append(kwargs)
        self.client = FakeAsyncOpenAI(self.usage)
        self.client.responses.observed_model = self.observed_model
        return self.client


def controlled_configuration() -> dict[str, str]:
    return {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_MODEL": CONTROLLED_MODEL,
        "MAESTRO_OPENAI_ROUTE_ID": CONTROLLED_ROUTE_ID,
    }


def valid_price_document() -> dict[str, object]:
    return {
        "id": CONTROLLED_PRICE_ID,
        "currency": "USD",
        "version": "verified-2026-08-23",
        "source": "operator-maintained-reference",
        "rates": [
            {"unit": "input_token", "rate": "0.001", "base": 1000},
            {"unit": "output_token", "rate": "0.004", "base": 1000},
        ],
        "conditions": ["standard-text-context"],
        "context_complete": True,
        "units_exhaustive": True,
        "no_double_counting": True,
        "model_identity_exact": True,
    }


def configuration_with_price(
    document: object | None = None,
) -> dict[str, str]:
    configuration = controlled_configuration()
    configuration[PRICE_REFERENCE_VARIABLE] = json.dumps(
        valid_price_document() if document is None else document
    )
    return configuration


def valid_estimated_usage_document() -> dict[str, object]:
    return {
        "input_token": 300,
        "output_token": 500,
        "applicability_confirmed": True,
    }


def configuration_with_estimate(
    usage_document: object | None = None,
    *,
    price_document: object | None = None,
) -> dict[str, str]:
    configuration = configuration_with_price(price_document)
    configuration[ESTIMATED_USAGE_VARIABLE] = json.dumps(
        valid_estimated_usage_document() if usage_document is None else usage_document
    )
    return configuration


def changed_price_document(**changes: object) -> dict[str, object]:
    document = valid_price_document()
    document.update(changes)
    return document


def price_rate(
    unit: object = "input_token",
    rate: object = "0.001",
    base: object = 1000,
    **extra: object,
) -> dict[str, object]:
    result = {"unit": unit, "rate": rate, "base": base}
    result.update(extra)
    return result


def changed_estimated_usage_document(**changes: object) -> dict[str, object]:
    document = valid_estimated_usage_document()
    document.update(changes)
    return document


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


@pytest.mark.parametrize(
    "raw_value",
    [
        "",
        "   ",
        "{",
        "[]",
        "null",
        "true",
        '{"id":"first","id":"second"}',
        (
            '{"id":"pricing","currency":"USD","version":"v1",'
            '"source":"operator","rates":['
            '{"unit":"input_token","unit":"output_token",'
            '"rate":"0.1","base":1},'
            '{"unit":"output_token","rate":"0.2","base":1}],'
            '"conditions":[],"context_complete":true,'
            '"units_exhaustive":true,"no_double_counting":true,'
            '"model_identity_exact":true}'
        ),
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_invalid_json_shapes_and_nonstandard_constants_prevent_client_construction(
    raw_value: str,
) -> None:
    configuration = controlled_configuration()
    configuration[PRICE_REFERENCE_VARIABLE] = raw_value
    factory = ControlledClientFactory()

    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(configuration, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == PRICE_REFERENCE_VARIABLE
    assert str(caught.value) == (
        f"{PRICE_REFERENCE_VARIABLE} contém uma configuração inválida."
    )
    if raw_value:
        assert raw_value not in str(caught.value)
    assert factory.calls == []


@pytest.mark.parametrize("raw_value", [None, 1, {}, []])
def test_non_string_price_configuration_prevents_client_construction(
    raw_value: object,
) -> None:
    configuration: dict[str, object] = controlled_configuration()
    configuration[PRICE_REFERENCE_VARIABLE] = raw_value
    factory = ControlledClientFactory()

    with pytest.raises(InvalidRuntimeConfigurationError):
        create_openai_app(configuration, client_factory=factory)  # type: ignore[arg-type]

    assert factory.calls == []


@pytest.mark.parametrize("field", list(valid_price_document()))
def test_missing_price_field_prevents_client_construction(field: str) -> None:
    document = valid_price_document()
    del document[field]
    _assert_invalid_price_configuration(json.dumps(document))


@pytest.mark.parametrize("unknown_field", ["unknown", "route_id", "provider", "model"])
def test_unknown_price_field_prevents_client_construction(
    unknown_field: str,
) -> None:
    document = valid_price_document()
    document[unknown_field] = "sensitive-unknown-value"
    _assert_invalid_price_configuration(json.dumps(document))


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("id", ""),
        ("id", "   "),
        ("id", 1),
        ("version", ""),
        ("version", "\t"),
        ("version", None),
        ("source", ""),
        ("source", "\n"),
        ("source", []),
        ("currency", "usd"),
        ("currency", "US"),
        ("currency", "USDD"),
        ("currency", "ÚSD"),
        ("currency", 123),
    ],
)
def test_invalid_price_identity_metadata_or_currency_prevents_client_construction(
    field: str,
    invalid_value: object,
) -> None:
    _assert_invalid_price_configuration(
        json.dumps(changed_price_document(**{field: invalid_value}))
    )


@pytest.mark.parametrize(
    "conditions",
    [
        "condition",
        [""],
        ["   "],
        [1],
        ["same", "same"],
    ],
)
def test_invalid_conditions_prevent_client_construction(
    conditions: object,
) -> None:
    _assert_invalid_price_configuration(
        json.dumps(changed_price_document(conditions=conditions))
    )


@pytest.mark.parametrize(
    "rates",
    [
        {},
        [],
        [price_rate()],
        [price_rate(), price_rate("output_token"), price_rate("output_token")],
        [price_rate(), {"unit": "output_token", "rate": "0.004"}],
        [price_rate(), price_rate("output_token", extra="forbidden")],
        [price_rate("unknown"), price_rate("output_token")],
        [price_rate(), price_rate("input_token", "0.004")],
        [price_rate(rate=1), price_rate("output_token")],
        [price_rate(rate="-1"), price_rate("output_token")],
        [price_rate(rate="+1"), price_rate("output_token")],
        [price_rate(rate="01"), price_rate("output_token")],
        [price_rate(rate=".1"), price_rate("output_token")],
        [price_rate(rate="1e3"), price_rate("output_token")],
        [price_rate(base=True), price_rate("output_token")],
        [price_rate(base=0), price_rate("output_token")],
        [price_rate(base=-10), price_rate("output_token")],
        [price_rate(base=20), price_rate("output_token")],
        [price_rate(base=1.0), price_rate("output_token")],
    ],
)
def test_invalid_rates_prevent_client_construction(rates: object) -> None:
    _assert_invalid_price_configuration(json.dumps(changed_price_document(rates=rates)))


@pytest.mark.parametrize(
    "field",
    [
        "context_complete",
        "units_exhaustive",
        "no_double_counting",
        "model_identity_exact",
    ],
)
@pytest.mark.parametrize("invalid_value", [False, 1, "true", None])
def test_invalid_completeness_declarations_prevent_client_construction(
    field: str,
    invalid_value: object,
) -> None:
    _assert_invalid_price_configuration(
        json.dumps(changed_price_document(**{field: invalid_value}))
    )


def test_invalid_price_error_never_reproduces_sensitive_values() -> None:
    raw_value = json.dumps(
        changed_price_document(
            source="sensitive-source-23",
            conditions=["sensitive-condition-29"],
            rates=[
                price_rate(rate="sensitive-rate-17"),
                price_rate("output_token", "0.004"),
            ],
        )
    )
    configuration = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_MODEL": CONTROLLED_MODEL,
        "MAESTRO_OPENAI_ROUTE_ID": CONTROLLED_ROUTE_ID,
        PRICE_REFERENCE_VARIABLE: raw_value,
    }

    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(configuration, client_factory=ControlledClientFactory())  # type: ignore[arg-type]

    message = str(caught.value)
    assert PRICE_REFERENCE_VARIABLE in message
    assert raw_value not in message
    assert all(sentinel not in message for sentinel in SENSITIVE_SENTINELS)


def _assert_invalid_price_configuration(raw_value: str) -> None:
    configuration = controlled_configuration()
    configuration[PRICE_REFERENCE_VARIABLE] = raw_value
    factory = ControlledClientFactory()

    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(configuration, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == PRICE_REFERENCE_VARIABLE
    assert factory.calls == []
    assert factory.client is None


@pytest.mark.parametrize(
    "raw_value",
    [
        "",
        "   ",
        "{",
        "[]",
        "null",
        "true",
        "1",
        (
            '{"input_token":300,"input_token":301,'
            '"output_token":500,"applicability_confirmed":true}'
        ),
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_invalid_estimated_usage_json_prevents_client_construction(
    raw_value: str,
) -> None:
    configuration = configuration_with_price()
    configuration[ESTIMATED_USAGE_VARIABLE] = raw_value
    factory = ControlledClientFactory()

    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(configuration, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == ESTIMATED_USAGE_VARIABLE
    assert str(caught.value) == (
        f"{ESTIMATED_USAGE_VARIABLE} contém uma configuração inválida."
    )
    if raw_value:
        assert raw_value not in str(caught.value)
    assert factory.calls == []
    assert factory.client is None


@pytest.mark.parametrize("raw_value", [None, 1, {}, []])
def test_non_string_estimated_usage_prevents_client_construction(
    raw_value: object,
) -> None:
    configuration: dict[str, object] = configuration_with_price()
    configuration[ESTIMATED_USAGE_VARIABLE] = raw_value
    factory = ControlledClientFactory()

    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(configuration, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == ESTIMATED_USAGE_VARIABLE
    assert factory.calls == []
    assert factory.client is None


@pytest.mark.parametrize("field", list(valid_estimated_usage_document()))
def test_missing_estimated_usage_field_prevents_client_construction(
    field: str,
) -> None:
    document = valid_estimated_usage_document()
    del document[field]
    _assert_invalid_estimated_usage_configuration(json.dumps(document))


@pytest.mark.parametrize(
    "unknown_field",
    ["unknown", "currency", "price_reference", "model", "route_id"],
)
def test_unknown_estimated_usage_field_prevents_client_construction(
    unknown_field: str,
) -> None:
    document = valid_estimated_usage_document()
    document[unknown_field] = "sensitive-unknown-value"
    _assert_invalid_estimated_usage_configuration(json.dumps(document))


@pytest.mark.parametrize("field", ["input_token", "output_token"])
@pytest.mark.parametrize(
    "invalid_value",
    [0, -1, True, False, 1.0, "1", None, [], {}],
)
def test_invalid_estimated_quantity_prevents_client_construction(
    field: str,
    invalid_value: object,
) -> None:
    document = changed_estimated_usage_document(**{field: invalid_value})
    _assert_invalid_estimated_usage_configuration(json.dumps(document))


@pytest.mark.parametrize("invalid_value", [False, 1, 0, "true", None, [], {}])
def test_unconfirmed_estimated_usage_prevents_client_construction(
    invalid_value: object,
) -> None:
    document = changed_estimated_usage_document(applicability_confirmed=invalid_value)
    _assert_invalid_estimated_usage_configuration(json.dumps(document))


def test_estimated_usage_requires_price_before_client_construction() -> None:
    configuration = controlled_configuration()
    raw_usage = json.dumps(valid_estimated_usage_document())
    configuration[ESTIMATED_USAGE_VARIABLE] = raw_usage
    factory = ControlledClientFactory()

    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(configuration, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == ESTIMATED_USAGE_VARIABLE
    assert raw_usage not in str(caught.value)
    assert factory.calls == []
    assert factory.client is None


def test_invalid_estimated_usage_error_never_reproduces_received_values() -> None:
    raw_usage = json.dumps(
        changed_estimated_usage_document(input_token="sensitive-quantity-41")
    )
    configuration = configuration_with_price()
    configuration[ESTIMATED_USAGE_VARIABLE] = raw_usage

    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(
            configuration,
            client_factory=ControlledClientFactory(),  # type: ignore[arg-type]
        )

    message = str(caught.value)
    assert ESTIMATED_USAGE_VARIABLE in message
    assert raw_usage not in message
    assert "sensitive-quantity-41" not in message
    assert all(sentinel not in message for sentinel in SENSITIVE_SENTINELS)


def _assert_invalid_estimated_usage_configuration(raw_value: str) -> None:
    configuration = configuration_with_price()
    configuration[ESTIMATED_USAGE_VARIABLE] = raw_value
    factory = ControlledClientFactory()

    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(configuration, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == ESTIMATED_USAGE_VARIABLE
    assert factory.calls == []
    assert factory.client is None


def test_environment_factory_reads_optional_economics_only_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, str]] = []

    def capture_configuration(configuration: dict[str, str]) -> FastAPI:
        captured.append(configuration)
        return FastAPI()

    monkeypatch.setattr(bootstrap_module, "create_openai_app", capture_configuration)
    for name, value in controlled_configuration().items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(PRICE_REFERENCE_VARIABLE, raising=False)
    monkeypatch.delenv(ESTIMATED_USAGE_VARIABLE, raising=False)

    create_openai_app_from_env()
    raw_price = json.dumps(valid_price_document())
    monkeypatch.setenv(PRICE_REFERENCE_VARIABLE, raw_price)
    create_openai_app_from_env()
    raw_usage = json.dumps(valid_estimated_usage_document())
    monkeypatch.setenv(ESTIMATED_USAGE_VARIABLE, raw_usage)
    create_openai_app_from_env()

    assert captured[0] == controlled_configuration()
    assert captured[1] == {
        **controlled_configuration(),
        PRICE_REFERENCE_VARIABLE: raw_price,
    }
    assert captured[2] == {
        **controlled_configuration(),
        PRICE_REFERENCE_VARIABLE: raw_price,
        ESTIMATED_USAGE_VARIABLE: raw_usage,
    }


def test_official_client_ignores_unapproved_environment_and_freezes_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx2.Request] = []
    clients: list[AsyncOpenAI] = []

    async def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200,
            request=request,
            json={
                "id": "resp_controlled",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": CONTROLLED_MODEL,
                "output": [
                    {
                        "id": "msg_controlled",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "controlled result",
                                "annotations": [],
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    transport_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(respond)
    )

    def official_factory(**kwargs: object) -> AsyncOpenAI:
        client = AsyncOpenAI(**kwargs, http_client=transport_client)
        clients.append(client)
        return client

    def reject_second_client(*args: object, **kwargs: object) -> AsyncOpenAI:
        raise AssertionError("with_options would construct a second AsyncOpenAI")

    monkeypatch.setattr(AsyncOpenAI, "with_options", reject_second_client)

    for name, value in {
        "OPENAI_BASE_URL": "https://unapproved.invalid/v1",
        "OPENAI_ORG_ID": "unapproved-organization",
        "OPENAI_PROJECT_ID": "unapproved-project",
        "OPENAI_ADMIN_KEY": "unapproved-admin-key",
        "OPENAI_WEBHOOK_SECRET": "unapproved-webhook-secret",
        "OPENAI_CUSTOM_HEADERS": (
            "X-Unapproved: leaked\n"
            "Authorization: Bearer unapproved\n"
            "OpenAI-Organization: custom-organization"
        ),
    }.items():
        monkeypatch.setenv(name, value)

    app = create_openai_app(
        controlled_configuration(), client_factory=official_factory
    )

    monkeypatch.setenv("OPENAI_BASE_URL", "https://changed.invalid/v1")
    monkeypatch.setenv("OPENAI_ORG_ID", "changed-organization")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "changed-project")
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", "X-Changed: leaked")

    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 200
    assert len(clients) == 1
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == f"Bearer {CONTROLLED_KEY}"
    assert request.headers["x-stainless-retry-count"] == "0"
    assert "openai-organization" not in request.headers
    assert "openai-project" not in request.headers
    assert "x-unapproved" not in request.headers
    assert "x-changed" not in request.headers
    assert clients[0].admin_api_key == ""
    assert clients[0].webhook_secret == ""


def test_overlapping_compositions_preserve_environment_and_isolate_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = {
        "OPENAI_BASE_URL": "https://unapproved.invalid/v1",
        "OPENAI_ORG_ID": "unapproved-organization",
        "OPENAI_PROJECT_ID": "unapproved-project",
        "OPENAI_ADMIN_KEY": "unapproved-admin-key",
        "OPENAI_WEBHOOK_SECRET": "unapproved-webhook-secret",
        "OPENAI_CUSTOM_HEADERS": "X-Unapproved: leaked",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    before = dict(os.environ)
    entered = Barrier(3)
    release = Barrier(3)
    lock = Lock()
    during: list[dict[str, str]] = []
    captured: list[tuple[dict[str, object], FakeAsyncOpenAI]] = []

    def overlapping_factory(**kwargs: object) -> FakeAsyncOpenAI:
        client = FakeAsyncOpenAI()
        with lock:
            captured.append((kwargs, client))
        entered.wait()
        with lock:
            during.append(dict(os.environ))
        release.wait()
        return client

    def compose() -> FastAPI:
        return create_openai_app(
            controlled_configuration(), client_factory=overlapping_factory
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(compose) for _ in range(2)]
        entered.wait()
        assert dict(os.environ) == before
        release.wait()
        apps = [future.result() for future in futures]

    assert len(apps) == 2
    assert during == [before, before]
    assert dict(os.environ) == before
    assert len(captured) == 2
    assert captured[0][1] is not captured[1][1]
    for options, client in captured:
        assert options["api_key"] == CONTROLLED_KEY
        assert options["admin_api_key"] == ""
        assert options["organization"] == ""
        assert options["project"] == ""
        assert options["webhook_secret"] == ""
        assert options["base_url"] == "https://api.openai.com/v1"
        assert options["max_retries"] == 0
        assert options["default_query"] == {}
        headers = options["default_headers"]
        assert isinstance(headers, dict)
        assert set(headers) == {
            "OpenAI-Organization",
            "OpenAI-Project",
            "X-Unapproved",
        }
        assert all(isinstance(value, Omit) for value in headers.values())
        assert client.option_calls == []


def test_legacy_price_reference_id_with_surrogate_fails_before_client() -> None:
    document = valid_price_document()
    document["id"] = "price-\ud800"
    factory = ControlledClientFactory()

    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(
            configuration_with_price(document), client_factory=factory
        )  # type: ignore[arg-type]

    assert caught.value.variable_name == PRICE_REFERENCE_VARIABLE
    assert "price-" not in str(caught.value)
    assert factory.calls == []


def test_valid_price_reference_is_bound_ordered_and_frozen_in_route_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_routes: list[object] = []

    def capture_create_app(
        catalog: RouteCatalog,
        adapters: dict[str, OpenAIResponsesAdapter],
    ) -> FastAPI:
        captured_routes.append(catalog.snapshot()[0])
        return FastAPI()

    monkeypatch.setattr(bootstrap_module, "create_app", capture_create_app)
    normal_document = changed_price_document(
        id="  public-reference  ",
        version="  version  ",
        source="  source  ",
        conditions=["  condition  "],
    )
    document = dict(normal_document)
    document["rates"] = list(reversed(document["rates"]))  # type: ignore[arg-type]
    configuration = configuration_with_price(document)
    factory = ControlledClientFactory()

    create_openai_app(configuration, client_factory=factory)  # type: ignore[arg-type]
    configuration[PRICE_REFERENCE_VARIABLE] = json.dumps(
        changed_price_document(id="later-reference")
    )
    create_openai_app(
        configuration_with_price(normal_document),
        client_factory=ControlledClientFactory(),  # type: ignore[arg-type]
    )

    first_route = captured_routes[0]
    second_route = captured_routes[1]
    first_reference = first_route.price_reference  # type: ignore[attr-defined]
    second_reference = second_route.price_reference  # type: ignore[attr-defined]
    assert first_reference is not None
    assert first_reference.id == "  public-reference  "
    assert first_reference.version == "  version  "
    assert first_reference.source == "  source  "
    assert first_reference.conditions == ("  condition  ",)
    assert first_reference.route_id == CONTROLLED_ROUTE_ID
    assert first_reference.provider == "openai"
    assert first_reference.model == CONTROLLED_MODEL
    assert [rate.unit for rate in first_reference.rates] == [
        "input_token",
        "output_token",
    ]
    assert second_reference is not None
    assert first_reference == second_reference
    with pytest.raises(FrozenInstanceError):
        first_reference.id = "mutated"  # type: ignore[misc]
    assert factory.calls == [{"api_key": CONTROLLED_KEY, **APPROVED_CLIENT_OPTIONS}]


def test_valid_estimated_usage_is_exact_order_independent_and_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_routes: list[object] = []

    def capture_create_app(
        catalog: RouteCatalog,
        adapters: dict[str, OpenAIResponsesAdapter],
    ) -> FastAPI:
        captured_routes.append(catalog.snapshot()[0])
        return FastAPI()

    monkeypatch.setattr(bootstrap_module, "create_app", capture_create_app)
    normal_document = valid_estimated_usage_document()
    reversed_document = dict(reversed(tuple(normal_document.items())))
    configuration = configuration_with_estimate(normal_document)

    create_openai_app(
        configuration,
        client_factory=ControlledClientFactory(),  # type: ignore[arg-type]
    )
    configuration[ESTIMATED_USAGE_VARIABLE] = json.dumps(
        changed_estimated_usage_document(input_token=999, output_token=999)
    )
    create_openai_app(
        configuration_with_estimate(reversed_document),
        client_factory=ControlledClientFactory(),  # type: ignore[arg-type]
    )

    first_estimate = captured_routes[0].estimate  # type: ignore[attr-defined]
    second_estimate = captured_routes[1].estimate  # type: ignore[attr-defined]
    assert first_estimate == second_estimate
    assert first_estimate.status == "available"
    assert first_estimate.amount == "0.0023"
    assert first_estimate.currency == "USD"
    assert first_estimate.price_reference == CONTROLLED_PRICE_ID
    assert list(first_estimate.assumptions) == CONTROLLED_ESTIMATE_ASSUMPTIONS
    assert first_estimate.reason is None
    assert first_estimate.comparable is True
    with pytest.raises(FrozenInstanceError):
        first_estimate.amount = "999"  # type: ignore[misc]


def test_economic_configuration_is_not_passed_to_openai_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class CapturingAdapter:
        def __init__(self, *args: object, **kwargs: object) -> None:
            adapter_calls.append((args, kwargs))

    monkeypatch.setattr(bootstrap_module, "OpenAIResponsesAdapter", CapturingAdapter)
    monkeypatch.setattr(bootstrap_module, "create_app", lambda *_: FastAPI())
    factory = ControlledClientFactory()

    create_openai_app(configuration_with_estimate(), client_factory=factory)  # type: ignore[arg-type]

    assert factory.client is not None
    assert adapter_calls == [
        ((factory.client,), {"retry_policy_configured": True})
    ]


def test_empty_conditions_are_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def capture_create_app(
        catalog: RouteCatalog,
        adapters: dict[str, OpenAIResponsesAdapter],
    ) -> FastAPI:
        captured["route"] = catalog.snapshot()[0]
        return FastAPI()

    monkeypatch.setattr(bootstrap_module, "create_app", capture_create_app)

    create_openai_app(
        configuration_with_price(changed_price_document(conditions=[])),
        client_factory=ControlledClientFactory(),  # type: ignore[arg-type]
    )

    reference = captured["route"].price_reference  # type: ignore[attr-defined]
    assert reference is not None
    assert reference.conditions == ()


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
    assert route.price_reference is None
    adapters = captured["adapters"]
    assert isinstance(adapters, dict)
    assert set(adapters) == {"openai-responses"}
    assert isinstance(adapters["openai-responses"], OpenAIResponsesAdapter)
    assert factory.calls == [{"api_key": CONTROLLED_KEY, **APPROVED_CLIENT_OPTIONS}]


def test_valid_composition_executes_once_and_preserves_unavailable_economics() -> None:
    factory = ControlledClientFactory()
    app = create_openai_app(
        controlled_configuration(), client_factory=factory  # type: ignore[arg-type]
    )
    assert factory.client is not None

    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})

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


def test_valid_price_and_complete_usage_produce_exact_public_cost_once() -> None:
    document = changed_price_document(
        source="sensitive-source-23",
        conditions=["sensitive-condition-29"],
    )
    raw_price = json.dumps(document)
    factory = ControlledClientFactory(
        SimpleNamespace(input_tokens=310, output_tokens=86)
    )
    app = create_openai_app(
        configuration_with_price(document),
        client_factory=factory,  # type: ignore[arg-type]
    )
    assert factory.client is not None

    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 200
    economics = response.json()["economics"]
    assert economics["estimate"] == {
        "status": "unavailable",
        "reason": PRICE_ONLY_UNAVAILABLE_ESTIMATE_REASON,
    }
    assert economics["calculated_cost"] == {
        "status": "available",
        "amount": "0.000654",
        "currency": "USD",
        "price_reference": CONTROLLED_PRICE_ID,
        "assumptions": [],
    }
    assert set(economics["calculated_cost"]) == {
        "status",
        "amount",
        "currency",
        "price_reference",
        "assumptions",
    }
    assert len(factory.client.responses.calls) == 1
    assert CONTROLLED_KEY not in response.text
    assert "sensitive-source-23" not in response.text
    assert "sensitive-condition-29" not in response.text
    assert '"rate"' not in response.text
    assert '"source"' not in response.text
    assert '"conditions"' not in response.text
    assert "0.001" not in response.text
    assert "0.004" not in response.text
    assert raw_price not in response.text


def test_valid_forecast_and_complete_usage_keep_estimate_and_cost_separate() -> None:
    factory = ControlledClientFactory(
        SimpleNamespace(input_tokens=310, output_tokens=86)
    )
    app = create_openai_app(
        configuration_with_estimate(),
        client_factory=factory,  # type: ignore[arg-type]
    )
    assert factory.client is not None

    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 200
    economics = response.json()["economics"]
    assert economics["estimate"] == {
        "status": "available",
        "amount": "0.0023",
        "currency": "USD",
        "price_reference": CONTROLLED_PRICE_ID,
        "assumptions": CONTROLLED_ESTIMATE_ASSUMPTIONS,
    }
    assert economics["calculated_cost"] == {
        "status": "available",
        "amount": "0.000654",
        "currency": "USD",
        "price_reference": CONTROLLED_PRICE_ID,
        "assumptions": [],
    }
    assert economics["estimate"]["amount"] != economics["calculated_cost"]["amount"]
    assert len(factory.client.responses.calls) == 1


def test_provider_model_divergence_keeps_calculated_cost_unavailable() -> None:
    factory = ControlledClientFactory(
        SimpleNamespace(input_tokens=310, output_tokens=86),
        observed_model="different-model-returned-by-provider",
    )
    app = create_openai_app(
        configuration_with_estimate(), client_factory=factory
    )  # type: ignore[arg-type]

    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["route"]["model"] == CONTROLLED_MODEL
    assert body["result"] == {"content": "controlled result"}
    assert body["economics"]["usage"]["status"] == "available"
    assert body["economics"]["calculated_cost"]["status"] == "unavailable"
    assert "different-model-returned-by-provider" not in response.text
    assert len(factory.client.responses.calls) == 1


def test_static_forecast_is_reused_for_different_requests_in_snapshot() -> None:
    factory = ControlledClientFactory()
    app = create_openai_app(
        configuration_with_estimate(),
        client_factory=factory,  # type: ignore[arg-type]
    )
    assert factory.client is not None
    client = TestClient(app)

    first = client.post("/v1/executions", json={"task": "First task."})
    second = client.post(
        "/v1/executions",
        json={"task": "Different task.", "context": "Different context."},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert (
        first.json()["economics"]["estimate"] == second.json()["economics"]["estimate"]
    )
    assert len(factory.client.responses.calls) == 2


def test_estimate_within_economic_ceiling_executes_once() -> None:
    factory = ControlledClientFactory()
    app = create_openai_app(
        configuration_with_estimate(),
        client_factory=factory,  # type: ignore[arg-type]
    )
    assert factory.client is not None

    response = TestClient(app).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {
                "max_estimated_cost": {"amount": "0.0023", "currency": "USD"}
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["economics"]["estimate"]["amount"] == "0.0023"
    assert len(factory.client.responses.calls) == 1


def test_estimate_above_economic_ceiling_refuses_without_external_call() -> None:
    factory = ControlledClientFactory()
    app = create_openai_app(
        configuration_with_estimate(),
        client_factory=factory,  # type: ignore[arg-type]
    )
    assert factory.client is not None

    response = TestClient(app).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {
                "max_estimated_cost": {"amount": "0.0022", "currency": "USD"}
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_ELIGIBLE_ROUTE"
    assert response.json()["decision"]["outcome"] == "refused"
    assert "economics" not in response.json()
    assert factory.client.responses.calls == []


def test_estimate_in_another_currency_refuses_without_external_call() -> None:
    factory = ControlledClientFactory()
    app = create_openai_app(
        configuration_with_estimate(),
        client_factory=factory,  # type: ignore[arg-type]
    )
    assert factory.client is not None

    response = TestClient(app).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {"max_estimated_cost": {"amount": "10", "currency": "BRL"}},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_ECONOMIC_INFORMATION"
    assert factory.client.responses.calls == []


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


@pytest.mark.parametrize(
    "configuration",
    [controlled_configuration(), configuration_with_price()],
)
def test_economic_ceiling_refuses_without_external_call(
    configuration: dict[str, str],
) -> None:
    factory = ControlledClientFactory()
    app = create_openai_app(
        configuration, client_factory=factory  # type: ignore[arg-type]
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
    assert response.json()["error"]["code"] == "INSUFFICIENT_ECONOMIC_INFORMATION"
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
    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 200
    assert response.json()["decision"]["route"]["id"] == CONTROLLED_ROUTE_ID
    assert response.json()["decision"]["route"]["model"] == CONTROLLED_MODEL
    assert factory.calls == [{"api_key": CONTROLLED_KEY, **APPROVED_CLIENT_OPTIONS}]
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

    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 200
    assert factory.calls == [
        {"api_key": "  controlled-key-input  ", **APPROVED_CLIENT_OPTIONS}
    ]
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


def make_route_json(
    route_id: str,
    model: str,
    price_id: str,
    input_rate: str = "0.001",
    output_rate: str = "0.004",
    input_tokens: int = 300,
    output_tokens: int = 500,
    currency: str = "USD",
) -> dict[str, Any]:
    return {
        "route_id": route_id,
        "model": model,
        "price_reference": {
            "id": price_id,
            "currency": currency,
            "version": "v1",
            "source": "operator",
            "rates": [
                {"unit": "input_token", "rate": input_rate, "base": 1000},
                {"unit": "output_token", "rate": output_rate, "base": 1000},
            ],
            "conditions": [],
            "context_complete": True,
            "units_exhaustive": True,
            "no_double_counting": True,
            "model_identity_exact": True,
        },
        "estimated_usage": {
            "input_token": input_tokens,
            "output_token": output_tokens,
            "applicability_confirmed": True,
        },
    }


def test_multiroute_selects_lowest_estimate() -> None:
    route_a = make_route_json(
        "route-a", "model-a", "price-a", input_rate="0.001", output_rate="0.004"
    )
    route_b = make_route_json(
        "route-b", "model-b", "price-b", input_rate="0.002", output_rate="0.008"
    )

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    factory = ControlledClientFactory()
    app = create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["decision"]["route"]["id"] == "route-a"
    assert res_data["decision"]["route"]["model"] == "model-a"
    assert res_data["economics"]["estimate"]["amount"] == "0.0023"


def test_multiroute_order_invariance_and_deterministic_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_a = make_route_json(
        "route-a", "model-a", "price-a", input_rate="0.001", output_rate="0.004"
    )
    route_b = make_route_json(
        "route-b", "model-b", "price-b", input_rate="0.002", output_rate="0.008"
    )

    config_1 = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    config_2 = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_b, route_a]}),
    }

    captured_catalogs = []

    def mock_create_app(catalog: RouteCatalog, adapters: Any) -> FastAPI:
        captured_catalogs.append(catalog.snapshot())
        return default_app

    monkeypatch.setattr(bootstrap_module, "create_app", mock_create_app)

    create_openai_app(config_1, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    create_openai_app(config_2, client_factory=ControlledClientFactory())  # type: ignore[arg-type]

    assert len(captured_catalogs) == 2
    assert [r.id for r in captured_catalogs[0]] == ["route-a", "route-b"]
    assert [r.id for r in captured_catalogs[1]] == ["route-a", "route-b"]


def test_multiroute_tie_breaker() -> None:
    route_a = make_route_json(
        "route-a", "model-a", "price-a", input_rate="0.001", output_rate="0.004"
    )
    route_b = make_route_json(
        "route-b", "model-b", "price-b", input_rate="0.001", output_rate="0.004"
    )

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_b, route_a]}),
    }
    factory = ControlledClientFactory()
    app = create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["decision"]["route"]["id"] == "route-a"
    assert any(f["category"] == "tie_breaker" for f in res_data["decision"]["factors"])


def test_multiroute_max_estimated_cost_filtering() -> None:
    route_a = make_route_json(
        "route-a", "model-a", "price-a", input_rate="0.003", output_rate="0.008"
    )
    route_b = make_route_json(
        "route-b", "model-b", "price-b", input_rate="0.002", output_rate="0.006"
    )

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    factory = ControlledClientFactory()
    app = create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    response = TestClient(app).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {
                "max_estimated_cost": {"amount": "0.0040", "currency": "USD"}
            },
        },
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["decision"]["route"]["id"] == "route-b"


def test_multiroute_incompatible_currencies() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a", currency="USD")
    route_b = make_route_json("route-b", "model-b", "price-b", currency="BRL")

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    factory = ControlledClientFactory()
    app = create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_ECONOMIC_INFORMATION"


def test_multiroute_adapter_calls_and_shares() -> None:
    route_a = make_route_json(
        "route-a", "model-a", "price-a", input_rate="0.001", output_rate="0.004"
    )
    route_b = make_route_json(
        "route-b", "model-b", "price-b", input_rate="0.002", output_rate="0.008"
    )

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    factory = ControlledClientFactory()
    app = create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    assert factory.calls == [{"api_key": CONTROLLED_KEY, **APPROVED_CLIENT_OPTIONS}]
    assert factory.client is not None

    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})
    assert response.status_code == 200

    assert len(factory.client.responses.calls) == 1
    assert factory.client.responses.calls[0]["model"] == "model-a"


def test_multiroute_absent_preserves_legacy() -> None:
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_MODEL": CONTROLLED_MODEL,
        "MAESTRO_OPENAI_ROUTE_ID": CONTROLLED_ROUTE_ID,
    }
    factory = ControlledClientFactory()
    app = create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]
    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})
    assert response.status_code == 200
    assert response.json()["decision"]["route"]["id"] == CONTROLLED_ROUTE_ID


@pytest.mark.parametrize(
    "legacy_var",
    [
        "MAESTRO_OPENAI_ROUTE_ID",
        "MAESTRO_OPENAI_MODEL",
        "MAESTRO_OPENAI_PRICE_REFERENCE_JSON",
        "MAESTRO_OPENAI_ESTIMATED_USAGE_JSON",
    ],
)
@pytest.mark.parametrize("legacy_val", ["some-value", "", "   "])
def test_multiroute_legacy_collision_fails(legacy_var: str, legacy_val: str) -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
        legacy_var: legacy_val,
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"
    assert "MAESTRO_OPENAI_ROUTES_JSON contém uma configuração inválida." in str(
        caught.value
    )


@pytest.mark.parametrize(
    "invalid_json",
    [
        "",
        "   ",
        "{",
        "[]",
        '{"routes": []}',
        '{"routes": [null]}',
        '{"routes": [{"route_id": "a", "route_id": "b", "model": "m", "price_reference": {}, "estimated_usage": {}}]}',
        '{"routes": [{"route_id": "a", "model": "m", "price_reference": {}, "estimated_usage": {}, "extra": 1}]}',
        '{"routes": [{"route_id": "a", "model": "m"}]}',
        '{"routes": [{"route_id": "a", "model": "m", "price_reference": null, "estimated_usage": null}]}',
        '{"routes": [{"route_id": "a", "model": "m", "price_reference": {}, "estimated_usage": {}}], "extra": 1}',
        '{"routes": NaN}',
    ],
)
def test_multiroute_invalid_json_shapes_fail(invalid_json: str) -> None:
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": invalid_json,
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"


@pytest.mark.parametrize(
    "invalid_route_id",
    [
        None,
        "",
        "   ",
        123,
        "route\ud800id",
    ],
)
def test_multiroute_invalid_route_id_fails_globally(invalid_route_id: Any) -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    if invalid_route_id is None:
        del route_a["route_id"]
    else:
        route_a["route_id"] = invalid_route_id

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"


def test_multiroute_duplicate_route_id_fails_globally() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_b = make_route_json("route-a", "model-b", "price-b")
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"


def test_multiroute_duplicate_model_fails_globally() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_b = make_route_json("route-b", "model-a", "price-b")
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"


def test_multiroute_duplicate_price_ref_id_fails_globally() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_b = make_route_json("route-b", "model-b", "price-a")
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"


def test_multiroute_isolable_failure_and_invalid_route_explanation() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_b = make_route_json("route-b", "model-b", "price-b")
    route_b["price_reference"]["currency"] = "invalid-currency-format"

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    factory = ControlledClientFactory()
    app = create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    response = TestClient(app).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {"allowed_route_ids": ["route-a", "route-b"]},
        },
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["decision"]["route"]["id"] == "route-a"

    applied_constraints = res_data["decision"]["applied_constraints"]
    assert any(
        c["source"] == "configuration"
        and c["category"] == "route"
        and "configuração local inválida" in c["description"]
        for c in applied_constraints
    )


def test_multiroute_no_valid_routes_fails_initialization() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_a["price_reference"]["currency"] = "invalid-currency"

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"


def test_multiroute_errors_are_sanitized() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_a["price_reference"]["currency"] = "invalid-currency"

    config = {
        "OPENAI_API_KEY": "sensitive-key-12345",
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]

    error_msg = str(caught.value)
    assert "sensitive-key-12345" not in error_msg
    assert "route-a" not in error_msg
    assert "model-a" not in error_msg
    assert "invalid-currency" not in error_msg
    assert "MAESTRO_OPENAI_ROUTES_JSON" in error_msg


def test_multiroute_snapshot_mutation_immunity() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    routes_dict = {"routes": [route_a]}

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps(routes_dict),
    }
    factory = ControlledClientFactory()
    app = create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    config["OPENAI_API_KEY"] = "mutated-key"
    routes_dict["routes"] = []

    response = TestClient(app).post("/v1/executions", json={"task": "Execute."})
    assert response.status_code == 200
    assert response.json()["decision"]["route"]["id"] == "route-a"


def test_multiroute_local_duplicate_in_price_reference() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    routes_json = (
        '{"routes": ['
        + json.dumps(route_a)
        + ', {'
        + '"route_id": "route-b", "model": "model-b", '
        + '"price_reference": {"id": "price-b", "id": "price-c", "currency": "USD", "version": "v1", "source": "operator", "rates": [{"unit": "input_token", "rate": "0.001", "base": 1000}, {"unit": "output_token", "rate": "0.004", "base": 1000}], "conditions": [], "context_complete": true, "units_exhaustive": true, "no_double_counting": true, "model_identity_exact": true}, '
        + '"estimated_usage": {"input_token": 300, "output_token": 500, "applicability_confirmed": true}'
        + '}]}'
    )
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": routes_json,
    }
    app = create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    response = TestClient(app).post(
        "/v1/executions",
        json={"task": "Execute.", "constraints": {"allowed_route_ids": ["route-a", "route-b"]}}
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["decision"]["route"]["id"] == "route-a"
    applied_constraints = res_data["decision"]["applied_constraints"]
    assert any("configuração local inválida" in c["description"] for c in applied_constraints)


def test_multiroute_local_duplicate_in_estimated_usage() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    routes_json = (
        '{"routes": ['
        + json.dumps(route_a)
        + ', {'
        + '"route_id": "route-b", "model": "model-b", '
        + '"price_reference": {"id": "price-b", "currency": "USD", "version": "v1", "source": "operator", "rates": [{"unit": "input_token", "rate": "0.001", "base": 1000}, {"unit": "output_token", "rate": "0.004", "base": 1000}], "conditions": [], "context_complete": true, "units_exhaustive": true, "no_double_counting": true, "model_identity_exact": true}, '
        + '"estimated_usage": {"input_token": 300, "input_token": 400, "output_token": 500, "applicability_confirmed": true}'
        + '}]}'
    )
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": routes_json,
    }
    app = create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    response = TestClient(app).post(
        "/v1/executions",
        json={"task": "Execute.", "constraints": {"allowed_route_ids": ["route-a", "route-b"]}}
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["decision"]["route"]["id"] == "route-a"


def test_multiroute_single_route_local_duplicate() -> None:
    routes_json = (
        '{"routes": [{'
        + '"route_id": "route-b", "model": "model-b", '
        + '"price_reference": {"id": "price-b", "currency": "USD", "version": "v1", "source": "operator", "rates": [{"unit": "input_token", "rate": "0.001", "base": 1000}, {"unit": "output_token", "rate": "0.004", "base": 1000}], "conditions": [], "context_complete": true, "units_exhaustive": true, "no_double_counting": true, "model_identity_exact": true}, '
        + '"estimated_usage": {"input_token": 300, "input_token": 400, "output_token": 500, "applicability_confirmed": true}'
        + '}]}'
    )
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": routes_json,
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"


def test_multiroute_price_ref_id_surrogate_isolated() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_b = make_route_json("route-b", "model-b", "price\ud800id")
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    app = create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    response = TestClient(app).post(
        "/v1/executions",
        json={"task": "Execute.", "constraints": {"allowed_route_ids": ["route-a", "route-b"]}}
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["decision"]["route"]["id"] == "route-a"


def test_multiroute_single_route_price_ref_id_surrogate() -> None:
    route_a = make_route_json("route-a", "model-a", "price\ud800id")
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"


def test_multiroute_sensitive_values_absent_in_errors() -> None:
    route_a = make_route_json("route-a", "model-a", "price\ud800id")
    config = {
        "OPENAI_API_KEY": "sensitive-key-99999",
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    error_msg = str(caught.value)
    assert "sensitive-key-99999" not in error_msg
    assert "price\ud800id" not in error_msg
    assert "price" not in error_msg
    assert "route-a" not in error_msg
    assert "model-a" not in error_msg


def test_multiroute_catalog_contains_only_valid_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_b = make_route_json("route-b", "model-b", "price-b")
    route_b["price_reference"]["currency"] = "invalid-currency-format"

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }

    captured_catalog = None
    def mock_create_app(catalog: RouteCatalog, adapters: Any) -> FastAPI:
        nonlocal captured_catalog
        captured_catalog = catalog
        return default_app

    monkeypatch.setattr(bootstrap_module, "create_app", mock_create_app)
    create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]

    assert captured_catalog is not None
    snapshot = captured_catalog.snapshot()
    assert len(snapshot) == 1
    assert snapshot[0].id == "route-a"
    assert "route-b" not in [r.id for r in snapshot]
    assert "invalid-model" not in [r.model for r in snapshot]
    assert not any("invalid-adapter" in r.adapter_id for r in snapshot)
    assert captured_catalog.configuration_invalid_route_ids == frozenset(["route-b"])


def test_multiroute_allowlist_only_invalid_route_refuses() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_b = make_route_json("route-b", "model-b", "price-b")
    route_b["price_reference"]["currency"] = "invalid-currency-format"

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    app = create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]

    response = TestClient(app).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {"allowed_route_ids": ["route-b"]},
        },
    )
    assert response.status_code == 422
    res_data = response.json()
    assert res_data["error"]["code"] == "NO_ELIGIBLE_ROUTE"


def test_multiroute_invalid_cheaper_route_not_selected() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a", input_rate="0.005", output_rate="0.010")
    route_b_json = (
        '{'
        + '"route_id": "route-b", "model": "model-b", '
        + '"price_reference": {"id": "price-b", "id": "price-c", "currency": "USD", "version": "v1", "source": "operator", "rates": [{"unit": "input_token", "rate": "0.001", "base": 1000}, {"unit": "output_token", "rate": "0.002", "base": 1000}], "conditions": [], "context_complete": true, "units_exhaustive": true, "no_double_counting": true, "model_identity_exact": true}, '
        + '"estimated_usage": {"input_token": 300, "output_token": 500, "applicability_confirmed": true}'
        + '}'
    )
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": '{"routes": [' + json.dumps(route_a) + ', ' + route_b_json + ']}',
    }
    app = create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]

    response = TestClient(app).post(
        "/v1/executions",
        json={"task": "Execute."},
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["decision"]["route"]["id"] == "route-a"


def test_multiroute_all_routes_invalid_fails_initialization() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_a["price_reference"]["currency"] = "invalid-currency"
    route_b = make_route_json("route-b", "model-b", "price-b")
    route_b["price_reference"]["currency"] = "invalid-currency"

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"


def test_route_catalog_validation_invariants() -> None:
    from maestro_router.routing import Route, EconomicEstimate, RouteCatalog

    route_a = Route(
        id="route-a",
        provider="openai",
        model="gpt-4",
        adapter_id="openai-responses",
        enabled=True,
        capabilities=frozenset(),
        quality_criteria=frozenset(),
        known_unavailable=False,
        estimate=EconomicEstimate(status="unavailable", reason="Unavailable."),
        price_reference=None,
    )
    # 1. aceita IDs de configuração válidos, únicos e ausentes do catálogo executável;
    catalog = RouteCatalog([route_a], configuration_invalid_route_ids=["route-b", "route-c"])
    # 2. armazena-os imutavelmente;
    assert isinstance(catalog.configuration_invalid_route_ids, frozenset)
    assert catalog.configuration_invalid_route_ids == frozenset(["route-b", "route-c"])

    # 3. rejeita ID vazio ou branco;
    with pytest.raises(ValueError) as caught:
        RouteCatalog([route_a], configuration_invalid_route_ids=[""])
    assert "non-blank strings" in str(caught.value)

    with pytest.raises(ValueError) as caught:
        RouteCatalog([route_a], configuration_invalid_route_ids=["   "])
    assert "non-blank strings" in str(caught.value)

    # 4. rejeita tipo diferente de string;
    with pytest.raises(ValueError) as caught:
        RouteCatalog([route_a], configuration_invalid_route_ids=[123])  # type: ignore[list-item]
    assert "non-blank strings" in str(caught.value)

    # 5. rejeita surrogate isolado;
    with pytest.raises(ValueError) as caught:
        RouteCatalog([route_a], configuration_invalid_route_ids=["price\ud800id"])
    assert "isolated Unicode surrogates" in str(caught.value)

    # 6. rejeita duplicidade antes da conversão para conjunto;
    with pytest.raises(ValueError) as caught:
        RouteCatalog([route_a], configuration_invalid_route_ids=["route-b", "route-b"])
    assert "must be unique" in str(caught.value)

    # 7. rejeita interseção com um route.id executável;
    with pytest.raises(ValueError) as caught:
        RouteCatalog([route_a], configuration_invalid_route_ids=["route-a"])
    assert "must not overlap with executable route IDs" in str(caught.value)


def test_route_catalog_carries_exclusion_to_explanation() -> None:
    from maestro_router.routing import Route, EconomicEstimate, RouteCatalog
    from maestro_router.api import create_app

    route_a = Route(
        id="route-a",
        provider="openai",
        model="gpt-4",
        adapter_id="openai-responses",
        enabled=True,
        capabilities=frozenset(),
        quality_criteria=frozenset(),
        known_unavailable=False,
        estimate=EconomicEstimate(status="unavailable", reason="Unavailable."),
        price_reference=None,
    )
    catalog = RouteCatalog([route_a], configuration_invalid_route_ids=["route-b"])

    from maestro_router.execution import TextExecutionResult

    class MockAdapter:
        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            return TextExecutionResult(content="Success.")

    app = create_app(catalog, {"openai-responses": MockAdapter()})
    response = TestClient(app).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {"allowed_route_ids": ["route-a", "route-b"]},
        },
    )
    assert response.status_code == 200
    res_data = response.json()
    applied_constraints = res_data["decision"]["applied_constraints"]
    assert any(
        c["source"] == "configuration"
        and c["category"] == "route"
        and "route-b possuía configuração local inválida" in c["description"]
        for c in applied_constraints
    )


# ---------------------------------------------------------------------------
# ADR 0009: Operational Routing Constraints & Extended Route Bootstrap Tests
# ---------------------------------------------------------------------------

ROUTING_CONSTRAINTS_VARIABLE = "MAESTRO_ROUTING_CONSTRAINTS_JSON"


def make_extended_route_json(
    route_id: str,
    model: str,
    price_id: str,
    input_rate: str = "0.001",
    output_rate: str = "0.004",
    input_tokens: int = 1500,
    output_tokens: int = 200,
    currency: str = "USD",
    capabilities: list[str] | None = None,
    quality_criteria: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    base = make_route_json(
        route_id=route_id,
        model=model,
        price_id=price_id,
        input_rate=input_rate,
        output_rate=output_rate,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        currency=currency,
    )
    if capabilities is not None:
        base["capabilities"] = capabilities
    if quality_criteria is not None:
        base["quality_criteria"] = quality_criteria
    return base


def test_routing_constraints_requires_multiroute_mode() -> None:
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        ROUTING_CONSTRAINTS_VARIABLE: json.dumps({"required_capabilities": ["chat"]}),
    }
    factory = ControlledClientFactory()
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == ROUTING_CONSTRAINTS_VARIABLE
    assert factory.calls == []
    assert factory.client is None


@pytest.mark.parametrize(
    "legacy_key,legacy_val",
    [
        ("MAESTRO_OPENAI_ROUTE_ID", "legacy-id"),
        ("MAESTRO_OPENAI_ROUTE_ID", ""),
        ("MAESTRO_OPENAI_ROUTE_ID", "   "),
        ("MAESTRO_OPENAI_MODEL", "gpt-4"),
        ("MAESTRO_OPENAI_PRICE_REFERENCE_JSON", "{}"),
        ("MAESTRO_OPENAI_ESTIMATED_USAGE_JSON", "{}"),
    ],
)
def test_routing_constraints_rejects_legacy_variables(legacy_key: str, legacy_val: str) -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
        ROUTING_CONSTRAINTS_VARIABLE: json.dumps({"required_capabilities": ["chat"]}),
        legacy_key: legacy_val,
    }
    factory = ControlledClientFactory()
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == ROUTING_CONSTRAINTS_VARIABLE
    assert factory.calls == []
    assert factory.client is None


def test_routing_constraints_sanitized_error_message() -> None:
    raw_payload = '{"required_capabilities": ["sensitive-secret-value-99"]}'
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        ROUTING_CONSTRAINTS_VARIABLE: raw_payload,
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]

    msg = str(caught.value)
    assert ROUTING_CONSTRAINTS_VARIABLE in msg
    assert "sensitive-secret-value-99" not in msg
    assert raw_payload not in msg


def test_routing_constraints_valid_configuration_passes_to_catalog() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    constraints_doc = {
        "required_capabilities": ["global-cap"],
        "required_quality_criteria": ["global-crit"],
        "allowed_route_ids": ["route-a"],
        "max_estimated_costs": [{"currency": "USD", "amount": "1.0000"}],
        "defaults": {
            "required_capabilities": ["default-cap"],
            "required_quality_criteria": ["default-crit"],
            "allowed_route_ids": ["default-route"],
            "max_estimated_cost": {"currency": "USD", "amount": "0.5000"},
        },
    }
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
        ROUTING_CONSTRAINTS_VARIABLE: json.dumps(constraints_doc),
    }

    captured_catalog: list[RouteCatalog] = []

    def mock_create_app(catalog: RouteCatalog, adapters: Any) -> FastAPI:
        captured_catalog.append(catalog)
        return default_app

    import maestro_router.bootstrap as bm

    orig_create_app = bm.create_app
    bm.create_app = mock_create_app
    try:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    finally:
        bm.create_app = orig_create_app

    assert len(captured_catalog) == 1
    cat = captured_catalog[0]
    oc = cat.operational_constraints
    assert oc.required_capabilities == frozenset({"global-cap"})
    assert oc.required_quality_criteria == frozenset({"global-crit"})
    assert oc.allowed_route_ids == frozenset({"route-a"})
    assert len(oc.max_estimated_costs) == 1
    assert oc.max_estimated_costs[0].amount == "1.0000"
    assert oc.max_estimated_costs[0].currency == "USD"
    assert oc.defaults.required_capabilities == frozenset({"default-cap"})
    assert oc.defaults.required_quality_criteria == frozenset({"default-crit"})
    assert oc.defaults.allowed_route_ids == frozenset({"default-route"})
    assert oc.defaults.max_estimated_cost is not None
    assert oc.defaults.max_estimated_cost.amount == "0.5000"
    assert oc.defaults.max_estimated_cost.currency == "USD"


@pytest.mark.parametrize(
    "invalid_constraints_raw",
    [
        "",
        "   ",
        "invalid json",
        "123",
        '"string"',
        "[]",
        "{}",
        '{"defaults": {}}',
        '{"unknown_top_field": 1}',
        '{"defaults": {"unknown_sub_field": 1}}',
        '{"required_capabilities": []}',
        '{"required_quality_criteria": []}',
        '{"allowed_route_ids": []}',
        '{"max_estimated_costs": []}',
        '{"defaults": {"required_capabilities": []}}',
        '{"defaults": {"required_quality_criteria": []}}',
        '{"defaults": {"allowed_route_ids": []}}',
        '{"required_capabilities": null}',
        '{"defaults": null}',
        '{"max_estimated_costs": null}',
        '{"required_capabilities": [123]}',
        '{"required_capabilities": ["   "]}',
        '{"required_capabilities": ["\\ud800"]}',
        '{"required_capabilities": ["dup", "dup"]}',
        '{"required_quality_criteria": ["qc", "qc"]}',
        '{"allowed_route_ids": ["r1", "r1"]}',
        '{"defaults": {"required_capabilities": ["dup", "dup"]}}',
        '{"max_estimated_costs": [{"currency": "USD", "amount": "1.0000", "extra": 1}]}',
        '{"max_estimated_costs": [{"currency": "usd", "amount": "1.0000"}]}',
        '{"max_estimated_costs": [{"currency": "USDT", "amount": "1.0000"}]}',
        '{"max_estimated_costs": [{"currency": "USD", "amount": 1.0}]}',
        '{"max_estimated_costs": [{"currency": "USD", "amount": "not-decimal"}]}',
        '{"max_estimated_costs": [{"currency": "USD", "amount": "1.0000"}, {"currency": "USD", "amount": "2.0000"}]}',
        '{"defaults": {"max_estimated_cost": {"currency": "USD", "amount": 1.0}}}',
        '{"defaults": {"max_estimated_cost": {"currency": "US", "amount": "1.0000"}}}',
        '{"defaults": {"max_estimated_cost": {"currency": "USD", "amount": "abc"}}}',
        '{"defaults": {"max_estimated_cost": {}}}',
        '{"required_capabilities": ["c1"], "required_capabilities": ["c2"]}',
        '{"defaults": {"required_capabilities": ["c1"], "required_capabilities": ["c2"]}}',
        '{"max_estimated_costs": [{"currency": "USD", "currency": "USD", "amount": "1.0000"}]}',
        '{"max_estimated_costs": [{"currency": "USD", "amount": NaN}]}',
    ],
)
def test_routing_constraints_strict_parsing_rejections(invalid_constraints_raw: str) -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
        ROUTING_CONSTRAINTS_VARIABLE: invalid_constraints_raw,
    }
    factory = ControlledClientFactory()
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == ROUTING_CONSTRAINTS_VARIABLE
    assert factory.calls == []
    assert factory.client is None


def test_route_extended_fields_valid() -> None:
    route_a = make_extended_route_json(
        "route-a",
        "model-a",
        "price-a",
        capabilities=["fast", "vision"],
        quality_criteria=[
            {"criterion": "math", "evidence_references": ["gsm8k-ref", "math-ref"]},
            {"criterion": "coding", "evidence_references": ["humaneval-ref"]},
        ],
    )
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
    }
    captured_routes: list[tuple[Any, ...]] = []

    def mock_create_app(catalog: RouteCatalog, adapters: Any) -> FastAPI:
        captured_routes.append(catalog.snapshot())
        return default_app

    import maestro_router.bootstrap as bm

    orig_create_app = bm.create_app
    bm.create_app = mock_create_app
    try:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    finally:
        bm.create_app = orig_create_app

    assert len(captured_routes) == 1
    r = captured_routes[0][0]
    assert r.capabilities == frozenset({"fast", "vision"})
    assert r.quality_criteria == frozenset({"math", "coding"})
    assert r.quality_evidence_references == {
        "math": ("gsm8k-ref", "math-ref"),
        "coding": ("humaneval-ref",),
    }


def test_route_extended_fields_omitted_defaults_to_empty() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
    }
    captured_routes: list[tuple[Any, ...]] = []

    def mock_create_app(catalog: RouteCatalog, adapters: Any) -> FastAPI:
        captured_routes.append(catalog.snapshot())
        return default_app

    import maestro_router.bootstrap as bm

    orig_create_app = bm.create_app
    bm.create_app = mock_create_app
    try:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    finally:
        bm.create_app = orig_create_app

    assert len(captured_routes) == 1
    r = captured_routes[0][0]
    assert r.capabilities == frozenset()
    assert r.quality_criteria == frozenset()
    assert r.quality_evidence_references == {}


@pytest.mark.parametrize(
    "malformed_route_extra",
    [
        {"capabilities": []},
        {"capabilities": [123]},
        {"capabilities": ["   "]},
        {"capabilities": ["\ud800"]},
        {"capabilities": ["dup", "dup"]},
        {"quality_criteria": []},
        {"quality_criteria": ["not-a-dict"]},
        {"quality_criteria": [{"criterion": "c"}]},
        {"quality_criteria": [{"evidence_references": ["ref1"]}]},
        {"quality_criteria": [{"criterion": "c", "evidence_references": []}]},
        {"quality_criteria": [{"criterion": "c", "evidence_references": [123]}]},
        {"quality_criteria": [{"criterion": "c", "evidence_references": ["   "]}]},
        {"quality_criteria": [{"criterion": "c", "evidence_references": ["\ud800"]}]},
        {"quality_criteria": [{"criterion": "c", "evidence_references": ["ref1", "ref1"]}]},
        {"quality_criteria": [{"criterion": "   ", "evidence_references": ["ref1"]}]},
        {"quality_criteria": [{"criterion": "\ud800", "evidence_references": ["ref1"]}]},
        {
            "quality_criteria": [
                {"criterion": "dup", "evidence_references": ["ref1"]},
                {"criterion": "dup", "evidence_references": ["ref2"]},
            ]
        },
        {"quality_criteria": [{"criterion": "c", "evidence_references": ["ref1"], "extra": 1}]},
        {"unknown_field": "val"},
    ],
)
def test_route_local_isolation_for_malformed_extended_fields(malformed_route_extra: dict[str, Any]) -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_a.update(malformed_route_extra)
    route_b = make_route_json("route-b", "model-b", "price-b")

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    captured_catalogs: list[RouteCatalog] = []

    def mock_create_app(catalog: RouteCatalog, adapters: Any) -> FastAPI:
        captured_catalogs.append(catalog)
        return default_app

    import maestro_router.bootstrap as bm

    orig_create_app = bm.create_app
    bm.create_app = mock_create_app
    try:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    finally:
        bm.create_app = orig_create_app

    assert len(captured_catalogs) == 1
    cat = captured_catalogs[0]
    assert [r.id for r in cat.snapshot()] == ["route-b"]
    assert cat.configuration_invalid_route_ids == frozenset({"route-a"})


def test_all_routes_locally_invalid_fails_startup() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    route_a["capabilities"] = []
    route_b = make_route_json("route-b", "model-b", "price-b")
    route_b["quality_criteria"] = []

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    factory = ControlledClientFactory()
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"
    assert factory.calls == []
    assert factory.client is None


def test_global_uniqueness_still_enforced_with_extended_fields() -> None:
    route_a = make_extended_route_json("route-dup", "model-a", "price-a", capabilities=["cap1"])
    route_b = make_extended_route_json("route-dup", "model-b", "price-b", capabilities=["cap2"])

    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a, route_b]}),
    }
    factory = ControlledClientFactory()
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=factory)  # type: ignore[arg-type]

    assert caught.value.variable_name == "MAESTRO_OPENAI_ROUTES_JSON"
    assert factory.calls == []
    assert factory.client is None


def test_snapshot_immutability_against_environment_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    constraints = {"required_capabilities": ["cap1"]}

    monkeypatch.setenv("OPENAI_API_KEY", CONTROLLED_KEY)
    monkeypatch.setenv("MAESTRO_OPENAI_ROUTES_JSON", json.dumps({"routes": [route_a]}))
    monkeypatch.setenv(ROUTING_CONSTRAINTS_VARIABLE, json.dumps(constraints))

    captured_catalog: list[RouteCatalog] = []

    def mock_create_app(catalog: RouteCatalog, adapters: Any) -> FastAPI:
        captured_catalog.append(catalog)
        return default_app

    import maestro_router.bootstrap as bm

    factory = ControlledClientFactory()
    orig_create_adapter = bm._create_openai_adapter
    monkeypatch.setattr(bm, "create_app", mock_create_app)
    monkeypatch.setattr(
        bm,
        "_create_openai_adapter",
        lambda api_key, client_factory=None: orig_create_adapter(api_key, factory),
    )

    create_openai_app_from_env()

    # Mutate environment
    monkeypatch.setenv(ROUTING_CONSTRAINTS_VARIABLE, json.dumps({"required_capabilities": ["mutated"]}))

    cat = captured_catalog[0]
    assert cat.operational_constraints.required_capabilities == frozenset({"cap1"})
    assert len(factory.calls) == 1
    assert factory.calls[0]["api_key"] == CONTROLLED_KEY


def test_snapshot_immutability_against_input_mutation() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    constraints = {"required_capabilities": ["cap1"]}
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
        ROUTING_CONSTRAINTS_VARIABLE: json.dumps(constraints),
    }

    captured_catalog: list[RouteCatalog] = []

    def mock_create_app(catalog: RouteCatalog, adapters: Any) -> FastAPI:
        captured_catalog.append(catalog)
        return default_app

    import maestro_router.bootstrap as bm

    orig_create_app = bm.create_app
    bm.create_app = mock_create_app
    try:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]
    finally:
        bm.create_app = orig_create_app

    # Mutate input dict
    config[ROUTING_CONSTRAINTS_VARIABLE] = json.dumps({"required_capabilities": ["mutated"]})

    cat = captured_catalog[0]
    assert cat.operational_constraints.required_capabilities == frozenset({"cap1"})


def test_route_quality_evidence_references_empty_map_defense() -> None:
    refs: dict[str, tuple[str, ...]] = {}
    route = Route(
        id="route-r",
        provider="openai",
        model="model-m",
        adapter_id="openai-responses",
        quality_evidence_references=refs,
    )
    # Mutate source dict
    refs["injected"] = ("bad-evidence",)
    assert route.quality_evidence_references == {}
    assert len(route.quality_evidence_references) == 0

    # Attempt modification via route attribute
    with pytest.raises(TypeError):
        route.quality_evidence_references["injected"] = ("bad-evidence",)  # type: ignore[index]


def test_route_quality_evidence_references_filled_map_defense() -> None:
    source_list = ["ref-z", "ref-a"]
    refs = {"quality-crit": source_list}
    route = Route(
        id="route-r",
        provider="openai",
        model="model-m",
        adapter_id="openai-responses",
        quality_evidence_references=refs,
    )
    # Mutate source structures
    source_list.append("ref-injected")
    refs["new-crit"] = ["ref-other"]

    assert route.quality_evidence_references["quality-crit"] == ("ref-a", "ref-z")
    assert isinstance(route.quality_evidence_references["quality-crit"], tuple)
    assert "new-crit" not in route.quality_evidence_references

    # Attempt modification via route attribute
    with pytest.raises(TypeError):
        route.quality_evidence_references["quality-crit"] = ("mutated",)  # type: ignore[index]
    with pytest.raises(TypeError):
        route.quality_evidence_references["new-crit"] = ("other",)  # type: ignore[index]


def test_route_quality_evidence_references_default_compatibility() -> None:
    route = Route(
        id="route-r",
        provider="openai",
        model="model-m",
        adapter_id="openai-responses",
    )
    assert route.quality_evidence_references == {}
    assert len(route.quality_evidence_references) == 0
    with pytest.raises(TypeError):
        route.quality_evidence_references["q"] = ("val",)  # type: ignore[index]


@pytest.mark.parametrize(
    ("invalid_constraints", "expected_path", "sensitive_values"),
    [
        (
            {"defaults": {"max_estimated_cost": {"currency": "USD", "amount": "invalid-amt"}}},
            "defaults.max_estimated_cost.amount",
            ["invalid-amt"],
        ),
        (
            {"defaults": {"max_estimated_cost": {"currency": "invalid-curr", "amount": "1.0000"}}},
            "defaults.max_estimated_cost.currency",
            ["invalid-curr"],
        ),
        (
            {
                "max_estimated_costs": [
                    {"currency": "USD", "amount": "1.0000"},
                    {"currency": "EUR", "amount": "sensitive-eur-amount-999"},
                ]
            },
            "max_estimated_costs[1].amount",
            ["sensitive-eur-amount-999"],
        ),
        (
            {"required_capabilities": ["   "]},
            "required_capabilities[0]",
            ["   "],
        ),
        (
            {"defaults": {"required_quality_criteria": ["valid-crit", "   "]}},
            "defaults.required_quality_criteria[1]",
            ["   "],
        ),
        (
            {
                "max_estimated_costs": [
                    {"currency": "USD", "amount": "1.0000"},
                    {"currency": "USD", "amount": "2.0000"},
                ]
            },
            "max_estimated_costs[1].currency",
            ["2.0000"],
        ),
        (
            {"required_capabilities": ["sensitive-cap-1", "sensitive-cap-1"]},
            "required_capabilities[1]",
            ["sensitive-cap-1"],
        ),
        (
            {"defaults": {"unknown_operator_setting_xyz": "sensitive-value-secret"}},
            "defaults",
            ["unknown_operator_setting_xyz", "sensitive-value-secret"],
        ),
        (
            {
                "defaults": {
                    "max_estimated_cost": {
                        "currency": "USD",
                        "amount": "1.0000",
                        "operator_private_secret_field": "secret-val",
                    }
                }
            },
            "defaults.max_estimated_cost",
            ["operator_private_secret_field", "secret-val"],
        ),
        (
            {
                "max_estimated_costs": [
                    {
                        "currency": "USD",
                        "amount": "1.0000",
                        "operator_custom_annotation": "do-not-leak",
                    }
                ]
            },
            "max_estimated_costs[0]",
            ["operator_custom_annotation", "do-not-leak"],
        ),
    ],
)
def test_routing_constraints_sanitized_error_locations_and_no_leakage(
    invalid_constraints: dict[str, Any],
    expected_path: str,
    sensitive_values: list[str],
) -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
        ROUTING_CONSTRAINTS_VARIABLE: json.dumps(invalid_constraints),
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]

    error = caught.value
    assert error.variable_name == ROUTING_CONSTRAINTS_VARIABLE
    assert error.path == expected_path
    msg = str(error)
    assert f"{ROUTING_CONSTRAINTS_VARIABLE} contém uma configuração inválida em {expected_path}." == msg
    for sensitive in sensitive_values:
        assert sensitive not in msg


def test_routing_constraints_duplicate_json_keys_sanitized() -> None:
    route_a = make_route_json("route-a", "model-a", "price-a")
    raw_json = (
        '{"defaults": {"max_estimated_cost": {'
        '"currency": "USD", "amount": "1.0000", "amount": "sensitive-amount-2.0000"'
        "}},"
        '"allowed_route_ids": ["route-a"]}'
    )
    config = {
        "OPENAI_API_KEY": CONTROLLED_KEY,
        "MAESTRO_OPENAI_ROUTES_JSON": json.dumps({"routes": [route_a]}),
        ROUTING_CONSTRAINTS_VARIABLE: raw_json,
    }
    with pytest.raises(InvalidRuntimeConfigurationError) as caught:
        create_openai_app(config, client_factory=ControlledClientFactory())  # type: ignore[arg-type]

    error = caught.value
    assert error.variable_name == ROUTING_CONSTRAINTS_VARIABLE
    assert error.path == "defaults.max_estimated_cost.amount"
    msg = str(error)
    assert "defaults.max_estimated_cost.amount" in msg
    assert "sensitive-amount-2.0000" not in msg

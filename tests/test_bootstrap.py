from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
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
    create_openai_app_from_env,
)
from maestro_router.routing import RouteCatalog


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
CONTROLLED_ESTIMATE_ASSUMPTIONS = [
    "A estimativa considera 300 unidades de input_token configuradas pelo operador.",
    "A estimativa considera 500 unidades de output_token configuradas pelo operador.",
]


class FakeResponses:
    def __init__(self, usage: object | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.usage = usage

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        text_part = SimpleNamespace(type="output_text", text="controlled result")
        message = SimpleNamespace(type="message", content=[text_part])
        response = SimpleNamespace(
            status="completed",
            output=[message],
            output_text="controlled result",
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
    def __init__(self, usage: object | None = None) -> None:
        self.client: FakeAsyncOpenAI | None = None
        self.calls: list[dict[str, str]] = []
        self.usage = usage

    def __call__(self, **kwargs: str) -> FakeAsyncOpenAI:
        self.calls.append(kwargs)
        self.client = FakeAsyncOpenAI(self.usage)
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
        valid_estimated_usage_document()
        if usage_document is None
        else usage_document
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
    _assert_invalid_price_configuration(
        json.dumps(changed_price_document(rates=rates))
    )


@pytest.mark.parametrize("field", [
    "context_complete",
    "units_exhaustive",
    "no_double_counting",
    "model_identity_exact",
])
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
    document = changed_estimated_usage_document(
        applicability_confirmed=invalid_value
    )
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
    assert factory.calls == [{"api_key": CONTROLLED_KEY}]


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
    assert adapter_calls == [((factory.client,), {})]


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

    response = TestClient(app).post(
        "/v1/executions", json={"task": "Execute."}
    )

    assert response.status_code == 200
    economics = response.json()["economics"]
    assert economics["estimate"] == {
        "status": "unavailable",
        "reason": UNAVAILABLE_ESTIMATE_REASON,
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

    response = TestClient(app).post(
        "/v1/executions", json={"task": "Execute."}
    )

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
    assert economics["estimate"]["amount"] != economics["calculated_cost"][
        "amount"
    ]
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
    assert first.json()["economics"]["estimate"] == second.json()["economics"][
        "estimate"
    ]
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
            "constraints": {
                "max_estimated_cost": {"amount": "10", "currency": "BRL"}
            },
        },
    )

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_ECONOMIC_INFORMATION"
    )
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

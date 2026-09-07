from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import maestro_router.api as api_module
from maestro_router.api import create_app
from maestro_router.contracts import (
    AvailableUsage,
    ExecutionEconomics,
    UnavailableEconomicValue,
    UncertainEconomicValue,
)
from maestro_router.economics import (
    PriceReference,
    UnitPrice,
    calculate_post_execution_cost,
)
from maestro_router.execution import (
    ExecutionRoute,
    NormalizedUsage,
    NormalizedUsageItem,
    TextExecutionRequest,
    TextExecutionResult,
)
from maestro_router.routing import EconomicEstimate, Route, RouteCatalog


SENSITIVE_DETAIL = "secret price source and external payload"


class ControlledAdapter:
    def __init__(
        self,
        usage: NormalizedUsage,
        observed_model: str = "model-a",
    ) -> None:
        self.usage = usage
        self.observed_model = observed_model
        self.calls: list[tuple[TextExecutionRequest, ExecutionRoute]] = []

    async def execute(
        self, request: TextExecutionRequest, route: ExecutionRoute
    ) -> TextExecutionResult:
        self.calls.append((request, route))
        return TextExecutionResult(
            content="controlled result",
            usage=self.usage,
            observed_model=self.observed_model,
        )


def complete_usage(
    input_quantity: int = 310, output_quantity: int = 86
) -> NormalizedUsage:
    return NormalizedUsage(
        status="available",
        items=(
            NormalizedUsageItem("input_token", input_quantity),
            NormalizedUsageItem("output_token", output_quantity),
        ),
    )


def available_estimate(
    *, currency: str = "USD", reference: str = "pricing-test"
) -> EconomicEstimate:
    return EconomicEstimate(
        status="available",
        amount="0.01",
        currency=currency,
        price_reference=reference,
        assumptions=("Estimativa anterior preservada.",),
    )


def uncertain_estimate() -> EconomicEstimate:
    return EconomicEstimate(
        status="uncertain",
        amount="0.01",
        currency="USD",
        price_reference="pricing-test",
        assumptions=("Estimativa anterior aproximada.",),
        reason="A estimativa anterior possui limitação material.",
    )


def unavailable_estimate() -> EconomicEstimate:
    return EconomicEstimate(
        status="unavailable",
        reason="A estimativa anterior não estava disponível.",
    )


def price_reference(
    *,
    rates: tuple[UnitPrice, ...] | None = None,
    **changes: object,
) -> PriceReference:
    values: dict[str, object] = {
        "id": "pricing-test",
        "route_id": "route-a",
        "provider": "provider-a",
        "model": "model-a",
        "currency": "USD",
        "version": "verified-2026-08-23",
        "source": "operator-maintained-reference",
        "rates": (
            rates
            if rates is not None
            else (
                UnitPrice("input_token", "0.001", 1000),
                UnitPrice("output_token", "0.004", 1000),
            )
        ),
        "conditions": ("standard-text-context",),
        "context_complete": True,
        "units_exhaustive": True,
        "no_double_counting": True,
        "model_identity_exact": True,
    }
    values.update(changes)
    return PriceReference(**values)  # type: ignore[arg-type]


def configured_route(
    *,
    estimate: EconomicEstimate | None = None,
    reference: PriceReference | None = None,
    route_id: str = "route-a",
    provider: str = "provider-a",
    model: str = "model-a",
    adapter_id: str = "adapter-a",
) -> Route:
    return Route(
        id=route_id,
        provider=provider,
        model=model,
        adapter_id=adapter_id,
        estimate=estimate or available_estimate(),
        price_reference=reference,
    )


def response_for(
    *,
    estimate: EconomicEstimate | None = None,
    reference: PriceReference | None = None,
    usage: NormalizedUsage | None = None,
    observed_model: str = "model-a",
) -> tuple[dict[str, object], ControlledAdapter]:
    route = configured_route(estimate=estimate, reference=reference)
    adapter = ControlledAdapter(
        usage or complete_usage(), observed_model=observed_model
    )
    response = TestClient(
        create_app(RouteCatalog((route,)), {route.adapter_id: adapter})
    ).post("/v1/executions", json={"task": "Execute."})
    assert response.status_code == 200
    return response.json(), adapter


@pytest.mark.parametrize("rate", [True, 1, 1.0, "-1", "+1", "01", ".1", "1e3", "NaN"])
def test_unit_price_rejects_non_normative_rates(rate: object) -> None:
    with pytest.raises(ValueError, match="decimal string"):
        UnitPrice("input_token", rate, 1000)  # type: ignore[arg-type]


@pytest.mark.parametrize("base", [True, 0, -10, 3, 20, 1.0, "1000"])
def test_unit_price_requires_integer_power_of_ten(base: object) -> None:
    with pytest.raises(ValueError, match="power of ten"):
        UnitPrice("input_token", "0.1", base)  # type: ignore[arg-type]


@pytest.mark.parametrize("unit", ["", "   ", "\t"])
def test_unit_price_requires_non_blank_unit(unit: str) -> None:
    with pytest.raises(ValueError, match="non-blank"):
        UnitPrice(unit, "0.1", 1)


@pytest.mark.parametrize(
    "field",
    ["id", "route_id", "provider", "model", "version", "source"],
)
def test_price_reference_requires_non_blank_identity_and_metadata(field: str) -> None:
    with pytest.raises(ValueError, match="non-blank"):
        price_reference(**{field: "   "})


def test_price_reference_validates_currency_units_conditions_and_flags() -> None:
    with pytest.raises(ValueError, match="currency"):
        price_reference(currency="usd")
    with pytest.raises(ValueError, match="unique"):
        price_reference(
            rates=(
                UnitPrice("input_token", "1", 1),
                UnitPrice("input_token", "2", 1),
            )
        )
    with pytest.raises(ValueError, match="immutable tuple"):
        price_reference(rates=[])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="conditions"):
        price_reference(conditions=("   ",))
    with pytest.raises(ValueError, match="explicit boolean"):
        price_reference(context_complete=1)


def test_price_reference_and_rates_are_deeply_immutable_and_ordered() -> None:
    output_rate = UnitPrice("output_token", "0.004", 1000)
    reference = price_reference(
        rates=(output_rate, UnitPrice("input_token", "0.001", 1000)),
        conditions=("z-condition", "a-condition"),
    )

    assert tuple(rate.unit for rate in reference.rates) == (
        "input_token",
        "output_token",
    )
    assert reference.conditions == ("a-condition", "z-condition")
    with pytest.raises(FrozenInstanceError):
        reference.currency = "EUR"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        output_rate.rate = "9"  # type: ignore[misc]


def test_exact_cost_uses_independent_input_and_output_rates() -> None:
    cost = calculate_post_execution_cost(
        route_id="route-a",
        provider="provider-a",
        model="model-a",
        estimate=available_estimate(),
        usage=complete_usage(),
        reference=price_reference(),
    )

    assert cost.status == "available"
    assert cost.amount == "0.000654"
    assert cost.currency == "USD"
    assert cost.price_reference == "pricing-test"
    assert cost.assumptions == ()


@pytest.mark.parametrize(
    ("unsupported_unit", "include_input"),
    [
        ("total_tokens", True),
        ("cached_input_token", False),
        ("cache_write_token", False),
        ("reasoning_token", False),
        (SENSITIVE_DETAIL, False),
    ],
)
def test_matching_unsupported_units_keep_cost_unavailable(
    unsupported_unit: str, include_input: bool
) -> None:
    usage_items = (NormalizedUsageItem(unsupported_unit, 15),)
    rates = (UnitPrice(unsupported_unit, "1", 1),)
    if include_input:
        usage_items = (NormalizedUsageItem("input_token", 10), *usage_items)
        rates = (UnitPrice("input_token", "1", 1), *rates)

    cost = calculate_post_execution_cost(
        route_id="route-a",
        provider="provider-a",
        model="model-a",
        estimate=available_estimate(),
        usage=NormalizedUsage(status="available", items=usage_items),
        reference=price_reference(rates=rates),
    )

    assert cost.status == "unavailable"
    assert cost.amount is None
    assert cost.reason == (
        "A primeira política não cobre todas as unidades observadas ou tarifadas."
    )
    assert unsupported_unit not in cost.reason


def test_exact_cost_sums_multiple_finite_decimals_without_floating_point() -> None:
    reference = price_reference(
        rates=(
            UnitPrice("input_token", "0.1", 10),
            UnitPrice("output_token", "0.2", 100),
        )
    )
    cost = calculate_post_execution_cost(
        route_id="route-a",
        provider="provider-a",
        model="model-a",
        estimate=available_estimate(),
        usage=complete_usage(3, 7),
        reference=reference,
    )

    assert cost.amount == "0.044"
    assert "e" not in cost.amount.lower()  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("quantity", "rate", "expected"),
    [
        (1, "0.00000000000000000000000000000000000000000000000001", "0.00000000000000000000000000000000000000000000000001"),
        (10**60, "1", "1" + "0" * 60),
    ],
)
def test_exact_cost_supports_very_small_and_very_large_values(
    quantity: int, rate: str, expected: str
) -> None:
    reference = price_reference(
        rates=(UnitPrice("input_token", rate, 1),)
    )
    usage = NormalizedUsage(
        status="available",
        items=(NormalizedUsageItem("input_token", quantity),),
    )

    cost = calculate_post_execution_cost(
        route_id="route-a",
        provider="provider-a",
        model="model-a",
        estimate=available_estimate(),
        usage=usage,
        reference=reference,
    )

    assert cost.amount == expected
    assert "e" not in cost.amount.lower()  # type: ignore[union-attr]


def test_rate_order_does_not_change_reference_or_cost() -> None:
    input_rate = UnitPrice("input_token", "0.001", 1000)
    output_rate = UnitPrice("output_token", "0.004", 1000)
    first = price_reference(rates=(input_rate, output_rate))
    second = price_reference(rates=(output_rate, input_rate))

    first_cost = calculate_post_execution_cost(
        route_id="route-a",
        provider="provider-a",
        model="model-a",
        estimate=available_estimate(),
        usage=complete_usage(),
        reference=first,
    )
    second_cost = calculate_post_execution_cost(
        route_id="route-a",
        provider="provider-a",
        model="model-a",
        estimate=available_estimate(),
        usage=complete_usage(),
        reference=second,
    )

    assert first == second
    assert first_cost == second_cost


@pytest.mark.parametrize(
    ("usage", "rates"),
    [
        (complete_usage(0, 0), None),
        (
            complete_usage(9, 11),
            (
                UnitPrice("input_token", "0", 1),
                UnitPrice("output_token", "0.0", 1000),
            ),
        ),
    ],
)
def test_zero_cost_requires_observed_zero_usage_or_explicit_zero_rates(
    usage: NormalizedUsage, rates: tuple[UnitPrice, ...] | None
) -> None:
    cost = calculate_post_execution_cost(
        route_id="route-a",
        provider="provider-a",
        model="model-a",
        estimate=available_estimate(),
        usage=usage,
        reference=price_reference(rates=rates),
    )

    assert cost.status == "available"
    assert cost.amount == "0"


@pytest.mark.parametrize(
    "estimate",
    [available_estimate(), uncertain_estimate(), unavailable_estimate()],
)
def test_public_cost_is_available_for_compatible_estimate_states(
    estimate: EconomicEstimate,
) -> None:
    body, adapter = response_for(
        estimate=estimate,
        reference=price_reference(),
    )
    economics = body["economics"]  # type: ignore[index]

    assert economics["estimate"]["status"] == estimate.status
    assert economics["calculated_cost"] == {
        "status": "available",
        "amount": "0.000654",
        "currency": "USD",
        "price_reference": "pricing-test",
        "assumptions": [],
    }
    assert len(adapter.calls) == 1


def test_observed_model_mismatch_preserves_result_and_keeps_cost_unavailable() -> None:
    body, adapter = response_for(
        reference=price_reference(),
        observed_model="different-model-returned-by-provider",
    )

    assert body["result"] == {"content": "controlled result"}
    assert body["economics"]["usage"]["status"] == "available"  # type: ignore[index]
    cost = body["economics"]["calculated_cost"]  # type: ignore[index]
    assert cost["status"] == "unavailable"
    assert "modelo observado" in cost["reason"]
    assert "different-model-returned-by-provider" not in str(body)
    assert len(adapter.calls) == 1


def test_compatible_observed_model_preserves_available_cost() -> None:
    body, _ = response_for(
        reference=price_reference(), observed_model="model-a"
    )

    assert body["economics"]["calculated_cost"]["status"] == "available"  # type: ignore[index]


def test_public_cost_schema_remains_closed_and_accepts_contractual_uncertain() -> None:
    economics = ExecutionEconomics(
        estimate=UnavailableEconomicValue(reason="Estimativa indisponível."),
        usage=AvailableUsage(
            items=[{"unit": "input_token", "quantity": "1"}]
        ),
        calculated_cost=UncertainEconomicValue(
            amount="0.01",
            currency="USD",
            price_reference="pricing-contract",
            assumptions=[],
            reason="Valor aproximado apenas para validar o contrato.",
        ),
    )

    assert economics.calculated_cost.status == "uncertain"
    with pytest.raises(ValidationError):
        ExecutionEconomics.model_validate(
            {
                **economics.model_dump(),
                "calculated_cost": {
                    **economics.calculated_cost.model_dump(),
                    "provider_payload": "forbidden",
                },
            }
        )


def test_absent_reference_keeps_cost_unavailable() -> None:
    body, _ = response_for(reference=None)

    cost = body["economics"]["calculated_cost"]  # type: ignore[index]
    assert set(cost) == {"status", "reason"}
    assert cost["status"] == "unavailable"
    assert "referência de preço" in cost["reason"]


@pytest.mark.parametrize(
    "usage",
    [
        NormalizedUsage(
            status="uncertain",
            items=(NormalizedUsageItem("input_token", 1),),
            reason="Uso parcial controlado.",
        ),
        NormalizedUsage(status="unavailable", reason="Uso ausente controlado."),
    ],
)
def test_non_available_usage_keeps_cost_unavailable(
    usage: NormalizedUsage,
) -> None:
    body, _ = response_for(reference=price_reference(), usage=usage)

    assert body["economics"]["usage"]["status"] == usage.status  # type: ignore[index]
    assert body["economics"]["calculated_cost"]["status"] == "unavailable"  # type: ignore[index]


@pytest.mark.parametrize(
    ("usage", "rates", "reason_fragment"),
    [
        (
            NormalizedUsage(
                status="available",
                items=(NormalizedUsageItem("input_token", 1),),
            ),
            (
                UnitPrice("input_token", "1", 1),
                UnitPrice("output_token", "1", 1),
            ),
            "todas as unidades",
        ),
        (
            NormalizedUsage(
                status="available",
                items=(
                    NormalizedUsageItem("input_token", 1),
                    NormalizedUsageItem("output_token", 1),
                    NormalizedUsageItem("custom_unit", 1),
                ),
            ),
            (
                UnitPrice("input_token", "1", 1),
                UnitPrice("output_token", "1", 1),
            ),
            "primeira política",
        ),
    ],
)
def test_missing_or_additional_unit_is_not_assumed_to_be_zero(
    usage: NormalizedUsage,
    rates: tuple[UnitPrice, ...],
    reason_fragment: str,
) -> None:
    body, _ = response_for(
        reference=price_reference(rates=rates), usage=usage
    )

    cost = body["economics"]["calculated_cost"]  # type: ignore[index]
    assert cost["status"] == "unavailable"
    assert reason_fragment in cost["reason"]


@pytest.mark.parametrize(
    "estimate",
    [
        available_estimate(currency="EUR"),
        available_estimate(reference="other-pricing"),
    ],
)
def test_estimate_currency_or_reference_mismatch_keeps_cost_unavailable(
    estimate: EconomicEstimate,
) -> None:
    body, _ = response_for(estimate=estimate, reference=price_reference())

    assert body["economics"]["estimate"]["status"] == "available"  # type: ignore[index]
    assert body["economics"]["calculated_cost"]["status"] == "unavailable"  # type: ignore[index]
    assert "estimativa registrada" in body["economics"]["calculated_cost"]["reason"]  # type: ignore[index]


@pytest.mark.parametrize(
    "reference",
    [
        price_reference(route_id="other-route"),
        price_reference(provider="other-provider"),
        price_reference(model="other-model"),
    ],
)
def test_route_provider_or_model_mismatch_keeps_cost_unavailable(
    reference: PriceReference,
) -> None:
    body, _ = response_for(reference=reference)

    assert body["economics"]["calculated_cost"]["status"] == "unavailable"  # type: ignore[index]
    assert "rota executada" in body["economics"]["calculated_cost"]["reason"]  # type: ignore[index]


@pytest.mark.parametrize(
    ("field", "reason_fragment"),
    [
        ("context_complete", "contexto tarifário"),
        ("units_exhaustive", "exaustivas"),
        ("no_double_counting", "dupla contagem"),
        ("model_identity_exact", "identidade tarifária"),
    ],
)
def test_incomplete_context_or_unproven_identity_keeps_cost_unavailable(
    field: str, reason_fragment: str
) -> None:
    body, _ = response_for(reference=price_reference(**{field: False}))

    cost = body["economics"]["calculated_cost"]  # type: ignore[index]
    assert cost["status"] == "unavailable"
    assert reason_fragment in cost["reason"]


def test_cost_calculation_does_not_repeat_routing_or_external_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_reference = price_reference()
    selected = configured_route(reference=selected_reference)
    unselected = configured_route(
        route_id="route-b",
        provider="provider-b",
        model="model-b",
        adapter_id="adapter-b",
        estimate=EconomicEstimate(
            status="available",
            amount="0.02",
            currency="USD",
            price_reference="pricing-b",
            assumptions=(),
        ),
    )
    selected_adapter = ControlledAdapter(complete_usage())
    unselected_adapter = ControlledAdapter(complete_usage())
    adapters: Mapping[str, ControlledAdapter] = {
        selected.adapter_id: selected_adapter,
        unselected.adapter_id: unselected_adapter,
    }
    original_route_request = api_module.route_request
    routing_calls = 0

    def counted_route_request(*args: object, **kwargs: object) -> object:
        nonlocal routing_calls
        routing_calls += 1
        return original_route_request(*args, **kwargs)

    monkeypatch.setattr(api_module, "route_request", counted_route_request)
    response = TestClient(
        create_app(RouteCatalog((unselected, selected)), adapters)
    ).post("/v1/executions", json={"task": "Execute."})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["route"]["id"] == "route-a"
    assert body["economics"]["estimate"] == {
        "status": "available",
        "amount": "0.01",
        "currency": "USD",
        "price_reference": "pricing-test",
        "assumptions": ["Estimativa anterior preservada."],
    }
    assert body["economics"]["calculated_cost"]["status"] == "available"
    assert routing_calls == 1
    assert len(selected_adapter.calls) == 1
    assert selected_adapter.calls[0][1] == ExecutionRoute(
        id="route-a", provider="provider-a", model="model-a"
    )
    assert not hasattr(selected_adapter.calls[0][1], "price_reference")
    assert unselected_adapter.calls == []


def test_public_unavailability_reason_is_closed_and_sanitized() -> None:
    reference = price_reference(
        route_id=SENSITIVE_DETAIL,
        source=SENSITIVE_DETAIL,
        conditions=(SENSITIVE_DETAIL,),
    )
    body, _ = response_for(reference=reference)

    cost = body["economics"]["calculated_cost"]  # type: ignore[index]
    assert set(cost) == {"status", "reason"}
    assert cost["status"] == "unavailable"
    assert SENSITIVE_DETAIL not in str(body)


def test_route_rejects_non_neutral_price_reference_object() -> None:
    with pytest.raises(ValueError, match="provider-neutral"):
        replace(configured_route(), price_reference=object())

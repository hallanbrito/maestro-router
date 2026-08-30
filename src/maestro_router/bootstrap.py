from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI
from openai import AsyncOpenAI

from .adapters import OpenAIResponsesAdapter
from .api import create_app
from .contracts import CURRENCY_PATTERN
from .economics import PriceReference, UnitPrice, calculate_pre_execution_amount
from .routing import EconomicEstimate, Route, RouteCatalog


_OPENAI_API_KEY = "OPENAI_API_KEY"
_OPENAI_MODEL = "MAESTRO_OPENAI_MODEL"
_OPENAI_ROUTE_ID = "MAESTRO_OPENAI_ROUTE_ID"
_OPENAI_PRICE_REFERENCE_JSON = "MAESTRO_OPENAI_PRICE_REFERENCE_JSON"
_OPENAI_ESTIMATED_USAGE_JSON = "MAESTRO_OPENAI_ESTIMATED_USAGE_JSON"
_REQUIRED_VARIABLES = (_OPENAI_API_KEY, _OPENAI_MODEL, _OPENAI_ROUTE_ID)
_OPTIONAL_VARIABLES = (
    _OPENAI_PRICE_REFERENCE_JSON,
    _OPENAI_ESTIMATED_USAGE_JSON,
)
_PRICE_REFERENCE_FIELDS = frozenset(
    {
        "id",
        "currency",
        "version",
        "source",
        "rates",
        "conditions",
        "context_complete",
        "units_exhaustive",
        "no_double_counting",
        "model_identity_exact",
    }
)
_RATE_FIELDS = frozenset({"unit", "rate", "base"})
_ESTIMATED_USAGE_FIELDS = frozenset(
    {"input_token", "output_token", "applicability_confirmed"}
)
_SUPPORTED_UNITS = frozenset({"input_token", "output_token"})
_COMPLETENESS_FIELDS = (
    "context_complete",
    "units_exhaustive",
    "no_double_counting",
    "model_identity_exact",
)
_UNAVAILABLE_ESTIMATE_REASON = (
    "Não há preço nem método de estimativa aprovados para esta rota."
)


class InvalidRuntimeConfigurationError(ValueError):
    def __init__(
        self, variable_name: str, *, invalid_optional: bool = False
    ) -> None:
        self.variable_name = variable_name
        message = (
            f"{variable_name} contém uma configuração inválida."
            if invalid_optional
            else f"{variable_name} é obrigatória e deve conter valor não branco."
        )
        super().__init__(message)


class _DuplicateJsonMemberError(ValueError):
    pass


def create_openai_app(
    configuration: Mapping[str, str],
    *,
    client_factory: Callable[..., AsyncOpenAI] = AsyncOpenAI,
) -> FastAPI:
    api_key, model, route_id, price_reference, estimate = (
        _validated_configuration(configuration)
    )

    route = Route(
        id=route_id,
        provider="openai",
        model=model,
        adapter_id="openai-responses",
        enabled=True,
        capabilities=frozenset(),
        quality_criteria=frozenset(),
        known_unavailable=False,
        estimate=estimate,
        price_reference=price_reference,
    )
    client = client_factory(api_key=api_key)
    adapter = OpenAIResponsesAdapter(client)
    return create_app(
        RouteCatalog((route,)),
        {route.adapter_id: adapter},
    )


def create_openai_app_from_env() -> FastAPI:
    configuration = {
        name: os.environ[name]
        for name in (*_REQUIRED_VARIABLES, *_OPTIONAL_VARIABLES)
        if name in os.environ
    }
    return create_openai_app(configuration)


def _validated_configuration(
    configuration: Mapping[str, str],
) -> tuple[str, str, str, PriceReference | None, EconomicEstimate]:
    values: list[str] = []
    for variable_name in _REQUIRED_VARIABLES:
        value = configuration.get(variable_name)
        if not isinstance(value, str) or not any(
            not character.isspace() for character in value
        ):
            raise InvalidRuntimeConfigurationError(variable_name)
        values.append(value)
    api_key, model, route_id = values
    price_reference = None
    if _OPENAI_PRICE_REFERENCE_JSON in configuration:
        price_reference = _parse_price_reference(
            configuration[_OPENAI_PRICE_REFERENCE_JSON],
            route_id=route_id,
            model=model,
        )
    estimate = EconomicEstimate(
        status="unavailable",
        reason=_UNAVAILABLE_ESTIMATE_REASON,
    )
    if _OPENAI_ESTIMATED_USAGE_JSON in configuration:
        quantities = _parse_estimated_usage(
            configuration[_OPENAI_ESTIMATED_USAGE_JSON]
        )
        if price_reference is None:
            raise InvalidRuntimeConfigurationError(
                _OPENAI_ESTIMATED_USAGE_JSON,
                invalid_optional=True,
            )
        try:
            amount = calculate_pre_execution_amount(
                quantities=quantities,
                reference=price_reference,
            )
        except ValueError:
            raise InvalidRuntimeConfigurationError(
                _OPENAI_ESTIMATED_USAGE_JSON,
                invalid_optional=True,
            ) from None
        estimate = EconomicEstimate(
            status="available",
            amount=amount,
            currency=price_reference.currency,
            price_reference=price_reference.id,
            assumptions=(
                _estimated_usage_assumption(
                    "input_token", quantities["input_token"]
                ),
                _estimated_usage_assumption(
                    "output_token", quantities["output_token"]
                ),
            ),
        )
    return api_key, model, route_id, price_reference, estimate


def _parse_estimated_usage(raw_value: object) -> dict[str, int]:
    try:
        if not isinstance(raw_value, str) or not any(
            not character.isspace() for character in raw_value
        ):
            raise ValueError
        document = json.loads(
            raw_value,
            object_pairs_hook=_object_without_duplicate_members,
            parse_constant=_reject_non_json_constant,
        )
        if (
            not isinstance(document, dict)
            or set(document) != _ESTIMATED_USAGE_FIELDS
            or type(document["input_token"]) is not int
            or document["input_token"] <= 0
            or type(document["output_token"]) is not int
            or document["output_token"] <= 0
            or document["applicability_confirmed"] is not True
        ):
            raise ValueError
        return {
            "input_token": document["input_token"],
            "output_token": document["output_token"],
        }
    except (TypeError, ValueError):
        raise InvalidRuntimeConfigurationError(
            _OPENAI_ESTIMATED_USAGE_JSON,
            invalid_optional=True,
        ) from None


def _estimated_usage_assumption(unit: str, quantity: int) -> str:
    return (
        f"A estimativa considera {quantity} unidades de {unit} "
        "configuradas pelo operador."
    )


def _parse_price_reference(
    raw_value: object,
    *,
    route_id: str,
    model: str,
) -> PriceReference:
    try:
        if not isinstance(raw_value, str) or not any(
            not character.isspace() for character in raw_value
        ):
            raise ValueError
        document = json.loads(
            raw_value,
            object_pairs_hook=_object_without_duplicate_members,
            parse_constant=_reject_non_json_constant,
        )
        if (
            not isinstance(document, dict)
            or set(document) != _PRICE_REFERENCE_FIELDS
        ):
            raise ValueError

        for field_name in ("id", "version", "source"):
            if not _is_non_blank_string(document[field_name]):
                raise ValueError
        currency = document["currency"]
        if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):
            raise ValueError

        conditions = document["conditions"]
        if (
            not isinstance(conditions, list)
            or any(not _is_non_blank_string(condition) for condition in conditions)
            or len(set(conditions)) != len(conditions)
        ):
            raise ValueError

        rates = document["rates"]
        if not isinstance(rates, list) or len(rates) != 2:
            raise ValueError
        parsed_rates = tuple(_parse_unit_price(rate) for rate in rates)
        if frozenset(rate.unit for rate in parsed_rates) != _SUPPORTED_UNITS:
            raise ValueError

        for field_name in _COMPLETENESS_FIELDS:
            if document[field_name] is not True:
                raise ValueError

        return PriceReference(
            id=document["id"],
            route_id=route_id,
            provider="openai",
            model=model,
            currency=currency,
            version=document["version"],
            source=document["source"],
            rates=parsed_rates,
            conditions=tuple(conditions),
            context_complete=True,
            units_exhaustive=True,
            no_double_counting=True,
            model_identity_exact=True,
        )
    except (TypeError, ValueError):
        raise InvalidRuntimeConfigurationError(
            _OPENAI_PRICE_REFERENCE_JSON,
            invalid_optional=True,
        ) from None


def _object_without_duplicate_members(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise _DuplicateJsonMemberError
        result[name] = value
    return result


def _reject_non_json_constant(_: str) -> None:
    raise ValueError


def _is_non_blank_string(value: object) -> bool:
    return isinstance(value, str) and any(
        not character.isspace() for character in value
    )


def _parse_unit_price(value: object) -> UnitPrice:
    if not isinstance(value, dict) or set(value) != _RATE_FIELDS:
        raise ValueError
    unit = value["unit"]
    rate = value["rate"]
    base = value["base"]
    if unit not in _SUPPORTED_UNITS:
        raise ValueError
    return UnitPrice(unit=unit, rate=rate, base=base)

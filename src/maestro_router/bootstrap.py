from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from fastapi import FastAPI
from openai import AsyncOpenAI

from .adapters import OpenAIResponsesAdapter
from .api import create_app
from .routing import EconomicEstimate, Route, RouteCatalog


_OPENAI_API_KEY = "OPENAI_API_KEY"
_OPENAI_MODEL = "MAESTRO_OPENAI_MODEL"
_OPENAI_ROUTE_ID = "MAESTRO_OPENAI_ROUTE_ID"
_REQUIRED_VARIABLES = (_OPENAI_API_KEY, _OPENAI_MODEL, _OPENAI_ROUTE_ID)
_UNAVAILABLE_ESTIMATE_REASON = (
    "Não há preço nem método de estimativa aprovados para esta rota."
)


class InvalidRuntimeConfigurationError(ValueError):
    def __init__(self, variable_name: str) -> None:
        self.variable_name = variable_name
        super().__init__(
            f"{variable_name} é obrigatória e deve conter valor não branco."
        )


def create_openai_app(
    configuration: Mapping[str, str],
    *,
    client_factory: Callable[..., AsyncOpenAI] = AsyncOpenAI,
) -> FastAPI:
    api_key, model, route_id = _validated_configuration(configuration)

    route = Route(
        id=route_id,
        provider="openai",
        model=model,
        adapter_id="openai-responses",
        enabled=True,
        capabilities=frozenset(),
        quality_criteria=frozenset(),
        known_unavailable=False,
        estimate=EconomicEstimate(
            status="unavailable",
            reason=_UNAVAILABLE_ESTIMATE_REASON,
        ),
    )
    client = client_factory(api_key=api_key)
    adapter = OpenAIResponsesAdapter(client)
    return create_app(
        RouteCatalog((route,)),
        {route.adapter_id: adapter},
    )


def create_openai_app_from_env() -> FastAPI:
    configuration = {
        name: os.environ[name] for name in _REQUIRED_VARIABLES if name in os.environ
    }
    return create_openai_app(configuration)


def _validated_configuration(
    configuration: Mapping[str, str],
) -> tuple[str, str, str]:
    values: list[str] = []
    for variable_name in _REQUIRED_VARIABLES:
        value = configuration.get(variable_name)
        if not isinstance(value, str) or not any(
            not character.isspace() for character in value
        ):
            raise InvalidRuntimeConfigurationError(variable_name)
        values.append(value)
    return values[0], values[1], values[2]

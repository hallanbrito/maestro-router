"""Explicit OpenAI runtime composition for the Maestro Router MVP.

This module is the only place that reads OpenAI-oriented operational settings.
It validates either the legacy single-route variables or the multiroute JSON,
constructs immutable neutral routes, and injects one shared OpenAI adapter into
the otherwise unconfigured application factory.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI
from openai import AsyncOpenAI, omit

from .adapters import OpenAIResponsesAdapter
from .api import create_app
from .contracts import CURRENCY_PATTERN, DECIMAL_PATTERN
from .economics import PriceReference, UnitPrice, calculate_pre_execution_amount
from .routing import (
    EconomicEstimate,
    MoneyCeiling,
    OperationalConstraints,
    OperationalDefaults,
    Route,
    RouteCatalog,
)

_OPENAI_API_KEY = "OPENAI_API_KEY"
_OPENAI_MODEL = "MAESTRO_OPENAI_MODEL"
_OPENAI_ROUTE_ID = "MAESTRO_OPENAI_ROUTE_ID"
_OPENAI_PRICE_REFERENCE_JSON = "MAESTRO_OPENAI_PRICE_REFERENCE_JSON"
_OPENAI_ESTIMATED_USAGE_JSON = "MAESTRO_OPENAI_ESTIMATED_USAGE_JSON"
_OPENAI_ROUTES_JSON = "MAESTRO_OPENAI_ROUTES_JSON"
_ROUTING_CONSTRAINTS_JSON = "MAESTRO_ROUTING_CONSTRAINTS_JSON"
_REQUIRED_VARIABLES = (_OPENAI_API_KEY, _OPENAI_MODEL, _OPENAI_ROUTE_ID)
_OPTIONAL_VARIABLES = (
    _OPENAI_PRICE_REFERENCE_JSON,
    _OPENAI_ESTIMATED_USAGE_JSON,
    _ROUTING_CONSTRAINTS_JSON,
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
_OPENAI_PUBLIC_BASE_URL = "https://api.openai.com/v1"
_OPENAI_CUSTOM_HEADERS = "OPENAI_CUSTOM_HEADERS"


class InvalidRuntimeConfigurationError(ValueError):
    """Identify one invalid runtime variable without exposing its raw value."""

    def __init__(
        self,
        variable_name: str,
        *,
        invalid_optional: bool = False,
        path: str | None = None,
    ) -> None:
        """Build a sanitized message for a missing or malformed variable."""

        self.variable_name = variable_name
        self.path = path
        if path:
            message = f"{variable_name} contém uma configuração inválida em {path}."
        elif invalid_optional:
            message = f"{variable_name} contém uma configuração inválida."
        else:
            message = f"{variable_name} é obrigatória e deve conter valor não branco."
        super().__init__(message)


class _DuplicateJsonMemberError(ValueError):
    """Internal signal raised when strict JSON contains a duplicate member."""

    pass


class DuplicateTrackingDict(dict):
    """Dictionary created by ``json.loads`` that remembers duplicate keys."""

    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        """Keep the final JSON values and separately record repeated names."""

        self.duplicate_keys = set()
        d = {}
        for k, v in pairs:
            if k in d:
                self.duplicate_keys.add(k)
            d[k] = v
        super().__init__(d)


def _nested_has_duplicates(obj: Any) -> bool:
    """Recursively detect duplicate members captured anywhere in parsed JSON."""

    if isinstance(obj, DuplicateTrackingDict):
        if obj.duplicate_keys:
            return True
        return any(_nested_has_duplicates(v) for v in obj.values())
    elif isinstance(obj, list):
        return any(_nested_has_duplicates(item) for item in obj)
    return False


def _is_structurally_valid_string(val: Any) -> bool:
    """Accept non-blank Unicode strings that contain no lone surrogates."""

    return (
        isinstance(val, str)
        and any(not c.isspace() for c in val)
        and not any(0xD800 <= ord(c) <= 0xDFFF for c in val)
    )


def create_openai_app(
    configuration: Mapping[str, str],
    *,
    client_factory: Callable[..., AsyncOpenAI] = AsyncOpenAI,
) -> FastAPI:
    """Validate OpenAI settings and compose an executable Maestro application.

    Presence of ``MAESTRO_OPENAI_ROUTES_JSON`` selects multiroute mode and makes
    legacy route variables invalid.  Otherwise, the original single-route mode
    remains supported.  The client is constructed only after all applicable
    configuration has passed validation.

    Args:
        configuration: Explicit runtime settings, normally environment values.
        client_factory: Injectable OpenAI client constructor used by tests.

    Raises:
        InvalidRuntimeConfigurationError: If required configuration is missing,
            ambiguous, structurally invalid, or economically incomplete.
    """

    legacy_keys = {
        _OPENAI_ROUTE_ID,
        _OPENAI_MODEL,
        _OPENAI_PRICE_REFERENCE_JSON,
        _OPENAI_ESTIMATED_USAGE_JSON,
    }
    if _ROUTING_CONSTRAINTS_JSON in configuration:
        if _OPENAI_ROUTES_JSON not in configuration or any(
            key in configuration for key in legacy_keys
        ):
            raise InvalidRuntimeConfigurationError(
                _ROUTING_CONSTRAINTS_JSON, invalid_optional=True
            )

    if _OPENAI_ROUTES_JSON in configuration:
        # One client and adapter serve every configured OpenAI route; model
        # identity still remains attached to each neutral Route snapshot.
        api_key, routes, configuration_invalid_route_ids = _validated_multiroute_configuration(configuration)
        operational_constraints = None
        if _ROUTING_CONSTRAINTS_JSON in configuration:
            operational_constraints = _parse_routing_constraints(
                configuration[_ROUTING_CONSTRAINTS_JSON]
            )
        adapter = _create_openai_adapter(api_key, client_factory)
        return create_app(
            RouteCatalog(
                routes,
                configuration_invalid_route_ids=configuration_invalid_route_ids,
                operational_constraints=operational_constraints,
            ),
            {"openai-responses": adapter},
        )

    api_key, model, route_id, price_reference, estimate = _validated_configuration(
        configuration
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
    adapter = _create_openai_adapter(api_key, client_factory)
    return create_app(
        RouteCatalog((route,)),
        {route.adapter_id: adapter},
    )


def create_openai_app_from_env() -> FastAPI:
    """Compose the OpenAI runtime from only the recognized environment keys."""

    configuration = {
        name: os.environ[name]
        for name in (*_REQUIRED_VARIABLES, *_OPTIONAL_VARIABLES, _OPENAI_ROUTES_JSON)
        if name in os.environ
    }
    return create_openai_app(configuration)


def _create_openai_adapter(
    api_key: str,
    client_factory: Callable[..., AsyncOpenAI],
) -> OpenAIResponsesAdapter:
    """Construct an OpenAI adapter isolated from ambient SDK options.

    Unsupported options are explicitly overridden or neutralized so ambient
    SDK variables cannot affect the captured client, without mutating the
    process environment.
    """
    # The official SDK otherwise infers several unsupported options from the
    # process environment. All supported inputs are supplied explicitly here.
    client = client_factory(
        api_key=api_key,
        admin_api_key="",
        organization="",
        project="",
        webhook_secret="",
        base_url=_OPENAI_PUBLIC_BASE_URL,
        max_retries=0,
        default_headers=_unapproved_openai_header_omissions(api_key),
        default_query={},
    )
    return OpenAIResponsesAdapter(client, retry_policy_configured=True)


def _unapproved_openai_header_omissions(api_key: str) -> dict[str, object]:
    """Override SDK-only environment headers without mutating process state."""

    headers: dict[str, object] = {
        "OpenAI-Organization": omit,
        "OpenAI-Project": omit,
    }
    configured = os.environ.get(_OPENAI_CUSTOM_HEADERS)
    if configured is None:
        return headers

    for line in configured.split("\n"):
        name, separator, _ = line.partition(":")
        if not separator:
            continue
        name = name.strip()
        if not name:
            continue
        headers[name] = (
            f"Bearer {api_key}" if name.lower() == "authorization" else omit
        )
    return headers


def _validated_configuration(
    configuration: Mapping[str, str],
) -> tuple[str, str, str, PriceReference | None, EconomicEstimate]:
    """Validate legacy single-route configuration and derive its estimate."""

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
        reason=(
            "Não há previsão de uso configurada para estimar esta rota."
            if price_reference is not None
            else _UNAVAILABLE_ESTIMATE_REASON
        ),
    )
    if _OPENAI_ESTIMATED_USAGE_JSON in configuration:
        # A usage forecast alone is not monetary.  It becomes an estimate only
        # when the same route also has a complete approved price reference.
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


def _validated_multiroute_configuration(
    configuration: Mapping[str, str],
) -> tuple[str, list[Route], list[str]]:
    """Validate multiroute JSON and return usable routes plus local exclusions.

    Document-wide ambiguity, such as duplicate route identifiers or mixing
    legacy settings, invalidates startup.  A malformed individual route with a
    trustworthy unique ``route_id`` is excluded locally when at least one other
    complete route remains usable.
    """

    api_key = configuration.get(_OPENAI_API_KEY)
    if not isinstance(api_key, str) or not any(not c.isspace() for c in api_key):
        raise InvalidRuntimeConfigurationError(_OPENAI_API_KEY)

    legacy_keys = {
        _OPENAI_ROUTE_ID,
        _OPENAI_MODEL,
        _OPENAI_PRICE_REFERENCE_JSON,
        _OPENAI_ESTIMATED_USAGE_JSON,
    }
    if any(key in configuration for key in legacy_keys):
        raise InvalidRuntimeConfigurationError(_OPENAI_ROUTES_JSON, invalid_optional=True)

    routes_json = configuration[_OPENAI_ROUTES_JSON]
    if not isinstance(routes_json, str) or not any(not c.isspace() for c in routes_json):
        raise InvalidRuntimeConfigurationError(_OPENAI_ROUTES_JSON, invalid_optional=True)

    try:
        document = json.loads(
            routes_json,
            object_pairs_hook=DuplicateTrackingDict,
            parse_constant=_reject_non_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        raise InvalidRuntimeConfigurationError(_OPENAI_ROUTES_JSON, invalid_optional=True)

    if not isinstance(document, dict) or document.duplicate_keys or set(document.keys()) != {"routes"}:
        raise InvalidRuntimeConfigurationError(_OPENAI_ROUTES_JSON, invalid_optional=True)

    routes_list = document["routes"]
    if not isinstance(routes_list, list) or len(routes_list) == 0:
        raise InvalidRuntimeConfigurationError(
            _OPENAI_ROUTES_JSON, invalid_optional=True, path="routes"
        )

    route_ids = []
    for i, route_entry in enumerate(routes_list):
        if not isinstance(route_entry, dict):
            raise InvalidRuntimeConfigurationError(
                _OPENAI_ROUTES_JSON, invalid_optional=True, path=f"routes[{i}]"
            )
        if isinstance(route_entry, DuplicateTrackingDict) and "route_id" in route_entry.duplicate_keys:
            raise InvalidRuntimeConfigurationError(
                _OPENAI_ROUTES_JSON, invalid_optional=True, path=f"routes[{i}].route_id"
            )
        if "route_id" not in route_entry:
            raise InvalidRuntimeConfigurationError(
                _OPENAI_ROUTES_JSON, invalid_optional=True, path=f"routes[{i}].route_id"
            )
        route_id = route_entry["route_id"]
        if (
            not isinstance(route_id, str)
            or not any(not c.isspace() for c in route_id)
            or any(0xD800 <= ord(c) <= 0xDFFF for c in route_id)
        ):
            raise InvalidRuntimeConfigurationError(
                _OPENAI_ROUTES_JSON, invalid_optional=True, path=f"routes[{i}].route_id"
            )
        route_ids.append(route_id)

    if len(route_ids) != len(set(route_ids)):
        raise InvalidRuntimeConfigurationError(
            _OPENAI_ROUTES_JSON, invalid_optional=True, path="routes"
        )

    # Models and price-reference identifiers are collected before local route
    # validation because their uniqueness is a document-wide invariant.
    models = []
    price_ref_ids = []
    for route_entry in routes_list:
        is_duplicate_model_local = isinstance(route_entry, DuplicateTrackingDict) and "model" in route_entry.duplicate_keys
        if "model" in route_entry and not is_duplicate_model_local:
            model_val = route_entry["model"]
            if _is_structurally_valid_string(model_val):
                models.append(model_val)

        is_duplicate_price_local = isinstance(route_entry, DuplicateTrackingDict) and "price_reference" in route_entry.duplicate_keys
        if "price_reference" in route_entry and not is_duplicate_price_local:
            price_ref = route_entry["price_reference"]
            if isinstance(price_ref, dict):
                is_duplicate_id_local = isinstance(price_ref, DuplicateTrackingDict) and "id" in price_ref.duplicate_keys
                if "id" in price_ref and not is_duplicate_id_local:
                    ref_id = price_ref["id"]
                    if _is_structurally_valid_string(ref_id):
                        price_ref_ids.append(ref_id)

    if len(models) != len(set(models)):
        raise InvalidRuntimeConfigurationError(
            _OPENAI_ROUTES_JSON, invalid_optional=True, path="routes"
        )
    if len(price_ref_ids) != len(set(price_ref_ids)):
        raise InvalidRuntimeConfigurationError(
            _OPENAI_ROUTES_JSON, invalid_optional=True, path="routes"
        )

    routes: list[Route] = []
    configuration_invalid_route_ids: list[str] = []
    num_valid_routes = 0

    for route_entry in routes_list:
        route_id = route_entry["route_id"]
        local_failed = False

        # From this point onward, failures belong to a known unique route and can
        # be represented as an explicit configuration exclusion.
        if _nested_has_duplicates(route_entry):
            local_failed = True

        allowed_keys = {
            "route_id",
            "model",
            "price_reference",
            "estimated_usage",
            "capabilities",
            "quality_criteria",
        }
        required_keys = {"route_id", "model", "price_reference", "estimated_usage"}
        if not required_keys.issubset(route_entry.keys()) or not set(route_entry.keys()).issubset(allowed_keys):
            local_failed = True

        model = route_entry.get("model")
        if not _is_structurally_valid_string(model):
            local_failed = True

        capabilities: frozenset[str] = frozenset()
        if "capabilities" in route_entry:
            cap_val = route_entry["capabilities"]
            if (
                not isinstance(cap_val, list)
                or len(cap_val) == 0
                or any(not _is_structurally_valid_string(c) for c in cap_val)
                or len(set(cap_val)) != len(cap_val)
            ):
                local_failed = True
            else:
                capabilities = frozenset(cap_val)

        quality_criteria_set: frozenset[str] = frozenset()
        quality_evidence_refs: dict[str, tuple[str, ...]] = {}
        if "quality_criteria" in route_entry:
            qc_val = route_entry["quality_criteria"]
            if not isinstance(qc_val, list) or len(qc_val) == 0:
                local_failed = True
            else:
                seen_criteria: list[str] = []
                for item in qc_val:
                    if not isinstance(item, dict):
                        local_failed = True
                        break
                    if _nested_has_duplicates(item):
                        local_failed = True
                        break
                    if set(item.keys()) != {"criterion", "evidence_references"}:
                        local_failed = True
                        break
                    crit = item["criterion"]
                    if not _is_structurally_valid_string(crit):
                        local_failed = True
                        break
                    refs = item["evidence_references"]
                    if (
                        not isinstance(refs, list)
                        or len(refs) == 0
                        or any(not _is_structurally_valid_string(r) for r in refs)
                        or len(set(refs)) != len(refs)
                    ):
                        local_failed = True
                        break
                    seen_criteria.append(crit)
                    quality_evidence_refs[crit] = tuple(sorted(refs))
                if not local_failed:
                    if len(set(seen_criteria)) != len(seen_criteria):
                        local_failed = True
                    else:
                        quality_criteria_set = frozenset(seen_criteria)

        price_ref_val = route_entry.get("price_reference")
        price_reference = None
        if not isinstance(price_ref_val, dict):
            local_failed = True
        else:
            price_ref_id = price_ref_val.get("id")
            if not _is_structurally_valid_string(price_ref_id):
                local_failed = True
            else:
                try:
                    raw_price = json.dumps(price_ref_val)
                    temp_model = model if isinstance(model, str) else "dummy"
                    price_reference = _parse_price_reference(
                        raw_price,
                        route_id=route_id,
                        model=temp_model,
                    )
                except (InvalidRuntimeConfigurationError, ValueError, TypeError, KeyError):
                    local_failed = True

        est_usage_val = route_entry.get("estimated_usage")
        quantities = None
        if not isinstance(est_usage_val, dict):
            local_failed = True
        else:
            try:
                raw_usage = json.dumps(est_usage_val)
                quantities = _parse_estimated_usage(raw_usage)
            except (InvalidRuntimeConfigurationError, ValueError, TypeError, KeyError):
                local_failed = True

        estimate = None
        if not local_failed:
            try:
                amount = calculate_pre_execution_amount(
                    quantities=quantities,
                    reference=price_reference,
                )
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
                num_valid_routes += 1
            except (ValueError, TypeError, KeyError):
                local_failed = True

        if local_failed:
            configuration_invalid_route_ids.append(route_id)
        else:
            route = Route(
                id=route_id,
                provider="openai",
                model=model,
                adapter_id="openai-responses",
                enabled=True,
                capabilities=capabilities,
                quality_criteria=quality_criteria_set,
                quality_evidence_references=quality_evidence_refs,
                known_unavailable=False,
                estimate=estimate,
                price_reference=price_reference,
            )
            routes.append(route)

    if num_valid_routes == 0:
        raise InvalidRuntimeConfigurationError(
            _OPENAI_ROUTES_JSON, invalid_optional=True, path="routes"
        )

    # Canonical ordering makes selection inputs independent of JSON array order.
    routes.sort(key=lambda r: r.id)
    return api_key, routes, configuration_invalid_route_ids


def _parse_estimated_usage(raw_value: object) -> dict[str, int]:
    """Parse the closed, positive two-unit operator usage forecast."""

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
    """Describe one operator-supplied forecast quantity in public language."""

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
    """Parse one closed and fully confirmed operator price reference.

    The parser accepts no partial completeness state: every approved evidence
    flag must be explicitly true and rates must cover exactly the two units in
    the first cost policy.
    """

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
        if not isinstance(document, dict) or set(document) != _PRICE_REFERENCE_FIELDS:
            raise ValueError

        if not _is_structurally_valid_string(document["id"]):
            raise ValueError
        for field_name in ("version", "source"):
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
    """Construct a strict JSON object or reject its first duplicate member."""

    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise _DuplicateJsonMemberError
        result[name] = value
    return result


def _reject_non_json_constant(_: str) -> None:
    """Reject NaN and infinity spellings accepted by Python's JSON parser."""

    raise ValueError


def _is_non_blank_string(value: object) -> bool:
    """Return whether a value is a string with visible content."""

    return isinstance(value, str) and any(
        not character.isspace() for character in value
    )


def _parse_unit_price(value: object) -> UnitPrice:
    """Parse one closed rate entry for a currently supported usage unit."""

    if not isinstance(value, dict) or set(value) != _RATE_FIELDS:
        raise ValueError
    unit = value["unit"]
    rate = value["rate"]
    base = value["base"]
    if unit not in _SUPPORTED_UNITS:
        raise ValueError
    return UnitPrice(unit=unit, rate=rate, base=base)


_ROUTING_CONSTRAINTS_ALLOWED_KEYS = frozenset(
    {
        "required_capabilities",
        "required_quality_criteria",
        "allowed_route_ids",
        "max_estimated_costs",
        "defaults",
    }
)
_DEFAULTS_ALLOWED_KEYS = frozenset(
    {
        "required_capabilities",
        "required_quality_criteria",
        "allowed_route_ids",
        "max_estimated_cost",
    }
)


def _parse_unique_string_list(val: object, path_prefix: str) -> frozenset[str]:
    """Parse a non-empty JSON list of unique, structurally valid strings."""

    if not isinstance(val, list) or len(val) == 0:
        raise InvalidRuntimeConfigurationError(
            _ROUTING_CONSTRAINTS_JSON, invalid_optional=True, path=path_prefix
        )
    seen: set[str] = set()
    for i, item in enumerate(val):
        if not _is_structurally_valid_string(item):
            raise InvalidRuntimeConfigurationError(
                _ROUTING_CONSTRAINTS_JSON,
                invalid_optional=True,
                path=f"{path_prefix}[{i}]",
            )
        if item in seen:
            raise InvalidRuntimeConfigurationError(
                _ROUTING_CONSTRAINTS_JSON,
                invalid_optional=True,
                path=f"{path_prefix}[{i}]",
            )
        seen.add(item)
    return frozenset(seen)


def _parse_routing_constraints(raw_value: object) -> OperationalConstraints:
    """Parse the closed, strict operational routing constraints JSON document."""

    if not isinstance(raw_value, str) or not any(
        not character.isspace() for character in raw_value
    ):
        raise InvalidRuntimeConfigurationError(
            _ROUTING_CONSTRAINTS_JSON, invalid_optional=True
        )

    try:
        document = json.loads(
            raw_value,
            object_pairs_hook=DuplicateTrackingDict,
            parse_constant=_reject_non_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        raise InvalidRuntimeConfigurationError(
            _ROUTING_CONSTRAINTS_JSON, invalid_optional=True
        ) from None

    if not isinstance(document, dict):
        raise InvalidRuntimeConfigurationError(
            _ROUTING_CONSTRAINTS_JSON, invalid_optional=True
        )

    if isinstance(document, DuplicateTrackingDict) and document.duplicate_keys:
        dup_key = next((k for k in document.duplicate_keys if k in _ROUTING_CONSTRAINTS_ALLOWED_KEYS), None)
        raise InvalidRuntimeConfigurationError(
            _ROUTING_CONSTRAINTS_JSON,
            invalid_optional=True,
            path=dup_key,
        )

    doc_keys = set(document.keys())
    if len(doc_keys) == 0 or not doc_keys.issubset(_ROUTING_CONSTRAINTS_ALLOWED_KEYS):
        raise InvalidRuntimeConfigurationError(
            _ROUTING_CONSTRAINTS_JSON, invalid_optional=True
        )

    try:
        required_capabilities: frozenset[str] = frozenset()
        if "required_capabilities" in document:
            required_capabilities = _parse_unique_string_list(
                document["required_capabilities"], "required_capabilities"
            )

        required_quality_criteria: frozenset[str] = frozenset()
        if "required_quality_criteria" in document:
            required_quality_criteria = _parse_unique_string_list(
                document["required_quality_criteria"], "required_quality_criteria"
            )

        allowed_route_ids: frozenset[str] | None = None
        if "allowed_route_ids" in document:
            allowed_route_ids = _parse_unique_string_list(
                document["allowed_route_ids"], "allowed_route_ids"
            )

        max_estimated_costs: list[MoneyCeiling] = []
        if "max_estimated_costs" in document:
            costs_val = document["max_estimated_costs"]
            if not isinstance(costs_val, list) or len(costs_val) == 0:
                raise InvalidRuntimeConfigurationError(
                    _ROUTING_CONSTRAINTS_JSON,
                    invalid_optional=True,
                    path="max_estimated_costs",
                )
            seen_currencies: set[str] = set()
            for i, item in enumerate(costs_val):
                if not isinstance(item, dict):
                    raise InvalidRuntimeConfigurationError(
                        _ROUTING_CONSTRAINTS_JSON,
                        invalid_optional=True,
                        path=f"max_estimated_costs[{i}]",
                    )
                if isinstance(item, DuplicateTrackingDict) and item.duplicate_keys:
                    dup_key = next((k for k in item.duplicate_keys if k in {"currency", "amount"}), None)
                    dup_path = f"max_estimated_costs[{i}].{dup_key}" if dup_key else f"max_estimated_costs[{i}]"
                    raise InvalidRuntimeConfigurationError(
                        _ROUTING_CONSTRAINTS_JSON,
                        invalid_optional=True,
                        path=dup_path,
                    )
                if set(item.keys()) != {"currency", "amount"}:
                    raise InvalidRuntimeConfigurationError(
                        _ROUTING_CONSTRAINTS_JSON,
                        invalid_optional=True,
                        path=f"max_estimated_costs[{i}]",
                    )
                curr = item["currency"]
                amt = item["amount"]
                if not isinstance(curr, str) or not CURRENCY_PATTERN.fullmatch(curr):
                    raise InvalidRuntimeConfigurationError(
                        _ROUTING_CONSTRAINTS_JSON,
                        invalid_optional=True,
                        path=f"max_estimated_costs[{i}].currency",
                    )
                if not isinstance(amt, str) or not DECIMAL_PATTERN.fullmatch(amt):
                    raise InvalidRuntimeConfigurationError(
                        _ROUTING_CONSTRAINTS_JSON,
                        invalid_optional=True,
                        path=f"max_estimated_costs[{i}].amount",
                    )
                if curr in seen_currencies:
                    raise InvalidRuntimeConfigurationError(
                        _ROUTING_CONSTRAINTS_JSON,
                        invalid_optional=True,
                        path=f"max_estimated_costs[{i}].currency",
                    )
                seen_currencies.add(curr)
                max_estimated_costs.append(MoneyCeiling(amount=amt, currency=curr))

        defaults = OperationalDefaults()
        if "defaults" in document:
            def_doc = document["defaults"]
            if not isinstance(def_doc, dict):
                raise InvalidRuntimeConfigurationError(
                    _ROUTING_CONSTRAINTS_JSON,
                    invalid_optional=True,
                    path="defaults",
                )
            if isinstance(def_doc, DuplicateTrackingDict) and def_doc.duplicate_keys:
                dup_key = next((k for k in def_doc.duplicate_keys if k in _DEFAULTS_ALLOWED_KEYS), None)
                dup_path = f"defaults.{dup_key}" if dup_key else "defaults"
                raise InvalidRuntimeConfigurationError(
                    _ROUTING_CONSTRAINTS_JSON,
                    invalid_optional=True,
                    path=dup_path,
                )
            def_keys = set(def_doc.keys())
            if len(def_keys) == 0 or not def_keys.issubset(_DEFAULTS_ALLOWED_KEYS):
                raise InvalidRuntimeConfigurationError(
                    _ROUTING_CONSTRAINTS_JSON,
                    invalid_optional=True,
                    path="defaults",
                )

            def_caps: frozenset[str] = frozenset()
            if "required_capabilities" in def_doc:
                def_caps = _parse_unique_string_list(
                    def_doc["required_capabilities"], "defaults.required_capabilities"
                )

            def_qual: frozenset[str] = frozenset()
            if "required_quality_criteria" in def_doc:
                def_qual = _parse_unique_string_list(
                    def_doc["required_quality_criteria"], "defaults.required_quality_criteria"
                )

            def_routes: frozenset[str] | None = None
            if "allowed_route_ids" in def_doc:
                def_routes = _parse_unique_string_list(
                    def_doc["allowed_route_ids"], "defaults.allowed_route_ids"
                )

            def_cost: MoneyCeiling | None = None
            if "max_estimated_cost" in def_doc:
                cost_item = def_doc["max_estimated_cost"]
                if not isinstance(cost_item, dict):
                    raise InvalidRuntimeConfigurationError(
                        _ROUTING_CONSTRAINTS_JSON,
                        invalid_optional=True,
                        path="defaults.max_estimated_cost",
                    )
                if isinstance(cost_item, DuplicateTrackingDict) and cost_item.duplicate_keys:
                    dup_key = next((k for k in cost_item.duplicate_keys if k in {"currency", "amount"}), None)
                    dup_path = f"defaults.max_estimated_cost.{dup_key}" if dup_key else "defaults.max_estimated_cost"
                    raise InvalidRuntimeConfigurationError(
                        _ROUTING_CONSTRAINTS_JSON,
                        invalid_optional=True,
                        path=dup_path,
                    )
                if set(cost_item.keys()) != {"currency", "amount"}:
                    raise InvalidRuntimeConfigurationError(
                        _ROUTING_CONSTRAINTS_JSON,
                        invalid_optional=True,
                        path="defaults.max_estimated_cost",
                    )
                curr = cost_item["currency"]
                amt = cost_item["amount"]
                if not isinstance(curr, str) or not CURRENCY_PATTERN.fullmatch(curr):
                    raise InvalidRuntimeConfigurationError(
                        _ROUTING_CONSTRAINTS_JSON,
                        invalid_optional=True,
                        path="defaults.max_estimated_cost.currency",
                    )
                if not isinstance(amt, str) or not DECIMAL_PATTERN.fullmatch(amt):
                    raise InvalidRuntimeConfigurationError(
                        _ROUTING_CONSTRAINTS_JSON,
                        invalid_optional=True,
                        path="defaults.max_estimated_cost.amount",
                    )
                def_cost = MoneyCeiling(amount=amt, currency=curr)

            defaults = OperationalDefaults(
                required_capabilities=def_caps,
                required_quality_criteria=def_qual,
                allowed_route_ids=def_routes,
                max_estimated_cost=def_cost,
            )

        if _nested_has_duplicates(document):
            raise InvalidRuntimeConfigurationError(
                _ROUTING_CONSTRAINTS_JSON,
                invalid_optional=True,
            )

        return OperationalConstraints(
            required_capabilities=required_capabilities,
            required_quality_criteria=required_quality_criteria,
            allowed_route_ids=allowed_route_ids,
            max_estimated_costs=tuple(max_estimated_costs),
            defaults=defaults,
        )
    except InvalidRuntimeConfigurationError:
        raise
    except (TypeError, ValueError):
        raise InvalidRuntimeConfigurationError(
            _ROUTING_CONSTRAINTS_JSON,
            invalid_optional=True,
        ) from None

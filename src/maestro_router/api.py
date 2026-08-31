"""FastAPI boundary for validating, routing, and executing public requests.

The HTTP layer coordinates existing domain components.  It owns strict JSON
handling and public response projection, but delegates selection, provider
execution, and economic calculation to their respective neutral modules.
"""

from __future__ import annotations

import json
import inspect
from types import MappingProxyType
from typing import Any, Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .contracts import (
    ErrorIssue,
    AvailableEconomicValue,
    AvailableUsage,
    ExecutionEconomics,
    ExecutionErrorResponse,
    ExecutionPublicError,
    ExecutionRequest,
    ExecutionResult,
    ExecutionSuccessResponse,
    InternalErrorResponse,
    InternalPublicError,
    InvalidRequestError,
    InvalidRequestResponse,
    RefusalResponse,
    SelectedPublicDecision,
    SelectedRoute,
    SelectedStrategy,
    UnavailableUsage,
    UnavailableEconomicValue,
    UncertainUsage,
    UncertainEconomicValue,
    UsageItem,
)
from .execution import (
    ExecutionAdapter,
    ExecutionFailedError,
    ExecutionRoute,
    ExecutionTimeoutError,
    ExecutionUnavailableError,
    NormalizedUsage,
    TextExecutionRequest,
    TextExecutionResult,
)
from .economics import calculate_post_execution_cost
from .routing import (
    InvalidDecisionError,
    Route,
    RouteCatalog,
    SelectedDecision,
    route_request,
)


class DuplicateMemberError(ValueError):
    """Signal a repeated JSON object member while preserving its name."""

    def __init__(self, member: str) -> None:
        """Create an error for the duplicate member reported to the caller."""

        self.member = member
        super().__init__(member)


def create_app(
    catalog: RouteCatalog | None = None,
    adapters: Mapping[str, ExecutionAdapter] | None = None,
) -> FastAPI:
    """Compose the Maestro HTTP application from explicit runtime components.

    Args:
        catalog: Immutable-snapshot source for routes available to the router.
            An empty catalog is used when it is omitted.
        adapters: Mapping from configured adapter identifiers to provider-neutral
            execution adapters.  An empty registry is used when it is omitted.

    Returns:
        A FastAPI application exposing only ``POST /v1/executions``.
    """

    app = FastAPI(
        title="Maestro Router",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    route_catalog = catalog if catalog is not None else RouteCatalog()
    adapter_registry = adapters if adapters is not None else {}

    @app.post(
        "/v1/executions",
        response_model=ExecutionSuccessResponse,
        responses={
            400: {"model": InvalidRequestResponse},
            415: {"model": InvalidRequestResponse},
            422: {"model": RefusalResponse},
            500: {"model": InternalErrorResponse},
            502: {"model": ExecutionErrorResponse},
            503: {"model": ExecutionErrorResponse},
            504: {"model": ExecutionErrorResponse},
        },
    )
    async def create_execution(request: Request) -> JSONResponse:
        """Validate one request, select one route, and execute it at most once."""

        # The body is decoded and parsed manually because the public contract
        # distinguishes invalid UTF-8, duplicate JSON members, and media errors
        # that ordinary framework parsing may normalize before validation.
        media_issue = _validate_content_type(request.headers.get("content-type"))
        if media_issue is not None:
            return _invalid_request([media_issue], status_code=415)

        try:
            body = (await request.body()).decode("utf-8")
            payload = json.loads(body, object_pairs_hook=_reject_duplicate_members)
            if _has_isolated_surrogate(payload):
                return _invalid_request(
                    [ErrorIssue(message="O corpo JSON contém Unicode inválido.")]
                )
        except UnicodeDecodeError:
            return _invalid_request(
                [ErrorIssue(message="O corpo JSON deve usar codificação UTF-8.")]
            )
        except DuplicateMemberError as error:
            member = (
                error.member
                if not _has_isolated_surrogate(error.member)
                else "não representável"
            )
            return _invalid_request(
                [
                    ErrorIssue(
                        message=(
                            "O JSON contém um nome de membro duplicado: "
                            f"{member}."
                        )
                    )
                ]
            )
        except (json.JSONDecodeError, RecursionError, ValueError):
            return _invalid_request(
                [ErrorIssue(message="O corpo deve conter um objeto JSON válido.")]
            )

        try:
            execution_request = ExecutionRequest.model_validate(payload)
        except ValidationError as error:
            return _invalid_request(_validation_issues(error))

        try:
            # Freeze adapter associations before routing so registry mutation
            # cannot change the executor after a decision has been made.
            adapter_snapshot = _snapshot_adapters(
                route_catalog, adapter_registry
            )
            enabled_routes = tuple(
                route for route in route_catalog.snapshot() if route.enabled
            )
            catalog_invalid_ids = frozenset(
                route.id
                for route in enabled_routes
                if not _is_valid_adapter(
                    adapter_snapshot.get(route.adapter_id)
                )
            )
            if enabled_routes and len(catalog_invalid_ids) == len(
                enabled_routes
            ):
                return _internal_error(
                    code="INVALID_CONFIGURATION",
                    message="A configuração indispensável é inválida.",
                    issue=(
                        "Nenhuma rota habilitada possui uma associação "
                        "de execução válida."
                    ),
                )
            locally_invalid_route_ids = catalog_invalid_ids | getattr(
                route_catalog, "configuration_invalid_route_ids", frozenset()
            )
            # Invalid runtime associations are expressed as route exclusions.
            # This lets a valid route still win while preventing selection of a
            # route that cannot be executed.
            routing_result = route_request(
                execution_request,
                route_catalog,
                locally_invalid_route_ids=locally_invalid_route_ids,
                invalid_execution_route_ids=catalog_invalid_ids,
            )
        except InvalidDecisionError:
            return _internal_error(
                code="INVALID_DECISION",
                message="A decisão interna é inválida.",
                issue="A decisão não satisfez os invariantes obrigatórios.",
            )
        if isinstance(routing_result, SelectedDecision):
            return await _execute_selection(
                execution_request, routing_result, adapter_snapshot
            )
        return JSONResponse(
            status_code=422,
            content=routing_result.model_dump(exclude_none=True),
            media_type="application/json",
        )

    return app


def _snapshot_adapters(
    catalog: RouteCatalog,
    adapters: Mapping[str, ExecutionAdapter],
) -> Mapping[str, ExecutionAdapter | None]:
    """Freeze only adapter associations used by enabled catalog routes."""

    applicable_adapter_ids = {
        route.adapter_id for route in catalog.snapshot() if route.enabled
    }
    snapshot = {
        adapter_id: adapters.get(adapter_id)
        for adapter_id in applicable_adapter_ids
    }
    return MappingProxyType(snapshot)


def _is_valid_adapter(adapter: object | None) -> bool:
    """Return whether an object exposes the required asynchronous operation."""

    try:
        execute = getattr(adapter, "execute", None)
        return (
            adapter is not None
            and callable(execute)
            and inspect.iscoroutinefunction(execute)
        )
    except Exception:
        return False


async def _execute_selection(
    request: ExecutionRequest,
    decision: SelectedDecision,
    adapters: Mapping[str, ExecutionAdapter],
) -> JSONResponse:
    """Execute one validated decision and map its outcome to public JSON.

    Provider-neutral exceptions receive distinct public status codes.  Unknown
    exceptions and invalid adapter results are sanitized as execution failures
    so implementation details never leak through the API boundary.
    """

    route = decision.route
    adapter = adapters.get(route.adapter_id)
    if not _is_valid_adapter(adapter):
        return _internal_error(
            code="INVALID_CONFIGURATION",
            message="A configuração indispensável é inválida.",
            issue="A rota selecionada não possui um adaptador assíncrono válido.",
        )
    execute = adapter.execute

    public_decision = _public_decision(decision)
    economics = _execution_economics(route)
    try:
        result = await execute(
            TextExecutionRequest(task=request.task, context=request.context),
            ExecutionRoute(
                id=route.id,
                provider=route.provider,
                model=route.model,
            ),
        )
    except ExecutionTimeoutError:
        return _execution_error(
            "EXECUTION_TIMEOUT",
            "A execução da rota selecionada excedeu o timeout aplicável.",
            public_decision,
            economics,
            504,
        )
    except ExecutionUnavailableError:
        return _execution_error(
            "EXECUTION_UNAVAILABLE",
            "A rota selecionada estava indisponível durante a execução.",
            public_decision,
            economics,
            503,
        )
    except ExecutionFailedError:
        return _execution_error(
            "EXECUTION_FAILED",
            "A execução da rota selecionada falhou.",
            public_decision,
            economics,
            502,
        )
    except Exception:
        return _execution_error(
            "EXECUTION_FAILED",
            "A execução da rota selecionada falhou.",
            public_decision,
            economics,
            502,
        )

    if not isinstance(result, TextExecutionResult):
        return _execution_error(
            "EXECUTION_FAILED",
            "A execução da rota selecionada falhou.",
            public_decision,
            economics,
            502,
        )

    response = ExecutionSuccessResponse(
        result=ExecutionResult(content=result.content),
        decision=public_decision,
        economics=_execution_economics(
            route, result.usage, observed_model=result.observed_model
        ),
    )
    return JSONResponse(
        status_code=200,
        content=response.model_dump(exclude_none=True),
        media_type="application/json",
    )


def _public_decision(decision: SelectedDecision) -> SelectedPublicDecision:
    """Project a validated internal selection into its public explanation."""

    route = decision.route
    return SelectedPublicDecision(
        route=SelectedRoute(
            id=route.id,
            provider=route.provider,
            model=route.model,
        ),
        strategy=SelectedStrategy(),
        applied_constraints=list(decision.applied_constraints),
        reason=decision.reason,
        factors=list(decision.factors),
    )


def _execution_economics(
    route: Route,
    usage: NormalizedUsage | None = None,
    *,
    observed_model: str | None = None,
) -> ExecutionEconomics:
    """Build the three public economic views for an execution.

    The pre-execution estimate is preserved from the selected route, observed
    usage is normalized independently, and calculated cost is attempted only
    through the conservative post-execution policy.
    """

    estimate = route.estimate
    if estimate.status == "unavailable":
        assert estimate.reason is not None
        public_estimate = UnavailableEconomicValue(reason=estimate.reason)
    else:
        assert estimate.amount is not None
        assert estimate.currency is not None
        assert estimate.price_reference is not None
        assert estimate.assumptions is not None
        estimate_fields = {
            "amount": estimate.amount,
            "currency": estimate.currency,
            "price_reference": estimate.price_reference,
            "assumptions": list(estimate.assumptions),
        }
        if estimate.status == "uncertain":
            assert estimate.reason is not None
            public_estimate = UncertainEconomicValue(
                **estimate_fields, reason=estimate.reason
            )
        else:
            public_estimate = AvailableEconomicValue(**estimate_fields)

    if usage is None or usage.status == "unavailable":
        public_usage = UnavailableUsage(
            reason=(
                usage.reason
                if usage is not None and usage.reason is not None
                else "A execução não produziu uso normalizado."
            )
        )
    else:
        usage_fields = {
            "items": [
                UsageItem(unit=item.unit, quantity=str(item.quantity))
                for item in usage.items
            ]
        }
        if usage.status == "uncertain":
            assert usage.reason is not None
            public_usage = UncertainUsage(
                **usage_fields, reason=usage.reason
            )
        else:
            public_usage = AvailableUsage(**usage_fields)

    calculated_cost = calculate_post_execution_cost(
        route_id=route.id,
        provider=route.provider,
        configured_model=route.model,
        observed_model=observed_model,
        estimate=estimate,
        usage=usage,
        reference=route.price_reference,
    )
    if calculated_cost.status == "available":
        assert calculated_cost.amount is not None
        assert calculated_cost.currency is not None
        assert calculated_cost.price_reference is not None
        assert calculated_cost.assumptions is not None
        public_calculated_cost = AvailableEconomicValue(
            amount=calculated_cost.amount,
            currency=calculated_cost.currency,
            price_reference=calculated_cost.price_reference,
            assumptions=list(calculated_cost.assumptions),
        )
    else:
        assert calculated_cost.reason is not None
        public_calculated_cost = UnavailableEconomicValue(
            reason=calculated_cost.reason
        )

    return ExecutionEconomics(
        estimate=public_estimate,
        usage=public_usage,
        calculated_cost=public_calculated_cost,
    )


def _execution_error(
    code: str,
    message: str,
    decision: SelectedPublicDecision,
    economics: ExecutionEconomics,
    status_code: int,
) -> JSONResponse:
    """Create a provider-neutral error while preserving known decision facts."""

    response = ExecutionErrorResponse(
        error=ExecutionPublicError(code=code, message=message),
        decision=decision,
        economics=economics,
    )
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(exclude_none=True),
        media_type="application/json",
    )


def _internal_error(code: str, message: str, issue: str) -> JSONResponse:
    """Create a sanitized server error for invalid local state."""

    response = InternalErrorResponse(
        error=InternalPublicError(
            code=code,
            message=message,
            issues=[ErrorIssue(message=issue)],
        )
    )
    return JSONResponse(
        status_code=500,
        content=response.model_dump(exclude_none=True),
        media_type="application/json",
    )


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build a JSON object while rejecting ambiguous repeated member names."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateMemberError(key)
        result[key] = value
    return result


def _has_isolated_surrogate(value: object) -> bool:
    """Check iteratively whether a decoded JSON structure contains Unicode surrogates.

    Iterates through strings, lists, and dict keys/values using an explicit stack
    to avoid recursion depth limits while rejecting unpaired surrogates (U+D800..U+DFFF).
    """
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in current):
                return True
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
    return False


def _validate_content_type(content_type: str | None) -> ErrorIssue | None:
    """Accept JSON with no parameter or with one explicit UTF-8 charset."""

    if content_type is None:
        return ErrorIssue(message="Content-Type deve ser application/json.")

    parts = [part.strip() for part in content_type.split(";")]
    if parts[0].lower() != "application/json":
        return ErrorIssue(message="Content-Type deve ser application/json.")

    charset_seen = False
    for parameter in parts[1:]:
        name, separator, value = parameter.partition("=")
        if name.strip().lower() != "charset" or charset_seen:
            return ErrorIssue(
                message="application/json aceita somente o parâmetro opcional charset."
            )
        charset_seen = True
        if not separator or value.strip().strip('"').lower() != "utf-8":
            return ErrorIssue(
                message="O charset de application/json deve ser UTF-8."
            )
    return None


def _validation_issues(error: ValidationError) -> list[ErrorIssue]:
    """Translate Pydantic errors into the stable public issue model."""

    return [
        ErrorIssue(
            path=_json_pointer(item["loc"]),
            message=_validation_message(item),
        )
        for item in error.errors(include_url=False, include_input=False)
    ]


def _json_pointer(location: tuple[str | int, ...]) -> str:
    """Encode a Pydantic location as an RFC 6901-style JSON Pointer."""

    if not location:
        return ""
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in location]
    return "/" + "/".join(encoded)


def _validation_message(item: dict[str, Any]) -> str:
    """Replace framework wording with stable Portuguese contract messages."""

    error_type = item["type"]
    if error_type == "missing":
        return "O campo é obrigatório."
    if error_type == "extra_forbidden":
        return "O campo não pertence ao schema fechado da solicitação."
    if error_type == "string_type":
        return "O campo deve ser uma string."
    if error_type == "list_type":
        return "O campo deve ser um array."
    if error_type == "model_type":
        return "O campo deve ser um objeto."
    message = item["msg"]
    if message.startswith("Value error, "):
        return message.removeprefix("Value error, ")
    return message


def _invalid_request(
    issues: list[ErrorIssue], status_code: int = 400
) -> JSONResponse:
    """Create the public invalid-request envelope with its applicable status."""

    response = InvalidRequestResponse(error=InvalidRequestError(issues=issues))
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(exclude_none=True),
        media_type="application/json",
    )


# Default imports remain intentionally unconfigured.  Operational composition
# with provider routes is performed by the explicit bootstrap module.
app = create_app()

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
    UnavailableEconomicValue,
    UncertainEconomicValue,
)
from .execution import (
    ExecutionAdapter,
    ExecutionFailedError,
    ExecutionRoute,
    ExecutionTimeoutError,
    ExecutionUnavailableError,
    TextExecutionRequest,
    TextExecutionResult,
)
from .routing import (
    EconomicEstimate,
    InvalidDecisionError,
    RouteCatalog,
    SelectedDecision,
    route_request,
)


class DuplicateMemberError(ValueError):
    def __init__(self, member: str) -> None:
        self.member = member
        super().__init__(member)


def create_app(
    catalog: RouteCatalog | None = None,
    adapters: Mapping[str, ExecutionAdapter] | None = None,
) -> FastAPI:
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
        media_issue = _validate_content_type(request.headers.get("content-type"))
        if media_issue is not None:
            return _invalid_request([media_issue], status_code=415)

        try:
            body = (await request.body()).decode("utf-8")
            payload = json.loads(body, object_pairs_hook=_reject_duplicate_members)
        except UnicodeDecodeError:
            return _invalid_request(
                [ErrorIssue(message="O corpo JSON deve usar codificação UTF-8.")]
            )
        except DuplicateMemberError as error:
            return _invalid_request(
                [
                    ErrorIssue(
                        message=(
                            "O JSON contém um nome de membro duplicado: "
                            f"{error.member}."
                        )
                    )
                ]
            )
        except json.JSONDecodeError:
            return _invalid_request(
                [ErrorIssue(message="O corpo deve conter um objeto JSON válido.")]
            )

        try:
            execution_request = ExecutionRequest.model_validate(payload)
        except ValidationError as error:
            return _invalid_request(_validation_issues(error))

        try:
            adapter_snapshot = _snapshot_adapters(
                route_catalog, adapter_registry
            )
            enabled_routes = tuple(
                route for route in route_catalog.snapshot() if route.enabled
            )
            locally_invalid_route_ids = frozenset(
                route.id
                for route in enabled_routes
                if not _is_valid_adapter(
                    adapter_snapshot.get(route.adapter_id)
                )
            )
            if enabled_routes and len(locally_invalid_route_ids) == len(
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
            routing_result = route_request(
                execution_request,
                route_catalog,
                locally_invalid_route_ids=locally_invalid_route_ids,
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
    applicable_adapter_ids = {
        route.adapter_id for route in catalog.snapshot() if route.enabled
    }
    snapshot = {
        adapter_id: adapters.get(adapter_id)
        for adapter_id in applicable_adapter_ids
    }
    return MappingProxyType(snapshot)


def _is_valid_adapter(adapter: object | None) -> bool:
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
    economics = _execution_economics(route.estimate)
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
        economics=economics,
    )
    return JSONResponse(
        status_code=200,
        content=response.model_dump(exclude_none=True),
        media_type="application/json",
    )


def _public_decision(decision: SelectedDecision) -> SelectedPublicDecision:
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


def _execution_economics(estimate: EconomicEstimate) -> ExecutionEconomics:
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

    return ExecutionEconomics(
        estimate=public_estimate,
        usage=UnavailableEconomicValue(
            reason="O adaptador desta fatia não fornece uso normalizado."
        ),
        calculated_cost=UnavailableEconomicValue(
            reason="Não é possível calcular custo sem uso normalizado suficiente."
        ),
    )


def _execution_error(
    code: str,
    message: str,
    decision: SelectedPublicDecision,
    economics: ExecutionEconomics,
    status_code: int,
) -> JSONResponse:
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
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateMemberError(key)
        result[key] = value
    return result


def _validate_content_type(content_type: str | None) -> ErrorIssue | None:
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
    return [
        ErrorIssue(
            path=_json_pointer(item["loc"]),
            message=_validation_message(item),
        )
        for item in error.errors(include_url=False, include_input=False)
    ]


def _json_pointer(location: tuple[str | int, ...]) -> str:
    if not location:
        return ""
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in location]
    return "/" + "/".join(encoded)


def _validation_message(item: dict[str, Any]) -> str:
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
    response = InvalidRequestResponse(error=InvalidRequestError(issues=issues))
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(exclude_none=True),
        media_type="application/json",
    )


app = create_app()

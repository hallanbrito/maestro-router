from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .contracts import (
    ErrorIssue,
    ExecutionRequest,
    InvalidRequestError,
    InvalidRequestResponse,
    RefusalResponse,
)
from .routing import RouteCatalog, refuse_when_no_route


class DuplicateMemberError(ValueError):
    def __init__(self, member: str) -> None:
        self.member = member
        super().__init__(member)


def create_app(catalog: RouteCatalog | None = None) -> FastAPI:
    app = FastAPI(
        title="Maestro Router",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    route_catalog = catalog if catalog is not None else RouteCatalog()

    @app.post(
        "/v1/executions",
        response_model=RefusalResponse,
        responses={
            400: {"model": InvalidRequestResponse},
            415: {"model": InvalidRequestResponse},
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

        refusal = refuse_when_no_route(execution_request, route_catalog)
        return JSONResponse(
            status_code=422,
            content=refusal.model_dump(exclude_none=True),
            media_type="application/json",
        )

    return app


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

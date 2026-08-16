from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest
from fastapi.testclient import TestClient

from maestro_router.adapters import OpenAIResponsesAdapter
from maestro_router.api import _is_valid_adapter, create_app
from maestro_router.execution import (
    ExecutionAdapter,
    ExecutionFailedError,
    ExecutionRoute,
    ExecutionTimeoutError,
    ExecutionUnavailableError,
    TextExecutionRequest,
    TextExecutionResult,
)
from maestro_router.routing import EconomicEstimate, Route, RouteCatalog


SENSITIVE_DETAIL = "external key material and payload https://internal.invalid"


class FakeResponses:
    def __init__(
        self, response: object | None = None, error: Exception | None = None
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeAsyncOpenAI:
    def __init__(
        self, response: object | None = None, error: Exception | None = None
    ) -> None:
        self.responses = FakeResponses(response, error)
        self.option_calls: list[dict[str, Any]] = []

    def with_options(self, **kwargs: Any) -> FakeAsyncOpenAI:
        self.option_calls.append(kwargs)
        return self


def completed_response(text: str) -> SimpleNamespace:
    text_part = SimpleNamespace(type="output_text", text=text)
    message = SimpleNamespace(type="message", content=[text_part])
    return SimpleNamespace(
        status="completed", output=[message], output_text=text
    )


def execution_route() -> ExecutionRoute:
    return ExecutionRoute(
        id="route-secret-id",
        provider="provider-secret-id",
        model="configured-model-id",
    )


def status_error(
    error_type: type[openai.APIStatusError], status_code: int
) -> openai.APIStatusError:
    request = httpx2.Request("POST", "https://internal.invalid/v1/responses")
    response = httpx2.Response(status_code, request=request)
    return error_type(
        SENSITIVE_DETAIL,
        response=response,
        body={"payload": SENSITIVE_DETAIL},
    )


def available_estimate() -> EconomicEstimate:
    return EconomicEstimate(
        status="available",
        amount="0.01",
        currency="USD",
        price_reference="pricing-test",
        assumptions=(),
    )


def configured_route() -> Route:
    return Route(
        id="route-openai",
        provider="openai",
        model="configured-model-id",
        adapter_id="openai-responses",
        capabilities=frozenset({"text_generation"}),
        estimate=available_estimate(),
    )


def test_adapter_is_structurally_compatible_with_execution_frontier() -> None:
    client = FakeAsyncOpenAI(completed_response("ok"))
    adapter: ExecutionAdapter = OpenAIResponsesAdapter(client)  # type: ignore[arg-type]

    assert inspect.iscoroutinefunction(adapter.execute)
    assert _is_valid_adapter(adapter)


@pytest.mark.parametrize(
    ("execution_request", "expected_content"),
    [
        (
            TextExecutionRequest(task="Execute the task."),
            [{"type": "input_text", "text": "Execute the task."}],
        ),
        (
            TextExecutionRequest(
                task="Execute the task.", context="Application context."
            ),
            [
                {"type": "input_text", "text": "Execute the task."},
                {"type": "input_text", "text": "Application context."},
            ],
        ),
    ],
)
@pytest.mark.anyio
async def test_request_translation_is_deterministic_and_uses_route_model(
    execution_request: TextExecutionRequest,
    expected_content: list[dict[str, str]],
) -> None:
    client = FakeAsyncOpenAI(completed_response("normalized"))
    adapter = OpenAIResponsesAdapter(client)  # type: ignore[arg-type]

    result = await adapter.execute(execution_request, execution_route())

    assert result == TextExecutionResult(content="normalized")
    assert len(client.responses.calls) == 1
    assert client.responses.calls[0] == {
        "model": "configured-model-id",
        "input": [{"role": "user", "content": expected_content}],
        "stream": False,
    }
    serialized_input = repr(client.responses.calls[0]["input"])
    assert "route-secret-id" not in serialized_input
    assert "provider-secret-id" not in serialized_input


@pytest.mark.anyio
async def test_sdk_automatic_retry_is_disabled_per_execution() -> None:
    client = FakeAsyncOpenAI(completed_response("ok"))
    adapter = OpenAIResponsesAdapter(client)  # type: ignore[arg-type]

    await adapter.execute(TextExecutionRequest(task="Execute."), execution_route())

    assert client.option_calls == [{"max_retries": 0}]
    assert len(client.responses.calls) == 1


@pytest.mark.anyio
async def test_completed_empty_text_is_a_valid_normalized_result() -> None:
    client = FakeAsyncOpenAI(completed_response(""))
    adapter = OpenAIResponsesAdapter(client)  # type: ignore[arg-type]

    result = await adapter.execute(
        TextExecutionRequest(task="Return empty text."), execution_route()
    )

    assert result == TextExecutionResult(content="")


@pytest.mark.parametrize(
    "response",
    [
        None,
        SimpleNamespace(status="incomplete", output=[], output_text="partial"),
        SimpleNamespace(status="completed", output=[], output_text=""),
        SimpleNamespace(
            status="completed",
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="refusal", refusal="rejected")],
                )
            ],
            output_text="",
        ),
        SimpleNamespace(
            status="completed",
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", text="valid")],
                )
            ],
            output_text=None,
        ),
    ],
)
@pytest.mark.anyio
async def test_invalid_or_non_textual_response_is_execution_failure(
    response: object | None,
) -> None:
    client = FakeAsyncOpenAI(response)
    adapter = OpenAIResponsesAdapter(client)  # type: ignore[arg-type]

    with pytest.raises(ExecutionFailedError, match="execução externa falhou"):
        await adapter.execute(TextExecutionRequest(task="Execute."), execution_route())


@pytest.mark.anyio
async def test_sdk_timeout_is_normalized() -> None:
    request = httpx2.Request("POST", "https://internal.invalid/v1/responses")
    client = FakeAsyncOpenAI(error=openai.APITimeoutError(request))
    adapter = OpenAIResponsesAdapter(client)  # type: ignore[arg-type]

    with pytest.raises(ExecutionTimeoutError) as caught:
        await adapter.execute(TextExecutionRequest(task="Execute."), execution_route())

    assert SENSITIVE_DETAIL not in str(caught.value)
    assert len(client.responses.calls) == 1


@pytest.mark.parametrize(
    "error",
    [
        openai.APIConnectionError(
            message=SENSITIVE_DETAIL,
            request=httpx2.Request("POST", "https://internal.invalid"),
        ),
        status_error(openai.RateLimitError, 429),
        status_error(openai.InternalServerError, 503),
    ],
)
@pytest.mark.anyio
async def test_temporary_sdk_errors_are_normalized_as_unavailable(
    error: Exception,
) -> None:
    client = FakeAsyncOpenAI(error=error)
    adapter = OpenAIResponsesAdapter(client)  # type: ignore[arg-type]

    with pytest.raises(ExecutionUnavailableError) as caught:
        await adapter.execute(TextExecutionRequest(task="Execute."), execution_route())

    assert SENSITIVE_DETAIL not in str(caught.value)
    assert len(client.responses.calls) == 1


@pytest.mark.parametrize(
    "error",
    [
        status_error(openai.AuthenticationError, 401),
        status_error(openai.PermissionDeniedError, 403),
        status_error(openai.NotFoundError, 404),
        status_error(openai.BadRequestError, 400),
        openai.APIError(
            SENSITIVE_DETAIL,
            httpx2.Request("POST", "https://internal.invalid"),
            body={"payload": SENSITIVE_DETAIL},
        ),
    ],
)
@pytest.mark.anyio
async def test_non_temporary_sdk_errors_are_normalized_as_failed(
    error: Exception,
) -> None:
    client = FakeAsyncOpenAI(error=error)
    adapter = OpenAIResponsesAdapter(client)  # type: ignore[arg-type]

    with pytest.raises(ExecutionFailedError) as caught:
        await adapter.execute(TextExecutionRequest(task="Execute."), execution_route())

    assert type(caught.value) is ExecutionFailedError
    assert SENSITIVE_DETAIL not in str(caught.value)
    assert len(client.responses.calls) == 1


def test_external_error_details_do_not_reach_http_response() -> None:
    client = FakeAsyncOpenAI(
        error=status_error(openai.AuthenticationError, 401)
    )
    adapter = OpenAIResponsesAdapter(client)  # type: ignore[arg-type]
    route = configured_route()
    app = create_app(RouteCatalog([route]), {route.adapter_id: adapter})

    response = TestClient(app).post(
        "/v1/executions", json={"task": "Execute."}
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EXECUTION_FAILED"
    assert SENSITIVE_DETAIL not in response.text
    assert "internal.invalid" not in response.text
    assert len(client.responses.calls) == 1


def test_openai_adapter_is_not_registered_by_default() -> None:
    client = FakeAsyncOpenAI(completed_response("must not execute"))
    route = configured_route()

    response = TestClient(create_app(RouteCatalog([route]))).post(
        "/v1/executions", json={"task": "Execute."}
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INVALID_CONFIGURATION"
    assert client.responses.calls == []


def test_routing_refusal_does_not_call_openai_adapter() -> None:
    client = FakeAsyncOpenAI(completed_response("must not execute"))
    adapter = OpenAIResponsesAdapter(client)  # type: ignore[arg-type]
    route = configured_route()
    app = create_app(RouteCatalog([route]), {route.adapter_id: adapter})

    response = TestClient(app).post(
        "/v1/executions",
        json={
            "task": "Execute.",
            "constraints": {"required_capabilities": ["missing-capability"]},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_ELIGIBLE_ROUTE"
    assert client.responses.calls == []


def test_openai_success_keeps_usage_and_calculated_cost_unavailable() -> None:
    client = FakeAsyncOpenAI(completed_response("normalized"))
    adapter = OpenAIResponsesAdapter(client)  # type: ignore[arg-type]
    route = configured_route()
    app = create_app(RouteCatalog([route]), {route.adapter_id: adapter})

    response = TestClient(app).post(
        "/v1/executions", json={"task": "Execute."}
    )

    assert response.status_code == 200
    assert response.json()["result"] == {"content": "normalized"}
    assert response.json()["economics"]["usage"]["status"] == "unavailable"
    assert (
        response.json()["economics"]["calculated_cost"]["status"]
        == "unavailable"
    )

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from maestro_router.adapters import GoogleGeminiInteractionsAdapter
from maestro_router.api import _is_valid_adapter
from maestro_router.execution import (
    ExecutionAdapter,
    ExecutionFailedError,
    ExecutionRoute,
    ExecutionTimeoutError,
    ExecutionUnavailableError,
    NormalizedUsage,
    NormalizedUsageItem,
    TextExecutionRequest,
    TextExecutionResult,
    USAGE_UNAVAILABLE_REASON,
)


SENSITIVE_SECRET = "gemini-api-key-secret-payload-never-leak-12345"
OMITTED = object()


class FakeInteractions:
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


class FakeGenAIClient:
    def __init__(
        self, response: object | None = None, error: Exception | None = None
    ) -> None:
        self.interactions = FakeInteractions(response, error)
        self.aio = SimpleNamespace(interactions=self.interactions)


class MockAPIError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


def completed_interaction(
    text: str,
    usage: object = OMITTED,
    model: str = "gemini-2.5-flash",
    status: str = "completed",
    errors: list[Any] | None = None,
    steps: list[Any] | None = None,
) -> SimpleNamespace:
    res = SimpleNamespace(
        status=status,
        output_text=text,
        model=model,
        errors=errors,
        steps=steps,
    )
    if usage is not OMITTED:
        res.usage = usage
    return res


def execution_route() -> ExecutionRoute:
    return ExecutionRoute(
        id="route-google-gemini",
        provider="google",
        model="gemini-2.5-flash",
    )


def test_adapter_is_structurally_compatible_with_execution_frontier() -> None:
    client = FakeGenAIClient(completed_interaction("ok"))
    adapter: ExecutionAdapter = GoogleGeminiInteractionsAdapter(client)

    assert inspect.iscoroutinefunction(adapter.execute)
    assert _is_valid_adapter(adapter)


@pytest.mark.anyio
async def test_store_false_always_present_and_disallowed_parameters_absent() -> None:
    client = FakeGenAIClient(completed_interaction("Texto de resposta"))
    adapter = GoogleGeminiInteractionsAdapter(client)

    request = TextExecutionRequest(task="Analise este texto.")
    route = execution_route()

    result = await adapter.execute(request, route)

    assert result.content == "Texto de resposta"
    assert len(client.interactions.calls) == 1
    call_args = client.interactions.calls[0]

    # Invariante 1: store=False sempre presente
    assert "store" in call_args
    assert call_args["store"] is False

    # Invariante 2 e 3: ausência estrita de previous_interaction_id e background
    assert "previous_interaction_id" not in call_args
    assert "background" not in call_args

    # Parâmetros fora de escopo do MVP não devem ser enviados
    assert "tools" not in call_args
    assert "stream" not in call_args
    assert "agent" not in call_args
    assert "agent_config" not in call_args


@pytest.mark.parametrize(
    ("execution_request", "expected_input"),
    [
        (
            TextExecutionRequest(task="Resuma este artigo."),
            [{"type": "text", "text": "Resuma este artigo."}],
        ),
        (
            TextExecutionRequest(
                task="Traduza o documento.", context="Documento técnico em inglês."
            ),
            [
                {"type": "text", "text": "Traduza o documento."},
                {"type": "text", "text": "Documento técnico em inglês."},
            ],
        ),
    ],
)
@pytest.mark.anyio
async def test_exact_translation_of_task_and_context(
    execution_request: TextExecutionRequest,
    expected_input: list[dict[str, str]],
) -> None:
    client = FakeGenAIClient(completed_interaction("Resultado"))
    adapter = GoogleGeminiInteractionsAdapter(client)

    result = await adapter.execute(execution_request, execution_route())

    assert result.content == "Resultado"
    assert len(client.interactions.calls) == 1
    assert client.interactions.calls[0]["input"] == expected_input
    assert client.interactions.calls[0]["model"] == "gemini-2.5-flash"


@pytest.mark.anyio
async def test_completed_text_normalized() -> None:
    client = FakeGenAIClient(
        completed_interaction(
            "Resposta gerada com sucesso.", model="gemini-2.5-flash"
        )
    )
    adapter = GoogleGeminiInteractionsAdapter(client)

    result = await adapter.execute(
        TextExecutionRequest(task="Gere um poema."), execution_route()
    )

    assert result.content == "Resposta gerada com sucesso."
    assert result.observed_model == "gemini-2.5-flash"


@pytest.mark.anyio
async def test_complete_usage_mapped() -> None:
    usage_obj = SimpleNamespace(
        total_input_tokens=120,
        total_output_tokens=45,
    )
    client = FakeGenAIClient(
        completed_interaction("Texto", usage=usage_obj)
    )
    adapter = GoogleGeminiInteractionsAdapter(client)

    result = await adapter.execute(
        TextExecutionRequest(task="Tarefa"), execution_route()
    )

    assert result.usage == NormalizedUsage(
        status="available",
        items=(
            NormalizedUsageItem(unit="input_token", quantity=120),
            NormalizedUsageItem(unit="output_token", quantity=45),
        ),
    )


@pytest.mark.parametrize(
    ("usage_obj", "expected_item"),
    [
        (
            SimpleNamespace(total_input_tokens=100, total_output_tokens=None),
            NormalizedUsageItem(unit="input_token", quantity=100),
        ),
        (
            SimpleNamespace(total_input_tokens=-1, total_output_tokens=50),
            NormalizedUsageItem(unit="output_token", quantity=50),
        ),
        (
            SimpleNamespace(total_input_tokens="invalid", total_output_tokens=30),
            NormalizedUsageItem(unit="output_token", quantity=30),
        ),
    ],
)
@pytest.mark.anyio
async def test_partial_usage_normalized_as_uncertain(
    usage_obj: object, expected_item: NormalizedUsageItem
) -> None:
    client = FakeGenAIClient(
        completed_interaction("Texto", usage=usage_obj)
    )
    adapter = GoogleGeminiInteractionsAdapter(client)

    result = await adapter.execute(
        TextExecutionRequest(task="Tarefa"), execution_route()
    )

    assert result.usage.status == "uncertain"
    assert result.usage.items == (expected_item,)
    assert (
        result.usage.reason
        == "A resposta concluída forneceu somente parte do uso normalizável."
    )


@pytest.mark.parametrize(
    "usage_obj",
    [
        None,
        OMITTED,
        SimpleNamespace(),
        SimpleNamespace(total_input_tokens=-5, total_output_tokens="abc"),
        SimpleNamespace(total_input_tokens=None, total_output_tokens=None),
    ],
)
@pytest.mark.anyio
async def test_absent_or_invalid_usage_normalized_as_unavailable(
    usage_obj: object,
) -> None:
    client = FakeGenAIClient(
        completed_interaction("Texto", usage=usage_obj)
    )
    adapter = GoogleGeminiInteractionsAdapter(client)

    result = await adapter.execute(
        TextExecutionRequest(task="Tarefa"), execution_route()
    )

    assert result.usage.status == "unavailable"
    assert result.usage.items == ()
    assert result.usage.reason == USAGE_UNAVAILABLE_REASON


@pytest.mark.parametrize(
    "error",
    [
        MockAPIError(f"Unauthorized: {SENSITIVE_SECRET}", status_code=401),
        MockAPIError(f"Unauthorized: {SENSITIVE_SECRET}", code=401),
        MockAPIError(f"API key not valid: {SENSITIVE_SECRET}", status_code=400),
    ],
)
@pytest.mark.anyio
async def test_authentication_denied_raises_execution_failed(error: Any) -> None:
    client = FakeGenAIClient(error=error)
    adapter = GoogleGeminiInteractionsAdapter(client)

    with pytest.raises(ExecutionFailedError) as exc_info:
        await adapter.execute(
            TextExecutionRequest(task="Tarefa"), execution_route()
        )

    assert str(exc_info.value) == "A execução externa falhou."
    assert SENSITIVE_SECRET not in str(exc_info.value)


@pytest.mark.parametrize(
    "error",
    [
        MockAPIError(f"Permission Denied: {SENSITIVE_SECRET}", status_code=403),
        MockAPIError(f"Permission Denied: {SENSITIVE_SECRET}", code=403),
    ],
)
@pytest.mark.anyio
async def test_permission_denied_raises_execution_failed(error: Any) -> None:
    client = FakeGenAIClient(error=error)
    adapter = GoogleGeminiInteractionsAdapter(client)

    with pytest.raises(ExecutionFailedError) as exc_info:
        await adapter.execute(
            TextExecutionRequest(task="Tarefa"), execution_route()
        )

    assert str(exc_info.value) == "A execução externa falhou."
    assert SENSITIVE_SECRET not in str(exc_info.value)


@pytest.mark.parametrize(
    "error",
    [
        MockAPIError(f"Resource exhausted: {SENSITIVE_SECRET}", status_code=429),
        MockAPIError("Rate limit exceeded", code=429),
        RuntimeError("Quota exceeded for project 12345"),
        RuntimeError("RESOURCE_EXHAUSTED"),
    ],
)
@pytest.mark.anyio
async def test_quota_and_rate_limit_raises_execution_unavailable(error: Any) -> None:
    client = FakeGenAIClient(error=error)
    adapter = GoogleGeminiInteractionsAdapter(client)

    with pytest.raises(ExecutionUnavailableError) as exc_info:
        await adapter.execute(
            TextExecutionRequest(task="Tarefa"), execution_route()
        )

    assert str(exc_info.value) == "A execução externa estava temporariamente indisponível."
    assert SENSITIVE_SECRET not in str(exc_info.value)


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("Connection timed out"),
        httpx.ReadTimeout("Read timed out"),
        httpx.ConnectTimeout("Connect timed out"),
        MockAPIError("Request Timeout", status_code=408),
        MockAPIError("Request Timeout", code=408),
    ],
)
@pytest.mark.anyio
async def test_timeout_raises_execution_timeout(error: Any) -> None:
    client = FakeGenAIClient(error=error)
    adapter = GoogleGeminiInteractionsAdapter(client)

    with pytest.raises(ExecutionTimeoutError) as exc_info:
        await adapter.execute(
            TextExecutionRequest(task="Tarefa"), execution_route()
        )

    assert str(exc_info.value) == "A execução externa excedeu o timeout aplicável."


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("Connection refused"),
        httpx.NetworkError("Network down"),
        MockAPIError(f"Internal Server Error: {SENSITIVE_SECRET}", status_code=500),
        MockAPIError("Bad Gateway", status_code=502),
        MockAPIError("Service Unavailable", status_code=503),
        MockAPIError("Gateway Timeout", status_code=504),
        MockAPIError("Unavailable", code=503),
    ],
)
@pytest.mark.anyio
async def test_unavailability_raises_execution_unavailable(error: Any) -> None:
    client = FakeGenAIClient(error=error)
    adapter = GoogleGeminiInteractionsAdapter(client)

    with pytest.raises(ExecutionUnavailableError) as exc_info:
        await adapter.execute(
            TextExecutionRequest(task="Tarefa"), execution_route()
        )

    assert str(exc_info.value) == "A execução externa estava temporariamente indisponível."
    assert SENSITIVE_SECRET not in str(exc_info.value)


@pytest.mark.parametrize(
    "interaction",
    [
        completed_interaction(""),
        completed_interaction("   \n\t  "),
        completed_interaction(None),  # type: ignore[arg-type]
    ],
)
@pytest.mark.anyio
async def test_empty_or_whitespace_text_raises_execution_failed(
    interaction: SimpleNamespace,
) -> None:
    client = FakeGenAIClient(interaction)
    adapter = GoogleGeminiInteractionsAdapter(client)

    with pytest.raises(ExecutionFailedError) as exc_info:
        await adapter.execute(
            TextExecutionRequest(task="Tarefa"), execution_route()
        )

    assert str(exc_info.value) == "A execução externa falhou."


@pytest.mark.parametrize(
    "interaction",
    [
        completed_interaction("Texto", status="failed"),
        completed_interaction("Texto", status="cancelled"),
        completed_interaction("Texto", status="budget_exceeded"),
        completed_interaction("Texto", errors=[SimpleNamespace(code="SAFETY", message="Blocked")]),
        completed_interaction(
            "Texto",
            steps=[SimpleNamespace(error=SimpleNamespace(code=400, message="Step failed"))],
        ),
    ],
)
@pytest.mark.anyio
async def test_blocked_or_incompatible_response_raises_execution_failed(
    interaction: SimpleNamespace,
) -> None:
    client = FakeGenAIClient(interaction)
    adapter = GoogleGeminiInteractionsAdapter(client)

    with pytest.raises(ExecutionFailedError) as exc_info:
        await adapter.execute(
            TextExecutionRequest(task="Tarefa"), execution_route()
        )

    assert str(exc_info.value) == "A execução externa falhou."


@pytest.mark.anyio
async def test_no_secret_leak_in_exceptions_or_responses() -> None:
    hostile_error = RuntimeError(f"SDK internal dump with key {SENSITIVE_SECRET}")
    client = FakeGenAIClient(error=hostile_error)
    adapter = GoogleGeminiInteractionsAdapter(client)

    with pytest.raises(ExecutionFailedError) as exc_info:
        await adapter.execute(
            TextExecutionRequest(task="Tarefa"), execution_route()
        )

    # O texto da exceção pública normalizada deve ser imutável e livre do segredo
    assert str(exc_info.value) == "A execução externa falhou."
    assert SENSITIVE_SECRET not in str(exc_info.value)

from __future__ import annotations

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)

from ..execution import (
    ExecutionFailedError,
    ExecutionRoute,
    ExecutionTimeoutError,
    ExecutionUnavailableError,
    TextExecutionRequest,
    TextExecutionResult,
)


_FAILED_MESSAGE = "A execução externa falhou."
_TIMEOUT_MESSAGE = "A execução externa excedeu o timeout aplicável."
_UNAVAILABLE_MESSAGE = "A execução externa estava temporariamente indisponível."


class OpenAIResponsesAdapter:
    """Translate the neutral execution contract to the OpenAI Responses API."""

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    async def execute(
        self, request: TextExecutionRequest, route: ExecutionRoute
    ) -> TextExecutionResult:
        try:
            response = await self._client.with_options(
                max_retries=0
            ).responses.create(
                model=route.model,
                input=_response_input(request),
                stream=False,
            )
        except APITimeoutError as error:
            raise ExecutionTimeoutError(_TIMEOUT_MESSAGE) from error
        except (APIConnectionError, RateLimitError) as error:
            raise ExecutionUnavailableError(_UNAVAILABLE_MESSAGE) from error
        except APIStatusError as error:
            if error.status_code >= 500:
                raise ExecutionUnavailableError(
                    _UNAVAILABLE_MESSAGE
                ) from error
            raise ExecutionFailedError(_FAILED_MESSAGE) from error
        except OpenAIError as error:
            raise ExecutionFailedError(_FAILED_MESSAGE) from error
        except Exception as error:
            raise ExecutionFailedError(_FAILED_MESSAGE) from error

        return _normalize_response(response)


def _response_input(request: TextExecutionRequest) -> list[dict[str, object]]:
    content = [{"type": "input_text", "text": request.task}]
    if request.context is not None:
        content.append({"type": "input_text", "text": request.context})
    return [{"role": "user", "content": content}]


def _normalize_response(response: object) -> TextExecutionResult:
    try:
        if getattr(response, "status", None) != "completed":
            raise ExecutionFailedError(_FAILED_MESSAGE)

        output = getattr(response, "output")
        if not isinstance(output, list) or not _has_valid_text_output(output):
            raise ExecutionFailedError(_FAILED_MESSAGE)

        output_text = getattr(response, "output_text")
        if not isinstance(output_text, str):
            raise ExecutionFailedError(_FAILED_MESSAGE)
        return TextExecutionResult(content=output_text)
    except ExecutionFailedError:
        raise
    except Exception as error:
        raise ExecutionFailedError(_FAILED_MESSAGE) from error


def _has_valid_text_output(output: list[object]) -> bool:
    found_text = False
    for item in output:
        if getattr(item, "type", None) != "message":
            continue
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            return False
        for part in content:
            if getattr(part, "type", None) != "output_text":
                continue
            if not isinstance(getattr(part, "text", None), str):
                return False
            found_text = True
    return found_text

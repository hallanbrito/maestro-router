"""OpenAI Responses API implementation of the neutral execution boundary."""

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
    NormalizedUsage,
    NormalizedUsageItem,
    TextExecutionRequest,
    TextExecutionResult,
    USAGE_UNAVAILABLE_REASON,
)


_FAILED_MESSAGE = "A execução externa falhou."
_TIMEOUT_MESSAGE = "A execução externa excedeu o timeout aplicável."
_UNAVAILABLE_MESSAGE = "A execução externa estava temporariamente indisponível."
_PARTIAL_USAGE_REASON = (
    "A resposta concluída forneceu somente parte do uso normalizável."
)
_MISSING = object()


class OpenAIResponsesAdapter:
    """Translate the neutral execution contract to the OpenAI Responses API."""

    def __init__(
        self,
        client: AsyncOpenAI,
        *,
        retry_policy_configured: bool = False,
    ) -> None:
        """Store an explicitly constructed asynchronous OpenAI client."""

        # Freeze the retry policy once when the adapter joins the application
        # snapshot. Rebuilding SDK options per request could re-read process state.
        self._client = (
            client
            if retry_policy_configured
            else client.with_options(max_retries=0)
        )

    async def execute(
        self, request: TextExecutionRequest, route: ExecutionRoute
    ) -> TextExecutionResult:
        """Execute the selected model and translate failures to neutral errors.

        The adapter does not select routes, infer prices, or expose provider
        payloads.  It sends one non-streaming Responses API request and returns
        only validated text and normalized usage.
        """

        try:
            # SDK retries are disabled (max_retries=0) when the adapter is initialized
            # to guarantee that the core's single execution authorization is respected.
            response = await self._client.responses.create(
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
            # Unexpected SDK shapes must cross the boundary as the same
            # sanitized provider-neutral failure, never as raw provider data.
            raise ExecutionFailedError(_FAILED_MESSAGE) from error

        return _normalize_response(response)


def _response_input(request: TextExecutionRequest) -> list[dict[str, object]]:
    """Build the narrow Responses API input supported by the MVP."""

    content = [{"type": "input_text", "text": request.task}]
    if request.context is not None:
        content.append({"type": "input_text", "text": request.context})
    return [{"role": "user", "content": content}]


def _normalize_response(response: object) -> TextExecutionResult:
    """Validate a completed text response and project it into the core model."""

    try:
        if getattr(response, "status", None) != "completed":
            raise ExecutionFailedError(_FAILED_MESSAGE)

        output = getattr(response, "output")
        if not isinstance(output, list) or not _has_valid_text_output(output):
            raise ExecutionFailedError(_FAILED_MESSAGE)

        output_text = getattr(response, "output_text")
        if not isinstance(output_text, str):
            raise ExecutionFailedError(_FAILED_MESSAGE)
        return TextExecutionResult(
            content=output_text,
            usage=_normalize_usage(response),
            observed_model=_normalize_observed_model(response),
        )
    except ExecutionFailedError:
        raise
    except Exception as error:
        raise ExecutionFailedError(_FAILED_MESSAGE) from error


def _normalize_usage(response: object) -> NormalizedUsage:
    """Map supported OpenAI token counters to provider-neutral usage units.

    Complete input and output counts become ``available`` usage.  One valid
    count becomes ``uncertain`` usage, while absent or malformed counts become
    ``unavailable`` rather than being guessed.
    """

    usage = _read_attribute(response, "usage")
    if usage is _MISSING or usage is None:
        return NormalizedUsage(
            status="unavailable", reason=USAGE_UNAVAILABLE_REASON
        )

    items = []
    for external_name, neutral_unit in (
        ("input_tokens", "input_token"),
        ("output_tokens", "output_token"),
    ):
        quantity = _read_attribute(usage, external_name)
        if type(quantity) is int and quantity >= 0:
            items.append(
                NormalizedUsageItem(unit=neutral_unit, quantity=quantity)
            )

    normalized_items = tuple(items)
    if len(normalized_items) == 2:
        return NormalizedUsage(status="available", items=normalized_items)
    if normalized_items:
        return NormalizedUsage(
            status="uncertain",
            items=normalized_items,
            reason=_PARTIAL_USAGE_REASON,
        )
    return NormalizedUsage(
        status="unavailable", reason=USAGE_UNAVAILABLE_REASON
    )


def _normalize_observed_model(response: object) -> str | None:
    """Extract and validate the model identifier reported by the provider.

    Returns the model string if it is non-blank and free of isolated Unicode
    surrogates; otherwise returns None so post-execution validation rejects
    unverifiable model identities.
    """
    model = _read_attribute(response, "model")
    if (
        isinstance(model, str)
        and any(not character.isspace() for character in model)
        and not any(0xD800 <= ord(character) <= 0xDFFF for character in model)
    ):
        return model
    return None


def _read_attribute(value: object, name: str) -> object:
    """Read an SDK attribute without letting hostile accessors escape."""

    try:
        return getattr(value, name)
    except Exception:
        return _MISSING


def _has_valid_text_output(output: list[object]) -> bool:
    """Confirm that the provider output contains structurally valid text."""

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

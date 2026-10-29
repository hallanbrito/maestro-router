"""Google Gemini Interactions API implementation of the neutral execution boundary."""

from __future__ import annotations

from typing import Any

import httpx

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


class GoogleGeminiInteractionsAdapter:
    """Translate the neutral execution contract to Google Gemini Interactions API."""

    def __init__(self, client: Any) -> None:
        """Store an explicitly constructed Google GenAI client."""
        self._client = client

    async def execute(
        self, request: TextExecutionRequest, route: ExecutionRoute
    ) -> TextExecutionResult:
        """Execute the selected model via Interactions API and translate failures to neutral errors.

        The adapter does not select routes, infer prices, or expose provider
        payloads. It sends one non-streaming, stateless Interactions API request
        with store=False, without previous_interaction_id or background execution,
        and returns only validated text and normalized usage.
        """

        try:
            interactions_client = getattr(
                self._client, "aio", self._client
            ).interactions
            response = await interactions_client.create(
                model=route.model,
                input=_interaction_input(request),
                store=False,
            )
        except (httpx.TimeoutException, TimeoutError) as error:
            raise ExecutionTimeoutError(_TIMEOUT_MESSAGE) from error
        except (httpx.NetworkError, httpx.ConnectError) as error:
            raise ExecutionUnavailableError(_UNAVAILABLE_MESSAGE) from error
        except Exception as error:
            status_code = getattr(
                error, "status_code", getattr(error, "code", None)
            )
            if status_code == 408:
                raise ExecutionTimeoutError(_TIMEOUT_MESSAGE) from error
            if status_code in (429, 500, 502, 503, 504):
                raise ExecutionUnavailableError(_UNAVAILABLE_MESSAGE) from error
            if isinstance(status_code, int) and 500 <= status_code < 600:
                raise ExecutionUnavailableError(_UNAVAILABLE_MESSAGE) from error

            error_str = str(error).lower()
            if (
                "rate limit" in error_str
                or "quota" in error_str
                or "resource_exhausted" in error_str
            ):
                raise ExecutionUnavailableError(_UNAVAILABLE_MESSAGE) from error

            # Unexpected SDK shapes or ClientErrors must cross the boundary as the
            # same sanitized provider-neutral failure, never as raw provider data.
            raise ExecutionFailedError(_FAILED_MESSAGE) from error

        return _normalize_response(response)


def _interaction_input(request: TextExecutionRequest) -> list[dict[str, str]]:
    """Build the narrow Interactions API input supported by the stateless MVP.

    Translates task and context deterministically into text content items.
    Application data is never elevated to system instructions or tools.
    """
    content = [{"type": "text", "text": request.task}]
    if request.context is not None:
        content.append({"type": "text", "text": request.context})
    return content


def _normalize_response(response: object) -> TextExecutionResult:
    """Validate a completed text response and project it into the core model.

    Rejects non-completed status, blocked responses, empty text, or structural
    incompatibilities, translating them to normalized execution failures.
    """

    try:
        if getattr(response, "status", None) != "completed":
            raise ExecutionFailedError(_FAILED_MESSAGE)

        errors = getattr(response, "errors", None)
        if errors:
            raise ExecutionFailedError(_FAILED_MESSAGE)

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise ExecutionFailedError(_FAILED_MESSAGE)

        steps = getattr(response, "steps", None)
        if isinstance(steps, list):
            for step in steps:
                if getattr(step, "error", None) is not None:
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
    """Map supported Google Gemini token counters to provider-neutral usage units.

    Maps ``total_input_tokens`` to ``input_token`` and ``total_output_tokens`` to
    ``output_token``. Complete input and output counts become ``available`` usage.
    One valid count becomes ``uncertain`` usage, while absent or malformed counts
    become ``unavailable`` rather than being guessed.
    """

    usage = _read_attribute(response, "usage")
    if usage is _MISSING or usage is None:
        return NormalizedUsage(
            status="unavailable", reason=USAGE_UNAVAILABLE_REASON
        )

    items = []
    for external_name, neutral_unit in (
        ("total_input_tokens", "input_token"),
        ("total_output_tokens", "output_token"),
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
    """Extract, canonicalize, and validate the model identifier reported by Google.

    In the Google Gemini Developer API, the Interaction response may report
    the model either as a canonical name (e.g. ``gemini-2.5-flash``) or prefixed
    with the API namespace (e.g. ``models/gemini-2.5-flash``).

    This normalizer strips the standard ``models/`` prefix if present, producing
    the provider-neutral canonical model identity. Unexpected formats or prefixes
    are not guessed, preserving conservative post-execution validation (B4).
    """
    model = _read_attribute(response, "model")
    if (
        isinstance(model, str)
        and any(not character.isspace() for character in model)
        and not any(0xD800 <= ord(character) <= 0xDFFF for character in model)
    ):
        trimmed = model.strip()
        if trimmed.startswith("models/"):
            canonical = trimmed[len("models/") :].strip()
            return canonical if canonical else None
        return trimmed
    return None


def _read_attribute(value: object, name: str) -> object:
    """Read an SDK attribute without letting hostile accessors escape."""

    try:
        return getattr(value, name)
    except Exception:
        return _MISSING

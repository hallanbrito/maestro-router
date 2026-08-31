"""Provider-neutral contracts for executing one already-selected route.

This module deliberately knows nothing about HTTP or any provider SDK.  It is
the boundary that every concrete adapter must implement so the routing core can
execute a route without becoming coupled to OpenAI or another provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


def _require_non_blank(value: str, field_name: str) -> None:
    """Reject values that are not strings or contain only whitespace."""

    if not isinstance(value, str) or not any(
        not character.isspace() for character in value
    ):
        raise ValueError(f"{field_name} must be a non-blank string.")


@dataclass(frozen=True, slots=True)
class TextExecutionRequest:
    """Minimal text request passed from the public API to an adapter."""

    task: str
    context: str | None = None

    def __post_init__(self) -> None:
        """Validate the request while preserving the immutable dataclass."""

        _require_non_blank(self.task, "task")
        if self.context is not None:
            _require_non_blank(self.context, "context")


@dataclass(frozen=True, slots=True)
class ExecutionRoute:
    """Provider-facing identity of the route selected by the router."""

    id: str
    provider: str
    model: str

    def __post_init__(self) -> None:
        """Require every part of the selected route identity to be explicit."""

        _require_non_blank(self.id, "route id")
        _require_non_blank(self.provider, "provider")
        _require_non_blank(self.model, "model")


# ``available`` is complete, ``uncertain`` is partial, and ``unavailable``
# carries no usable quantities.  These meanings are enforced below.
UsageStatus = Literal["available", "uncertain", "unavailable"]


@dataclass(frozen=True, slots=True)
class NormalizedUsageItem:
    """One provider-neutral usage quantity, such as consumed input tokens."""

    unit: str
    quantity: int

    def __post_init__(self) -> None:
        """Accept only a named unit and a non-negative integer quantity."""

        _require_non_blank(self.unit, "usage unit")
        if type(self.quantity) is not int or self.quantity < 0:
            raise ValueError("usage quantity must be a non-negative integer.")


@dataclass(frozen=True, slots=True)
class NormalizedUsage:
    """Usage facts normalized independently of a provider response shape.

    ``available`` requires items and no reason, ``uncertain`` requires partial
    items plus a reason, and ``unavailable`` requires only a reason.  Keeping
    those states explicit prevents missing provider data from looking like a
    trustworthy zero.
    """

    status: UsageStatus
    items: tuple[NormalizedUsageItem, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        """Enforce the invariants attached to each normalized usage state."""

        if self.status not in ("available", "uncertain", "unavailable"):
            raise ValueError("usage status is invalid.")
        if not isinstance(self.items, tuple) or any(
            not isinstance(item, NormalizedUsageItem) for item in self.items
        ):
            raise ValueError("usage items must be normalized usage items.")
        units = tuple(item.unit for item in self.items)
        if len(set(units)) != len(units):
            raise ValueError("usage units must be unique.")
        if self.status in ("available", "uncertain") and not self.items:
            raise ValueError("known usage must contain at least one item.")
        if self.status == "available":
            if self.reason is not None:
                raise ValueError("available usage must not contain a reason.")
            return
        if self.reason is None:
            raise ValueError("non-available usage must contain a reason.")
        _require_non_blank(self.reason, "usage reason")
        if self.status == "unavailable" and self.items:
            raise ValueError("unavailable usage must not contain items.")


# Public responses use one stable, provider-neutral explanation when an adapter
# cannot recover any supported usage quantity.
USAGE_UNAVAILABLE_REASON = "A execução não forneceu uso normalizável."


USAGE_NOT_PROVIDED = NormalizedUsage(
    status="unavailable",
    reason=USAGE_UNAVAILABLE_REASON,
)


@dataclass(frozen=True, slots=True)
class TextExecutionResult:
    """Provider-neutral text, usage, and observed model returned by an adapter."""

    content: str
    usage: NormalizedUsage = USAGE_NOT_PROVIDED
    observed_model: str | None = None

    def __post_init__(self) -> None:
        """Ensure adapters cannot return an invalid neutral result."""

        if not isinstance(self.content, str):
            raise ValueError("content must be a string.")
        if not isinstance(self.usage, NormalizedUsage):
            raise ValueError("usage must be normalized usage.")
        if self.observed_model is not None:
            _require_non_blank(self.observed_model, "observed model")
            if any(
                0xD800 <= ord(character) <= 0xDFFF
                for character in self.observed_model
            ):
                raise ValueError(
                    "observed model must be a well-formed Unicode scalar sequence."
                )


class ExecutionFailedError(RuntimeError):
    """A provider-neutral execution failure."""


class ExecutionUnavailableError(ExecutionFailedError):
    """The selected execution route was unavailable."""


class ExecutionTimeoutError(ExecutionFailedError):
    """The selected execution exceeded its applicable timeout."""


class ExecutionAdapter(Protocol):
    """Structural interface implemented by every provider adapter."""

    async def execute(
        self, request: TextExecutionRequest, route: ExecutionRoute
    ) -> TextExecutionResult:
        """Execute exactly one selected route and return normalized output."""

        ...

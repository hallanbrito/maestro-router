from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not any(
        not character.isspace() for character in value
    ):
        raise ValueError(f"{field_name} must be a non-blank string.")


@dataclass(frozen=True, slots=True)
class TextExecutionRequest:
    task: str
    context: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.task, "task")
        if self.context is not None:
            _require_non_blank(self.context, "context")


@dataclass(frozen=True, slots=True)
class ExecutionRoute:
    id: str
    provider: str
    model: str

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "route id")
        _require_non_blank(self.provider, "provider")
        _require_non_blank(self.model, "model")


UsageStatus = Literal["available", "uncertain", "unavailable"]


@dataclass(frozen=True, slots=True)
class NormalizedUsageItem:
    unit: str
    quantity: int

    def __post_init__(self) -> None:
        _require_non_blank(self.unit, "usage unit")
        if type(self.quantity) is not int or self.quantity < 0:
            raise ValueError("usage quantity must be a non-negative integer.")


@dataclass(frozen=True, slots=True)
class NormalizedUsage:
    status: UsageStatus
    items: tuple[NormalizedUsageItem, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
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


USAGE_UNAVAILABLE_REASON = "A execução não forneceu uso normalizável."


USAGE_NOT_PROVIDED = NormalizedUsage(
    status="unavailable",
    reason=USAGE_UNAVAILABLE_REASON,
)


@dataclass(frozen=True, slots=True)
class TextExecutionResult:
    content: str
    usage: NormalizedUsage = USAGE_NOT_PROVIDED
    observed_model: str | None = None

    def __post_init__(self) -> None:
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
    async def execute(
        self, request: TextExecutionRequest, route: ExecutionRoute
    ) -> TextExecutionResult: ...

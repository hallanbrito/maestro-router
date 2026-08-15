from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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


@dataclass(frozen=True, slots=True)
class TextExecutionResult:
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise ValueError("content must be a string.")


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

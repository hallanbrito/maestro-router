from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


DECIMAL_PATTERN = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def _is_non_blank(value: str) -> bool:
    return any(not character.isspace() for character in value)


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class MoneyLimit(ClosedModel):
    amount: str
    currency: str

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: str) -> str:
        if not DECIMAL_PATTERN.fullmatch(value):
            raise ValueError("O valor deve ser uma string decimal não negativa.")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        if not CURRENCY_PATTERN.fullmatch(value):
            raise ValueError("A moeda deve usar exatamente três letras ASCII maiúsculas.")
        return value


class RequestConstraints(ClosedModel):
    required_capabilities: list[str] | None = None
    required_quality_criteria: list[str] | None = None
    allowed_route_ids: list[str] | None = None
    max_estimated_cost: MoneyLimit | None = None

    @field_validator(
        "required_capabilities",
        "required_quality_criteria",
        "allowed_route_ids",
    )
    @classmethod
    def validate_identifier_list(
        cls, value: list[str] | None
    ) -> list[str]:
        if value is None:
            raise ValueError("O campo não aceita null; omita-o quando não houver valor.")
        if not value:
            raise ValueError("O array deve conter ao menos um identificador.")
        if any(not _is_non_blank(identifier) for identifier in value):
            raise ValueError("Os identificadores não podem ser vazios ou somente espaços.")
        if len(set(value)) != len(value):
            raise ValueError("O array não pode conter identificadores duplicados.")
        return value

    @field_validator("max_estimated_cost", mode="before")
    @classmethod
    def reject_null_money(cls, value: object) -> object:
        if value is None:
            raise ValueError("O campo não aceita null; omita-o quando não houver valor.")
        return value


class ExecutionRequest(ClosedModel):
    task: str
    context: str | None = None
    constraints: RequestConstraints | None = None

    @field_validator("task")
    @classmethod
    def validate_task(cls, value: str) -> str:
        if not _is_non_blank(value):
            raise ValueError("O campo deve conter ao menos um caractere não branco.")
        return value

    @field_validator("context")
    @classmethod
    def validate_context(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("O campo não aceita null; omita-o quando não houver valor.")
        if not _is_non_blank(value):
            raise ValueError("O campo deve conter ao menos um caractere não branco.")
        return value

    @field_validator("constraints", mode="before")
    @classmethod
    def reject_null_constraints(cls, value: object) -> object:
        if value is None:
            raise ValueError("O campo não aceita null; omita-o quando não houver valor.")
        return value


ConstraintSource = Literal["request", "configuration"]
ConstraintCategory = Literal[
    "route", "capability", "quality", "availability", "preference", "economics"
]
FactorCategory = Literal[
    "route",
    "capability",
    "quality",
    "availability",
    "preference",
    "economics",
    "configuration",
    "strategy",
    "tie_breaker",
]


class AppliedConstraint(ClosedModel):
    source: ConstraintSource
    category: ConstraintCategory
    description: str


class DecisionFactor(ClosedModel):
    category: FactorCategory
    description: str
    references: list[str] | None = None


class Strategy(ClosedModel):
    id: Literal["lowest-estimated-cost"] = "lowest-estimated-cost"
    applied: Literal[False] = False


class RefusedDecision(ClosedModel):
    outcome: Literal["refused"] = "refused"
    strategy: Strategy
    applied_constraints: list[AppliedConstraint]
    reason: str
    factors: list[DecisionFactor]


class PublicError(ClosedModel):
    code: Literal[
        "NO_ELIGIBLE_ROUTE", "INSUFFICIENT_ECONOMIC_INFORMATION"
    ]
    message: str


class RefusalResponse(ClosedModel):
    error: PublicError
    decision: RefusedDecision


class ErrorIssue(ClosedModel):
    path: str | None = None
    message: str


class InvalidRequestError(ClosedModel):
    code: Literal["INVALID_REQUEST"] = "INVALID_REQUEST"
    message: str = "A solicitação é inválida."
    issues: list[ErrorIssue]


class InvalidRequestResponse(ClosedModel):
    error: InvalidRequestError

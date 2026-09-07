"""Strict Pydantic models for the public ``POST /v1/executions`` contract.

The models in this module describe only API-facing JSON.  Internal routing and
execution dataclasses live in their own modules and are projected into these
closed schemas at the HTTP boundary.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


DECIMAL_PATTERN = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def _is_non_blank(value: str) -> bool:
    """Return whether a validated string contains a non-whitespace character."""

    return any(not character.isspace() for character in value)


class ClosedModel(BaseModel):
    """Base model that rejects coercion and undeclared JSON members."""

    model_config = ConfigDict(extra="forbid", strict=True)


class MoneyLimit(ClosedModel):
    """Exact non-negative amount and ISO-like uppercase currency constraint."""

    amount: str
    currency: str

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: str) -> str:
        """Require the normative non-negative decimal string grammar."""

        if not DECIMAL_PATTERN.fullmatch(value):
            raise ValueError("O valor deve ser uma string decimal não negativa.")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        """Require exactly three uppercase ASCII letters for a currency."""

        if not CURRENCY_PATTERN.fullmatch(value):
            raise ValueError("A moeda deve usar exatamente três letras ASCII maiúsculas.")
        return value


class RequestConstraints(ClosedModel):
    """Optional route, capability, quality, and economic request constraints."""

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
        """Reject null, empty, blank, or duplicate identifier arrays."""

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
        """Distinguish an omitted cost limit from an explicitly null one."""

        if value is None:
            raise ValueError("O campo não aceita null; omita-o quando não houver valor.")
        return value


class ExecutionRequest(ClosedModel):
    """Validated public request accepted by the synchronous MVP endpoint."""

    task: str
    context: str | None = None
    constraints: RequestConstraints | None = None

    @field_validator("task")
    @classmethod
    def validate_task(cls, value: str) -> str:
        """Require a task containing at least one non-whitespace character."""

        if not _is_non_blank(value):
            raise ValueError("O campo deve conter ao menos um caractere não branco.")
        return value

    @field_validator("context")
    @classmethod
    def validate_context(cls, value: str | None) -> str:
        """Allow omitted context while rejecting null or blank context."""

        if value is None:
            raise ValueError("O campo não aceita null; omita-o quando não houver valor.")
        if not _is_non_blank(value):
            raise ValueError("O campo deve conter ao menos um caractere não branco.")
        return value

    @field_validator("constraints", mode="before")
    @classmethod
    def reject_null_constraints(cls, value: object) -> object:
        """Allow omitted constraints while rejecting an explicit null object."""

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
    """Public explanation of one request or configuration constraint."""

    source: ConstraintSource
    category: ConstraintCategory
    description: str


class DecisionFactor(ClosedModel):
    """Public explanation of one fact that influenced routing."""

    category: FactorCategory
    description: str
    references: list[str] | None = None


class Strategy(ClosedModel):
    """Routing strategy metadata used when no route was selected."""

    id: Literal["lowest-estimated-cost"] = "lowest-estimated-cost"
    applied: Literal[False] = False


class RefusedDecision(ClosedModel):
    """Public decision trace for a routing refusal."""

    outcome: Literal["refused"] = "refused"
    strategy: Strategy
    applied_constraints: list[AppliedConstraint]
    reason: str
    factors: list[DecisionFactor]


class PublicError(ClosedModel):
    """Public error returned when the router cannot select a route."""

    code: Literal[
        "NO_ELIGIBLE_ROUTE", "INSUFFICIENT_ECONOMIC_INFORMATION"
    ]
    message: str


class RefusalResponse(ClosedModel):
    """Complete response shape for a routing refusal."""

    error: PublicError
    decision: RefusedDecision


class ErrorIssue(ClosedModel):
    """Sanitized validation or configuration issue exposed to the caller."""

    path: str | None = None
    message: str


class SelectedRoute(ClosedModel):
    """Public identity of the route chosen for execution."""

    id: str
    provider: str
    model: str


class SelectedStrategy(ClosedModel):
    """Routing strategy metadata for a successful selection."""

    id: Literal["lowest-estimated-cost"] = "lowest-estimated-cost"
    applied: Literal[True] = True


class SelectedPublicDecision(ClosedModel):
    """Public, explainable record of one selected route."""

    outcome: Literal["selected"] = "selected"
    route: SelectedRoute
    strategy: SelectedStrategy
    applied_constraints: list[AppliedConstraint]
    reason: str
    factors: list[DecisionFactor]


class ExecutionResult(ClosedModel):
    """Provider-neutral result returned by a successful execution."""

    content: str


class AvailableEconomicValue(ClosedModel):
    """Complete monetary fact represented with exact decimal text."""

    status: Literal["available"] = "available"
    amount: str
    currency: str
    price_reference: str
    assumptions: list[str]


class UncertainEconomicValue(AvailableEconomicValue):
    """Monetary estimate that is numeric but carries explicit uncertainty."""

    status: Literal["uncertain"] = "uncertain"
    reason: str


class UnavailableEconomicValue(ClosedModel):
    """Economic value that cannot safely expose a numeric amount."""

    status: Literal["unavailable"] = "unavailable"
    reason: str


class UsageItem(ClosedModel):
    """One provider-neutral usage unit projected into public JSON."""

    unit: str
    quantity: str

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        """Require a non-blank provider-neutral unit name."""

        if not _is_non_blank(value):
            raise ValueError("A unidade deve ser uma string não branca.")
        return value

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: str) -> str:
        """Serialize usage through the same exact decimal grammar as money."""

        if not DECIMAL_PATTERN.fullmatch(value):
            raise ValueError("A quantidade deve ser uma string decimal não negativa.")
        return value


class AvailableUsage(ClosedModel):
    """Complete normalized usage containing one or more unique units."""

    status: Literal["available"] = "available"
    items: list[UsageItem]

    @model_validator(mode="after")
    def validate_items(self) -> AvailableUsage:
        """Require known usage items and prevent duplicate units."""

        if not self.items:
            raise ValueError("O uso conhecido deve conter ao menos um item.")
        units = [item.unit for item in self.items]
        if len(set(units)) != len(units):
            raise ValueError("As unidades de uso não podem se repetir.")
        return self


class UncertainUsage(AvailableUsage):
    """Partial normalized usage with a public explanation."""

    status: Literal["uncertain"] = "uncertain"
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        """Require an explanation for partial usage."""

        if not _is_non_blank(value):
            raise ValueError("A razão deve ser uma string não branca.")
        return value


class UnavailableUsage(ClosedModel):
    """Usage state used when no supported quantity is trustworthy."""

    status: Literal["unavailable"] = "unavailable"
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        """Require an explanation for unavailable usage."""

        if not _is_non_blank(value):
            raise ValueError("A razão deve ser uma string não branca.")
        return value


class ExecutionEconomics(ClosedModel):
    """Estimate, observed usage, and calculated-cost views for one execution."""

    estimate: (
        AvailableEconomicValue
        | UncertainEconomicValue
        | UnavailableEconomicValue
    )
    usage: AvailableUsage | UncertainUsage | UnavailableUsage
    calculated_cost: (
        AvailableEconomicValue
        | UncertainEconomicValue
        | UnavailableEconomicValue
    )


class ExecutionSuccessResponse(ClosedModel):
    """Public response returned after a successful provider execution."""

    result: ExecutionResult
    decision: SelectedPublicDecision
    economics: ExecutionEconomics


class ExecutionPublicError(ClosedModel):
    """Sanitized provider-neutral execution failure."""

    code: Literal[
        "EXECUTION_FAILED", "EXECUTION_UNAVAILABLE", "EXECUTION_TIMEOUT"
    ]
    message: str


class ExecutionErrorResponse(ClosedModel):
    """Execution failure plus the selection and economic facts already known."""

    error: ExecutionPublicError
    decision: SelectedPublicDecision
    economics: ExecutionEconomics


class InternalPublicError(ClosedModel):
    """Sanitized server-side configuration or decision error."""

    code: Literal["INVALID_CONFIGURATION", "INVALID_DECISION"]
    message: str
    issues: list[ErrorIssue]


class InternalErrorResponse(ClosedModel):
    """Public envelope for an internal Maestro error."""

    error: InternalPublicError


class InvalidRequestError(ClosedModel):
    """Stable public error for malformed or contract-invalid requests."""

    code: Literal["INVALID_REQUEST"] = "INVALID_REQUEST"
    message: str = "A solicitação é inválida."
    issues: list[ErrorIssue]


class InvalidRequestResponse(ClosedModel):
    """Public envelope for request-validation issues."""

    error: InvalidRequestError

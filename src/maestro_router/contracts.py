"""Modelos Pydantic estritos do contrato público ``POST /v1/executions``.

Os modelos deste módulo descrevem somente o JSON exposto pela API. As classes
internas de roteamento e execução ficam em seus próprios módulos e são
projetadas nestes esquemas fechados apenas na fronteira HTTP.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


DECIMAL_PATTERN = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def _is_non_blank(value: str) -> bool:
    """Informa se a string validada contém algum caractere não branco."""

    return any(not character.isspace() for character in value)


class ClosedModel(BaseModel):
    """Modelo-base que rejeita coerção e membros JSON não declarados."""

    model_config = ConfigDict(extra="forbid", strict=True)


class MoneyLimit(ClosedModel):
    """Limite com valor exato não negativo e moeda maiúscula semelhante à ISO."""

    amount: str
    currency: str

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: str) -> str:
        """Exige a gramática normativa de string decimal não negativa."""

        if not DECIMAL_PATTERN.fullmatch(value):
            raise ValueError("O valor deve ser uma string decimal não negativa.")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        """Exige exatamente três letras ASCII maiúsculas para a moeda."""

        if not CURRENCY_PATTERN.fullmatch(value):
            raise ValueError("A moeda deve usar exatamente três letras ASCII maiúsculas.")
        return value


class RequestConstraints(ClosedModel):
    """Restrições opcionais de rota, capacidade, qualidade e economia."""

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
        """Rejeita arrays nulos, vazios ou com identificadores brancos ou repetidos."""

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
        """Distingue limite de custo omitido de um limite explicitamente nulo."""

        if value is None:
            raise ValueError("O campo não aceita null; omita-o quando não houver valor.")
        return value


class ExecutionRequest(ClosedModel):
    """Solicitação pública validada aceita pelo endpoint síncrono do MVP."""

    task: str
    context: str | None = None
    constraints: RequestConstraints | None = None

    @field_validator("task")
    @classmethod
    def validate_task(cls, value: str) -> str:
        """Exige uma tarefa com pelo menos um caractere não branco."""

        if not _is_non_blank(value):
            raise ValueError("O campo deve conter ao menos um caractere não branco.")
        return value

    @field_validator("context")
    @classmethod
    def validate_context(cls, value: str | None) -> str:
        """Permite contexto omitido, mas rejeita contexto nulo ou em branco."""

        if value is None:
            raise ValueError("O campo não aceita null; omita-o quando não houver valor.")
        if not _is_non_blank(value):
            raise ValueError("O campo deve conter ao menos um caractere não branco.")
        return value

    @field_validator("constraints", mode="before")
    @classmethod
    def reject_null_constraints(cls, value: object) -> object:
        """Permite restrições omitidas, mas rejeita um objeto explicitamente nulo."""

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
    """Explicação pública de uma restrição da requisição ou configuração."""

    source: ConstraintSource
    category: ConstraintCategory
    description: str


class DecisionFactor(ClosedModel):
    """Explicação pública de um fato que influenciou o roteamento."""

    category: FactorCategory
    description: str
    references: list[str] | None = None


class Strategy(ClosedModel):
    """Metadados da estratégia usados quando nenhuma rota foi selecionada."""

    id: Literal["lowest-estimated-cost"] = "lowest-estimated-cost"
    applied: Literal[False] = False


class RefusedDecision(ClosedModel):
    """Rastro público da decisão que recusou o roteamento."""

    outcome: Literal["refused"] = "refused"
    strategy: Strategy
    applied_constraints: list[AppliedConstraint]
    reason: str
    factors: list[DecisionFactor]


class PublicError(ClosedModel):
    """Erro público retornado quando o roteador não consegue selecionar uma rota."""

    code: Literal[
        "NO_ELIGIBLE_ROUTE", "INSUFFICIENT_ECONOMIC_INFORMATION"
    ]
    message: str


class RefusalResponse(ClosedModel):
    """Formato completo da resposta de recusa do roteamento."""

    error: PublicError
    decision: RefusedDecision


class ErrorIssue(ClosedModel):
    """Problema sanitizado de validação ou configuração exposto ao cliente."""

    path: str | None = None
    message: str


class SelectedRoute(ClosedModel):
    """Identidade pública da rota escolhida para execução."""

    id: str
    provider: str
    model: str


class SelectedStrategy(ClosedModel):
    """Metadados da estratégia de uma seleção bem-sucedida."""

    id: Literal["lowest-estimated-cost"] = "lowest-estimated-cost"
    applied: Literal[True] = True


class SelectedPublicDecision(ClosedModel):
    """Registro público e explicável de uma rota selecionada."""

    outcome: Literal["selected"] = "selected"
    route: SelectedRoute
    strategy: SelectedStrategy
    applied_constraints: list[AppliedConstraint]
    reason: str
    factors: list[DecisionFactor]


class ExecutionResult(ClosedModel):
    """Resultado neutro de provedor retornado após uma execução bem-sucedida."""

    content: str


class AvailableEconomicValue(ClosedModel):
    """Fato monetário completo representado por texto decimal exato."""

    status: Literal["available"] = "available"
    amount: str
    currency: str
    price_reference: str
    assumptions: list[str]


class UncertainEconomicValue(AvailableEconomicValue):
    """Estimativa monetária numérica que carrega incerteza explícita."""

    status: Literal["uncertain"] = "uncertain"
    reason: str


class UnavailableEconomicValue(ClosedModel):
    """Valor econômico que não pode expor uma quantia numérica com segurança."""

    status: Literal["unavailable"] = "unavailable"
    reason: str


class UsageItem(ClosedModel):
    """Uma unidade de uso neutra de provedor projetada no JSON público."""

    unit: str
    quantity: str

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        """Exige um nome não branco para a unidade neutra de provedor."""

        if not _is_non_blank(value):
            raise ValueError("A unidade deve ser uma string não branca.")
        return value

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: str) -> str:
        """Serializa uso com a mesma gramática decimal exata usada para dinheiro."""

        if not DECIMAL_PATTERN.fullmatch(value):
            raise ValueError("A quantidade deve ser uma string decimal não negativa.")
        return value


class AvailableUsage(ClosedModel):
    """Uso normalizado completo com uma ou mais unidades únicas."""

    status: Literal["available"] = "available"
    items: list[UsageItem]

    @model_validator(mode="after")
    def validate_items(self) -> AvailableUsage:
        """Exige itens de uso conhecidos e impede unidades repetidas."""

        if not self.items:
            raise ValueError("O uso conhecido deve conter ao menos um item.")
        units = [item.unit for item in self.items]
        if len(set(units)) != len(units):
            raise ValueError("As unidades de uso não podem se repetir.")
        return self


class UncertainUsage(AvailableUsage):
    """Uso normalizado parcial acompanhado de explicação pública."""

    status: Literal["uncertain"] = "uncertain"
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        """Exige uma explicação para o uso parcial."""

        if not _is_non_blank(value):
            raise ValueError("A razão deve ser uma string não branca.")
        return value


class UnavailableUsage(ClosedModel):
    """Estado usado quando nenhuma quantidade suportada é confiável."""

    status: Literal["unavailable"] = "unavailable"
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        """Exige uma explicação para o uso indisponível."""

        if not _is_non_blank(value):
            raise ValueError("A razão deve ser uma string não branca.")
        return value


class ExecutionEconomics(ClosedModel):
    """Visões de estimativa, uso observado e custo calculado de uma execução."""

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
    """Resposta pública retornada após uma execução bem-sucedida no provedor."""

    result: ExecutionResult
    decision: SelectedPublicDecision
    economics: ExecutionEconomics


class ExecutionPublicError(ClosedModel):
    """Falha de execução sanitizada e neutra de provedor."""

    code: Literal[
        "EXECUTION_FAILED", "EXECUTION_UNAVAILABLE", "EXECUTION_TIMEOUT"
    ]
    message: str


class ExecutionErrorResponse(ClosedModel):
    """Falha de execução acompanhada da seleção e dos fatos econômicos conhecidos."""

    error: ExecutionPublicError
    decision: SelectedPublicDecision
    economics: ExecutionEconomics


class InternalPublicError(ClosedModel):
    """Erro sanitizado de configuração ou decisão ocorrido no servidor."""

    code: Literal["INVALID_CONFIGURATION", "INVALID_DECISION"]
    message: str
    issues: list[ErrorIssue]


class InternalErrorResponse(ClosedModel):
    """Envelope público de um erro interno do Maestro."""

    error: InternalPublicError


class InvalidRequestError(ClosedModel):
    """Erro público estável para requisições malformadas ou fora do contrato."""

    code: Literal["INVALID_REQUEST"] = "INVALID_REQUEST"
    message: str = "A solicitação é inválida."
    issues: list[ErrorIssue]


class InvalidRequestResponse(ClosedModel):
    """Envelope público dos problemas de validação da requisição."""

    error: InvalidRequestError

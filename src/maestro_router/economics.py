from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, DecimalException, Inexact, Rounded, localcontext
from typing import TYPE_CHECKING, Literal

from .contracts import CURRENCY_PATTERN, DECIMAL_PATTERN
from .execution import NormalizedUsage

if TYPE_CHECKING:
    from .routing import EconomicEstimate


def _require_non_blank(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not any(
        not character.isspace() for character in value
    ):
        raise ValueError(f"{field_name} must be a non-blank string.")


def _is_power_of_ten(value: int) -> bool:
    if value < 1:
        return False
    while value > 1 and value % 10 == 0:
        value //= 10
    return value == 1


@dataclass(frozen=True, slots=True)
class UnitPrice:
    """One provider-neutral rate for an independent billable unit."""

    unit: str
    rate: str
    base: int

    def __post_init__(self) -> None:
        _require_non_blank(self.unit, "price unit")
        if not isinstance(self.rate, str) or not DECIMAL_PATTERN.fullmatch(
            self.rate
        ):
            raise ValueError("price rate must be a non-negative decimal string.")
        if type(self.base) is not int or not _is_power_of_ten(self.base):
            raise ValueError(
                "price base must be a positive integer power of ten."
            )


@dataclass(frozen=True, slots=True)
class PriceReference:
    """Validated economic facts frozen with an execution route snapshot."""

    id: str
    route_id: str
    provider: str
    model: str
    currency: str
    version: str
    source: str
    rates: tuple[UnitPrice, ...]
    conditions: tuple[str, ...]
    context_complete: bool
    units_exhaustive: bool
    no_double_counting: bool
    model_identity_exact: bool

    def __post_init__(self) -> None:
        for field_name, value in (
            ("price reference id", self.id),
            ("price route id", self.route_id),
            ("price provider", self.provider),
            ("price model", self.model),
            ("price version", self.version),
            ("price source", self.source),
        ):
            _require_non_blank(value, field_name)
        if not isinstance(self.currency, str) or not CURRENCY_PATTERN.fullmatch(
            self.currency
        ):
            raise ValueError(
                "price currency must contain three uppercase ASCII letters."
            )
        if not isinstance(self.rates, tuple) or not self.rates or any(
            not isinstance(rate, UnitPrice) for rate in self.rates
        ):
            raise ValueError("price rates must be a non-empty immutable tuple.")
        units = tuple(rate.unit for rate in self.rates)
        if len(set(units)) != len(units):
            raise ValueError("price units must be unique.")
        if not isinstance(self.conditions, tuple) or any(
            not isinstance(condition, str)
            or not any(not character.isspace() for character in condition)
            for condition in self.conditions
        ):
            raise ValueError("price conditions must be non-blank strings.")
        if len(set(self.conditions)) != len(self.conditions):
            raise ValueError("price conditions must be unique.")
        for field_name, value in (
            ("context_complete", self.context_complete),
            ("units_exhaustive", self.units_exhaustive),
            ("no_double_counting", self.no_double_counting),
            ("model_identity_exact", self.model_identity_exact),
        ):
            if type(value) is not bool:
                raise ValueError(f"{field_name} must be an explicit boolean.")

        object.__setattr__(
            self, "rates", tuple(sorted(self.rates, key=lambda rate: rate.unit))
        )
        object.__setattr__(self, "conditions", tuple(sorted(self.conditions)))


CostStatus = Literal["available", "unavailable"]
_SUPPORTED_COST_UNITS = frozenset({"input_token", "output_token"})
_UNSUPPORTED_COST_UNIT_REASON = (
    "A primeira política não cobre todas as unidades observadas ou tarifadas."
)


@dataclass(frozen=True, slots=True)
class PostExecutionCost:
    status: CostStatus
    amount: str | None = None
    currency: str | None = None
    price_reference: str | None = None
    assumptions: tuple[str, ...] | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status == "available":
            if (
                self.amount is None
                or self.currency is None
                or self.price_reference is None
                or self.assumptions is None
            ):
                raise ValueError("available cost requires complete monetary facts.")
            if not DECIMAL_PATTERN.fullmatch(self.amount):
                raise ValueError("available cost must be an exact decimal string.")
            if not CURRENCY_PATTERN.fullmatch(self.currency):
                raise ValueError("available cost must use a valid currency.")
            _require_non_blank(self.price_reference, "cost price reference")
            if self.reason is not None:
                raise ValueError("available cost must not contain a reason.")
            return
        if self.status != "unavailable":
            raise ValueError("post-execution cost status is invalid.")
        if any(
            value is not None
            for value in (
                self.amount,
                self.currency,
                self.price_reference,
                self.assumptions,
            )
        ):
            raise ValueError("unavailable cost must not contain monetary facts.")
        _require_non_blank(self.reason, "cost unavailability reason")


def _unavailable(reason: str) -> PostExecutionCost:
    return PostExecutionCost(status="unavailable", reason=reason)


def calculate_pre_execution_amount(
    *,
    quantities: Mapping[str, int],
    reference: PriceReference,
) -> str:
    """Calculate an exact amount from a complete configured usage forecast."""

    if set(quantities) != _SUPPORTED_COST_UNITS or any(
        type(quantity) is not int or quantity <= 0
        for quantity in quantities.values()
    ):
        raise ValueError(
            "pre-execution quantities must contain the two supported units"
        )
    if {rate.unit for rate in reference.rates} != _SUPPORTED_COST_UNITS:
        raise ValueError("price reference does not cover the supported units")
    if not all(
        (
            reference.context_complete,
            reference.units_exhaustive,
            reference.no_double_counting,
            reference.model_identity_exact,
        )
    ):
        raise ValueError("price reference is not complete")

    try:
        amount = _calculate_exact_amount(reference, quantities)
    except (DecimalException, ArithmeticError, ValueError, KeyError):
        raise ValueError(
            "pre-execution amount cannot be represented exactly"
        ) from None
    if not DECIMAL_PATTERN.fullmatch(amount):
        raise ValueError(
            "pre-execution amount does not match the public decimal grammar"
        )
    return amount


def calculate_post_execution_cost(
    *,
    route_id: str,
    provider: str,
    model: str | None = None,
    configured_model: str | None = None,
    observed_model: str | None = None,
    estimate: EconomicEstimate,
    usage: NormalizedUsage | None,
    reference: PriceReference | None,
) -> PostExecutionCost:
    """Apply the first conservative post-execution cost policy."""

    # ``model`` keeps the original internal call form meaningful: callers that
    # provide one identity are asserting it as both configured and observed.
    if configured_model is None:
        configured_model = model
    if observed_model is None and model is not None:
        observed_model = model

    if usage is None or usage.status != "available":
        return _unavailable(
            "O uso completo necessário para calcular o custo não está disponível."
        )
    if reference is None:
        return _unavailable(
            "Não há referência de preço configurada para calcular o custo posterior."
        )
    if not reference.context_complete:
        return _unavailable("O contexto tarifário configurado está incompleto.")
    if not reference.units_exhaustive:
        return _unavailable(
            "A referência não comprova que as unidades tarifáveis são exaustivas."
        )
    if not reference.no_double_counting:
        return _unavailable(
            "A referência não comprova ausência de dupla contagem tarifária."
        )
    if not reference.model_identity_exact:
        return _unavailable(
            "A identidade tarifária exata do modelo não foi comprovada."
        )
    if configured_model is None or observed_model is None:
        return _unavailable(
            "A identidade do modelo usado na execução não pôde ser comprovada."
        )
    if observed_model != configured_model:
        return _unavailable(
            "O modelo observado não corresponde ao modelo configurado na rota."
        )
    if (
        reference.route_id != route_id
        or reference.provider != provider
        or reference.model != configured_model
    ):
        return _unavailable(
            "A referência de preço não corresponde exatamente à rota executada."
        )
    if estimate.status in ("available", "uncertain") and (
        estimate.currency != reference.currency
        or estimate.price_reference != reference.id
    ):
        return _unavailable(
            "A referência posterior não corresponde à estimativa registrada."
        )

    usage_by_unit = {item.unit: item.quantity for item in usage.items}
    rates_by_unit = {rate.unit: rate for rate in reference.rates}
    if (
        not usage_by_unit.keys() <= _SUPPORTED_COST_UNITS
        or not rates_by_unit.keys() <= _SUPPORTED_COST_UNITS
    ):
        return _unavailable(_UNSUPPORTED_COST_UNIT_REASON)
    missing_units = rates_by_unit.keys() - usage_by_unit.keys()
    if missing_units:
        return _unavailable(
            "O uso não contém todas as unidades tarifáveis exigidas."
        )
    additional_units = usage_by_unit.keys() - rates_by_unit.keys()
    if additional_units:
        return _unavailable(
            "O uso contém unidade material não coberta pela referência de preço."
        )

    try:
        amount = _calculate_exact_amount(reference, usage_by_unit)
    except (DecimalException, ArithmeticError, ValueError, KeyError):
        return _unavailable(
            "O custo não pode ser representado exatamente pela política aprovada."
        )

    if not DECIMAL_PATTERN.fullmatch(amount):
        return _unavailable(
            "O custo não pode ser representado exatamente pela gramática pública."
        )
    return PostExecutionCost(
        status="available",
        amount=amount,
        currency=reference.currency,
        price_reference=reference.id,
        assumptions=(),
    )


def _required_precision(
    reference: PriceReference, quantities: Mapping[str, int]
) -> int:
    scales = [
        _fractional_digits(rate.rate) + len(str(rate.base)) - 1
        for rate in reference.rates
    ]
    maximum_scale = max(scales)
    aligned_digits = []
    for rate, scale in zip(reference.rates, scales, strict=True):
        coefficient_digits = len(rate.rate.replace(".", "").lstrip("0")) or 1
        quantity_digits = len(str(quantities[rate.unit]))
        aligned_digits.append(
            coefficient_digits
            + quantity_digits
            + maximum_scale
            - scale
        )
    return max(aligned_digits) + len(str(len(reference.rates))) + 4


def _calculate_exact_amount(
    reference: PriceReference,
    quantities: Mapping[str, int],
) -> str:
    with localcontext() as context:
        context.prec = _required_precision(reference, quantities)
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        total = Decimal(0)
        for rate in reference.rates:
            total += (
                Decimal(quantities[rate.unit])
                * Decimal(rate.rate)
                / Decimal(rate.base)
            )
    return _plain_decimal(total)


def _fractional_digits(value: str) -> int:
    separator = value.find(".")
    return 0 if separator < 0 else len(value) - separator - 1


def _plain_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"

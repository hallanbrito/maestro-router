from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Literal

from .contracts import (
    AppliedConstraint,
    CURRENCY_PATTERN,
    DECIMAL_PATTERN,
    DecisionFactor,
    ExecutionRequest,
    FactorCategory,
    PublicError,
    RefusalResponse,
    RefusedDecision,
    Strategy,
)


EstimateStatus = Literal["available", "uncertain", "unavailable"]


@dataclass(frozen=True, slots=True)
class EconomicEstimate:
    """Provider-neutral estimate produced before route selection."""

    status: EstimateStatus
    amount: str | None = None
    currency: str | None = None
    price_reference: str | None = None
    assumptions: tuple[str, ...] | None = None
    reason: str | None = None
    comparable: bool = True
    non_comparability_reason: str | None = None

    def __post_init__(self) -> None:
        valued_fields = (self.amount, self.currency, self.price_reference)
        if self.status in {"available", "uncertain"}:
            if any(value is None for value in valued_fields) or self.assumptions is None:
                raise ValueError(
                    f"{self.status} estimates require amount, currency, "
                    "price_reference, and assumptions."
                )
            assert self.amount is not None
            assert self.currency is not None
            assert self.price_reference is not None
            if not DECIMAL_PATTERN.fullmatch(self.amount):
                raise ValueError("Estimate amounts must be non-negative decimals.")
            if not CURRENCY_PATTERN.fullmatch(self.currency):
                raise ValueError("Estimate currencies must be three uppercase letters.")
            if not _non_blank(self.price_reference):
                raise ValueError("Estimate price references must be non-blank.")
            if any(not _non_blank(item) for item in self.assumptions):
                raise ValueError("Estimate assumptions must be non-blank.")
            if self.status == "available" and self.reason is not None:
                raise ValueError("Available estimates do not have a reason.")
            if self.status == "uncertain" and not _non_blank(self.reason):
                raise ValueError("Uncertain estimates require a reason.")
        elif self.status != "unavailable":
            raise ValueError(f"Unknown estimate status: {self.status}.")
        else:
            if any(value is not None for value in valued_fields):
                raise ValueError("Unavailable estimates do not have monetary values.")
            if self.assumptions is not None:
                raise ValueError("Unavailable estimates do not have assumptions.")
            if not _non_blank(self.reason):
                raise ValueError("Unavailable estimates require a reason.")

        if self.status != "available" and (
            not self.comparable or self.non_comparability_reason is not None
        ):
            raise ValueError(
                "Comparability metadata applies only to available estimates."
            )
        if self.comparable and self.non_comparability_reason is not None:
            raise ValueError("Comparable estimates do not have a comparability reason.")
        if not self.comparable and not _non_blank(self.non_comparability_reason):
            raise ValueError("Non-comparable estimates require a reason.")

    def decimal_amount(self) -> Decimal:
        if self.amount is None:
            raise ValueError("This estimate has no amount.")
        return Decimal(self.amount)


def _default_estimate() -> EconomicEstimate:
    return EconomicEstimate(
        status="unavailable",
        reason="Não há estimativa econômica disponível para a rota.",
    )


def _non_blank(value: str | None) -> bool:
    return value is not None and any(not character.isspace() for character in value)


@dataclass(frozen=True, slots=True)
class Route:
    id: str
    provider: str
    model: str
    adapter_id: str
    enabled: bool = True
    capabilities: frozenset[str] = field(default_factory=frozenset)
    quality_criteria: frozenset[str] = field(default_factory=frozenset)
    known_unavailable: bool = False
    estimate: EconomicEstimate = field(default_factory=_default_estimate)

    def __post_init__(self) -> None:
        for field_name, value in (
            ("Route IDs", self.id),
            ("Provider IDs", self.provider),
            ("Model IDs", self.model),
            ("Adapter IDs", self.adapter_id),
        ):
            if not _non_blank(value):
                raise ValueError(
                    f"{field_name} must contain a non-whitespace character."
                )
        if any(0xD800 <= ord(character) <= 0xDFFF for character in self.id):
            raise ValueError("Route IDs must be well-formed Unicode scalar sequences.")


class RouteCatalog:
    """In-memory route snapshot used by the routing decision.

    This slice classifies only the execution-adapter association as a minimal
    local-validity concern. Other ``invalid_route`` and
    ``INVALID_CONFIGURATION`` semantics remain outside this implementation.
    """

    def __init__(self, routes: Iterable[Route] = ()) -> None:
        snapshot = tuple(routes)
        route_ids = [route.id for route in snapshot]
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("Route IDs must be unique.")
        self._routes = snapshot

    def snapshot(self) -> tuple[Route, ...]:
        return self._routes


@dataclass(frozen=True, slots=True)
class Exclusion:
    route_id: str
    reason: str
    category: FactorCategory
    description: str


@dataclass(frozen=True, slots=True)
class SelectedDecision:
    """Minimal internal representation of a validated route selection."""

    selected_routes: tuple[Route, ...]
    strategy_id: str
    strategy_applied: bool
    applied_constraints: tuple[AppliedConstraint, ...]
    reason: str
    factors: tuple[DecisionFactor, ...]
    selectable_routes: tuple[Route, ...]
    compared_routes: tuple[Route, ...]
    evaluated_estimates: tuple[tuple[str, EconomicEstimate], ...]

    @property
    def route(self) -> Route:
        if len(self.selected_routes) != 1:
            raise ValueError("A validated selection must contain exactly one route.")
        return self.selected_routes[0]


class InvalidDecisionError(ValueError):
    """Internal selection validation rejected a routing decision."""


@dataclass(frozen=True, slots=True)
class _SelectionContext:
    """Authoritative facts frozen before the routing strategy is applied."""

    candidates: tuple[Route, ...]
    evaluated_estimates: tuple[tuple[str, EconomicEstimate], ...]
    selectable_routes: tuple[Route, ...]
    comparable_routes: tuple[Route, ...]
    compared_routes: tuple[Route, ...]
    applied_constraints: tuple[AppliedConstraint, ...]
    allowed_route_ids: frozenset[str] | None
    required_capabilities: frozenset[str]
    required_quality: frozenset[str]
    max_estimated_cost: tuple[str, str] | None
    locally_invalid_route_ids: frozenset[str]


def route_request(
    request: ExecutionRequest,
    catalog: RouteCatalog,
    *,
    locally_invalid_route_ids: frozenset[str] = frozenset(),
) -> RefusalResponse | SelectedDecision:
    """Evaluate routing and return a refusal or one validated selection.

    Execution-association validity is supplied from the request snapshot and
    classified as ``invalid_route``. Other local-validity semantics remain an
    upstream precondition in this slice.
    """
    constraints = request.constraints
    allowed_route_ids = (
        frozenset(constraints.allowed_route_ids)
        if constraints and constraints.allowed_route_ids
        else None
    )
    required_capabilities = frozenset(
        constraints.required_capabilities or [] if constraints else []
    )
    required_quality = frozenset(
        constraints.required_quality_criteria or [] if constraints else []
    )

    exclusions: list[Exclusion] = []
    candidates: list[Route] = []
    for route in sorted(catalog.snapshot(), key=lambda item: item.id):
        exclusion = _first_implemented_exclusion(
            route,
            locally_invalid_route_ids,
            allowed_route_ids,
            required_capabilities,
            required_quality,
        )
        if exclusion is None:
            candidates.append(route)
        else:
            exclusions.append(exclusion)

    if not candidates:
        return _refusal(
            request=request,
            exclusions=exclusions,
            code="NO_ELIGIBLE_ROUTE",
            message=(
                "Nenhuma rota configurada, habilitada e válida satisfaz "
                "as restrições aplicáveis."
            ),
            reason="Todas as rotas foram excluídas antes da comparação econômica.",
            factors=_factors(exclusions),
        )

    return _evaluate_economics(request, candidates, exclusions)


def _evaluate_economics(
    request: ExecutionRequest,
    candidates: list[Route],
    exclusions: list[Exclusion],
) -> RefusalResponse | SelectedDecision:
    limit = request.constraints.max_estimated_cost if request.constraints else None
    if limit is None:
        if len(candidates) == 1:
            route = candidates[0]
            context = _selection_context(
                request,
                candidates,
                exclusions,
            )
            decision = SelectedDecision(
                selected_routes=(route,),
                strategy_id="lowest-estimated-cost",
                strategy_applied=True,
                applied_constraints=context.applied_constraints,
                reason=f"{route.id} foi selecionada por ser a única rota elegível.",
                factors=tuple(
                    (_factors(exclusions) if exclusions else [])
                    + [
                        DecisionFactor(
                            category="route",
                            description=(
                                f"{route.id} era a única rota elegível para a decisão."
                            ),
                        )
                    ]
                ),
                selectable_routes=context.selectable_routes,
                compared_routes=context.compared_routes,
                evaluated_estimates=context.evaluated_estimates,
            )
            return _validate_selection(context, decision)

        comparable = [
            route
            for route in candidates
            if route.estimate.status == "available" and route.estimate.comparable
        ]
        if not comparable:
            return _economic_information_refusal(
                request, exclusions, [_estimate_factor(route) for route in candidates]
            )

        currencies = {route.estimate.currency for route in comparable}
        if len(currencies) != 1:
            return _economic_information_refusal(
                request,
                exclusions,
                [_currency_factor(route) for route in comparable],
            )

        context = _selection_context(
            request,
            candidates,
            exclusions,
        )
        return _select_lowest_cost(context, exclusions)

    ceiling = Decimal(limit.amount)
    admissible: list[Route] = []
    indeterminate: list[Route] = []
    violations: list[Route] = []
    for route in candidates:
        estimate = route.estimate
        if (
            estimate.status != "available"
            or not estimate.comparable
            or estimate.currency != limit.currency
        ):
            indeterminate.append(route)
        elif estimate.decimal_amount() <= ceiling:
            admissible.append(route)
        else:
            violations.append(route)

    if admissible:
        if len(admissible) == 1:
            route = admissible[0]
            context = _selection_context(
                request,
                candidates,
                exclusions,
            )
            economic_factors = []
            for candidate in candidates:
                if candidate is route:
                    economic_factors.append(
                        _selected_estimate_factor(candidate, limit.amount)
                    )
                elif candidate in indeterminate:
                    economic_factors.append(
                        _estimate_factor(candidate, limit.currency)
                    )
                else:
                    economic_factors.append(
                        _ceiling_violation_factor(candidate, limit.amount)
                    )
            decision = SelectedDecision(
                selected_routes=(route,),
                strategy_id="lowest-estimated-cost",
                strategy_applied=True,
                applied_constraints=context.applied_constraints,
                reason=(
                    f"{route.id} foi selecionada por ser a única rota que "
                    "comprovou admissibilidade econômica."
                ),
                factors=tuple(
                    (_factors(exclusions) if exclusions else [])
                    + economic_factors
                ),
                selectable_routes=context.selectable_routes,
                compared_routes=context.compared_routes,
                evaluated_estimates=context.evaluated_estimates,
            )
            return _validate_selection(context, decision)
        context = _selection_context(
            request,
            candidates,
            exclusions,
        )
        return _select_lowest_cost(context, exclusions)
    if indeterminate:
        factors = [
            _estimate_factor(route, limit.currency)
            if route in indeterminate
            else _ceiling_violation_factor(route, limit.amount)
            for route in candidates
        ]
        return _economic_information_refusal(request, exclusions, factors)

    return _refusal(
        request=request,
        exclusions=exclusions,
        code="NO_ELIGIBLE_ROUTE",
        message=(
            "Nenhuma rota configurada, habilitada e válida satisfaz "
            "as restrições aplicáveis."
        ),
        reason="Todas as rotas restantes excederam o teto econômico aplicável.",
        factors=(
            (_factors(exclusions) if exclusions else [])
            + [_ceiling_violation_factor(route, limit.amount) for route in violations]
        ),
    )


def _selection_context(
    request: ExecutionRequest,
    candidates: list[Route],
    exclusions: list[Exclusion],
) -> _SelectionContext:
    constraints = request.constraints
    limit = constraints.max_estimated_cost if constraints else None
    ordered_candidates = tuple(sorted(candidates, key=lambda route: route.id))
    comparable_routes = [
        route
        for route in ordered_candidates
        if (
            route.estimate.status == "available"
            and route.estimate.comparable
            and (limit is None or route.estimate.currency == limit.currency)
        )
    ]
    if limit is None:
        selectable_routes = (
            list(ordered_candidates)
            if len(ordered_candidates) == 1
            else comparable_routes
        )
        compared_routes = comparable_routes if len(ordered_candidates) > 1 else []
    else:
        ceiling = Decimal(limit.amount)
        selectable_routes = [
            route
            for route in comparable_routes
            if route.estimate.decimal_amount() <= ceiling
        ]
        compared_routes = selectable_routes if len(selectable_routes) > 1 else []

    return _SelectionContext(
        candidates=ordered_candidates,
        evaluated_estimates=tuple(
            (route.id, route.estimate)
            for route in ordered_candidates
        ),
        selectable_routes=tuple(
            sorted(selectable_routes, key=lambda route: route.id)
        ),
        comparable_routes=tuple(
            sorted(comparable_routes, key=lambda route: route.id)
        ),
        compared_routes=tuple(
            sorted(
                compared_routes,
                key=lambda route: (route.estimate.decimal_amount(), route.id),
            )
        ),
        applied_constraints=tuple(
            _request_constraints(request) + _configuration_constraints(exclusions)
        ),
        allowed_route_ids=(
            frozenset(constraints.allowed_route_ids)
            if constraints and constraints.allowed_route_ids
            else None
        ),
        required_capabilities=frozenset(
            constraints.required_capabilities or [] if constraints else []
        ),
        required_quality=frozenset(
            constraints.required_quality_criteria or [] if constraints else []
        ),
        max_estimated_cost=(
            (limit.amount, limit.currency) if limit is not None else None
        ),
        locally_invalid_route_ids=frozenset(
            exclusion.route_id
            for exclusion in exclusions
            if exclusion.reason == "invalid_route"
        ),
    )


def _select_lowest_cost(
    context: _SelectionContext,
    exclusions: list[Exclusion],
) -> SelectedDecision:
    minimum = min(
        route.estimate.decimal_amount() for route in context.compared_routes
    )
    tied = [
        route
        for route in context.compared_routes
        if route.estimate.decimal_amount() == minimum
    ]
    selected = min(tied, key=lambda route: route.id)
    removed = [
        route
        for route in context.candidates
        if route not in context.selectable_routes
    ]

    factors = (_factors(exclusions) if exclusions else [])
    for route in context.candidates:
        if context.max_estimated_cost is not None and route in removed:
            ceiling, currency = context.max_estimated_cost
            if route in context.comparable_routes:
                factors.append(_ceiling_violation_factor(route, ceiling))
                continue
            factors.append(_estimate_factor(route, currency))
            continue
        factors.append(_estimate_factor(route))
    factors.append(
        DecisionFactor(
            category="strategy",
            description=(
                f"{selected.id} tinha a menor estimativa entre as rotas "
                "economicamente comparáveis."
            ),
        )
    )
    if len(tied) > 1:
        factors.append(
            DecisionFactor(
                category="tie_breaker",
                description=(
                    "Estimativas mínimas numericamente equivalentes foram "
                    "desempatadas pelo menor route.id em ordem lexicográfica "
                    f"Unicode; {selected.id} venceu."
                ),
            )
        )

    decision = SelectedDecision(
        selected_routes=(selected,),
        strategy_id="lowest-estimated-cost",
        strategy_applied=True,
        applied_constraints=context.applied_constraints,
        reason=(
            f"{selected.id} foi selecionada pela menor estimativa entre as "
            "rotas economicamente comparáveis."
        ),
        factors=tuple(factors),
        selectable_routes=context.selectable_routes,
        compared_routes=context.compared_routes,
        evaluated_estimates=context.evaluated_estimates,
    )
    return _validate_selection(context, decision)


def _validate_selection(
    context: _SelectionContext, decision: SelectedDecision
) -> SelectedDecision:
    if len(decision.selected_routes) != 1:
        raise InvalidDecisionError("Selection must contain exactly one route.")
    selected = decision.selected_routes[0]
    if selected not in context.selectable_routes:
        raise InvalidDecisionError("Selected route is outside the selectable set.")
    if decision.selectable_routes != context.selectable_routes:
        raise InvalidDecisionError(
            "Decision changed the authoritative selectable set."
        )
    if decision.compared_routes != context.compared_routes:
        raise InvalidDecisionError(
            "Decision changed the authoritative comparison set."
        )
    if decision.evaluated_estimates != context.evaluated_estimates:
        raise InvalidDecisionError(
            "Decision changed the authoritative economic evaluations."
        )
    if decision.applied_constraints != context.applied_constraints:
        raise InvalidDecisionError(
            "Decision changed the authoritative applied constraints."
        )
    if decision.strategy_id != "lowest-estimated-cost":
        raise InvalidDecisionError("Selection used an unsupported strategy.")
    if not decision.strategy_applied:
        raise InvalidDecisionError("Selection must mark the strategy as applied.")
    if (
        not _non_blank(decision.reason)
        or not decision.factors
        or any(not _non_blank(factor.description) for factor in decision.factors)
    ):
        raise InvalidDecisionError(
            "Selection requires a reason and determining factors."
        )

    if _first_implemented_exclusion(
        selected,
        context.locally_invalid_route_ids,
        context.allowed_route_ids,
        context.required_capabilities,
        context.required_quality,
    ) is not None:
        raise InvalidDecisionError(
            "Selected route violates an applicable constraint."
        )
    if context.max_estimated_cost is not None:
        ceiling, currency = context.max_estimated_cost
        estimate = selected.estimate
        if (
            estimate.status != "available"
            or not estimate.comparable
            or estimate.currency != currency
            or estimate.decimal_amount() > Decimal(ceiling)
        ):
            raise InvalidDecisionError(
                "Selected route did not prove ceiling compliance."
            )

    tie_factors = [
        factor for factor in decision.factors if factor.category == "tie_breaker"
    ]
    if context.compared_routes:
        if any(
            route.estimate.status != "available" or not route.estimate.comparable
            for route in context.compared_routes
        ):
            raise InvalidDecisionError(
                "Compared routes must have available comparable estimates."
            )
        if len({route.estimate.currency for route in context.compared_routes}) != 1:
            raise InvalidDecisionError("Compared routes must use one currency.")
        ordered = tuple(
            sorted(
                context.compared_routes,
                key=lambda route: (route.estimate.decimal_amount(), route.id),
            )
        )
        if context.compared_routes != ordered:
            raise InvalidDecisionError(
                "Compared routes are not in deterministic order."
            )
        minimum = context.compared_routes[0].estimate.decimal_amount()
        tied = [
            route
            for route in context.compared_routes
            if route.estimate.decimal_amount() == minimum
        ]
        if selected.id != min(route.id for route in tied):
            raise InvalidDecisionError(
                "Selection does not match the minimum and tie-break rule."
            )
        if len(tie_factors) != (1 if len(tied) > 1 else 0):
            raise InvalidDecisionError(
                "Tie-breaker factor does not match the comparison."
            )
    elif len(context.selectable_routes) != 1 or tie_factors:
        raise InvalidDecisionError(
            "Single-candidate selection is internally inconsistent."
        )

    return decision


def _selected_estimate_factor(route: Route, ceiling: str) -> DecisionFactor:
    estimate = route.estimate
    assert estimate.amount is not None
    assert estimate.currency is not None
    assert estimate.price_reference is not None
    return DecisionFactor(
        category="economics",
        description=(
            f"{route.id} tinha estimativa available de {estimate.currency} "
            f"{estimate.amount} ({estimate.price_reference}), dentro do teto "
            f"{estimate.currency} {ceiling}."
        ),
        references=[estimate.price_reference],
    )


def _economic_information_refusal(
    request: ExecutionRequest,
    exclusions: list[Exclusion],
    factors: list[DecisionFactor],
) -> RefusalResponse:
    all_factors = (_factors(exclusions) if exclusions else []) + factors
    return _refusal(
        request=request,
        exclusions=exclusions,
        code="INSUFFICIENT_ECONOMIC_INFORMATION",
        message="Não há informação econômica suficiente para decidir a rota.",
        reason=(
            "O custo era indispensável, mas nenhuma base econômica suficiente "
            "permitiu continuar para a seleção."
        ),
        factors=all_factors,
    )


def _refusal(
    *,
    request: ExecutionRequest,
    exclusions: list[Exclusion],
    code: Literal["NO_ELIGIBLE_ROUTE", "INSUFFICIENT_ECONOMIC_INFORMATION"],
    message: str,
    reason: str,
    factors: list[DecisionFactor],
) -> RefusalResponse:
    applied_constraints = _request_constraints(request)
    applied_constraints.extend(_configuration_constraints(exclusions))
    return RefusalResponse(
        error=PublicError(code=code, message=message),
        decision=RefusedDecision(
            strategy=Strategy(),
            applied_constraints=applied_constraints,
            reason=reason,
            factors=factors,
        ),
    )


def _estimate_factor(
    route: Route, required_currency: str | None = None
) -> DecisionFactor:
    estimate = route.estimate
    if estimate.status == "unavailable":
        return DecisionFactor(
            category="economics",
            description=(
                f"{route.id} tinha estimativa unavailable: {estimate.reason}"
            ),
        )

    if not estimate.comparable:
        assert estimate.amount is not None
        assert estimate.currency is not None
        assert estimate.price_reference is not None
        return DecisionFactor(
            category="economics",
            description=(
                f"{route.id} tinha estimativa available de {estimate.currency} "
                f"{estimate.amount} ({estimate.price_reference}), mas a base não "
                f"era comparável: {estimate.non_comparability_reason}."
            ),
            references=[estimate.price_reference],
        )

    assert estimate.amount is not None
    assert estimate.currency is not None
    assert estimate.price_reference is not None
    mismatch = (
        f"; a moeda não comprovava o teto em {required_currency}"
        if required_currency is not None and estimate.currency != required_currency
        else ""
    )
    reason = f": {estimate.reason}" if estimate.reason else ""
    return DecisionFactor(
        category="economics",
        description=(
            f"{route.id} tinha estimativa {estimate.status} de "
            f"{estimate.currency} {estimate.amount} ({estimate.price_reference})"
            f"{mismatch}{reason}."
        ),
        references=[estimate.price_reference],
    )


def _currency_factor(route: Route) -> DecisionFactor:
    estimate = route.estimate
    assert estimate.amount is not None
    assert estimate.currency is not None
    assert estimate.price_reference is not None
    return DecisionFactor(
        category="economics",
        description=(
            f"{route.id} tinha estimativa available de {estimate.currency} "
            f"{estimate.amount} ({estimate.price_reference}); moedas distintas "
            "não são comparadas."
        ),
        references=[estimate.price_reference],
    )


def _ceiling_violation_factor(route: Route, ceiling: str) -> DecisionFactor:
    estimate = route.estimate
    assert estimate.amount is not None
    assert estimate.currency is not None
    assert estimate.price_reference is not None
    return DecisionFactor(
        category="economics",
        description=(
            f"{route.id} tinha estimativa available de {estimate.currency} "
            f"{estimate.amount} ({estimate.price_reference}), acima do teto "
            f"{estimate.currency} {ceiling}."
        ),
        references=[estimate.price_reference],
    )


def _first_implemented_exclusion(
    route: Route,
    locally_invalid_route_ids: frozenset[str],
    allowed_route_ids: frozenset[str] | None,
    required_capabilities: frozenset[str],
    required_quality: frozenset[str],
) -> Exclusion | None:
    if not route.enabled:
        return Exclusion(
            route.id,
            "disabled_route",
            "route",
            f"{route.id} estava desabilitada na configuração.",
        )
    if route.id in locally_invalid_route_ids:
        return Exclusion(
            route.id,
            "invalid_route",
            "configuration",
            (
                f"{route.id} foi excluída porque sua associação de execução "
                "era inválida."
            ),
        )
    if allowed_route_ids is not None and route.id not in allowed_route_ids:
        return Exclusion(
            route.id,
            "route_not_allowed",
            "route",
            f"{route.id} não pertencia à allowlist efetiva.",
        )

    missing_capabilities = sorted(required_capabilities - route.capabilities)
    if missing_capabilities:
        return Exclusion(
            route.id,
            "incompatible_capability",
            "capability",
            f"{route.id} não declarou: {', '.join(missing_capabilities)}.",
        )

    missing_quality = sorted(required_quality - route.quality_criteria)
    if missing_quality:
        return Exclusion(
            route.id,
            "unsatisfied_quality",
            "quality",
            f"{route.id} não satisfez: {', '.join(missing_quality)}.",
        )

    if route.known_unavailable:
        return Exclusion(
            route.id,
            "known_unavailability",
            "availability",
            f"{route.id} estava conhecida como indisponível antes da decisão.",
        )
    return None


def _request_constraints(request: ExecutionRequest) -> list[AppliedConstraint]:
    constraints = request.constraints
    if constraints is None:
        return []

    applied: list[AppliedConstraint] = []
    if constraints.allowed_route_ids:
        applied.append(
            AppliedConstraint(
                source="request",
                category="route",
                description=(
                    "Somente "
                    + ", ".join(sorted(constraints.allowed_route_ids))
                    + " podiam ser consideradas."
                ),
            )
        )
    if constraints.required_capabilities:
        applied.append(
            AppliedConstraint(
                source="request",
                category="capability",
                description=(
                    "A rota precisava declarar "
                    + ", ".join(sorted(constraints.required_capabilities))
                    + "."
                ),
            )
        )
    if constraints.required_quality_criteria:
        applied.append(
            AppliedConstraint(
                source="request",
                category="quality",
                description=(
                    "A rota precisava satisfazer "
                    + ", ".join(sorted(constraints.required_quality_criteria))
                    + "."
                ),
            )
        )
    if constraints.max_estimated_cost:
        limit = constraints.max_estimated_cost
        applied.append(
            AppliedConstraint(
                source="request",
                category="economics",
                description=(
                    f"A estimativa não podia exceder {limit.currency} {limit.amount}."
                ),
            )
        )
    return applied


def _configuration_constraints(
    exclusions: list[Exclusion],
) -> list[AppliedConstraint]:
    constraints: list[AppliedConstraint] = []
    for exclusion in exclusions:
        if exclusion.reason == "disabled_route":
            constraints.append(
                AppliedConstraint(
                    source="configuration",
                    category="route",
                    description=f"{exclusion.route_id} estava desabilitada.",
                )
            )
        elif exclusion.reason == "invalid_route":
            constraints.append(
                AppliedConstraint(
                    source="configuration",
                    category="route",
                    description=(
                        f"{exclusion.route_id} possuía associação de execução "
                        "inválida."
                    ),
                )
            )
        elif exclusion.reason == "known_unavailability":
            constraints.append(
                AppliedConstraint(
                    source="configuration",
                    category="availability",
                    description=f"{exclusion.route_id} estava indisponível.",
                )
            )
    return constraints


def _factors(exclusions: list[Exclusion]) -> list[DecisionFactor]:
    if not exclusions:
        return [
            DecisionFactor(
                category="route",
                description="O catálogo não continha rotas configuradas.",
            )
        ]
    return [
        DecisionFactor(
            category=exclusion.category,
            description=exclusion.description,
        )
        for exclusion in exclusions
    ]

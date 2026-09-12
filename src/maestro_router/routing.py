"""Deterministic provider-neutral route eligibility and economic selection.

Routing is deliberately pure: it evaluates validated request constraints and an
immutable catalog snapshot, then returns either an explainable refusal or one
internally validated selection.  It never calls a provider or mutates a route.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Literal

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
from .economics import PriceReference


@dataclass(frozen=True, slots=True)
class MoneyCeiling:
    """Exact economic limit and ISO-like uppercase currency."""

    amount: str
    currency: str

    def __post_init__(self) -> None:
        """Validate decimal grammar and uppercase currency code."""
        if not DECIMAL_PATTERN.fullmatch(self.amount):
            raise ValueError("Ceiling amount must be a non-negative decimal string.")
        if not CURRENCY_PATTERN.fullmatch(self.currency):
            raise ValueError("Ceiling currency must be three uppercase letters.")

    def decimal_amount(self) -> Decimal:
        """Return the exact decimal value used in economic comparisons."""
        return Decimal(self.amount)


@dataclass(frozen=True, slots=True)
class OperationalDefaults:
    """Operational default constraints applied when omitted by the request."""

    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    required_quality_criteria: frozenset[str] = field(default_factory=frozenset)
    allowed_route_ids: frozenset[str] | None = None
    max_estimated_cost: MoneyCeiling | None = None


@dataclass(frozen=True, slots=True)
class OperationalConstraints:
    """Operator-governed global constraints, ceilings, and default values."""

    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    required_quality_criteria: frozenset[str] = field(default_factory=frozenset)
    allowed_route_ids: frozenset[str] | None = None
    max_estimated_costs: tuple[MoneyCeiling, ...] = ()
    defaults: OperationalDefaults = field(default_factory=OperationalDefaults)



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
        """Enforce monetary, uncertainty, and comparability state invariants."""

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
        """Return the exact amount used for comparison, or reject its absence."""

        if self.amount is None:
            raise ValueError("This estimate has no amount.")
        return Decimal(self.amount)


def _default_estimate() -> EconomicEstimate:
    """Create the explicit unavailable estimate used by unpriced routes."""

    return EconomicEstimate(
        status="unavailable",
        reason="Não há estimativa econômica disponível para a rota.",
    )


def _non_blank(value: str | None) -> bool:
    """Return whether optional text contains a non-whitespace character."""

    return value is not None and any(not character.isspace() for character in value)


@dataclass(frozen=True, slots=True)
class Route:
    """Immutable provider-neutral facts evaluated during route selection."""

    id: str
    provider: str
    model: str
    adapter_id: str
    enabled: bool = True
    capabilities: frozenset[str] = field(default_factory=frozenset)
    quality_criteria: frozenset[str] = field(default_factory=frozenset)
    known_unavailable: bool = False
    estimate: EconomicEstimate = field(default_factory=_default_estimate)
    price_reference: PriceReference | None = None
    quality_evidence_references: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Validate route identity and the optional neutral price reference."""

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
        if self.price_reference is not None and not isinstance(
            self.price_reference, PriceReference
        ):
            raise ValueError("Route price reference must be provider-neutral.")
        if self.quality_evidence_references:
            for crit, refs in self.quality_evidence_references.items():
                if not _non_blank(crit):
                    raise ValueError("Quality criteria must be non-blank.")
                if not refs or any(not _non_blank(r) for r in refs):
                    raise ValueError("Evidence references must be non-blank.")
            object.__setattr__(
                self,
                "quality_evidence_references",
                MappingProxyType(dict(self.quality_evidence_references)),
            )


class RouteCatalog:
    """In-memory route snapshot used by the routing decision.

    This slice contains valid and executable routes, alongside explicitly tracked
    configuration-isolated invalid route IDs necessary for routing explanations,
    and frozen operational routing constraints.
    """

    def __init__(
        self,
        routes: Iterable[Route] = (),
        *,
        configuration_invalid_route_ids: Iterable[str] = (),
        operational_constraints: OperationalConstraints | None = None,
    ) -> None:
        """Freeze executable routes, invalid route IDs, and operational constraints."""

        snapshot = tuple(routes)
        route_ids = [route.id for route in snapshot]
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("Route IDs must be unique.")
        self._routes = snapshot

        invalid_ids = tuple(configuration_invalid_route_ids)
        for val in invalid_ids:
            if not isinstance(val, str) or not any(not c.isspace() for c in val):
                raise ValueError("Configuration invalid route IDs must be non-blank strings.")
            if any(0xD800 <= ord(c) <= 0xDFFF for c in val):
                raise ValueError("Configuration invalid route IDs must not contain isolated Unicode surrogates.")

        if len(invalid_ids) != len(set(invalid_ids)):
            raise ValueError("Configuration invalid route IDs must be unique.")

        executable_ids = set(route_ids)
        if executable_ids.intersection(invalid_ids):
            raise ValueError("Configuration invalid route IDs must not overlap with executable route IDs.")

        self.configuration_invalid_route_ids = frozenset(invalid_ids)
        self.operational_constraints = (
            operational_constraints
            if operational_constraints is not None
            else OperationalConstraints()
        )

    def snapshot(self) -> tuple[Route, ...]:
        """Return the immutable route tuple used for one routing evaluation."""

        return self._routes


@dataclass(frozen=True, slots=True)
class Exclusion:
    """First applicable reason why one route cannot enter selection."""

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
        """Return the single route carried by a validated selection."""

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
    effective_ceilings: tuple[tuple[str, str], ...]
    locally_invalid_route_ids: frozenset[str]
    exclusions: tuple[Exclusion, ...]


@dataclass(frozen=True, slots=True)
class _RefusalContext:
    """Authoritative facts used to validate a routing refusal."""

    request: ExecutionRequest
    candidates: tuple[Route, ...]
    exclusions: tuple[Exclusion, ...]
    kind: Literal[
        "no_candidates", "economic_insufficiency", "ceiling_violations"
    ]
    applied_constraints: tuple[AppliedConstraint, ...] = ()
    effective_ceilings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class _ComposedConstraints:
    """Monotonically composed operational and request constraints."""

    effective_allowed_route_ids: frozenset[str] | None
    effective_required_capabilities: frozenset[str]
    effective_required_quality: frozenset[str]
    effective_ceilings: tuple[tuple[str, str], ...]
    all_applicable_ceilings: tuple[tuple[str, str], ...]
    applied_constraints: tuple[AppliedConstraint, ...]


def _compose_effective_constraints(
    request: ExecutionRequest,
    operational_constraints: OperationalConstraints,
) -> _ComposedConstraints:
    """Form effective constraints monotonically from configuration and request."""

    constraints = request.constraints
    defaults = operational_constraints.defaults

    req_allowed_specified = (
        constraints is not None and constraints.allowed_route_ids is not None
    )
    req_allowed = (
        frozenset(constraints.allowed_route_ids)
        if req_allowed_specified
        else None
    )
    default_allowed = defaults.allowed_route_ids
    config_allowed = operational_constraints.allowed_route_ids

    if req_allowed_specified:
        candidate_allowed = req_allowed
    elif default_allowed is not None:
        candidate_allowed = default_allowed
    else:
        candidate_allowed = None

    if config_allowed is not None and candidate_allowed is not None:
        effective_allowed = config_allowed & candidate_allowed
    elif config_allowed is not None:
        effective_allowed = config_allowed
    elif candidate_allowed is not None:
        effective_allowed = candidate_allowed
    else:
        effective_allowed = None

    req_caps_specified = (
        constraints is not None and constraints.required_capabilities is not None
    )
    if req_caps_specified:
        assert constraints is not None
        assert constraints.required_capabilities is not None
        req_caps = frozenset(constraints.required_capabilities)
    elif defaults.required_capabilities:
        req_caps = defaults.required_capabilities
    else:
        req_caps = frozenset()
    effective_caps = operational_constraints.required_capabilities | req_caps

    req_qual_specified = (
        constraints is not None and constraints.required_quality_criteria is not None
    )
    if req_qual_specified:
        assert constraints is not None
        assert constraints.required_quality_criteria is not None
        req_qual = frozenset(constraints.required_quality_criteria)
    elif defaults.required_quality_criteria:
        req_qual = defaults.required_quality_criteria
    else:
        req_qual = frozenset()
    effective_qual = operational_constraints.required_quality_criteria | req_qual

    req_cost_specified = (
        constraints is not None and constraints.max_estimated_cost is not None
    )
    if req_cost_specified:
        assert constraints is not None
        assert constraints.max_estimated_cost is not None
        req_ceiling = (
            constraints.max_estimated_cost.amount,
            constraints.max_estimated_cost.currency,
        )
    elif defaults.max_estimated_cost is not None:
        req_ceiling = (
            defaults.max_estimated_cost.amount,
            defaults.max_estimated_cost.currency,
        )
    else:
        req_ceiling = None

    config_ceilings = tuple(
        (c.amount, c.currency) for c in operational_constraints.max_estimated_costs
    )

    all_applicable: list[tuple[str, str]] = list(config_ceilings)
    if req_ceiling is not None:
        all_applicable.append(req_ceiling)

    effective_ceiling_map: dict[str, str] = {}
    for amount, currency in all_applicable:
        dec_amount = Decimal(amount)
        if currency not in effective_ceiling_map:
            effective_ceiling_map[currency] = amount
        else:
            if dec_amount < Decimal(effective_ceiling_map[currency]):
                effective_ceiling_map[currency] = amount

    effective_ceilings_tuple = tuple(
        (effective_ceiling_map[curr], curr)
        for curr in sorted(effective_ceiling_map.keys())
    )

    applied: list[AppliedConstraint] = []
    if req_allowed_specified:
        assert constraints is not None
        assert constraints.allowed_route_ids is not None
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
    if req_caps_specified:
        assert constraints is not None
        assert constraints.required_capabilities is not None
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
    if req_qual_specified:
        assert constraints is not None
        assert constraints.required_quality_criteria is not None
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
    if req_cost_specified:
        assert constraints is not None
        assert constraints.max_estimated_cost is not None
        limit = constraints.max_estimated_cost
        applied.append(
            AppliedConstraint(
                source="request",
                category="economics",
                description=f"A estimativa não podia exceder {limit.currency} {limit.amount}.",
            )
        )

    if operational_constraints.allowed_route_ids is not None:
        applied.append(
            AppliedConstraint(
                source="configuration",
                category="route",
                description=(
                    "Somente "
                    + ", ".join(sorted(operational_constraints.allowed_route_ids))
                    + " podiam ser consideradas."
                ),
            )
        )
    if operational_constraints.required_capabilities:
        applied.append(
            AppliedConstraint(
                source="configuration",
                category="capability",
                description=(
                    "A rota precisava declarar "
                    + ", ".join(sorted(operational_constraints.required_capabilities))
                    + "."
                ),
            )
        )
    if operational_constraints.required_quality_criteria:
        applied.append(
            AppliedConstraint(
                source="configuration",
                category="quality",
                description=(
                    "A rota precisava satisfazer "
                    + ", ".join(sorted(operational_constraints.required_quality_criteria))
                    + "."
                ),
            )
        )
    for ceiling in sorted(operational_constraints.max_estimated_costs, key=lambda c: c.currency):
        applied.append(
            AppliedConstraint(
                source="configuration",
                category="economics",
                description=f"A estimativa não podia exceder {ceiling.currency} {ceiling.amount}.",
            )
        )

    if not req_allowed_specified and default_allowed is not None:
        applied.append(
            AppliedConstraint(
                source="configuration",
                category="route",
                description=(
                    "Somente "
                    + ", ".join(sorted(default_allowed))
                    + " podiam ser consideradas."
                ),
            )
        )
    if not req_caps_specified and defaults.required_capabilities:
        applied.append(
            AppliedConstraint(
                source="configuration",
                category="capability",
                description=(
                    "A rota precisava declarar "
                    + ", ".join(sorted(defaults.required_capabilities))
                    + "."
                ),
            )
        )
    if not req_qual_specified and defaults.required_quality_criteria:
        applied.append(
            AppliedConstraint(
                source="configuration",
                category="quality",
                description=(
                    "A rota precisava satisfazer "
                    + ", ".join(sorted(defaults.required_quality_criteria))
                    + "."
                ),
            )
        )
    if not req_cost_specified and defaults.max_estimated_cost is not None:
        def_limit = defaults.max_estimated_cost
        applied.append(
            AppliedConstraint(
                source="configuration",
                category="economics",
                description=f"A estimativa não podia exceder {def_limit.currency} {def_limit.amount}.",
            )
        )

    return _ComposedConstraints(
        effective_allowed_route_ids=effective_allowed,
        effective_required_capabilities=effective_caps,
        effective_required_quality=effective_qual,
        effective_ceilings=effective_ceilings_tuple,
        all_applicable_ceilings=tuple(all_applicable),
        applied_constraints=tuple(applied),
    )


def _quality_factors(
    route: Route, required_quality: frozenset[str]
) -> list[DecisionFactor]:
    """Generate determining quality factors for a route satisfying required criteria."""

    factors: list[DecisionFactor] = []
    if required_quality:
        for criterion in sorted(required_quality):
            refs = list(route.quality_evidence_references.get(criterion, ()))
            factors.append(
                DecisionFactor(
                    category="quality",
                    description=f"{route.id} satisfez o critério de qualidade {criterion}.",
                    references=refs if refs else None,
                )
            )
    return factors


def route_request(
    request: ExecutionRequest,
    catalog: RouteCatalog,
    *,
    locally_invalid_route_ids: frozenset[str] = frozenset(),
    invalid_execution_route_ids: frozenset[str] = frozenset(),
    operational_constraints: OperationalConstraints | None = None,
) -> RefusalResponse | SelectedDecision:
    """Evaluate routing and return a refusal or one validated selection.

    Local configuration and execution-association failures are supplied from
    the request snapshot and remain distinct sanitized causes of
    ``invalid_route``.
    """

    if operational_constraints is None:
        operational_constraints = getattr(
            catalog, "operational_constraints", OperationalConstraints()
        )

    composed = _compose_effective_constraints(request, operational_constraints)

    exclusions: list[Exclusion] = []
    candidates: list[Route] = []
    # Stable route-id order makes both the selected result and its explanations
    # independent of catalog insertion order.
    for route in sorted(catalog.snapshot(), key=lambda item: item.id):
        exclusion = _first_implemented_exclusion(
            route,
            locally_invalid_route_ids,
            invalid_execution_route_ids,
            composed.effective_allowed_route_ids,
            composed.effective_required_capabilities,
            composed.effective_required_quality,
        )
        if exclusion is None:
            candidates.append(route)
        else:
            exclusions.append(exclusion)

    catalog_route_ids = {route.id for route in catalog.snapshot()}
    # Multiroute bootstrap can preserve the identity of a malformed local entry
    # without constructing it as an executable Route.  Keep that exclusion in
    # the decision explanation even though it is absent from the catalog tuple.
    for invalid_id in sorted(locally_invalid_route_ids):
        if invalid_id not in catalog_route_ids:
            exclusions.append(
                Exclusion(
                    invalid_id,
                    "invalid_route",
                    "configuration",
                    f"{invalid_id} foi excluída por configuração local inválida.",
                )
            )

    applied_constraints = tuple(
        list(composed.applied_constraints)
        + _configuration_constraints(exclusions)
    )

    if not candidates:
        return _validated_refusal(
            _RefusalContext(
                request=request,
                candidates=(),
                exclusions=tuple(exclusions),
                kind="no_candidates",
                applied_constraints=applied_constraints,
                effective_ceilings=composed.effective_ceilings,
            )
        )

    return _evaluate_economics(request, candidates, exclusions, composed)


def _evaluate_economics(
    request: ExecutionRequest,
    candidates: list[Route],
    exclusions: list[Exclusion],
    composed: _ComposedConstraints,
) -> RefusalResponse | SelectedDecision:
    """Apply economic gates and proceed to deterministic selection when safe."""

    ceilings = composed.effective_ceilings
    applied_constraints = tuple(
        list(composed.applied_constraints)
        + _configuration_constraints(exclusions)
    )

    if not ceilings:
        # With one eligible route there is nothing to compare, so missing price
        # information cannot alter which route wins.
        if len(candidates) == 1:
            route = candidates[0]
            context = _selection_context(
                request,
                candidates,
                exclusions,
                composed,
            )
            quality_factors = _quality_factors(
                route, composed.effective_required_quality
            )
            decision = SelectedDecision(
                selected_routes=(route,),
                strategy_id="lowest-estimated-cost",
                strategy_applied=True,
                applied_constraints=context.applied_constraints,
                reason=f"{route.id} foi selecionada por ser a única rota elegível.",
                factors=tuple(
                    (_factors(exclusions) if exclusions else [])
                    + quality_factors
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

        # Multiple candidates require comparable available estimates; otherwise
        # lowest-estimated-cost has no defensible ordering to apply.
        comparable = [
            route
            for route in candidates
            if route.estimate.status == "available" and route.estimate.comparable
        ]
        if not comparable:
            return _economic_information_refusal(
                request,
                exclusions,
                candidates,
                applied_constraints=applied_constraints,
            )

        currencies = {route.estimate.currency for route in comparable}
        if len(currencies) != 1:
            return _economic_information_refusal(
                request,
                exclusions,
                candidates,
                applied_constraints=applied_constraints,
            )

        context = _selection_context(
            request,
            candidates,
            exclusions,
            composed,
        )
        return _select_lowest_cost(context, exclusions, composed)

    # Ceilings exist
    ceiling_map = {curr: Decimal(amt) for amt, curr in ceilings}
    ceiling_str_map = {curr: amt for amt, curr in ceilings}

    admissible: list[Route] = []
    indeterminate: list[Route] = []
    conclusive_violation: list[Route] = []

    for route in candidates:
        estimate = route.estimate
        if estimate.status != "available" or not estimate.comparable:
            indeterminate.append(route)
        elif estimate.currency not in ceiling_map:
            indeterminate.append(route)
        elif estimate.decimal_amount() > ceiling_map[estimate.currency]:
            conclusive_violation.append(route)
        else:
            if len(ceiling_map) == 1:
                admissible.append(route)
            else:
                indeterminate.append(route)

    if admissible:
        if len(admissible) == 1:
            route = admissible[0]
            context = _selection_context(
                request,
                candidates,
                exclusions,
                composed,
            )
            quality_factors = _quality_factors(
                route, composed.effective_required_quality
            )
            economic_factors = []
            for candidate in candidates:
                if candidate is route:
                    economic_factors.append(
                        _selected_estimate_factor(
                            candidate, ceiling_str_map[candidate.estimate.currency]
                        )
                    )
                elif candidate in indeterminate:
                    missing = sorted(
                        c for c in ceiling_map if c != candidate.estimate.currency
                    )
                    req_c = (
                        missing[0]
                        if len(missing) == 1
                        else (", ".join(missing) if missing else None)
                    )
                    economic_factors.append(
                        _estimate_factor(candidate, req_c)
                    )
                else:
                    economic_factors.append(
                        _ceiling_violation_factor(
                            candidate, ceiling_str_map[candidate.estimate.currency]
                        )
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
                    + quality_factors
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
            composed,
        )
        return _select_lowest_cost(context, exclusions, composed)

    if indeterminate:
        return _economic_information_refusal(
            request,
            exclusions,
            candidates,
            applied_constraints=applied_constraints,
            effective_ceilings=ceilings,
        )

    return _validated_refusal(
        _RefusalContext(
            request=request,
            candidates=tuple(candidates),
            exclusions=tuple(exclusions),
            kind="ceiling_violations",
            applied_constraints=applied_constraints,
            effective_ceilings=ceilings,
        )
    )


def _selection_context(
    request: ExecutionRequest,
    candidates: list[Route],
    exclusions: list[Exclusion],
    composed: _ComposedConstraints | None = None,
) -> _SelectionContext:
    """Freeze authoritative candidate sets and constraints before selection."""

    if composed is None:
        composed = _compose_effective_constraints(
            request, OperationalConstraints()
        )

    ordered_candidates = tuple(sorted(candidates, key=lambda route: route.id))
    ceilings = composed.effective_ceilings
    ceiling_map = {curr: Decimal(amt) for amt, curr in ceilings}

    if not ceilings:
        comparable_routes = [
            route
            for route in ordered_candidates
            if route.estimate.status == "available" and route.estimate.comparable
        ]
        selectable_routes = (
            list(ordered_candidates)
            if len(ordered_candidates) == 1
            else comparable_routes
        )
        compared_routes = (
            comparable_routes if len(ordered_candidates) > 1 else []
        )
    else:
        comparable_routes = [
            route
            for route in ordered_candidates
            if (
                route.estimate.status == "available"
                and route.estimate.comparable
                and route.estimate.currency in ceiling_map
            )
        ]
        selectable_routes = [
            route
            for route in comparable_routes
            if (
                len(ceiling_map) == 1
                and route.estimate.decimal_amount()
                <= ceiling_map[route.estimate.currency]
            )
        ]
        compared_routes = (
            selectable_routes if len(selectable_routes) > 1 else []
        )

    applied_constraints = tuple(
        list(composed.applied_constraints)
        + _configuration_constraints(exclusions)
    )
    max_est_cost = (
        (ceilings[0][0], ceilings[0][1]) if len(ceilings) == 1 else None
    )

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
        applied_constraints=applied_constraints,
        allowed_route_ids=composed.effective_allowed_route_ids,
        required_capabilities=composed.effective_required_capabilities,
        required_quality=composed.effective_required_quality,
        max_estimated_cost=max_est_cost,
        effective_ceilings=ceilings,
        locally_invalid_route_ids=frozenset(
            exclusion.route_id
            for exclusion in exclusions
            if exclusion.reason == "invalid_route"
        ),
        exclusions=tuple(exclusions),
    )


def _select_lowest_cost(
    context: _SelectionContext,
    exclusions: list[Exclusion],
    composed: _ComposedConstraints | None = None,
) -> SelectedDecision:
    """Select the minimum exact estimate and break numeric ties by route ID."""

    minimum = min(
        route.estimate.decimal_amount() for route in context.compared_routes
    )
    tied = [
        route
        for route in context.compared_routes
        if route.estimate.decimal_amount() == minimum
    ]
    # Decimal establishes numeric equality; Unicode lexicographic route ID is
    # the approved deterministic tie-breaker.
    selected = min(tied, key=lambda route: route.id)
    removed = [
        route
        for route in context.candidates
        if route not in context.selectable_routes
    ]

    factors = (_factors(exclusions) if exclusions else [])
    factors.extend(_quality_factors(selected, context.required_quality))

    ceiling_str_map = {curr: amt for amt, curr in context.effective_ceilings}
    for route in context.candidates:
        if ceiling_str_map and route in removed:
            if route in context.comparable_routes:
                factors.append(
                    _ceiling_violation_factor(
                        route, ceiling_str_map[route.estimate.currency]
                    )
                )
                continue
            missing = sorted(
                c for c in ceiling_str_map if c != route.estimate.currency
            )
            req_c = (
                missing[0]
                if len(missing) == 1
                else (", ".join(missing) if missing else None)
            )
            factors.append(_estimate_factor(route, req_c))
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
    """Recheck a proposed selection against frozen authoritative facts.

    This defensive pass ensures strategy construction cannot silently change
    candidate sets, constraints, estimates, ordering, or the tie-break rule.
    """

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

    expected_reason, expected_factors = _expected_selection_explanation(
        context, selected
    )
    if decision.reason != expected_reason or decision.factors != expected_factors:
        raise InvalidDecisionError(
            "Selection explanation does not match the authoritative facts."
        )

    if _first_implemented_exclusion(
        selected,
        context.locally_invalid_route_ids,
        frozenset(),
        context.allowed_route_ids,
        context.required_capabilities,
        context.required_quality,
    ) is not None:
        raise InvalidDecisionError(
            "Selected route violates an applicable constraint."
        )

    ceilings_to_check = (
        context.effective_ceilings
        if context.effective_ceilings
        else (
            ((context.max_estimated_cost[0], context.max_estimated_cost[1]),)
            if context.max_estimated_cost is not None
            else ()
        )
    )
    for ceiling_amount, ceiling_currency in ceilings_to_check:
        estimate = selected.estimate
        if (
            estimate.status != "available"
            or not estimate.comparable
            or estimate.currency != ceiling_currency
            or estimate.decimal_amount() > Decimal(ceiling_amount)
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


def _expected_selection_explanation(
    context: _SelectionContext, selected: Route
) -> tuple[str, tuple[DecisionFactor, ...]]:
    """Derive the authoritative selection reason and determining factors."""

    factors = _factors(list(context.exclusions)) if context.exclusions else []
    factors.extend(_quality_factors(selected, context.required_quality))
    ceiling_str_map = {curr: amt for amt, curr in context.effective_ceilings}

    if not ceiling_str_map and len(context.candidates) == 1:
        factors.append(
            DecisionFactor(
                category="route",
                description=f"{selected.id} era a única rota elegível para a decisão.",
            )
        )
        return (
            f"{selected.id} foi selecionada por ser a única rota elegível.",
            tuple(factors),
        )

    if ceiling_str_map and len(context.selectable_routes) == 1:
        for candidate in context.candidates:
            if candidate is selected:
                factors.append(
                    _selected_estimate_factor(
                        candidate, ceiling_str_map[candidate.estimate.currency]
                    )
                )
            elif candidate not in context.comparable_routes:
                missing = sorted(
                    c for c in ceiling_str_map if c != candidate.estimate.currency
                )
                req_c = (
                    missing[0]
                    if len(missing) == 1
                    else (", ".join(missing) if missing else None)
                )
                factors.append(_estimate_factor(candidate, req_c))
            else:
                factors.append(
                    _ceiling_violation_factor(
                        candidate, ceiling_str_map[candidate.estimate.currency]
                    )
                )
        return (
            f"{selected.id} foi selecionada por ser a única rota que "
            "comprovou admissibilidade econômica.",
            tuple(factors),
        )

    for candidate in context.candidates:
        if (
            ceiling_str_map
            and candidate not in context.selectable_routes
        ):
            if candidate in context.comparable_routes:
                factors.append(
                    _ceiling_violation_factor(
                        candidate, ceiling_str_map[candidate.estimate.currency]
                    )
                )
            else:
                missing = sorted(
                    c for c in ceiling_str_map if c != candidate.estimate.currency
                )
                req_c = (
                    missing[0]
                    if len(missing) == 1
                    else (", ".join(missing) if missing else None)
                )
                factors.append(_estimate_factor(candidate, req_c))
        else:
            factors.append(_estimate_factor(candidate))
    factors.append(
        DecisionFactor(
            category="strategy",
            description=(
                f"{selected.id} tinha a menor estimativa entre as rotas "
                "economicamente comparáveis."
            ),
        )
    )
    minimum = min(
        route.estimate.decimal_amount() for route in context.compared_routes
    )
    tied = [
        route
        for route in context.compared_routes
        if route.estimate.decimal_amount() == minimum
    ]
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
    return (
        f"{selected.id} foi selecionada pela menor estimativa entre as "
        "rotas economicamente comparáveis.",
        tuple(factors),
    )


def _expected_refusal_explanation(
    context: _RefusalContext,
) -> tuple[
    Literal["NO_ELIGIBLE_ROUTE", "INSUFFICIENT_ECONOMIC_INFORMATION"],
    str,
    str,
    list[DecisionFactor],
]:
    """Derive the authoritative refusal code, message, reason, and factors."""

    _validate_refusal_context(context)
    exclusions = list(context.exclusions)
    if context.kind == "no_candidates":
        return (
            "NO_ELIGIBLE_ROUTE",
            "Nenhuma rota configurada, habilitada e válida satisfaz "
            "as restrições aplicáveis.",
            "Todas as rotas foram excluídas antes da comparação econômica.",
            _factors(exclusions),
        )

    factors = _factors(exclusions) if exclusions else []
    limit = (
        context.request.constraints.max_estimated_cost
        if context.request.constraints
        else None
    )
    effective_ceilings_map = {curr: amt for amt, curr in context.effective_ceilings}
    if not effective_ceilings_map and limit is not None:
        effective_ceilings_map = {limit.currency: limit.amount}

    if context.kind == "ceiling_violations":
        if not effective_ceilings_map:
            raise InvalidDecisionError(
                "A ceiling refusal requires an authoritative economic limit."
            )
        factors.extend(
            _ceiling_violation_factor(
                route, effective_ceilings_map[route.estimate.currency]
            )
            for route in context.candidates
        )
        return (
            "NO_ELIGIBLE_ROUTE",
            "Nenhuma rota configurada, habilitada e válida satisfaz "
            "as restrições aplicáveis.",
            "Todas as rotas restantes excederam o teto econômico aplicável.",
            factors,
        )

    if context.kind != "economic_insufficiency":
        raise InvalidDecisionError("Unknown authoritative refusal kind.")

    if effective_ceilings_map:
        effective_ceilings_dec = {
            curr: Decimal(amt) for curr, amt in effective_ceilings_map.items()
        }
        for route in context.candidates:
            estimate = route.estimate
            if (
                estimate.status != "available"
                or not estimate.comparable
                or estimate.currency not in effective_ceilings_map
                or len(effective_ceilings_map) > 1
                or estimate.decimal_amount()
                <= effective_ceilings_dec[estimate.currency]
            ):
                missing = sorted(
                    c for c in effective_ceilings_map if c != estimate.currency
                )
                req_c = (
                    missing[0]
                    if len(missing) == 1
                    else (", ".join(missing) if missing else None)
                )
                factors.append(_estimate_factor(route, req_c))
            else:
                factors.append(
                    _ceiling_violation_factor(
                        route, effective_ceilings_map[estimate.currency]
                    )
                )
    else:
        comparable = [
            route
            for route in context.candidates
            if route.estimate.status == "available" and route.estimate.comparable
        ]
        if comparable:
            factors.extend(_currency_factor(route) for route in comparable)
        else:
            factors.extend(
                _estimate_factor(route) for route in context.candidates
            )
    return (
        "INSUFFICIENT_ECONOMIC_INFORMATION",
        "Não há informação econômica suficiente para decidir a rota.",
        "O custo era indispensável, mas nenhuma base econômica suficiente "
        "permitiu continuar para a seleção.",
        factors,
    )


def _validate_refusal_context(context: _RefusalContext) -> None:
    """Validate that refusal context invariants match the authoritative facts."""

    limit = (
        context.request.constraints.max_estimated_cost
        if context.request.constraints
        else None
    )
    if context.kind == "no_candidates":
        if context.candidates:
            raise InvalidDecisionError(
                "A no-candidates refusal cannot contain selectable candidates."
            )
        return
    if not context.candidates:
        raise InvalidDecisionError(
            "An economic refusal requires authoritative candidates."
        )

    effective_ceilings_dec = {
        curr: Decimal(amt) for amt, curr in context.effective_ceilings
    }
    if not effective_ceilings_dec and limit is not None:
        effective_ceilings_dec = {limit.currency: Decimal(limit.amount)}

    if context.kind == "ceiling_violations":
        if not effective_ceilings_dec or any(
            route.estimate.status != "available"
            or not route.estimate.comparable
            or route.estimate.currency not in effective_ceilings_dec
            or route.estimate.decimal_amount()
            <= effective_ceilings_dec[route.estimate.currency]
            for route in context.candidates
        ):
            raise InvalidDecisionError(
                "A ceiling refusal is incompatible with the authoritative facts."
            )
        return
    if context.kind != "economic_insufficiency":
        raise InvalidDecisionError("Unknown authoritative refusal kind.")

    if effective_ceilings_dec:
        admissible = [
            route
            for route in context.candidates
            if route.estimate.status == "available"
            and route.estimate.comparable
            and route.estimate.currency in effective_ceilings_dec
            and len(effective_ceilings_dec) == 1
            and route.estimate.decimal_amount()
            <= effective_ceilings_dec[route.estimate.currency]
        ]
        indeterminate = [
            route
            for route in context.candidates
            if route.estimate.status != "available"
            or not route.estimate.comparable
            or route.estimate.currency not in effective_ceilings_dec
            or len(effective_ceilings_dec) > 1
        ]
        if admissible or not indeterminate:
            raise InvalidDecisionError(
                "Economic insufficiency contradicts ceiling precedence."
            )
        return

    comparable = [
        route
        for route in context.candidates
        if route.estimate.status == "available" and route.estimate.comparable
    ]
    if len(context.candidates) < 2 or (
        comparable and len({route.estimate.currency for route in comparable}) == 1
    ):
        raise InvalidDecisionError(
            "Economic insufficiency contradicts comparison precedence."
        )


def _selected_estimate_factor(route: Route, ceiling: str) -> DecisionFactor:
    """Explain why the selected route proved compliance with a cost ceiling."""

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
    candidates: list[Route],
    *,
    applied_constraints: tuple[AppliedConstraint, ...] = (),
    effective_ceilings: tuple[tuple[str, str], ...] = (),
) -> RefusalResponse:
    """Build a refusal for insufficient comparable economic information."""

    return _validated_refusal(
        _RefusalContext(
            request=request,
            candidates=tuple(candidates),
            exclusions=tuple(exclusions),
            kind="economic_insufficiency",
            applied_constraints=applied_constraints,
            effective_ceilings=effective_ceilings,
        )
    )


def _validated_refusal(context: _RefusalContext) -> RefusalResponse:
    """Assemble one explainable refusal and validate it against authoritative facts."""

    code, message, reason, factors = _expected_refusal_explanation(context)
    applied_constraints = (
        list(context.applied_constraints)
        if context.applied_constraints
        else (
            _request_constraints(context.request)
            + _configuration_constraints(list(context.exclusions))
        )
    )
    response = RefusalResponse(
        error=PublicError(code=code, message=message),
        decision=RefusedDecision(
            strategy=Strategy(),
            applied_constraints=applied_constraints,
            reason=reason,
            factors=factors,
        ),
    )
    return _validate_refusal(context, response)


def _validate_refusal(
    context: _RefusalContext, response: RefusalResponse
) -> RefusalResponse:
    """Validate that a constructed refusal matches its expected explanation."""

    code, message, reason, factors = _expected_refusal_explanation(context)
    expected_constraints = (
        list(context.applied_constraints)
        if context.applied_constraints
        else (
            _request_constraints(context.request)
            + _configuration_constraints(list(context.exclusions))
        )
    )
    if (
        response.error.code != code
        or response.error.message != message
        or response.decision.strategy != Strategy()
        or response.decision.applied_constraints != expected_constraints
        or response.decision.reason != reason
        or response.decision.factors != factors
    ):
        raise InvalidDecisionError(
            "Routing refusal does not match the authoritative facts."
        )
    return response


def _estimate_factor(
    route: Route, required_currency: str | None = None
) -> DecisionFactor:
    """Explain the availability and comparability of one route estimate."""

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
    """Explain why one available estimate cannot cross currency boundaries."""

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
    """Explain that one comparable estimate exceeded the request ceiling."""

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
    invalid_execution_route_ids: frozenset[str],
    allowed_route_ids: frozenset[str] | None,
    required_capabilities: frozenset[str],
    required_quality: frozenset[str],
) -> Exclusion | None:
    """Return the first applicable non-economic exclusion in normative order.

    Returning immediately is intentional: one stable primary reason explains
    each excluded route even when several conditions would reject it.
    """

    if not route.enabled:
        return Exclusion(
            route.id,
            "disabled_route",
            "route",
            f"{route.id} estava desabilitada na configuração.",
        )
    if route.id in locally_invalid_route_ids:
        invalid_association = route.id in invalid_execution_route_ids
        return Exclusion(
            route.id,
            "invalid_route",
            "configuration",
            (
                f"{route.id} foi excluída porque sua associação de execução era inválida."
                if invalid_association
                else f"{route.id} foi excluída por configuração local inválida."
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
    """Project supplied request constraints into deterministic explanations."""

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
    """Project configuration-owned exclusions into applied constraints."""

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
                        f"{exclusion.route_id} possuía associação de execução inválida."
                        if "associação de execução" in exclusion.description
                        else f"{exclusion.route_id} possuía configuração local inválida."
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
    """Convert route exclusions into public decision factors."""

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

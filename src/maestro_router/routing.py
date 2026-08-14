from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .contracts import (
    AppliedConstraint,
    DecisionFactor,
    ExecutionRequest,
    FactorCategory,
    PublicError,
    RefusalResponse,
    RefusedDecision,
    Strategy,
)


@dataclass(frozen=True, slots=True)
class Route:
    id: str
    enabled: bool = True
    capabilities: frozenset[str] = field(default_factory=frozenset)
    quality_criteria: frozenset[str] = field(default_factory=frozenset)
    known_unavailable: bool = False

    def __post_init__(self) -> None:
        if not self.id or not any(not character.isspace() for character in self.id):
            raise ValueError("Route IDs must contain a non-whitespace character.")
        if any(0xD800 <= ord(character) <= 0xDFFF for character in self.id):
            raise ValueError("Route IDs must be well-formed Unicode scalar sequences.")


class RouteCatalog:
    """In-memory snapshot whose routes are assumed sufficiently locally valid.

    The ``invalid_route`` and ``INVALID_CONFIGURATION`` semantics are outside
    this slice and must not be inferred from the filters implemented below.
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


class RoutingNotImplementedError(RuntimeError):
    """A compatible route reached the execution boundary outside this slice."""


def refuse_when_no_route(
    request: ExecutionRequest, catalog: RouteCatalog
) -> RefusalResponse:
    """Refuse only when every prevalidated route fails an implemented filter.

    Local validity is an upstream precondition in this slice; this function
    does not implement the normative ``invalid_route`` phase.
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
            allowed_route_ids,
            required_capabilities,
            required_quality,
        )
        if exclusion is None:
            candidates.append(route)
        else:
            exclusions.append(exclusion)

    if candidates:
        raise RoutingNotImplementedError(
            "Selection, economic evaluation, and execution are intentionally "
            "outside the first refusal slice."
        )

    applied_constraints = _request_constraints(request)
    applied_constraints.extend(_configuration_constraints(exclusions))
    factors = _factors(exclusions)

    return RefusalResponse(
        error=PublicError(
            code="NO_ELIGIBLE_ROUTE",
            message=(
                "Nenhuma rota configurada, habilitada e válida satisfaz "
                "as restrições aplicáveis."
            ),
        ),
        decision=RefusedDecision(
            strategy=Strategy(),
            applied_constraints=applied_constraints,
            reason="Todas as rotas foram excluídas antes da comparação econômica.",
            factors=factors,
        ),
    )


def _first_implemented_exclusion(
    route: Route,
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

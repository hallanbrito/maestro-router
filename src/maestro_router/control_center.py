"""Camada administrativa local e composição operacional do Maestro Control Center.

Este módulo implementa uma composição operacional dedicada ao Control Center (ADR 0012),
fornecendo uma camada administrativa local que gerencia credenciais em memória volátil,
rotas em tempo de execução e sugestões explicáveis (prévias sem custo de tokens),
preservando estritamente o contrato neutro da API pública v1 (docs/05-API.md).
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)

from .adapters import OpenAIResponsesAdapter
from .api import (
    create_app,
    _execute_selection,
    _invalid_request,
    _is_valid_adapter,
    _snapshot_adapters,
    _validation_issues,
)
from .contracts import ExecutionRequest
from .economics import calculate_pre_execution_amount
from .execution import ExecutionAdapter
from .routing import (
    EconomicEstimate,
    OperationalConstraints,
    Route,
    RouteCatalog,
    SelectedDecision,
    route_request,
)
from .bootstrap import (
    _parse_estimated_usage,
    _parse_price_reference,
    _is_structurally_valid_string,
    _estimated_usage_assumption,
    _DISABLED_ROUTE_ESTIMATE_REASON,
)

CredentialStatus = Literal[
    "not_registered",
    "registered",
    "verified",
    "access_denied",
    "insufficient_quota",
    "verification_unavailable",
]

TrackType = Literal["free", "economica", "inteligente"]

KNOWN_OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "o1-mini",
    "o1-preview",
    "gpt-4-turbo",
]

# Referência de preço oficial documentada para o GPT-4o-mini (ADR 0008).
# Utilizada estritamente para a rota padrão inicial deste modelo específico.
INITIAL_GPT4O_MINI_PRICE_REFERENCE = {
    "id": "pricing-openai-gpt-4o-mini-2026",
    "currency": "USD",
    "version": "2026-08",
    "source": "https://openai.com/api/pricing/",
    "rates": [
        {"unit": "input_token", "rate": "0.1500", "base": 1000000},
        {"unit": "output_token", "rate": "0.6000", "base": 1000000},
    ],
    "conditions": ["standard tier", "direct api access"],
    "context_complete": True,
    "units_exhaustive": True,
    "no_double_counting": True,
    "model_identity_exact": True,
}

INITIAL_GPT4O_MINI_ESTIMATED_USAGE = {
    "input_token": 1500,
    "output_token": 500,
    "applicability_confirmed": True,
}


def is_operator_declared_free_route(route: Route) -> bool:
    """Verifica se a rota possui gratuidade declarada pelo operador.

    Para qualificar na trilha Free no Maestro Router:
    1. A rota precisa estar habilitada e não marcada como indisponível.
    2. A referência de preço declarada pelo operador deve existir e conter taxas exclusivamente iguais a zero ("0", "0.0", "0.00").
    3. A estimativa prévia calculada de custo deve estar disponível com montante igual a zero.
    4. Rotas com custo positivo declarado, custo desconhecido ou estimativa indisponível são estritamente excluídas.

    Nota de transparência e auditoria (Bloqueador 1):
    Esta checagem reflete unicamente as tarifas e estimativas declaradas localmente na
    configuração operacional pelo operador. O Maestro Router não valida, confirma nem garante
    ausência de cobrança ou faturamento real na conta do usuário junto ao provedor de IA.
    """
    if not route.enabled or route.known_unavailable:
        return False
    if route.price_reference is None:
        return False
    rates = route.price_reference.rates
    if not rates or not all(Decimal(r.rate) == Decimal("0") for r in rates):
        return False
    if route.estimate is None or route.estimate.status != "available":
        return False
    try:
        if route.estimate.decimal_amount() != Decimal("0"):
            return False
    except Exception:
        return False
    return True


# Alias para compatibilidade de interfaces anteriores
is_proven_free_route = is_operator_declared_free_route


class ControlCenterState:
    """Estado thread-safe em memória volátil para o runtime do Control Center."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.sessions: dict[str, dict[str, Any]] = {}
        self.credentials: dict[str, dict[str, Any]] = {
            "openai": {
                "api_key": None,
                "status": "not_registered",
                "verified_at": None,
                "models": list(KNOWN_OPENAI_MODELS),
                "message": None,
            }
        }
        # Rota inicial do modelo padrão. Observe que quality_criteria inicia vazio,
        # sem benchmarks inventados ou evidências forjadas.
        self.routes_raw: list[dict[str, Any]] = [
            {
                "route_id": "route-openai-gpt4o-mini",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "enabled": True,
                "known_unavailable": False,
                "capabilities": ["text_generation", "summarization"],
                "quality_criteria": [],
                "price_reference": INITIAL_GPT4O_MINI_PRICE_REFERENCE,
                "estimated_usage": INITIAL_GPT4O_MINI_ESTIMATED_USAGE,
            }
        ]
        self.current_catalog: RouteCatalog = RouteCatalog()
        self.current_adapters: dict[str, ExecutionAdapter] = {}
        self._rebuild_runtime_locked()

    def rebuild_runtime(self) -> None:
        with self._lock:
            self._rebuild_runtime_locked()

    def _rebuild_runtime_locked(self) -> None:
        """Reconstrói os snapshots imutáveis do RouteCatalog e dos adaptadores."""
        openai_cred = self.credentials.get("openai", {})
        api_key = openai_cred.get("api_key")
        adapters: dict[str, ExecutionAdapter] = {}
        if api_key:
            client = AsyncOpenAI(api_key=api_key)
            adapters["openai-responses"] = OpenAIResponsesAdapter(client=client)

        valid_routes: list[Route] = []
        invalid_route_ids: list[str] = []
        disabled_invalid_route_ids: list[str] = []

        for entry in self.routes_raw:
            route_id = entry.get("route_id")
            if not _is_structurally_valid_string(route_id):
                continue

            model = entry.get("model")
            provider = entry.get("provider", "openai")
            known_unavailable = bool(entry.get("known_unavailable", False))
            user_enabled = bool(entry.get("enabled", True))

            # Se não há chave de API para o provedor externo, a rota não possui adaptador
            # funcional associado. Para preservar a taxonomia da API pública (recusa 422
            # em vez de erro interno 500), a rota permanece desabilitada na composição.
            has_credential = bool(api_key) if provider == "openai" else False
            effective_enabled = user_enabled if has_credential else False

            capabilities = frozenset(entry.get("capabilities", []))
            qc_raw = entry.get("quality_criteria", [])
            qc_set: set[str] = set()
            qc_refs: dict[str, tuple[str, ...]] = {}
            for item in qc_raw:
                if isinstance(item, dict) and "criterion" in item:
                    c = item["criterion"]
                    refs = item.get("evidence_references", [])
                    if refs:
                        qc_set.add(c)
                        qc_refs[c] = tuple(sorted(refs))

            price_ref_val = entry.get("price_reference")
            price_reference = None
            if isinstance(price_ref_val, dict):
                try:
                    price_reference = _parse_price_reference(
                        json.dumps(price_ref_val),
                        route_id=route_id,
                        model=model or "dummy",
                    )
                except Exception:
                    price_reference = None

            est_usage_val = entry.get("estimated_usage")
            quantities = None
            if isinstance(est_usage_val, dict):
                try:
                    quantities = _parse_estimated_usage(json.dumps(est_usage_val))
                except Exception:
                    quantities = None

            estimate = None
            if not effective_enabled:
                reason = (
                    _DISABLED_ROUTE_ESTIMATE_REASON
                    if user_enabled
                    else "A rota está desabilitada na configuração."
                )
                if not has_credential and user_enabled:
                    reason = "A chave do provedor não está cadastrada na memória do servidor."
                estimate = EconomicEstimate(
                    status="unavailable",
                    reason=reason,
                )
            elif price_reference and quantities:
                try:
                    amount = calculate_pre_execution_amount(
                        quantities=quantities,
                        reference=price_reference,
                    )
                    estimate = EconomicEstimate(
                        status="available",
                        amount=amount,
                        currency=price_reference.currency,
                        price_reference=price_reference.id,
                        assumptions=(
                            _estimated_usage_assumption(
                                "input_token", quantities["input_token"]
                            ),
                            _estimated_usage_assumption(
                                "output_token", quantities["output_token"]
                            ),
                        ),
                    )
                except Exception:
                    estimate = EconomicEstimate(
                        status="unavailable",
                        reason="Falha no cálculo da estimativa econômica prévia.",
                    )
            else:
                estimate = EconomicEstimate(
                    status="unavailable",
                    reason="Não há preço nem método de estimativa aprovados para esta rota.",
                )

            route = Route(
                id=route_id,
                provider=provider,
                model=model or "unknown",
                adapter_id="openai-responses",
                enabled=effective_enabled,
                capabilities=capabilities,
                quality_criteria=frozenset(qc_set),
                quality_evidence_references=qc_refs,
                known_unavailable=known_unavailable,
                estimate=estimate,
                price_reference=price_reference,
            )
            valid_routes.append(route)

        self.current_catalog = RouteCatalog(
            valid_routes,
            configuration_invalid_route_ids=invalid_route_ids,
            configuration_disabled_invalid_route_ids=disabled_invalid_route_ids,
        )
        self.current_adapters = adapters

    def create_session(self) -> tuple[str, str]:
        with self._lock:
            session_id = secrets.token_hex(32)
            csrf_token = secrets.token_hex(32)
            self.sessions[session_id] = {
                "csrf_token": csrf_token,
                "created_at": time.time(),
            }
            return session_id, csrf_token

    def validate_session_and_csrf(
        self, session_id: str | None, csrf_token: str | None
    ) -> bool:
        if not session_id or not csrf_token:
            return False
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                return False
            return secrets.compare_digest(session["csrf_token"], csrf_token)

    def set_credential(self, provider: str, api_key: str) -> None:
        with self._lock:
            if provider not in self.credentials:
                self.credentials[provider] = {}
            self.credentials[provider]["api_key"] = api_key
            self.credentials[provider]["status"] = "registered"
            self.credentials[provider]["verified_at"] = None
            self.credentials[provider]["message"] = (
                "Credencial cadastrada na memória do servidor. Válida até o servidor ser encerrado."
            )
            self._rebuild_runtime_locked()

    def remove_credential(self, provider: str) -> None:
        with self._lock:
            if provider in self.credentials:
                self.credentials[provider]["api_key"] = None
                self.credentials[provider]["status"] = "not_registered"
                self.credentials[provider]["verified_at"] = None
                self.credentials[provider]["message"] = None
            self._rebuild_runtime_locked()

    def update_credential_status(
        self,
        provider: str,
        status: CredentialStatus,
        message: str | None = None,
        models: list[str] | None = None,
    ) -> None:
        with self._lock:
            if provider in self.credentials:
                self.credentials[provider]["status"] = status
                self.credentials[provider]["message"] = message
                if status == "verified":
                    self.credentials[provider]["verified_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    if models:
                        self.credentials[provider]["models"] = models
            self._rebuild_runtime_locked()

    def get_safe_config(self) -> dict[str, Any]:
        with self._lock:
            providers_info = []
            for p_id, cred in self.credentials.items():
                providers_info.append(
                    {
                        "id": p_id,
                        "name": "OpenAI" if p_id == "openai" else p_id.capitalize(),
                        "implemented": p_id == "openai",
                        "credential": {
                            "registered": bool(cred.get("api_key")),
                            "status": cred.get("status", "not_registered"),
                            "verified_at": cred.get("verified_at"),
                            "message": cred.get("message"),
                        },
                    }
                )

            routes_info = []
            has_openai_key = bool(self.credentials.get("openai", {}).get("api_key"))
            for r in self.routes_raw:
                blockers = []
                if not has_openai_key:
                    blockers.append("Chave do provedor não cadastrada no servidor.")
                if not r.get("enabled", True):
                    blockers.append("Rota desabilitada manualmente.")
                if r.get("known_unavailable", False):
                    blockers.append("Rota marcada como indisponível.")
                if not r.get("price_reference"):
                    blockers.append("Referência de preço ausente ou inválida.")
                if not r.get("estimated_usage"):
                    blockers.append("Estimativa de uso ausente.")

                routes_info.append(
                    {
                        "route_id": r.get("route_id"),
                        "provider": r.get("provider", "openai"),
                        "model": r.get("model"),
                        "enabled": r.get("enabled", True),
                        "known_unavailable": r.get("known_unavailable", False),
                        "capabilities": r.get("capabilities", []),
                        "quality_criteria": [
                            item["criterion"] if isinstance(item, dict) else str(item)
                            for item in r.get("quality_criteria", [])
                        ],
                        "price_reference": r.get("price_reference"),
                        "estimated_usage": r.get("estimated_usage"),
                        "status": "ready" if len(blockers) == 0 else "blocked",
                        "blockers": blockers,
                    }
                )

            return {
                "providers": providers_info,
                "routes": routes_info,
                "models": self.credentials.get("openai", {}).get(
                    "models", KNOWN_OPENAI_MODELS
                ),
            }


class DynamicRouteCatalog(RouteCatalog):
    """Proxy de catálogo que repassa chamadas ao catálogo ativo em memória.

    Preserva a fidelidade integral à interface RouteCatalog sem interceptar
    cabeçalhos ou manipular estratégias de forma oculta (Bloqueador 2).
    """

    def __init__(self, state: ControlCenterState) -> None:
        self._state = state

    def snapshot(self) -> tuple[Route, ...]:
        return self._state.current_catalog.snapshot()

    @property
    def configuration_invalid_route_ids(self) -> frozenset[str]:
        return getattr(
            self._state.current_catalog, "configuration_invalid_route_ids", frozenset()
        )

    @property
    def configuration_disabled_invalid_route_ids(self) -> frozenset[str]:
        return getattr(
            self._state.current_catalog,
            "configuration_disabled_invalid_route_ids",
            frozenset(),
        )

    @property
    def operational_constraints(self) -> OperationalConstraints | None:
        return getattr(
            self._state.current_catalog, "operational_constraints", None
        )


class DynamicAdapterRegistry(Mapping[str, ExecutionAdapter]):
    """Proxy de registro que delega a busca de adaptadores ao estado ativo."""

    def __init__(self, state: ControlCenterState) -> None:
        self._state = state

    def __getitem__(self, key: str) -> ExecutionAdapter:
        return self._state.current_adapters[key]

    def __iter__(self):
        return iter(self._state.current_adapters)

    def __len__(self) -> int:
        return len(self._state.current_adapters)

    def get(self, key: str, default=None):
        return self._state.current_adapters.get(key, default)


def _is_safe_origin(origin: str | None) -> bool:
    """Valida se as solicitações administrativas se originam do loopback local."""
    if origin is None:
        return True
    try:
        parsed = urlparse(origin)
        hostname = (parsed.hostname or "").lower()
        return hostname in {"localhost", "127.0.0.1", "::1"}
    except Exception:
        return False


def _validate_route_payload(body: Any) -> dict[str, Any]:
    """Valida exaustivamente o payload de rota ANTES de qualquer mutação de estado.

    Rejeita tipos incompatíveis, provedores não suportados e critérios sem evidência.
    Em falha, levanta HTTPException sem alterar a configuração anterior.
    """
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_JSON", "message": "O corpo deve ser um objeto JSON."},
        )

    provider = body.get("provider")
    if provider != "openai":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_PROVIDER",
                "message": "Apenas o provedor 'openai' possui adaptador suportado no momento.",
            },
        )

    route_id = body.get("route_id")
    if not _is_structurally_valid_string(route_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_ROUTE_ID",
                "message": "route_id é obrigatório e deve ser uma string não vazia.",
            },
        )

    model = body.get("model")
    if not _is_structurally_valid_string(model):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_MODEL",
                "message": "model é obrigatório e deve ser uma string não vazia.",
            },
        )

    if "enabled" in body and type(body["enabled"]) is not bool:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TYPE", "message": "enabled deve ser um valor booleano."},
        )

    if "known_unavailable" in body and type(body["known_unavailable"]) is not bool:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TYPE", "message": "known_unavailable deve ser um valor booleano."},
        )

    capabilities: list[str] = []
    if "capabilities" in body:
        caps_val = body["capabilities"]
        if not isinstance(caps_val, list) or any(not _is_structurally_valid_string(c) for c in caps_val):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_CAPABILITIES",
                    "message": "capabilities deve ser uma lista de strings não vazias.",
                },
            )
        if len(set(caps_val)) != len(caps_val):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_CAPABILITIES",
                    "message": "capabilities não pode conter duplicatas.",
                },
            )
        capabilities = list(caps_val)

    quality_criteria: list[dict[str, Any]] = []
    if "quality_criteria" in body:
        qc_val = body["quality_criteria"]
        if not isinstance(qc_val, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_QUALITY_CRITERIA",
                    "message": "quality_criteria deve ser uma lista de critérios.",
                },
            )
        seen_criteria: set[str] = set()
        for idx, item in enumerate(qc_val):
            if not isinstance(item, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "INVALID_QUALITY_CRITERIA",
                        "message": f"quality_criteria[{idx}] deve ser um objeto.",
                    },
                )
            crit = item.get("criterion")
            if not _is_structurally_valid_string(crit):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "INVALID_QUALITY_CRITERIA",
                        "message": f"quality_criteria[{idx}].criterion deve ser string válida.",
                    },
                )
            if crit in seen_criteria:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "INVALID_QUALITY_CRITERIA",
                        "message": f"Critério duplicado: {crit}.",
                    },
                )
            seen_criteria.add(crit)

            refs = item.get("evidence_references")
            if not isinstance(refs, list) or len(refs) == 0 or any(not _is_structurally_valid_string(r) for r in refs):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "INVALID_QUALITY_CRITERIA",
                        "message": (
                            f"quality_criteria[{idx}] exige ao menos uma evidence_reference "
                            "válida fornecida pelo operador. Não são permitidas declarações sem evidência."
                        ),
                    },
                )
            if len(set(refs)) != len(refs):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "INVALID_QUALITY_CRITERIA",
                        "message": f"evidence_references em quality_criteria[{idx}] contém duplicatas.",
                    },
                )
            quality_criteria.append({"criterion": crit, "evidence_references": list(refs)})

    # Validação estrita da referência de preço (sem auto-preenchimento para outros modelos)
    price_ref_obj: dict[str, Any] | None = None
    if "price_reference" in body and body["price_reference"] is not None:
        raw_price = body["price_reference"]
        if not isinstance(raw_price, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_PRICE_REFERENCE", "message": "price_reference deve ser um objeto JSON."},
            )
        try:
            _parse_price_reference(json.dumps(raw_price), route_id=route_id, model=model)
            price_ref_obj = raw_price
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_PRICE_REFERENCE", "message": f"price_reference inválida: {err}"},
            )

    # Validação estrita da previsão de uso (sem auto-preenchimento para outros modelos)
    est_usage_obj: dict[str, Any] | None = None
    if "estimated_usage" in body and body["estimated_usage"] is not None:
        raw_usage = body["estimated_usage"]
        if not isinstance(raw_usage, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_ESTIMATED_USAGE", "message": "estimated_usage deve ser um objeto JSON."},
            )
        try:
            _parse_estimated_usage(json.dumps(raw_usage))
            est_usage_obj = raw_usage
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_ESTIMATED_USAGE", "message": f"estimated_usage inválido: {err}"},
            )

    return {
        "route_id": route_id,
        "provider": provider,
        "model": model,
        "enabled": bool(body.get("enabled", True)),
        "known_unavailable": bool(body.get("known_unavailable", False)),
        "capabilities": capabilities,
        "quality_criteria": quality_criteria,
        "price_reference": price_ref_obj,
        "estimated_usage": est_usage_obj,
    }


def create_control_center_app(state: ControlCenterState | None = None) -> FastAPI:
    """Cria a aplicação FastAPI do Maestro Control Center com a camada administrativa local."""
    control_state = state if state is not None else ControlCenterState()

    dynamic_catalog = DynamicRouteCatalog(control_state)
    dynamic_adapters = DynamicAdapterRegistry(control_state)

    # Aplicação núcleo de execução expondo POST /v1/executions em conformidade com docs/05-API.md
    # O endpoint público v1 não interpreta trilhas, cabeçalhos ou estratégias externas.
    app = create_app(catalog=dynamic_catalog, adapters=dynamic_adapters)

    # Padroniza envelopes de erro HTTP e de validação para a camada administrativa do Control Center
    @app.exception_handler(HTTPException)
    async def custom_http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            code = detail.get("code", "HTTP_ERROR")
            message = detail.get("message", str(detail))
            extra = {k: v for k, v in detail.items() if k not in ("code", "message")}
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": {"code": code, "message": message, **extra},
                    "detail": detail,
                },
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": "HTTP_ERROR", "message": str(detail)},
                "detail": detail,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        issues = [
            {
                "path": "/" + "/".join(str(p) for p in err["loc"] if p != "body"),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "A solicitação contém dados inválidos.",
                    "issues": issues,
                },
                "detail": issues,
            },
        )

    admin_router = APIRouter(prefix="/admin", tags=["Control Center Admin"])

    async def _enforce_admin_security(
        request: Request,
        x_maestro_csrf_token: str | None = Header(None, alias="X-Maestro-CSRF-Token"),
    ) -> None:
        """Valida token CSRF, Origin e Sessão para operações administrativas mutantes."""
        origin = request.headers.get("origin") or request.headers.get("referer")
        if not _is_safe_origin(origin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": "Origem da solicitação administrativa não autorizada.",
                },
            )

        session_id = request.cookies.get("maestro_admin_session")
        if not control_state.validate_session_and_csrf(session_id, x_maestro_csrf_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": "Sessão expirada ou token CSRF inválido para operação administrativa.",
                },
            )

    @admin_router.get("/session")
    async def get_session(response: Response, request: Request) -> dict[str, str]:
        """Obtém ou atualiza a sessão administrativa local segura e token CSRF."""
        existing_session = request.cookies.get("maestro_admin_session")
        if existing_session and existing_session in control_state.sessions:
            csrf_token = control_state.sessions[existing_session]["csrf_token"]
            return {"csrf_token": csrf_token}

        session_id, csrf_token = control_state.create_session()
        response.set_cookie(
            key="maestro_admin_session",
            value=session_id,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return {"csrf_token": csrf_token}

    @admin_router.get("/config")
    async def get_config() -> dict[str, Any]:
        """Retorna metadados seguros dos provedores, credenciais e rotas operacionais."""
        return control_state.get_safe_config()

    @admin_router.post("/credentials")
    async def set_credentials(
        request: Request,
        x_maestro_csrf_token: str | None = Header(None, alias="X-Maestro-CSRF-Token"),
    ) -> dict[str, Any]:
        """Cadastra ou substitui a chave de API na memória volátil do backend."""
        await _enforce_admin_security(request, x_maestro_csrf_token)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_JSON", "message": "Corpo JSON inválido."},
            )

        if not isinstance(body, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_JSON", "message": "Corpo JSON deve ser um objeto."},
            )

        provider = body.get("provider")
        api_key = body.get("api_key")

        # Validação estrita: rejeita provedores não implementados e chaves inválidas
        if provider != "openai":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "UNSUPPORTED_PROVIDER",
                    "message": "Apenas o provedor 'openai' possui adaptador implementado no MVP atual.",
                },
            )

        if not _is_structurally_valid_string(api_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_KEY",
                    "message": "A chave da API deve ser um texto não vazio.",
                },
            )

        control_state.set_credential("openai", api_key.strip())
        return {
            "provider": "openai",
            "status": "registered",
            "message": "Credencial cadastrada na memória do servidor. Válida até o servidor ser encerrado.",
        }

    @admin_router.delete("/credentials")
    async def delete_credentials(
        request: Request,
        x_maestro_csrf_token: str | None = Header(None, alias="X-Maestro-CSRF-Token"),
    ) -> dict[str, Any]:
        """Remove a chave de API da memória volátil do backend."""
        await _enforce_admin_security(request, x_maestro_csrf_token)
        provider = request.query_params.get("provider", "openai")
        if provider != "openai":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "UNSUPPORTED_PROVIDER", "message": "Provedor não suportado."},
            )
        control_state.remove_credential(provider)
        return {
            "provider": provider,
            "status": "not_registered",
            "message": "Credencial removida com sucesso.",
        }

    @admin_router.post("/credentials/verify")
    async def verify_credentials(
        request: Request,
        x_maestro_csrf_token: str | None = Header(None, alias="X-Maestro-CSRF-Token"),
    ) -> dict[str, Any]:
        """Verifica a credencial via listagem neutra de modelos (zero custo de geração)."""
        await _enforce_admin_security(request, x_maestro_csrf_token)
        openai_cred = control_state.credentials.get("openai", {})
        api_key = openai_cred.get("api_key")

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "NO_CREDENTIAL",
                    "message": "Nenhuma credencial cadastrada para verificação.",
                },
            )

        client = AsyncOpenAI(api_key=api_key, max_retries=0)
        try:
            response_models = await client.models.list()
            model_ids = [m.id for m in response_models.data if hasattr(m, "id")]
            relevant_models = sorted(
                [m for m in model_ids if any(k in m for k in ("gpt-4", "o1", "gpt-3.5"))]
            )
            final_models = relevant_models if relevant_models else model_ids[:20]

            control_state.update_credential_status(
                "openai",
                "verified",
                message="Credencial verificada com sucesso via consulta oficial de modelos.",
                models=final_models,
            )
            return {
                "provider": "openai",
                "status": "verified",
                "models": final_models,
                "message": "Credencial verificada com sucesso. Modelos disponíveis atualizados.",
            }
        except AuthenticationError:
            control_state.update_credential_status(
                "openai",
                "access_denied",
                message="Acesso recusado pelo provedor. Verifique se a chave está correta.",
            )
            return {
                "provider": "openai",
                "status": "access_denied",
                "message": "Acesso recusado pelo provedor (chave inválida ou não autorizada).",
            }
        except PermissionDeniedError:
            control_state.update_credential_status(
                "openai",
                "access_denied",
                message="Permissão negada pelo provedor para a credencial informada.",
            )
            return {
                "provider": "openai",
                "status": "access_denied",
                "message": "Permissão negada pelo provedor.",
            }
        except RateLimitError as error:
            error_str = str(error).lower()
            if "quota" in error_str or "insufficient" in error_str:
                control_state.update_credential_status(
                    "openai",
                    "insufficient_quota",
                    message="Sem saldo ou cota de uso excedida na conta do provedor.",
                )
                return {
                    "provider": "openai",
                    "status": "insufficient_quota",
                    "message": "Sem saldo ou cota excedida no provedor.",
                }
            control_state.update_credential_status(
                "openai",
                "verification_unavailable",
                message="Limite de taxa atingido durante a verificação.",
            )
            return {
                "provider": "openai",
                "status": "verification_unavailable",
                "message": "Limite de taxa atingido ao verificar credencial.",
            }
        except (APIConnectionError, APITimeoutError):
            control_state.update_credential_status(
                "openai",
                "verification_unavailable",
                message="Não foi possível conectar ao provedor. Verifique sua conexão.",
            )
            return {
                "provider": "openai",
                "status": "verification_unavailable",
                "message": "Verificação indisponível (falha de rede ou timeout com o provedor).",
            }
        except Exception as err:
            control_state.update_credential_status(
                "openai",
                "verification_unavailable",
                message=f"Falha inesperada na verificação: {type(err).__name__}",
            )
            return {
                "provider": "openai",
                "status": "verification_unavailable",
                "message": "Verificação indisponível devido a erro inesperado.",
            }

    @admin_router.get("/models")
    async def list_models() -> dict[str, Any]:
        """Retorna os modelos reconhecidos para o adaptador operacional."""
        openai_cred = control_state.credentials.get("openai", {})
        models = openai_cred.get("models", KNOWN_OPENAI_MODELS)
        return {
            "provider": "openai",
            "models": models,
            "verified": openai_cred.get("status") == "verified",
        }

    @admin_router.post("/routes")
    async def add_or_update_route(
        request: Request,
        x_maestro_csrf_token: str | None = Header(None, alias="X-Maestro-CSRF-Token"),
    ) -> dict[str, Any]:
        """Cadastra ou atualiza uma rota após validação exaustiva de tipos e dados."""
        await _enforce_admin_security(request, x_maestro_csrf_token)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_JSON", "message": "Corpo JSON inválido."},
            )

        # Validação integral dos dados ANTES de qualquer modificação de estado (Item 5).
        validated_route = _validate_route_payload(body)

        with control_state._lock:
            existing_idx = next(
                (i for i, r in enumerate(control_state.routes_raw) if r.get("route_id") == validated_route["route_id"]),
                None,
            )
            if existing_idx is not None:
                control_state.routes_raw[existing_idx] = validated_route
            else:
                control_state.routes_raw.append(validated_route)
            control_state._rebuild_runtime_locked()

        return {"status": "success", "route": validated_route}

    @admin_router.patch("/routes/{route_id}/toggle")
    async def toggle_route(
        route_id: str,
        request: Request,
        x_maestro_csrf_token: str | None = Header(None, alias="X-Maestro-CSRF-Token"),
    ) -> dict[str, Any]:
        """Alterna a habilitação de uma rota na configuração ativa."""
        await _enforce_admin_security(request, x_maestro_csrf_token)
        with control_state._lock:
            target = next(
                (r for r in control_state.routes_raw if r.get("route_id") == route_id),
                None,
            )
            if not target:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "ROUTE_NOT_FOUND", "message": f"Rota {route_id} não encontrada."},
                )
            target["enabled"] = not target.get("enabled", True)
            new_enabled = target["enabled"]
            control_state._rebuild_runtime_locked()

        return {"route_id": route_id, "enabled": new_enabled}

    @admin_router.delete("/routes/{route_id}")
    async def delete_route(
        route_id: str,
        request: Request,
        x_maestro_csrf_token: str | None = Header(None, alias="X-Maestro-CSRF-Token"),
    ) -> dict[str, Any]:
        """Remove uma rota da configuração ativa."""
        await _enforce_admin_security(request, x_maestro_csrf_token)
        with control_state._lock:
            existing = any(r.get("route_id") == route_id for r in control_state.routes_raw)
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "ROUTE_NOT_FOUND", "message": f"Rota {route_id} não encontrada."},
                )
            control_state.routes_raw = [
                r for r in control_state.routes_raw if r.get("route_id") != route_id
            ]
            control_state._rebuild_runtime_locked()
        return {"status": "deleted", "route_id": route_id}

    @admin_router.post("/preview")
    async def preview_routing(request: Request) -> dict[str, Any]:
        """Prévia explicável de decisão sem acionamento externo (zero custo de tokens)."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_JSON", "message": "Corpo JSON inválido."},
            )

        task = body.get("task", "")
        if not isinstance(task, str) or not task.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_TASK", "message": "task é obrigatória para obter sugestão."},
            )

        track_raw = body.get("track")
        if track_raw is None:
            track: TrackType = "economica"
        elif track_raw not in {"free", "economica", "inteligente"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_TRACK",
                    "message": (
                        f"Trilha '{track_raw}' não é suportada. "
                        "As trilhas válidas são: 'free', 'economica' e 'inteligente'."
                    ),
                },
            )
        else:
            track = track_raw

        constraints_input = body.get("constraints") or {}
        req_kwargs: dict[str, Any] = {"task": task}
        if "context" in body and body["context"]:
            req_kwargs["context"] = body["context"]
        if constraints_input:
            req_kwargs["constraints"] = constraints_input

        try:
            exec_req = ExecutionRequest.model_validate(req_kwargs)
        except ValidationError as err:
            return _invalid_request(_validation_issues(err))
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_REQUEST", "message": f"Restrições inválidas: {err}"},
            )

        catalog_snapshot = control_state.current_catalog.snapshot()
        all_routes_count = len(catalog_snapshot)
        has_api_key = bool(control_state.credentials.get("openai", {}).get("api_key"))

        # Apresentação realista e auditável das políticas de trilha
        track_policies = {
            "free": "Trilha Free: aceita exclusivamente candidatos com gratuidade declarada pelo operador (tarifas e estimativa prévia calculada iguais a zero). Não atesta faturamento real no provedor externo.",
            "economica": "Trilha Econômica: aplica a estratégia canônica de menor custo estimado entre todos os candidatos elegíveis com dados econômicos comparáveis.",
            "inteligente": "Trilha Inteligente: aplica estritamente os critérios de qualidade obrigatórios (required_quality_criteria) com evidências documentadas, selecionando o menor custo entre as rotas qualificadas.",
        }

        # Tratamento da Trilha Free (Bloqueador 1):
        # Exclui ativamente qualquer rota que não tenha gratuidade declarada pelo operador.
        if track == "free":
            free_candidates: list[Route] = []
            exclusions: list[dict[str, str]] = []

            for r in catalog_snapshot:
                if is_operator_declared_free_route(r):
                    free_candidates.append(r)
                else:
                    reason_desc = (
                        f"{r.id} foi excluída por possuir tarifas declaradas maiores que zero "
                        "(incompatível com a trilha Free)."
                        if (r.price_reference and any(Decimal(rt.rate) > Decimal("0") for rt in r.price_reference.rates))
                        else f"{r.id} foi excluída por não possuir gratuidade declarada pelo operador (tarifas ausentes ou estimativa indisponível na trilha Free)."
                    )
                    exclusions.append({
                        "route_id": r.id,
                        "reason": "paid_or_unknown_cost",
                        "description": reason_desc,
                    })

            if not free_candidates:
                return {
                    "track": "free",
                    "policy_description": track_policies["free"],
                    "recommended_route": None,
                    "candidate_evaluations": [
                        {"route_id": e["route_id"], "status": "excluded", "reason": e["description"]}
                        for e in exclusions
                    ],
                    "factors": [
                        {
                            "category": "economic",
                            "description": "Trilha Free: exige tarifas e estimativas declaradas em zero pelo operador. Não confirma faturamento real na conta do provedor.",
                        }
                    ],
                    "exclusions": exclusions,
                    "economic_data_status": "Nenhum candidato com gratuidade declarada pelo operador.",
                    "billing_warning": False,
                    "explanation": (
                        "A trilha Free requer gratuidade declarada pelo operador (tarifas e estimativas calculadas iguais a zero). "
                        "Todas as rotas configuradas atualmente possuem tarifas positivas ou dados econômicos indisponíveis. "
                        "Aviso: o Maestro Router não valida faturamento real junto ao provedor. "
                        "Selecione a trilha 'Econômica' ou 'Inteligente' para utilizar as rotas configuradas."
                    ),
                }

            # Avalia se os candidatos gratuitos atendem às restrições adicionais do usuário (ex: capacidades)
            filtered_free_catalog = RouteCatalog(
                free_candidates,
                operational_constraints=OperationalConstraints(
                    allowed_route_ids=frozenset(r.id for r in free_candidates)
                ),
            )
            routing_decision = route_request(exec_req, filtered_free_catalog)
            if isinstance(routing_decision, SelectedDecision):
                selected = routing_decision.selected_routes[0]
                return {
                    "track": "free",
                    "policy_description": track_policies["free"],
                    "recommended_route": {
                        "route_id": selected.id,
                        "provider": selected.provider,
                        "model": selected.model,
                        "estimate": {"amount": "0.0000", "currency": selected.estimate.currency or "USD", "status": "available"},
                        "price_reference": {"id": selected.price_reference.id, "currency": selected.price_reference.currency} if selected.price_reference else None,
                        "justification": f"{selected.id} foi selecionada com base em gratuidade declarada pelo operador na trilha Free.",
                    },
                    "candidate_evaluations": [
                        {"route_id": selected.id, "status": "selected", "reason": "Gratuidade declarada pelo operador e requisitos satisfeitos."}
                    ] + [
                        {"route_id": e["route_id"], "status": "excluded", "reason": e["description"]}
                        for e in exclusions
                    ],
                    "factors": [{"category": f.category, "description": f.description} for f in routing_decision.factors],
                    "exclusions": exclusions,
                    "economic_data_status": "Gratuidade declarada pelo operador (0.0000 USD).",
                    "billing_warning": False,
                    "explanation": (
                        f"{selected.id} atende a todas as restrições da tarefa e possui gratuidade declarada pelo operador "
                        "(tarifas e estimativa calculada iguais a zero). Aviso: cabe ao operador validar condições de faturamento junto ao provedor."
                    ),
                }
            else:
                # Candidatos gratuitos existiam, mas foram eliminados por restrições da tarefa (ex: capacidade ausente)
                refusal_data = routing_decision.model_dump()
                return {
                    "track": "free",
                    "policy_description": track_policies["free"],
                    "recommended_route": None,
                    "candidate_evaluations": [
                        {"route_id": e["route_id"], "status": "excluded", "reason": e["description"]}
                        for e in exclusions
                    ],
                    "factors": refusal_data.get("decision", {}).get("factors", []),
                    "exclusions": exclusions,
                    "economic_data_status": "Rotas com gratuidade declarada existentes são incompatíveis com os requisitos da tarefa.",
                    "billing_warning": False,
                    "explanation": (
                        "As rotas com gratuidade declarada pelo operador foram excluídas por não atenderem aos requisitos da tarefa "
                        "(ex.: capacidades exigidas ou critérios ausentes). Rotas pagas permanecem estritamente excluídas na trilha Free."
                    ),
                    "refusal_code": refusal_data.get("error", {}).get("code"),
                }

        # Para as trilhas Econômica e Inteligente:
        # Se não há chave de API cadastrada, as rotas externas não possuem associação válida de execução.
        locally_invalid_ids = frozenset()
        invalid_exec_ids = frozenset()
        if not has_api_key:
            invalid_exec_ids = frozenset(r.id for r in catalog_snapshot if r.enabled)
            locally_invalid_ids = invalid_exec_ids

        routing_decision = route_request(
            exec_req,
            control_state.current_catalog,
            locally_invalid_route_ids=locally_invalid_ids,
            invalid_execution_route_ids=invalid_exec_ids,
        )

        if isinstance(routing_decision, SelectedDecision):
            selected = routing_decision.selected_routes[0]
            est_status = (
                f"{selected.estimate.amount} {selected.estimate.currency}"
                if selected.estimate and selected.estimate.amount
                else "Estimativa indisponível"
            )
            explanation = routing_decision.reason
            if track == "inteligente":
                has_req_quality = bool(
                    exec_req.constraints and exec_req.constraints.required_quality_criteria
                )
                if not has_req_quality:
                    explanation += (
                        " (Nota: nenhum critério de qualidade foi especificado na solicitação; "
                        "a seleção aplicou elegibilidade técnica e menor custo estimado padrão)."
                    )

            return {
                "track": track,
                "policy_description": track_policies[track],
                "recommended_route": {
                    "route_id": selected.id,
                    "provider": selected.provider,
                    "model": selected.model,
                    "estimate": {
                        "amount": selected.estimate.amount if selected.estimate else None,
                        "currency": selected.estimate.currency if selected.estimate else None,
                        "status": selected.estimate.status if selected.estimate else "unavailable",
                    },
                    "price_reference": (
                        {
                            "id": selected.price_reference.id,
                            "currency": selected.price_reference.currency,
                        }
                        if selected.price_reference
                        else None
                    ),
                    "justification": selected.id + " foi selecionada segundo as regras de elegibilidade e custo.",
                },
                "candidate_evaluations": [
                    {
                        "route_id": r.id,
                        "status": "selected" if r.id == selected.id else "compared",
                        "reason": f"Rota avaliada segundo {routing_decision.strategy_id}.",
                    }
                    for r in routing_decision.selectable_routes
                ],
                "factors": [
                    {"category": f.category, "description": f.description}
                    for f in routing_decision.factors
                ],
                "exclusions": [],
                "economic_data_status": f"Referência de preço ativa; estimativa: {est_status}.",
                "billing_warning": selected.provider != "local" and not is_operator_declared_free_route(selected),
                "explanation": explanation,
            }
        else:
            refusal_data = routing_decision.model_dump()
            error_info = refusal_data.get("error", {})
            factors_info = refusal_data.get("decision", {}).get("factors", [])
            exclusions_info = [
                {"route_id": f.get("description", ""), "reason": f.get("category", "")}
                for f in factors_info
                if f.get("category") in {"route", "configuration"}
            ]

            explanation = error_info.get("message", "Nenhuma rota elegível.")
            if all_routes_count == 0:
                explanation = "Falta configurar uma rota de IA. O catálogo de rotas está vazio."
            elif not has_api_key:
                explanation = "A chave de API do provedor não está cadastrada na memória do servidor."

            return {
                "track": track,
                "policy_description": track_policies[track],
                "recommended_route": None,
                "candidate_evaluations": [],
                "factors": factors_info,
                "exclusions": exclusions_info,
                "economic_data_status": "Dados econômicos não avaliados devido à recusa de elegibilidade.",
                "billing_warning": False,
                "explanation": explanation,
                "refusal_code": error_info.get("code"),
            }

    @admin_router.post("/executions")
    async def admin_execute(
        request: Request,
        x_maestro_csrf_token: str | None = Header(None, alias="X-Maestro-CSRF-Token"),
    ) -> Response:
        """Execução operacional governada pela trilha selecionada no Control Center (ADR 0012).

        Fronteira administrativa local estritamente separada de POST /v1/executions (docs/05-API.md).
        Reutiliza integralmente o motor neutro de roteamento (routing.py) e os adaptadores de execução
        sem duplicar o motor nem alterar a semântica da API pública v1 (Bloqueador 2).
        """
        await _enforce_admin_security(request, x_maestro_csrf_token)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_JSON", "message": "Corpo JSON inválido."},
            )

        if not isinstance(body, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_JSON", "message": "O corpo deve ser um objeto JSON."},
            )

        task = body.get("task")
        if not _is_structurally_valid_string(task):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_TASK", "message": "task é obrigatória e deve ser uma string não vazia."},
            )

        context = body.get("context")
        if context is not None and not isinstance(context, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_CONTEXT", "message": "context deve ser uma string quando fornecido."},
            )

        exec_payload: dict[str, Any] = {"task": task}
        if context is not None and context.strip():
            exec_payload["context"] = context
        if "constraints" in body and body["constraints"]:
            exec_payload["constraints"] = body["constraints"]

        try:
            execution_request = ExecutionRequest.model_validate(exec_payload)
        except ValidationError as val_err:
            return _invalid_request(_validation_issues(val_err))
        except Exception as val_err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_CONSTRAINTS", "message": f"Restrições inválidas: {val_err}"},
            )

        track_raw = body.get("track")
        if track_raw is None:
            track: TrackType = "economica"
        elif track_raw not in {"free", "economica", "inteligente"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_TRACK",
                    "message": (
                        f"Trilha '{track_raw}' não é suportada. "
                        "As trilhas válidas são: 'free', 'economica' e 'inteligente'."
                    ),
                },
            )
        else:
            track = track_raw

        catalog_snapshot = control_state.current_catalog.snapshot()
        adapter_snapshot = _snapshot_adapters(
            control_state.current_catalog, control_state.current_adapters
        )
        enabled_routes = tuple(route for route in catalog_snapshot if route.enabled)
        has_api_key = bool(control_state.credentials.get("openai", {}).get("api_key"))

        # Sem chave de API cadastrada, rotas externas não possuem execução válida -> 422 NO_ELIGIBLE_ROUTE
        if not has_api_key or not enabled_routes:
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "NO_ELIGIBLE_ROUTE",
                        "message": "Nenhuma rota configurada, habilitada e válida satisfaz as restrições aplicáveis.",
                    },
                    "decision": {
                        "outcome": "refused",
                        "strategy": {"id": "lowest-estimated-cost", "applied": False},
                        "applied_constraints": [],
                        "reason": "Nenhuma rota habilitada possui credencial/adaptador configurado no ambiente local.",
                        "factors": [
                            {
                                "category": "route",
                                "description": "Nenhuma chave de API está cadastrada na memória do servidor.",
                            }
                        ],
                        "exclusions": [
                            {
                                "route_id": r.id,
                                "reason": "missing_credential",
                                "description": f"{r.id} está desabilitada por ausência de credencial de API.",
                            }
                            for r in catalog_snapshot
                        ],
                    },
                },
            )

        catalog_invalid_ids = frozenset(
            route.id
            for route in enabled_routes
            if not _is_valid_adapter(adapter_snapshot.get(route.adapter_id))
        )
        locally_invalid_ids = catalog_invalid_ids | getattr(
            control_state.current_catalog, "configuration_invalid_route_ids", frozenset()
        )

        base_constraints = getattr(
            control_state.current_catalog, "operational_constraints", None
        ) or OperationalConstraints()

        # Trilha Free: restrição estrita a rotas com gratuidade declarada pelo operador
        if track == "free":
            free_candidates = tuple(
                r for r in catalog_snapshot if is_operator_declared_free_route(r)
            )
            if not free_candidates:
                # Recusa imediata sem acionar provedor externo nem realizar fallback para rotas pagas
                return JSONResponse(
                    status_code=422,
                    content={
                        "error": {
                            "code": "NO_ELIGIBLE_ROUTE",
                            "message": (
                                "Nenhuma rota com gratuidade declarada pelo operador está disponível. "
                                "A trilha Free exige que todas as tarifas declaradas e estimativas calculadas sejam 0.00. "
                                "Rotas com tarifas positivas ou estimativas indisponíveis permanecem estritamente excluídas."
                            ),
                        },
                        "decision": {
                            "outcome": "refused",
                            "strategy": {"id": "lowest-estimated-cost", "applied": False},
                            "applied_constraints": [],
                            "reason": "Nenhuma rota no catálogo possui gratuidade declarada pelo operador.",
                            "factors": [
                                {
                                    "category": "economics",
                                    "description": "Trilha Free: exige tarifas e estimativas declaradas em zero pelo operador. Não confirma faturamento real na conta do provedor.",
                                }
                            ],
                            "exclusions": [
                                {
                                    "route_id": r.id,
                                    "reason": "paid_or_unknown_cost",
                                    "description": f"{r.id} foi excluída por não possuir tarifas e estimativa declaradas em zero pelo operador.",
                                }
                                for r in catalog_snapshot
                            ],
                        },
                    },
                )

            free_ids = frozenset(r.id for r in free_candidates)
            free_constraints = OperationalConstraints(
                required_capabilities=base_constraints.required_capabilities,
                required_quality_criteria=base_constraints.required_quality_criteria,
                allowed_route_ids=free_ids,
                max_estimated_costs=base_constraints.max_estimated_costs,
                defaults=base_constraints.defaults,
            )

            routing_result = route_request(
                execution_request,
                control_state.current_catalog,
                operational_constraints=free_constraints,
                locally_invalid_route_ids=locally_invalid_ids,
                invalid_execution_route_ids=catalog_invalid_ids,
            )

            if isinstance(routing_result, SelectedDecision):
                # Defesa em profundidade: impede terminantemente fallback para rota tarifada
                if not is_operator_declared_free_route(routing_result.route):
                    return JSONResponse(
                        status_code=422,
                        content={
                            "error": {
                                "code": "NO_ELIGIBLE_ROUTE",
                                "message": "A rota selecionada não satisfaz a exigência de gratuidade declarada na trilha Free.",
                            }
                        },
                    )
                return await _execute_selection(execution_request, routing_result, adapter_snapshot)

            return JSONResponse(
                status_code=422,
                content=routing_result.model_dump(exclude_none=True),
            )

        # Trilhas Econômica e Inteligente:
        routing_result = route_request(
            execution_request,
            control_state.current_catalog,
            operational_constraints=base_constraints,
            locally_invalid_route_ids=locally_invalid_ids,
            invalid_execution_route_ids=catalog_invalid_ids,
        )

        if isinstance(routing_result, SelectedDecision):
            return await _execute_selection(execution_request, routing_result, adapter_snapshot)

        return JSONResponse(
            status_code=422,
            content=routing_result.model_dump(exclude_none=True),
        )

    app.include_router(admin_router)
    return app


app = create_control_center_app()

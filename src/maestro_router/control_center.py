"""Administrative layer and operational composition for Maestro Control Center.

This module provides a local, optional administrative layer that enables safe
in-memory credential management, route configuration, and explainable previews
(recommendations) for the Control Center, while preserving the neutral public
execution contract from docs/05-API.md intact.
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
from fastapi.responses import JSONResponse
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)

from .adapters import OpenAIResponsesAdapter
from .api import create_app
from .contracts import (
    CURRENCY_PATTERN,
    DECIMAL_PATTERN,
    ExecutionRequest,
    ExecutionSuccessResponse,
)
from .economics import PriceReference, calculate_pre_execution_amount
from .execution import ExecutionAdapter
from .routing import (
    EconomicEstimate,
    Exclusion,
    MoneyCeiling,
    OperationalConstraints,
    OperationalDefaults,
    Route,
    RouteCatalog,
    SelectedDecision,
    route_request,
)
from .bootstrap import (
    _parse_estimated_usage,
    _parse_price_reference,
    _parse_routing_constraints,
    _parse_unique_string_list,
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

DEFAULT_GPT4O_MINI_PRICE_REFERENCE = {
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

DEFAULT_GPT4O_MINI_ESTIMATED_USAGE = {
    "input_token": 1500,
    "output_token": 500,
    "applicability_confirmed": True,
}


class ControlCenterState:
    """Thread-safe in-memory state for the Control Center operational runtime."""

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
        self.routes_raw: list[dict[str, Any]] = [
            {
                "route_id": "route-openai-gpt4o-mini",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "enabled": True,
                "known_unavailable": False,
                "capabilities": ["text_generation", "summarization"],
                "quality_criteria": [
                    {
                        "criterion": "summary_faithfulness_accepted",
                        "evidence_references": ["benchmark-q3-2026"],
                    }
                ],
                "price_reference": DEFAULT_GPT4O_MINI_PRICE_REFERENCE,
                "estimated_usage": DEFAULT_GPT4O_MINI_ESTIMATED_USAGE,
            }
        ]
        self.current_catalog: RouteCatalog = RouteCatalog()
        self.current_adapters: dict[str, ExecutionAdapter] = {}
        self._rebuild_runtime_locked()

    def rebuild_runtime(self) -> None:
        with self._lock:
            self._rebuild_runtime_locked()

    def _rebuild_runtime_locked(self) -> None:
        """Construct immutable RouteCatalog and ExecutionAdapters from active state."""
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

            enabled = entry.get("enabled", True)
            model = entry.get("model")
            provider = entry.get("provider", "openai")
            known_unavailable = bool(entry.get("known_unavailable", False))

            capabilities = frozenset(entry.get("capabilities", []))
            qc_raw = entry.get("quality_criteria", [])
            qc_set: set[str] = set()
            qc_refs: dict[str, tuple[str, ...]] = {}
            for item in qc_raw:
                if isinstance(item, dict) and "criterion" in item:
                    c = item["criterion"]
                    refs = item.get("evidence_references", [])
                    qc_set.add(c)
                    qc_refs[c] = tuple(sorted(refs))
                elif isinstance(item, str):
                    qc_set.add(item)
                    qc_refs[item] = ()

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
            if not enabled:
                estimate = EconomicEstimate(
                    status="unavailable",
                    reason=_DISABLED_ROUTE_ESTIMATE_REASON,
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

            # Build route
            route = Route(
                id=route_id,
                provider=provider,
                model=model or "unknown",
                adapter_id="openai-responses",
                enabled=bool(enabled),
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
            # Constant-time comparison to prevent timing attacks
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
    """RouteCatalog proxy that forwards calls to the current active catalog snapshot."""

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
        return getattr(self._state.current_catalog, "operational_constraints", None)


class DynamicAdapterRegistry(Mapping[str, ExecutionAdapter]):
    """Mapping proxy that dynamically delegates adapter lookups to the active registry."""

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
    """Validate that requests originate from local browser loopback origins."""
    if origin is None:
        return True
    try:
        parsed = urlparse(origin)
        hostname = (parsed.hostname or "").lower()
        return hostname in {"localhost", "127.0.0.1", "::1"}
    except Exception:
        return False


def create_control_center_app(state: ControlCenterState | None = None) -> FastAPI:
    """Create the Maestro Control Center FastAPI application with admin layer."""
    control_state = state if state is not None else ControlCenterState()

    dynamic_catalog = DynamicRouteCatalog(control_state)
    dynamic_adapters = DynamicAdapterRegistry(control_state)

    # Core execution application exposing POST /v1/executions in strict compliance with docs/05-API.md
    app = create_app(catalog=dynamic_catalog, adapters=dynamic_adapters)

    admin_router = APIRouter(prefix="/admin", tags=["Control Center Admin"])

    async def _enforce_admin_security(
        request: Request,
        x_maestro_csrf_token: str | None = Header(None, alias="X-Maestro-CSRF-Token"),
    ) -> None:
        """Validate CSRF token, Origin, and Session on administrative mutating actions."""
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
        """Obtain or refresh a secure local administrative session and CSRF token."""
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
        """Return safe metadata of registered providers, credentials status, and routes."""
        return control_state.get_safe_config()

    @admin_router.post("/credentials")
    async def set_credentials(
        request: Request,
        x_maestro_csrf_token: str | None = Header(None, alias="X-Maestro-CSRF-Token"),
    ) -> dict[str, Any]:
        """Register or replace an API key in backend memory without persistence."""
        await _enforce_admin_security(request, x_maestro_csrf_token)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_JSON", "message": "Corpo JSON inválido."},
            )

        provider = body.get("provider")
        api_key = body.get("api_key")

        if provider != "openai":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "UNSUPPORTED_PROVIDER",
                    "message": "Apenas o provedor 'openai' possui adaptador implementado no MVP atual.",
                },
            )

        if not isinstance(api_key, str) or not api_key.strip():
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
        """Remove an API key from backend memory."""
        await _enforce_admin_security(request, x_maestro_csrf_token)
        provider = request.query_params.get("provider", "openai")
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
        """Explicitly verify the registered credential via lightweight model listing (zero paid generation)."""
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
            # Lightweight call that fetches official models list without generating tokens or charging costs
            response_models = await client.models.list()
            model_ids = [m.id for m in response_models.data if hasattr(m, "id")]
            # Filter for common chat/completion models to make UI useful
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
        """Return the available models for the operational adapter."""
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
        """Create or update a route in the Control Center active configuration."""
        await _enforce_admin_security(request, x_maestro_csrf_token)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_JSON", "message": "Corpo JSON inválido."},
            )

        route_id = body.get("route_id")
        model = body.get("model")
        if not _is_structurally_valid_string(route_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_ROUTE_ID",
                    "message": "route_id é obrigatório e deve ser um identificador textual válido.",
                },
            )
        if not _is_structurally_valid_string(model):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_MODEL",
                    "message": "model é obrigatório e deve ser um identificador válido.",
                },
            )

        with control_state._lock:
            existing_idx = next(
                (i for i, r in enumerate(control_state.routes_raw) if r.get("route_id") == route_id),
                None,
            )
            route_data = {
                "route_id": route_id,
                "provider": body.get("provider", "openai"),
                "model": model,
                "enabled": bool(body.get("enabled", True)),
                "known_unavailable": bool(body.get("known_unavailable", False)),
                "capabilities": list(body.get("capabilities", ["text_generation"])),
                "quality_criteria": list(body.get("quality_criteria", [])),
                "price_reference": body.get(
                    "price_reference", DEFAULT_GPT4O_MINI_PRICE_REFERENCE
                ),
                "estimated_usage": body.get(
                    "estimated_usage", DEFAULT_GPT4O_MINI_ESTIMATED_USAGE
                ),
            }
            if existing_idx is not None:
                control_state.routes_raw[existing_idx] = route_data
            else:
                control_state.routes_raw.append(route_data)
            control_state._rebuild_runtime_locked()

        return {"status": "success", "route": route_data}

    @admin_router.patch("/routes/{route_id}/toggle")
    async def toggle_route(
        route_id: str,
        request: Request,
        x_maestro_csrf_token: str | None = Header(None, alias="X-Maestro-CSRF-Token"),
    ) -> dict[str, Any]:
        """Quickly enable or disable a route in active configuration."""
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
        """Remove a route from active configuration."""
        await _enforce_admin_security(request, x_maestro_csrf_token)
        with control_state._lock:
            control_state.routes_raw = [
                r for r in control_state.routes_raw if r.get("route_id") != route_id
            ]
            control_state._rebuild_runtime_locked()
        return {"status": "deleted", "route_id": route_id}

    @admin_router.post("/preview")
    async def preview_routing(request: Request) -> dict[str, Any]:
        """Explainable routing preview without executing the external provider (zero cost)."""
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

        track: TrackType = body.get("track", "economica")
        if track not in {"free", "economica", "inteligente"}:
            track = "economica"

        constraints_input = body.get("constraints") or {}
        # Construct standard ExecutionRequest to reuse Maestro's pure routing engine
        req_kwargs: dict[str, Any] = {"task": task}
        if "context" in body and body["context"]:
            req_kwargs["context"] = body["context"]
        if constraints_input:
            req_kwargs["constraints"] = constraints_input

        try:
            exec_req = ExecutionRequest.model_validate(req_kwargs)
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_REQUEST", "message": f"Restrições inválidas: {err}"},
            )

        # Snapshot active routes
        catalog_snapshot = control_state.current_catalog.snapshot()
        all_routes_count = len(catalog_snapshot)

        has_api_key = bool(control_state.credentials.get("openai", {}).get("api_key"))

        # Policy descriptions
        track_policies = {
            "free": "Trilha Free: aceita exclusivamente candidatos cuja gratuidade esteja comprovada por referência de preço com taxas zero e condições documentadas.",
            "economica": "Trilha Econômica: aplica a estratégia canônica de menor custo estimado entre todos os candidatos elegíveis com dados econômicos comparáveis.",
            "inteligente": "Trilha Inteligente: avalia requisitos da tarefa e critérios de qualidade documentados, priorizando rotas com evidências técnicas comprovadas e menor custo.",
        }

        # Handling Track Free
        if track == "free":
            # Check if any route has proven 0-cost
            free_candidates: list[Route] = []
            exclusions: list[dict[str, str]] = []
            for r in catalog_snapshot:
                is_free = False
                if r.price_reference:
                    rates = r.price_reference.rates
                    if rates and all(rate.rate == Decimal("0") for rate in rates):
                        is_free = True
                if r.estimate and r.estimate.amount in {"0", "0.0", "0.00", "0.0000"}:
                    is_free = True

                if is_free:
                    free_candidates.append(r)
                else:
                    exclusions.append(
                        {
                            "route_id": r.id,
                            "reason": "paid_route",
                            "description": f"{r.id} foi excluída porque possui custo associado maior que zero (incompatível com a trilha Free).",
                        }
                    )

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
                            "description": "Nenhuma rota gratuita comprovada está disponível na configuração ativa.",
                        }
                    ],
                    "exclusions": exclusions,
                    "economic_data_status": "Nenhum candidato com gratuidade comprovada.",
                    "billing_warning": False,
                    "explanation": (
                        "A trilha Free requer comprovação de custo zero. "
                        "Todas as rotas configuradas atualmente possuem custos associados. "
                        "Selecione a trilha 'Econômica' ou 'Inteligente' para utilizar as rotas configuradas."
                    ),
                }

        # For track economica or inteligente, run route_request against catalog
        locally_invalid_ids = frozenset()
        invalid_exec_ids = frozenset()
        if not has_api_key:
            # If no API key is present in memory, all external adapter routes are missing adapter association
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
                    "justification": routing_decision.reason,
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
                "economic_data_status": f"Referência auditável de preço ativa; estimativa prévia: {est_status}.",
                "billing_warning": selected.provider != "local" and not (
                    selected.estimate and selected.estimate.amount in {"0", "0.0", "0.0000"}
                ),
                "explanation": routing_decision.reason,
            }
        else:
            # Refusal
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

    app.include_router(admin_router)
    return app


# Module-level default application for Control Center execution:
# e.g.: uvicorn --app-dir src maestro_router.control_center:app --port 8000
app = create_control_center_app()

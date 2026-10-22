"""Unit and integration tests for Maestro Control Center admin layer and operational composition."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from openai import (
    APIConnectionError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)

from maestro_router.control_center import (
    ControlCenterState,
    create_control_center_app,
    INITIAL_GPT4O_MINI_PRICE_REFERENCE,
    INITIAL_GPT4O_MINI_ESTIMATED_USAGE,
)
from maestro_router.execution import (
    NormalizedUsage,
    NormalizedUsageItem,
    TextExecutionResult,
)


@pytest.fixture
def clean_state() -> ControlCenterState:
    state = ControlCenterState()
    # Start with empty credentials and one sample route
    state.credentials["openai"]["api_key"] = None
    state.credentials["openai"]["status"] = "not_registered"
    state.credentials["openai"]["verified_at"] = None
    state.rebuild_runtime()
    return state


@pytest.fixture
def client(clean_state: ControlCenterState) -> TestClient:
    app = create_control_center_app(clean_state)
    return TestClient(app, base_url="http://localhost:8000")


def test_public_execution_endpoint_preserved_refusal_when_no_key(client: TestClient) -> None:
    """The public POST /v1/executions returns 422 NO_ELIGIBLE_ROUTE when no key is configured."""
    resp = client.post(
        "/v1/executions",
        headers={"Content-Type": "application/json"},
        json={"task": "Teste de tarefa inicial sem chave configurada."},
    )
    # Sem chave cadastrada, a rota externa é desabilitada na composição, resultando precisamente em 422 NO_ELIGIBLE_ROUTE
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "NO_ELIGIBLE_ROUTE"
    assert "Nenhuma rota configurada, habilitada e válida" in data["error"]["message"]


def test_public_execution_success_with_adapter(clean_state: ControlCenterState) -> None:
    """When a route and mock adapter are active, POST /v1/executions succeeds with 200."""
    clean_state.set_credential("openai", "sk-test-key-1234567890")
    
    # Mock the adapter execution
    mock_adapter = MagicMock()
    mock_adapter.execute = AsyncMock(
        return_value=TextExecutionResult(
            content="Resposta sintética do modelo de teste.",
            usage=NormalizedUsage(
                status="available",
                items=(
                    NormalizedUsageItem(unit="input_token", quantity=15),
                    NormalizedUsageItem(unit="output_token", quantity=10),
                ),
            ),
        )
    )
    clean_state.current_adapters["openai-responses"] = mock_adapter

    app = create_control_center_app(clean_state)
    local_client = TestClient(app, base_url="http://localhost:8000")

    resp = local_client.post(
        "/v1/executions",
        headers={"Content-Type": "application/json"},
        json={"task": "Explique a importância da neutralidade."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"]["content"] == "Resposta sintética do modelo de teste."
    assert data["decision"]["route"]["id"] == "route-openai-gpt4o-mini"
    assert "economics" in data


def test_session_handshake_and_csrf_protection(client: TestClient) -> None:
    """Mutating admin operations require valid session and CSRF token."""
    # 1. Attempt POST without session/CSRF -> 403 Forbidden
    unauth_resp = client.post(
        "/admin/credentials",
        json={"provider": "openai", "api_key": "sk-secret-123"},
    )
    assert unauth_resp.status_code == 403

    # 2. Perform session handshake
    session_resp = client.get("/admin/session")
    assert session_resp.status_code == 200
    session_data = session_resp.json()
    assert "csrf_token" in session_data
    csrf_token = session_data["csrf_token"]
    assert "maestro_admin_session" in session_resp.cookies

    # 3. Post with valid CSRF header and session cookie
    auth_resp = client.post(
        "/admin/credentials",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={"provider": "openai", "api_key": "sk-secret-valid"},
    )
    assert auth_resp.status_code == 200
    data = auth_resp.json()
    assert data["status"] == "registered"
    assert "sk-secret-valid" not in json.dumps(data)  # Never leak the secret!


def test_admin_config_safe_metadata(client: TestClient, clean_state: ControlCenterState) -> None:
    """GET /admin/config exposes safe operational status without secrets."""
    clean_state.set_credential("openai", "sk-test-secret-do-not-leak")
    resp = client.get("/admin/config")
    assert resp.status_code == 200
    data = resp.json()

    assert "providers" in data
    assert "routes" in data
    assert "models" in data

    openai_prov = next(p for p in data["providers"] if p["id"] == "openai")
    assert openai_prov["implemented"] is True
    assert openai_prov["credential"]["registered"] is True
    assert openai_prov["credential"]["status"] == "registered"

    # Verify no secret leakage
    content_str = json.dumps(data)
    assert "sk-test-secret-do-not-leak" not in content_str


def test_credentials_verify_success(client: TestClient, clean_state: ControlCenterState) -> None:
    """Verifying credentials calls models.list() without text generation."""
    clean_state.set_credential("openai", "sk-valid-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    mock_model_1 = MagicMock()
    mock_model_1.id = "gpt-4o"
    mock_model_2 = MagicMock()
    mock_model_2.id = "gpt-4o-mini"

    mock_models_response = MagicMock()
    mock_models_response.data = [mock_model_1, mock_model_2]

    with patch("maestro_router.control_center.AsyncOpenAI") as mock_openai_cls:
        mock_instance = MagicMock()
        mock_instance.models.list = AsyncMock(return_value=mock_models_response)
        mock_openai_cls.return_value = mock_instance

        verify_resp = client.post(
            "/admin/credentials/verify",
            headers={"X-Maestro-CSRF-Token": csrf_token},
            cookies=session_resp.cookies,
        )
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["status"] == "verified"
        assert "gpt-4o" in data["models"]
        assert clean_state.credentials["openai"]["status"] == "verified"


def test_credentials_verify_access_denied(client: TestClient, clean_state: ControlCenterState) -> None:
    """AuthenticationError maps to status 'access_denied'."""
    clean_state.set_credential("openai", "sk-invalid-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    with patch("maestro_router.control_center.AsyncOpenAI") as mock_openai_cls:
        mock_instance = MagicMock()
        mock_instance.models.list = AsyncMock(
            side_effect=AuthenticationError("Invalid API key", response=MagicMock(status_code=401), body={})
        )
        mock_openai_cls.return_value = mock_instance

        verify_resp = client.post(
            "/admin/credentials/verify",
            headers={"X-Maestro-CSRF-Token": csrf_token},
            cookies=session_resp.cookies,
        )
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["status"] == "access_denied"
        assert clean_state.credentials["openai"]["status"] == "access_denied"


def test_credentials_verify_insufficient_quota(client: TestClient, clean_state: ControlCenterState) -> None:
    """RateLimitError with quota maps to 'insufficient_quota'."""
    clean_state.set_credential("openai", "sk-key-no-balance")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    with patch("maestro_router.control_center.AsyncOpenAI") as mock_openai_cls:
        mock_instance = MagicMock()
        mock_instance.models.list = AsyncMock(
            side_effect=RateLimitError("You exceeded your current quota", response=MagicMock(status_code=429), body={})
        )
        mock_openai_cls.return_value = mock_instance

        verify_resp = client.post(
            "/admin/credentials/verify",
            headers={"X-Maestro-CSRF-Token": csrf_token},
            cookies=session_resp.cookies,
        )
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["status"] == "insufficient_quota"
        assert clean_state.credentials["openai"]["status"] == "insufficient_quota"


def test_credentials_verify_connection_unavailable(client: TestClient, clean_state: ControlCenterState) -> None:
    """APIConnectionError maps to 'verification_unavailable'."""
    clean_state.set_credential("openai", "sk-key-offline")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    with patch("maestro_router.control_center.AsyncOpenAI") as mock_openai_cls:
        mock_instance = MagicMock()
        mock_instance.models.list = AsyncMock(
            side_effect=APIConnectionError(request=MagicMock())
        )
        mock_openai_cls.return_value = mock_instance

        verify_resp = client.post(
            "/admin/credentials/verify",
            headers={"X-Maestro-CSRF-Token": csrf_token},
            cookies=session_resp.cookies,
        )
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["status"] == "verification_unavailable"
        assert clean_state.credentials["openai"]["status"] == "verification_unavailable"


def test_credentials_removal(client: TestClient, clean_state: ControlCenterState) -> None:
    """DELETE /admin/credentials removes the key from memory."""
    clean_state.set_credential("openai", "sk-key-to-delete")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    del_resp = client.delete(
        "/admin/credentials?provider=openai",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
    )
    assert del_resp.status_code == 200
    assert clean_state.credentials["openai"]["api_key"] is None
    assert clean_state.credentials["openai"]["status"] == "not_registered"


def test_route_toggle_and_crud(client: TestClient, clean_state: ControlCenterState) -> None:
    """Admin endpoints can toggle, create, and delete routes."""
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    # Toggle route
    toggle_resp = client.patch(
        "/admin/routes/route-openai-gpt4o-mini/toggle",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
    )
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["enabled"] is False

    # Create new route
    create_resp = client.post(
        "/admin/routes",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={
            "route_id": "route-openai-gpt4o",
            "model": "gpt-4o",
            "provider": "openai",
            "enabled": True,
            "capabilities": ["text_generation", "code_analysis"],
        },
    )
    assert create_resp.status_code == 200
    assert any(r["route_id"] == "route-openai-gpt4o" for r in clean_state.routes_raw)

    # Delete route
    del_route_resp = client.delete(
        "/admin/routes/route-openai-gpt4o",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
    )
    assert del_route_resp.status_code == 200
    assert not any(r["route_id"] == "route-openai-gpt4o" for r in clean_state.routes_raw)


def test_preview_track_free_refusal_when_only_paid_routes(client: TestClient, clean_state: ControlCenterState) -> None:
    """Track Free refuses when all routes have prices > 0."""
    clean_state.set_credential("openai", "sk-active-key")
    preview_resp = client.post(
        "/admin/preview",
        json={"task": "Escreva um poema curto.", "track": "free"},
    )
    assert preview_resp.status_code == 200
    data = preview_resp.json()
    assert data["track"] == "free"
    assert data["recommended_route"] is None
    assert "comprovação estrita de custo zero" in data["explanation"]


def test_preview_track_economica_recommends_route(client: TestClient, clean_state: ControlCenterState) -> None:
    """Track Econômica selects lowest estimated cost route without invoking external provider."""
    clean_state.set_credential("openai", "sk-active-key")
    preview_resp = client.post(
        "/admin/preview",
        json={"task": "Resuma este documento.", "track": "economica"},
    )
    assert preview_resp.status_code == 200
    data = preview_resp.json()
    assert data["track"] == "economica"
    assert data["recommended_route"] is not None
    assert data["recommended_route"]["route_id"] == "route-openai-gpt4o-mini"
    assert "justification" in data["recommended_route"]
    assert len(data["factors"]) > 0


def test_free_execution_without_preview_excludes_paid_routes(clean_state: ControlCenterState) -> None:
    """Regressão 1: Execução na trilha Free sem consultar a prévia recusa rotas pagas.

    Mesmo que o cliente envie a requisição diretamente para POST /v1/executions com o cabeçalho
    X-Maestro-Track: free e exista uma rota habilitada com adaptador ativo, se ela for paga
    (como a rota padrão do GPT-4o-mini), a requisição deve ser recusada com 422 NO_ELIGIBLE_ROUTE
    sem acionar o adaptador do provedor externo.
    """
    clean_state.set_credential("openai", "sk-active-test-key")
    mock_adapter = MagicMock()
    mock_adapter.execute = AsyncMock()
    clean_state.current_adapters["openai-responses"] = mock_adapter

    app = create_control_center_app(clean_state)
    local_client = TestClient(app, base_url="http://localhost:8000")

    resp = local_client.post(
        "/v1/executions",
        headers={
            "Content-Type": "application/json",
            "X-Maestro-Track": "free",
        },
        json={"task": "Gere um texto curto sem custo."},
    )

    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "NO_ELIGIBLE_ROUTE"
    mock_adapter.execute.assert_not_called()


def test_mixed_catalog_free_track_incompatible_free_and_paid_routes(clean_state: ControlCenterState) -> None:
    """Regressão 2: Catálogo misto com rota gratuita incompatível e rota paga.

    Em um catálogo contendo:
    - Rota A (gratuita comprovada, mas com capabilities=['text_generation'])
    - Rota B (paga, com capabilities=['text_generation', 'code_analysis'])

    Quando uma requisição na trilha Free exige 'code_analysis':
    - A rota gratuita é excluída por não atender às restrições da tarefa.
    - A rota paga não pode ser utilizada como fallback silencioso na trilha Free.
    - O resultado deve ser recusa (422 na execução e recommended_route=None na prévia).
    """
    clean_state.set_credential("openai", "sk-active-test-key")

    # Cadastra uma rota comprovadamente gratuita (preço zero e estimativa zero)
    free_route_payload = {
        "route_id": "route-free-model",
        "provider": "openai",
        "model": "gpt-free-model",
        "enabled": True,
        "capabilities": ["text_generation"],
        "price_reference": {
            "id": "pricing-free-model",
            "currency": "USD",
            "version": "2026-01",
            "source": "provider_free_tier",
            "rates": [
                {"unit": "input_token", "rate": "0.0", "base": 1000000},
                {"unit": "output_token", "rate": "0.0", "base": 1000000},
            ],
            "conditions": ["tier:free"],
            "context_complete": True,
            "units_exhaustive": True,
            "no_double_counting": True,
            "model_identity_exact": True,
        },
        "estimated_usage": {
            "input_token": 1000,
            "output_token": 500,
            "applicability_confirmed": True,
        },
    }

    clean_state.routes_raw.append(free_route_payload)
    mock_adapter = MagicMock()
    mock_adapter.execute = AsyncMock()
    clean_state.current_adapters["openai-responses"] = mock_adapter
    clean_state.rebuild_runtime()

    app = create_control_center_app(clean_state)
    local_client = TestClient(app, base_url="http://localhost:8000")

    # 1. Verifica na prévia explicável
    preview_resp = local_client.post(
        "/admin/preview",
        json={
            "task": "Analise o código de alta complexidade.",
            "track": "free",
            "constraints": {"required_capabilities": ["code_analysis"]},
        },
    )
    assert preview_resp.status_code == 200
    preview_data = preview_resp.json()
    assert preview_data["recommended_route"] is None
    assert "Rotas pagas permanecem estritamente excluídas na trilha Free" in preview_data["explanation"]

    # 2. Verifica na execução direta com header X-Maestro-Track
    exec_resp = local_client.post(
        "/v1/executions",
        headers={
            "Content-Type": "application/json",
            "X-Maestro-Track": "free",
        },
        json={
            "task": "Analise o código de alta complexidade.",
            "constraints": {"required_capabilities": ["code_analysis"]},
        },
    )
    assert exec_resp.status_code == 422
    assert exec_resp.json()["error"]["code"] == "NO_ELIGIBLE_ROUTE"
    mock_adapter.execute.assert_not_called()


def test_other_model_without_declared_price_or_usage_remains_unavailable(client: TestClient, clean_state: ControlCenterState) -> None:
    """Regressão 3: Cadastro de outro modelo sem preço ou previsão declarados.

    Garante que cadastrar um modelo diferente de GPT-4o-mini sem dados econômicos explícitos
    não receba preenchimento automático das tarifas ou do perfil de uso do GPT-4o-mini.
    Os dados econômicos devem permanecer explicitamente ausentes/indisponíveis.
    """
    clean_state.set_credential("openai", "sk-active-test-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    # Cadastra gpt-4o sem informar price_reference nem estimated_usage
    create_resp = client.post(
        "/admin/routes",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={
            "route_id": "route-openai-gpt4o",
            "provider": "openai",
            "model": "gpt-4o",
            "enabled": True,
            "capabilities": ["text_generation", "code_analysis"],
        },
    )
    assert create_resp.status_code == 200

    # Consulta configuração segura
    config_resp = client.get("/admin/config")
    assert config_resp.status_code == 200
    config_data = config_resp.json()
    gpt4o_route = next(r for r in config_data["routes"] if r["route_id"] == "route-openai-gpt4o")

    # Verifica que dados econômicos estão nulos e não herdaram o GPT-4o-mini
    assert gpt4o_route["price_reference"] is None
    assert gpt4o_route["estimated_usage"] is None

    # No catálogo em memória, a rota deve existir mas com estimativa indisponível
    snapshot_route = next(r for r in clean_state.current_catalog.snapshot() if r.id == "route-openai-gpt4o")
    assert snapshot_route.price_reference is None
    assert snapshot_route.estimate is not None
    assert snapshot_route.estimate.status == "unavailable"


def test_quality_criteria_without_evidence_reference_rejected(client: TestClient) -> None:
    """Regressão 4: Critério de qualidade sem evidência documentada é rejeitado.

    A camada administrativa deve exigir ao menos uma evidence_reference válida para qualquer
    critério de qualidade fornecido pelo operador, proibindo declarações sem evidência.
    """
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    # 1. Tentativa com lista de evidências vazia
    resp_empty_list = client.post(
        "/admin/routes",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={
            "route_id": "route-invalid-quality-1",
            "provider": "openai",
            "model": "gpt-4o",
            "quality_criteria": [
                {"criterion": "mmlu", "evidence_references": []}
            ],
        },
    )
    assert resp_empty_list.status_code == 400
    assert resp_empty_list.json()["detail"]["code"] == "INVALID_QUALITY_CRITERIA"

    # 2. Tentativa com referência vazia/em branco
    resp_blank_ref = client.post(
        "/admin/routes",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={
            "route_id": "route-invalid-quality-2",
            "provider": "openai",
            "model": "gpt-4o",
            "quality_criteria": [
                {"criterion": "mmlu", "evidence_references": ["   "]}
            ],
        },
    )
    assert resp_blank_ref.status_code == 400
    assert resp_blank_ref.json()["detail"]["code"] == "INVALID_QUALITY_CRITERIA"


def test_first_use_without_key_flow(client: TestClient, clean_state: ControlCenterState) -> None:
    """Regressão 5: Fluxo de primeiro uso sem credencial cadastrada.

    Garante que quando o usuário abre o Control Center sem nenhuma chave:
    - O status em GET /admin/config indica 'not_registered'.
    - POST /v1/executions retorna precisamente 422 NO_ELIGIBLE_ROUTE (sem 500 ou crash).
    - POST /admin/preview retorna recommended_route=None explicando ausência de credencial.
    """
    # 1. Configuração inicial sem chave
    config_resp = client.get("/admin/config")
    assert config_resp.status_code == 200
    openai_prov = next(p for p in config_resp.json()["providers"] if p["id"] == "openai")
    assert openai_prov["credential"]["registered"] is False
    assert openai_prov["credential"]["status"] == "not_registered"

    # 2. Execução direta sem chave
    exec_resp = client.post(
        "/v1/executions",
        headers={"Content-Type": "application/json"},
        json={"task": "Minha primeira execução no onboarding."},
    )
    assert exec_resp.status_code == 422
    assert exec_resp.json()["error"]["code"] == "NO_ELIGIBLE_ROUTE"

    # 3. Prévia sem chave
    preview_resp = client.post(
        "/admin/preview",
        json={"task": "Minha primeira consulta.", "track": "economica"},
    )
    assert preview_resp.status_code == 200
    preview_data = preview_resp.json()
    assert preview_data["recommended_route"] is None
    assert "A chave de API do provedor não está cadastrada" in preview_data["explanation"]


def test_invalid_admin_registration_does_not_mutate_state(client: TestClient, clean_state: ControlCenterState) -> None:
    """Regressão 6: Validação integral antes de modificar estado garante preservação em caso de erro.

    Se o payload contiver dados inválidos (provedor não suportado, tipos inválidos, etc.),
    a requisição é rejeitada e a lista de rotas anterior permanece exatamente inalterada.
    """
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    initial_routes_count = len(clean_state.routes_raw)
    initial_route_ids = [r["route_id"] for r in clean_state.routes_raw]

    # Tentativa com provedor não suportado
    resp_prov = client.post(
        "/admin/routes",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={
            "route_id": "route-anthropic-opus",
            "provider": "anthropic",
            "model": "claude-3-opus",
        },
    )
    assert resp_prov.status_code == 400
    assert resp_prov.json()["detail"]["code"] == "UNSUPPORTED_PROVIDER"

    # Tentativa com tipo inválido para 'enabled'
    resp_type = client.post(
        "/admin/routes",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={
            "route_id": "route-invalid-enabled",
            "provider": "openai",
            "model": "gpt-4o",
            "enabled": "true_as_string",
        },
    )
    assert resp_type.status_code == 400
    assert resp_type.json()["detail"]["code"] == "INVALID_TYPE"

    # Tentativa com route_id em branco
    resp_id = client.post(
        "/admin/routes",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={
            "route_id": "   ",
            "provider": "openai",
            "model": "gpt-4o",
        },
    )
    assert resp_id.status_code == 400
    assert resp_id.json()["detail"]["code"] == "INVALID_ROUTE_ID"

    # Confirma que nenhuma mutação ocorreu no estado
    assert len(clean_state.routes_raw) == initial_routes_count
    assert [r["route_id"] for r in clean_state.routes_raw] == initial_route_ids

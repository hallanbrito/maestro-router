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
    """Track Free recusa quando todas as rotas configuradas possuem tarifas > 0 ou preço ausente."""
    clean_state.set_credential("openai", "sk-active-key")
    preview_resp = client.post(
        "/admin/preview",
        json={"task": "Escreva um poema curto.", "track": "free"},
    )
    assert preview_resp.status_code == 200
    data = preview_resp.json()
    assert data["track"] == "free"
    assert data["recommended_route"] is None
    # Bloqueador 1: terminologia honesta baseada em declaração do operador e aviso de faturamento
    assert "gratuidade declarada pelo operador" in data["explanation"]
    assert "não valida faturamento real" in data["explanation"]


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


def test_public_executions_ignores_track_header(clean_state: ControlCenterState) -> None:
    """Bloqueador 2 (Prova 1): POST /v1/executions ignora qualquer cabeçalho de trilha e preserva o contrato v1.

    O endpoint público /v1/executions não possui conceito de trilhas. Se um cliente enviar
    X-Maestro-Track: free em um ambiente onde apenas uma rota paga está habilitada com adaptador,
    a requisição pública v1 executa normalmente a rota paga configurada com HTTP 200, comprovando
    que o cabeçalho não altera a estratégia do endpoint público.
    """
    clean_state.set_credential("openai", "sk-active-test-key")
    mock_adapter = MagicMock()
    mock_adapter.execute = AsyncMock(
        return_value=TextExecutionResult(
            content="Resposta gerada via contrato público v1.",
            usage=NormalizedUsage(
                status="available",
                items=(
                    NormalizedUsageItem(unit="input_token", quantity=10),
                    NormalizedUsageItem(unit="output_token", quantity=5),
                ),
            ),
        )
    )
    clean_state.current_adapters["openai-responses"] = mock_adapter

    app = create_control_center_app(clean_state)
    local_client = TestClient(app, base_url="http://localhost:8000")

    resp = local_client.post(
        "/v1/executions",
        headers={
            "Content-Type": "application/json",
            "X-Maestro-Track": "free",  # Deve ser estritamente ignorado por /v1/executions
        },
        json={"task": "Execução via contrato público padrão."},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["result"]["content"] == "Resposta gerada via contrato público v1."
    assert data["decision"]["route"]["id"] == "route-openai-gpt4o-mini"
    mock_adapter.execute.assert_called_once()


def test_admin_executions_track_free_refuses_paid_routes(clean_state: ControlCenterState) -> None:
    """Bloqueador 2 (Prova 2): Execução administrativa local na trilha Free recusa rotas pagas.

    Quando acionada via POST /admin/executions com track='free' e o catálogo só contém rotas pagas,
    a execução é recusada com 422 NO_ELIGIBLE_ROUTE sem acionar o adaptador do provedor externo.
    """
    clean_state.set_credential("openai", "sk-active-test-key")
    mock_adapter = MagicMock()
    mock_adapter.execute = AsyncMock()
    clean_state.current_adapters["openai-responses"] = mock_adapter

    app = create_control_center_app(clean_state)
    local_client = TestClient(app, base_url="http://localhost:8000")

    session_resp = local_client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    resp = local_client.post(
        "/admin/executions",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={"task": "Gere um texto curto sem custo.", "track": "free"},
    )

    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "NO_ELIGIBLE_ROUTE"
    assert "gratuidade declarada pelo operador" in data["error"]["message"]
    mock_adapter.execute.assert_not_called()


def test_admin_executions_track_economica_succeeds(clean_state: ControlCenterState) -> None:
    """Bloqueador 2 (Prova 3): Execução administrativa local na trilha Econômica funciona normalmente.

    Quando acionada via POST /admin/executions com track='economica', o fluxo seleciona
    a rota de menor custo estimado e conclui a execução com HTTP 200.
    """
    clean_state.set_credential("openai", "sk-active-test-key")
    mock_adapter = MagicMock()
    mock_adapter.execute = AsyncMock(
        return_value=TextExecutionResult(
            content="Resultado econômico do Control Center.",
            usage=NormalizedUsage(
                status="available",
                items=(
                    NormalizedUsageItem(unit="input_token", quantity=20),
                    NormalizedUsageItem(unit="output_token", quantity=10),
                ),
            ),
        )
    )
    clean_state.current_adapters["openai-responses"] = mock_adapter

    app = create_control_center_app(clean_state)
    local_client = TestClient(app, base_url="http://localhost:8000")

    session_resp = local_client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    resp = local_client.post(
        "/admin/executions",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={"task": "Resuma este documento na trilha econômica.", "track": "economica"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["result"]["content"] == "Resultado econômico do Control Center."
    assert data["decision"]["route"]["id"] == "route-openai-gpt4o-mini"
    mock_adapter.execute.assert_called_once()


def test_mixed_catalog_admin_execution_free_track_incompatible_free_and_paid_routes(
    clean_state: ControlCenterState,
) -> None:
    """Bloqueador 2: Catálogo misto no endpoint administrativo não realiza fallback para rota paga.

    Em um catálogo contendo:
    - Rota A (gratuidade declarada pelo operador, mas apenas com capability 'text_generation')
    - Rota B (paga, com capabilities 'text_generation' e 'code_analysis')

    Quando POST /admin/executions solicita 'code_analysis' na trilha Free:
    - A rota gratuita declarada é excluída por não atender às restrições da tarefa.
    - A rota paga permanece terminantemente excluída na trilha Free (sem fallback silencioso).
    - O resultado deve ser 422 NO_ELIGIBLE_ROUTE sem acionar nenhum adaptador.
    """
    clean_state.set_credential("openai", "sk-active-test-key")

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

    session_resp = local_client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

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

    # 2. Verifica na execução administrativa com track='free'
    exec_resp = local_client.post(
        "/admin/executions",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={
            "task": "Analise o código de alta complexidade.",
            "constraints": {"required_capabilities": ["code_analysis"]},
            "track": "free",
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


def test_new_route_gpt4o_mini_does_not_inherit_price_reference(
    client: TestClient, clean_state: ControlCenterState
) -> None:
    """Bloqueador 3: Nenhuma rota recém-criada herda preço ou estimativa sem dados explícitos.

    Garante que cadastrar uma rota adicional para o modelo gpt-4o-mini sem informar
    explicitamente price_reference nem estimated_usage resulte em rota com dados econômicos
    nulos e estimativa indisponível (status 'unavailable'), sem auto-preenchimento indevido.
    """
    clean_state.set_credential("openai", "sk-active-test-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    create_resp = client.post(
        "/admin/routes",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={
            "route_id": "route-new-gpt4o-mini-no-price",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "enabled": True,
            "capabilities": ["text_generation"],
        },
    )
    assert create_resp.status_code == 200

    config_resp = client.get("/admin/config")
    assert config_resp.status_code == 200
    config_data = config_resp.json()
    new_route = next(
        r for r in config_data["routes"] if r["route_id"] == "route-new-gpt4o-mini-no-price"
    )

    # Dados econômicos devem permanecer nulos
    assert new_route["price_reference"] is None
    assert new_route["estimated_usage"] is None

    # No catálogo em memória, a estimativa deve ser unavailable
    snapshot_route = next(
        r
        for r in clean_state.current_catalog.snapshot()
        if r.id == "route-new-gpt4o-mini-no-price"
    )
    assert snapshot_route.price_reference is None
    assert snapshot_route.estimate is not None
    assert snapshot_route.estimate.status == "unavailable"


def test_free_track_terminology_operator_declared_and_disclaimer(
    client: TestClient, clean_state: ControlCenterState
) -> None:
    """Bloqueador 1: Terminologia de gratuidade declarada pelo operador e aviso de faturamento.

    A prévia explicável da trilha Free deve explicitar que a gratuidade é 'declarada pelo operador'
    e alertar que o Maestro Router não valida nem confirma o faturamento real junto ao provedor.
    Não devem ser usadas promessas enganosas como 'gratuidade comprovada' ou 'custo zero garantido'.
    """
    clean_state.set_credential("openai", "sk-active-key")
    preview_resp = client.post(
        "/admin/preview",
        json={"task": "Verificação de conformidade terminológica.", "track": "free"},
    )
    assert preview_resp.status_code == 200
    data = preview_resp.json()

    # Confirma terminologia transparente
    assert "gratuidade declarada pelo operador" in data["policy_description"].lower()
    assert "gratuidade declarada pelo operador" in data["explanation"].lower()
    assert "não valida faturamento real" in data["explanation"].lower()

    # Assegura ausência de promessas não comprovadas
    assert "gratuidade comprovada" not in data["explanation"].lower()
    assert "sem custo garantido" not in data["explanation"].lower()
    assert "custo zero garantido" not in data["explanation"].lower()


def test_invalid_track_rejected_with_http_400(client: TestClient, clean_state: ControlCenterState) -> None:
    """Rejeita trilhas desconhecidas com HTTP 400 sem executar adaptador nem converter silenciosamente."""
    clean_state.set_credential("openai", "sk-active-key")
    mock_adapter = MagicMock()
    mock_adapter.execute = AsyncMock()
    clean_state.current_adapters["openai-responses"] = mock_adapter

    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    # 1. Prévia com trilha 'FREE' (maiúscula) e 'trilha-inexistente'
    for bad_track in ("FREE", "trilha-inexistente", "aleatoria"):
        prev_res = client.post(
            "/admin/preview",
            json={"task": "Tarefa de teste", "track": bad_track},
        )
        assert prev_res.status_code == 400
        data = prev_res.json()
        assert data["error"]["code"] == "INVALID_TRACK"
        assert f"Trilha '{bad_track}' não é suportada" in data["error"]["message"]

    # 2. Execução administrativa com trilha inválida
    for bad_track in ("FREE", "trilha-inexistente"):
        exec_res = client.post(
            "/admin/executions",
            headers={"X-Maestro-CSRF-Token": csrf_token},
            cookies=session_resp.cookies,
            json={"task": "Execução com trilha inválida", "track": bad_track},
        )
        assert exec_res.status_code == 400
        data = exec_res.json()
        assert data["error"]["code"] == "INVALID_TRACK"
        assert f"Trilha '{bad_track}' não é suportada" in data["error"]["message"]

    # Confirma que nenhum adaptador foi executado
    mock_adapter.execute.assert_not_called()


def test_invalid_constraints_returns_standard_error_envelope(client: TestClient, clean_state: ControlCenterState) -> None:
    """Erro de validação de teto de custo retorna envelope padronizado error.code == 'INVALID_REQUEST'."""
    clean_state.set_credential("openai", "sk-active-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    resp = client.post(
        "/admin/executions",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={
            "task": "Tarefa com teto inválido",
            "constraints": {
                "max_estimated_cost": {"amount": "abc", "currency": "USD"}
            },
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_REQUEST"
    assert "issues" in data["error"]
    assert any("amount" in str(issue) for issue in data["error"]["issues"])


def test_route_editing_preserves_unmodified_evidence_and_economics(
    client: TestClient, clean_state: ControlCenterState
) -> None:
    """Edição parcial de rota (ex: apenas capacidades) preserva integralmente evidências de qualidade e dados econômicos (B2)."""
    clean_state.set_credential("openai", "sk-active-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    # 1. Cria uma rota completa com critérios de qualidade contendo evidências reais e dados econômicos
    create_payload = {
        "route_id": "route-audit-preserved",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "enabled": True,
        "capabilities": ["text"],
        "quality_criteria": [
            {
                "criterion": "strict_instruction_following",
                "evidence_references": ["auditoria-interna-2026-q3", "benchmark-eval-42"],
            }
        ],
        "price_reference": INITIAL_GPT4O_MINI_PRICE_REFERENCE,
        "estimated_usage": INITIAL_GPT4O_MINI_ESTIMATED_USAGE,
    }
    create_res = client.post(
        "/admin/routes",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json=create_payload,
    )
    assert create_res.status_code == 200

    # Verifica que get_safe_config retorna os critérios com suas evidências intactas (sem achatamento)
    cfg_res = client.get("/admin/config")
    assert cfg_res.status_code == 200
    route_cfg = next(r for r in cfg_res.json()["routes"] if r["route_id"] == "route-audit-preserved")
    assert len(route_cfg["quality_criteria"]) == 1
    qc = route_cfg["quality_criteria"][0]
    assert qc["criterion"] == "strict_instruction_following"
    assert qc["evidence_references"] == ["auditoria-interna-2026-q3", "benchmark-eval-42"]

    # 2. Agora o operador edita APENAS as capacidades, omitindo quality_criteria, price_reference e estimated_usage
    update_res = client.post(
        "/admin/routes",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={
            "route_id": "route-audit-preserved",
            "capabilities": ["text", "code", "summarization"],
        },
    )
    assert update_res.status_code == 200
    updated_route = update_res.json()["route"]

    # Capacidades foram atualizadas
    assert updated_route["capabilities"] == ["text", "code", "summarization"]
    # Qualidade e evidências foram integralmente preservadas (B2)
    assert len(updated_route["quality_criteria"]) == 1
    assert updated_route["quality_criteria"][0]["criterion"] == "strict_instruction_following"
    assert updated_route["quality_criteria"][0]["evidence_references"] == [
        "auditoria-interna-2026-q3",
        "benchmark-eval-42",
    ]
    # Dados econômicos originais foram integralmente preservados (B2)
    assert updated_route["price_reference"] is not None
    assert updated_route["price_reference"]["id"] == INITIAL_GPT4O_MINI_PRICE_REFERENCE["id"]
    assert updated_route["estimated_usage"] is not None
    assert (
        updated_route["estimated_usage"]["input_token"]
        == INITIAL_GPT4O_MINI_ESTIMATED_USAGE["input_token"]
    )


def test_credential_verification_superseded_race_condition(
    client: TestClient, clean_state: ControlCenterState
) -> None:
    """Verificação assíncrona atrasada não altera o status de uma credencial modificada ou removida concorrentemente (B3)."""
    clean_state.set_credential("openai", "sk-initial-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    async def delayed_models_list(*args, **kwargs):
        # Simula que o operador removeu a credencial enquanto a chamada remota estava em trânsito
        clean_state.remove_credential("openai")
        mock_response = MagicMock()
        mock_item = MagicMock()
        mock_item.id = "gpt-4o-mini"
        mock_response.data = [mock_item]
        return mock_response

    with patch("maestro_router.control_center.AsyncOpenAI") as mock_openai_cls:
        mock_instance = MagicMock()
        mock_instance.models.list = AsyncMock(side_effect=delayed_models_list)
        mock_openai_cls.return_value = mock_instance

        resp = client.post(
            "/admin/credentials/verify",
            headers={"X-Maestro-CSRF-Token": csrf_token},
            cookies=session_resp.cookies,
        )
        # O backend detecta que a credencial foi alterada/removida durante a verificação e rejeita com 409
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"]["code"] == "CREDENTIAL_SUPERSEDED"

    # Confirma que a credencial removida NÃO foi marcada como verified
    assert clean_state.credentials["openai"]["api_key"] is None
    assert clean_state.credentials["openai"]["status"] == "not_registered"


def test_security_remote_client_blocked(clean_state: ControlCenterState) -> None:
    """Clientes com IP remoto (fora do loopback local) são terminantemente bloqueados com HTTP 403 (B4)."""
    app = create_control_center_app(clean_state)
    # Simula cliente vindo de IP externo de rede
    remote_client = TestClient(app, base_url="http://192.168.1.100:8000", client=("192.168.1.50", 42100))

    # Tentativa de obter sessão a partir de cliente remoto
    resp = remote_client.get("/admin/session")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
    assert "Acesso administrativo restrito a conexões locais" in resp.json()["error"]["message"]

    # Tentativa de mutação a partir de cliente remoto
    resp_mut = remote_client.post(
        "/admin/credentials",
        json={"provider": "openai", "api_key": "sk-remote-test"},
    )
    assert resp_mut.status_code == 403
    assert resp_mut.json()["error"]["code"] == "FORBIDDEN"


def test_security_unauthorized_origin_and_referer(client: TestClient, clean_state: ControlCenterState) -> None:
    """Solicitações com Origin ou Referer apontando para domínios externos não autorizados são bloqueadas (B4)."""
    clean_state.set_credential("openai", "sk-active-key")

    # 1. Origin maliciosa em /admin/session
    res_session = client.get("/admin/session", headers={"Origin": "https://malicious-site.example.com"})
    assert res_session.status_code == 403
    assert res_session.json()["error"]["code"] == "FORBIDDEN"

    # 2. Referer malicioso em /admin/session
    res_ref = client.get("/admin/session", headers={"Referer": "https://attacker.org/phishing"})
    assert res_ref.status_code == 403
    assert res_ref.json()["error"]["code"] == "FORBIDDEN"

    # 3. Origin maliciosa em mutação administrativa
    session_valid = client.get("/admin/session")
    csrf_token = session_valid.json()["csrf_token"]
    res_mut = client.post(
        "/admin/credentials",
        headers={
            "Origin": "http://evil-domain.com",
            "X-Maestro-CSRF-Token": csrf_token,
        },
        cookies=session_valid.cookies,
        json={"provider": "openai", "api_key": "sk-test"},
    )
    assert res_mut.status_code == 403
    assert res_mut.json()["error"]["code"] == "FORBIDDEN"


def test_defensive_validation_non_dict_and_unhashable_track(
    client: TestClient, clean_state: ControlCenterState
) -> None:
    """Validação defensiva rejeita payloads não-objeto e tracks não-hashable com HTTP 400 sem gerar erro 500 (B4)."""
    clean_state.set_credential("openai", "sk-active-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]

    # 1. JSON array em /admin/preview
    res_array = client.post(
        "/admin/preview",
        headers={"Content-Type": "application/json"},
        content="[1, 2, 3]",
    )
    assert res_array.status_code == 400
    assert res_array.json()["error"]["code"] == "INVALID_JSON"

    # 2. Valor de track como lista em /admin/preview (não hashable)
    res_list_track = client.post(
        "/admin/preview",
        json={"task": "Minha tarefa", "track": ["free"]},
    )
    assert res_list_track.status_code == 400
    assert res_list_track.json()["error"]["code"] == "INVALID_TRACK"

    # 3. Valor de track como dicionário em /admin/preview (não hashable)
    res_dict_track = client.post(
        "/admin/preview",
        json={"task": "Minha tarefa", "track": {"tipo": "free"}},
    )
    assert res_dict_track.status_code == 400
    assert res_dict_track.json()["error"]["code"] == "INVALID_TRACK"

    # 4. Valor de track não textual em /admin/executions
    res_exec_track = client.post(
        "/admin/executions",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=session_resp.cookies,
        json={"task": "Minha tarefa", "track": ["economica"]},
    )
    assert res_exec_track.status_code == 400
    assert res_exec_track.json()["error"]["code"] == "INVALID_TRACK"

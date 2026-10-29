from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from maestro_router.control_center import (
    ControlCenterState,
    create_control_center_app,
)
from maestro_router.execution import (
    NormalizedUsage,
    NormalizedUsageItem,
    TextExecutionResult,
)


@pytest.fixture
def clean_state() -> ControlCenterState:
    state = ControlCenterState()
    state.remove_credential("openai")
    state.remove_credential("google")
    state.routes_raw = []
    state.rebuild_runtime()
    return state


@pytest.fixture
def client(clean_state: ControlCenterState) -> TestClient:
    app = create_control_center_app(clean_state)
    return TestClient(app)


def test_register_and_remove_gemini_api_key(client: TestClient, clean_state: ControlCenterState) -> None:
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]
    cookies = session_resp.cookies

    # Cadastro de chave Google na memória
    save_resp = client.post(
        "/admin/credentials",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=cookies,
        json={"provider": "google", "api_key": "ai-test-key-google-12345"},
    )
    assert save_resp.status_code == 200
    save_data = save_resp.json()
    assert save_data["provider"] == "google"
    assert save_data["status"] == "registered"

    # Confirma que a chave foi registrada na memória volátil
    assert clean_state.credentials["google"]["api_key"] == "ai-test-key-google-12345"

    # O endpoint de configuração segura nunca deve expor o segredo
    config_resp = client.get("/admin/config", cookies=cookies)
    assert config_resp.status_code == 200
    cfg = config_resp.json()
    google_provider = next(p for p in cfg["providers"] if p["id"] == "google")
    assert google_provider["name"] == "Google"
    assert google_provider["implemented"] is True
    assert google_provider["credential"]["registered"] is True
    assert "api_key" not in google_provider["credential"]
    assert "ai-test-key-google-12345" not in config_resp.text

    # Remoção da chave Google da memória
    del_resp = client.delete(
        "/admin/credentials?provider=google",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=cookies,
    )
    assert del_resp.status_code == 200
    assert clean_state.credentials["google"]["api_key"] is None
    assert clean_state.credentials["google"]["status"] == "not_registered"


def test_verify_gemini_credentials_and_filter_models(client: TestClient, clean_state: ControlCenterState) -> None:
    clean_state.set_credential("google", "ai-valid-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]
    cookies = session_resp.cookies

    mock_models = [
        MagicMock(name="models/gemini-2.5-flash", supported_actions=["generateContent"]),
        MagicMock(name="models/gemini-2.5-pro", supported_actions=["generateContent"]),
        MagicMock(name="models/text-embedding-004", supported_actions=["embedContent"]),
        MagicMock(name="models/imagen-3.0-generate-002", supported_actions=["generateImages"]),
    ]
    # Set model name attributes explicitly
    mock_models[0].name = "models/gemini-2.5-flash"
    mock_models[1].name = "models/gemini-2.5-pro"
    mock_models[2].name = "models/text-embedding-004"
    mock_models[3].name = "models/imagen-3.0-generate-002"

    class AsyncMockPager:
        def __init__(self, items: list[Any]) -> None:
            self.items = items
        def __aiter__(self):
            self._iter = iter(self.items)
            return self
        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    with patch("maestro_router.control_center.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.aio.models.list = AsyncMock(return_value=AsyncMockPager(mock_models))
        mock_client_cls.return_value = mock_instance

        verify_resp = client.post(
            "/admin/credentials/verify",
            headers={"X-Maestro-CSRF-Token": csrf_token},
            cookies=cookies,
            json={"provider": "google"},
        )
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["provider"] == "google"
        assert data["status"] == "verified"
        assert "gemini-2.5-flash" in data["models"]
        assert "gemini-2.5-pro" in data["models"]
        # Modelos não textuais devem ser excluídos
        assert "text-embedding-004" not in data["models"]
        assert "imagen-3.0-generate-002" not in data["models"]


def test_verify_gemini_credentials_errors(client: TestClient, clean_state: ControlCenterState) -> None:
    clean_state.set_credential("google", "ai-invalid-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]
    cookies = session_resp.cookies

    # 1. Acesso recusado (400 com API key not valid / 401)
    with patch("maestro_router.control_center.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.aio.models.list = AsyncMock(
            side_effect=RuntimeError("API key not valid. Please pass a valid API key.")
        )
        mock_client_cls.return_value = mock_instance

        resp = client.post(
            "/admin/credentials/verify",
            headers={"X-Maestro-CSRF-Token": csrf_token},
            cookies=cookies,
            json={"provider": "google"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "access_denied"

    # 2. Cota excedida (429 / RESOURCE_EXHAUSTED)
    with patch("maestro_router.control_center.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.aio.models.list = AsyncMock(
            side_effect=RuntimeError("RESOURCE_EXHAUSTED: Quota exceeded for project")
        )
        mock_client_cls.return_value = mock_instance

        resp = client.post(
            "/admin/credentials/verify",
            headers={"X-Maestro-CSRF-Token": csrf_token},
            cookies=cookies,
            json={"provider": "google"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "insufficient_quota"


def test_create_google_route_without_automatic_pricing(client: TestClient, clean_state: ControlCenterState) -> None:
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]
    cookies = session_resp.cookies

    # Criação de rota Google sem tarifas automáticas
    create_resp = client.post(
        "/admin/routes",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=cookies,
        json={
            "route_id": "route-google-gemini-flash",
            "provider": "google",
            "model": "gemini-2.5-flash",
            "capabilities": ["text_generation", "summarization"],
            "quality_criteria": [],
        },
    )
    assert create_resp.status_code == 200
    data = create_resp.json()["route"]
    assert data["provider"] == "google"
    assert data["model"] == "gemini-2.5-flash"
    assert data["price_reference"] is None
    assert data["estimated_usage"] is None

    # No catálogo em memória, a estimativa prévia é unavailable
    route = next(r for r in clean_state.current_catalog.snapshot() if r.id == "route-google-gemini-flash")
    assert route.estimate.status == "unavailable"


def test_free_track_rejects_priced_google_route_and_accepts_declared_free(client: TestClient, clean_state: ControlCenterState) -> None:
    clean_state.set_credential("google", "ai-valid-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]
    cookies = session_resp.cookies

    # 1. Rota Google tarifada com tarifas positivas
    clean_state.routes_raw = [
        {
            "route_id": "route-google-priced",
            "provider": "google",
            "model": "gemini-2.5-flash",
            "enabled": True,
            "capabilities": ["text_generation"],
            "quality_criteria": [],
            "price_reference": {
                "id": "pricing-google-paid",
                "currency": "USD",
                "version": "2026-10",
                "source": "https://ai.google.dev/pricing",
                "rates": [
                    {"unit": "input_token", "rate": "0.075", "base": 1000000},
                    {"unit": "output_token", "rate": "0.300", "base": 1000000},
                ],
                "conditions": ["standard"],
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
    ]
    clean_state.rebuild_runtime()

    # Previa na trilha Free rejeita rota tarifada
    preview_resp = client.post(
        "/admin/preview",
        cookies=cookies,
        json={"task": "Minha tarefa", "track": "free"},
    )
    assert preview_resp.status_code == 200
    preview_data = preview_resp.json()
    assert preview_data["recommended_route"] is None
    assert len(preview_data["exclusions"]) == 1
    assert preview_data["exclusions"][0]["reason"] == "paid_or_unknown_cost"

    # Execução na trilha Free rejeita com 422 NO_ELIGIBLE_ROUTE
    exec_resp = client.post(
        "/admin/executions",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=cookies,
        json={"task": "Minha tarefa", "track": "free"},
    )
    assert exec_resp.status_code == 422
    assert exec_resp.json()["error"]["code"] == "NO_ELIGIBLE_ROUTE"

    # 2. Rota Google com gratuidade declarada pelo operador (tarifas e estimativa zero)
    clean_state.routes_raw = [
        {
            "route_id": "route-google-free",
            "provider": "google",
            "model": "gemini-2.5-flash",
            "enabled": True,
            "capabilities": ["text_generation"],
            "quality_criteria": [],
            "price_reference": {
                "id": "pricing-google-free-tier",
                "currency": "USD",
                "version": "2026-10",
                "source": "https://ai.google.dev/pricing-free",
                "rates": [
                    {"unit": "input_token", "rate": "0.00", "base": 1000000},
                    {"unit": "output_token", "rate": "0.00", "base": 1000000},
                ],
                "conditions": ["operator-declared-free-tier"],
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
    ]
    clean_state.rebuild_runtime()

    preview_free = client.post(
        "/admin/preview",
        cookies=cookies,
        json={"task": "Minha tarefa", "track": "free"},
    )
    assert preview_free.status_code == 200
    free_data = preview_free.json()
    assert free_data["recommended_route"] is not None
    assert free_data["recommended_route"]["route_id"] == "route-google-free"


def test_mixed_catalog_economica_and_inteligente_tracks(client: TestClient, clean_state: ControlCenterState) -> None:
    clean_state.set_credential("openai", "sk-valid-key")
    clean_state.set_credential("google", "ai-valid-key")
    session_resp = client.get("/admin/session")
    cookies = session_resp.cookies

    # Dois provedores concorrendo no mesmo catálogo:
    # route-openai: custo estimado 0.1500 USD
    # route-google: custo estimado 0.0500 USD (mais econômica)
    clean_state.routes_raw = [
        {
            "route_id": "route-openai-expensive",
            "provider": "openai",
            "model": "gpt-4o",
            "enabled": True,
            "capabilities": ["text_generation"],
            "quality_criteria": [
                {"criterion": "high_precision_factual", "evidence_references": ["doc-eval-1"]}
            ],
            "price_reference": {
                "id": "pricing-openai-high",
                "currency": "USD",
                "version": "2026-10",
                "source": "manual",
                "rates": [
                    {"unit": "input_token", "rate": "2.50", "base": 1000000},
                    {"unit": "output_token", "rate": "10.00", "base": 1000000},
                ],
                "conditions": ["standard"],
                "context_complete": True,
                "units_exhaustive": True,
                "no_double_counting": True,
                "model_identity_exact": True,
            },
            "estimated_usage": {
                "input_token": 10000,
                "output_token": 2000,
                "applicability_confirmed": True,
            },
        },
        {
            "route_id": "route-google-cheap",
            "provider": "google",
            "model": "gemini-2.5-flash",
            "enabled": True,
            "capabilities": ["text_generation"],
            "quality_criteria": [],
            "price_reference": {
                "id": "pricing-google-low",
                "currency": "USD",
                "version": "2026-10",
                "source": "manual",
                "rates": [
                    {"unit": "input_token", "rate": "0.10", "base": 1000000},
                    {"unit": "output_token", "rate": "0.40", "base": 1000000},
                ],
                "conditions": ["standard"],
                "context_complete": True,
                "units_exhaustive": True,
                "no_double_counting": True,
                "model_identity_exact": True,
            },
            "estimated_usage": {
                "input_token": 10000,
                "output_token": 2000,
                "applicability_confirmed": True,
            },
        },
    ]
    clean_state.rebuild_runtime()

    # 1. Trilha Econômica: seleciona neutralmente a rota de menor custo estimado (Google)
    preview_econ = client.post(
        "/admin/preview",
        cookies=cookies,
        json={"task": "Tarefa de teste", "track": "economica"},
    )
    assert preview_econ.status_code == 200
    econ_data = preview_econ.json()
    assert econ_data["recommended_route"]["route_id"] == "route-google-cheap"
    assert econ_data["recommended_route"]["provider"] == "google"

    # 2. Trilha Inteligente exigindo critério que apenas a OpenAI possui documentado
    preview_intel = client.post(
        "/admin/preview",
        cookies=cookies,
        json={
            "task": "Tarefa de teste",
            "track": "inteligente",
            "constraints": {"required_quality_criteria": ["high_precision_factual"]},
        },
    )
    assert preview_intel.status_code == 200
    intel_data = preview_intel.json()
    assert intel_data["recommended_route"]["route_id"] == "route-openai-expensive"
    assert intel_data["recommended_route"]["provider"] == "openai"


@pytest.mark.anyio
async def test_neutral_execution_dispatches_to_google_adapter(clean_state: ControlCenterState) -> None:
    # Teste de execução ponta a ponta pela API pública /v1/executions
    clean_state.set_credential("google", "ai-valid-key")
    clean_state.routes_raw = [
        {
            "route_id": "route-google-direct",
            "provider": "google",
            "model": "gemini-2.5-flash",
            "enabled": True,
            "capabilities": ["text_generation"],
            "quality_criteria": [],
            "price_reference": {
                "id": "pricing-google-free",
                "currency": "USD",
                "version": "2026-10",
                "source": "manual",
                "rates": [
                    {"unit": "input_token", "rate": "0.00", "base": 1000000},
                    {"unit": "output_token", "rate": "0.00", "base": 1000000},
                ],
                "conditions": ["free"],
                "context_complete": True,
                "units_exhaustive": True,
                "no_double_counting": True,
                "model_identity_exact": True,
            },
            "estimated_usage": {
                "input_token": 100,
                "output_token": 50,
                "applicability_confirmed": True,
            },
        }
    ]
    clean_state.rebuild_runtime()

    mock_adapter = MagicMock()
    mock_adapter.execute = AsyncMock(
        return_value=TextExecutionResult(
            content="Resposta neutra gerada pelo Google Gemini.",
            usage=NormalizedUsage(
                status="available",
                items=(
                    NormalizedUsageItem(unit="input_token", quantity=100),
                    NormalizedUsageItem(unit="output_token", quantity=50),
                ),
            ),
            observed_model="gemini-2.5-flash",
        )
    )
    clean_state.current_adapters["google-gemini-interactions"] = mock_adapter

    app = create_control_center_app(clean_state)
    test_client = TestClient(app)

    resp = test_client.post(
        "/v1/executions",
        json={"task": "Execute esta tarefa."},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["result"]["content"] == "Resposta neutra gerada pelo Google Gemini."
    assert res_data["decision"]["route"]["provider"] == "google"
    assert res_data["decision"]["route"]["id"] == "route-google-direct"
    assert res_data["economics"]["usage"]["status"] == "available"


def test_admin_access_restricted_to_local_client(clean_state: ControlCenterState) -> None:
    # Acesso administrativo vindo de IP externo deve ser rejeitado com 403 Forbidden
    app = create_control_center_app(clean_state)
    remote_client = TestClient(app, base_url="http://192.168.1.100:8000", client=("192.168.1.50", 42100))
    resp = remote_client.get("/admin/config")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_request_snapshot_isolation_with_google(clean_state: ControlCenterState) -> None:
    """Uma requisição em andamento utiliza exclusivamente o catálogo e adaptadores congelados no snapshot (B3)."""
    clean_state.set_credential("google", "ai-initial-key")
    clean_state.routes_raw = [
        {
            "route_id": "route-google-snapshot",
            "provider": "google",
            "model": "gemini-2.5-flash",
            "enabled": True,
            "capabilities": ["text_generation"],
            "quality_criteria": [],
            "price_reference": {
                "id": "pricing-google-free",
                "currency": "USD",
                "version": "2026-10",
                "source": "manual",
                "rates": [
                    {"unit": "input_token", "rate": "0.00", "base": 1000000},
                    {"unit": "output_token", "rate": "0.00", "base": 1000000},
                ],
                "conditions": ["free"],
                "context_complete": True,
                "units_exhaustive": True,
                "no_double_counting": True,
                "model_identity_exact": True,
            },
            "estimated_usage": {
                "input_token": 100,
                "output_token": 50,
                "applicability_confirmed": True,
            },
        }
    ]
    clean_state.rebuild_runtime()

    async def concurrent_removal_execute(*args, **kwargs):
        # A credencial e rota são removidas do estado vivo enquanto a requisição 1 está em trânsito
        clean_state.remove_credential("google")
        clean_state.routes_raw = []
        clean_state.rebuild_runtime()
        return TextExecutionResult(
            content="Executado com o snapshot congelado do início.",
            usage=NormalizedUsage(
                status="available",
                items=(
                    NormalizedUsageItem(unit="input_token", quantity=100),
                    NormalizedUsageItem(unit="output_token", quantity=50),
                ),
            ),
            observed_model="gemini-2.5-flash",
        )

    mock_adapter = MagicMock()
    mock_adapter.execute = AsyncMock(side_effect=concurrent_removal_execute)
    clean_state.current_adapters["google-gemini-interactions"] = mock_adapter

    app = create_control_center_app(clean_state)
    test_client = TestClient(app)

    # 1. Requisição 1 usa a composição congelada e completa com sucesso
    resp_1 = test_client.post("/v1/executions", json={"task": "Tarefa em andamento"})
    assert resp_1.status_code == 200
    assert resp_1.json()["result"]["content"] == "Executado com o snapshot congelado do início."

    # 2. Requisição posterior observa o novo catálogo sem rota elegível
    resp_2 = test_client.post("/v1/executions", json={"task": "Tarefa posterior"})
    assert resp_2.status_code == 422
    assert resp_2.json()["error"]["code"] == "NO_ELIGIBLE_ROUTE"


def test_extract_google_model_conservative_compatibility_filter() -> None:
    """Verifica estritamente as regras de filtro conservador de modelos do Google (B2)."""
    from maestro_router.control_center import _extract_google_model

    discovered: list[str] = []

    # 1. supported_actions=["generateContent"] -> incluído
    m1 = MagicMock(name="models/gemini-2.5-flash", supported_actions=["generateContent"])
    m1.name = "models/gemini-2.5-flash"
    _extract_google_model(m1, discovered)
    assert discovered == ["gemini-2.5-flash"]

    # 2. Duplicata -> evitada na lista final
    _extract_google_model(m1, discovered)
    assert discovered == ["gemini-2.5-flash"]

    # 3. Somente embedContent -> excluído
    m2 = MagicMock(name="models/text-embedding-004", supported_actions=["embedContent"])
    m2.name = "models/text-embedding-004"
    _extract_google_model(m2, discovered)
    assert "text-embedding-004" not in discovered

    # 4. supported_actions=None -> excluído
    m3 = MagicMock(name="models/gemini-unknown", supported_actions=None)
    m3.name = "models/gemini-unknown"
    _extract_google_model(m3, discovered)
    assert "gemini-unknown" not in discovered

    # 5. Atributo supported_actions ausente -> excluído
    class NoActionsModel:
        def __init__(self, name: str) -> None:
            self.name = name

    m4 = NoActionsModel("models/gemini-no-attr")
    _extract_google_model(m4, discovered)
    assert "gemini-no-attr" not in discovered

    # 6. Modelos incompatíveis de imagem, vídeo, embedding -> excluídos mesmo com generateContent
    m_imagen = MagicMock(name="models/imagen-3.0", supported_actions=["generateContent"])
    m_imagen.name = "models/imagen-3.0"
    _extract_google_model(m_imagen, discovered)
    assert "imagen-3.0" not in discovered

    m_veo = MagicMock(name="models/veo-2.0", supported_actions=["generateContent"])
    m_veo.name = "models/veo-2.0"
    _extract_google_model(m_veo, discovered)
    assert "veo-2.0" not in discovered

    m_emb = MagicMock(name="models/embedding-001", supported_actions=["generateContent"])
    m_emb.name = "models/embedding-001"
    _extract_google_model(m_emb, discovered)
    assert "embedding-001" not in discovered

    # Apenas o modelo válido comprovado permanece
    assert discovered == ["gemini-2.5-flash"]


def test_verify_gemini_credentials_zero_compatible_models_returns_empty_list(
    client: TestClient, clean_state: ControlCenterState
) -> None:
    """Verifica que zero modelos compatíveis resulta em lista vazia e sem catálogo hardcoded (B1)."""
    clean_state.set_credential("google", "ai-valid-key")
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]
    cookies = session_resp.cookies

    # Provedor retorna apenas modelo não compatível (ex.: somente embedding)
    mock_models = [
        MagicMock(name="models/text-embedding-004", supported_actions=["embedContent"]),
    ]
    mock_models[0].name = "models/text-embedding-004"

    class AsyncMockPager:
        def __init__(self, items: list[Any]) -> None:
            self.items = items
        def __aiter__(self):
            self._iter = iter(self.items)
            return self
        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    with patch("maestro_router.control_center.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.aio.models.list = AsyncMock(return_value=AsyncMockPager(mock_models))
        mock_client_cls.return_value = mock_instance

        verify_resp = client.post(
            "/admin/credentials/verify",
            headers={"X-Maestro-CSRF-Token": csrf_token},
            cookies=cookies,
            json={"provider": "google"},
        )
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["provider"] == "google"
        assert data["status"] == "verified"
        # Deve ser lista vazia, NUNCA lista hardcoded
        assert data["models"] == []
        assert "nenhum modelo compatível" in data["message"].lower()

    # Confirma em /admin/config
    config_resp = client.get("/admin/config", cookies=cookies)
    assert config_resp.status_code == 200
    cfg = config_resp.json()
    assert cfg["models_by_provider"]["google"] == []

    # Confirma em /admin/models?provider=google
    models_resp = client.get("/admin/models?provider=google", cookies=cookies)
    assert models_resp.status_code == 200
    assert models_resp.json()["models"] == []
    assert models_resp.json()["verified"] is True


def test_remove_google_credential_clears_models(
    client: TestClient, clean_state: ControlCenterState
) -> None:
    """Verifica que remover a credencial Google limpa os modelos descobertos."""
    clean_state.set_credential("google", "ai-valid-key")
    clean_state.credentials["google"]["models"] = ["gemini-2.5-flash"]
    session_resp = client.get("/admin/session")
    csrf_token = session_resp.json()["csrf_token"]
    cookies = session_resp.cookies

    del_resp = client.delete(
        "/admin/credentials?provider=google",
        headers={"X-Maestro-CSRF-Token": csrf_token},
        cookies=cookies,
    )
    assert del_resp.status_code == 200
    assert clean_state.credentials["google"]["models"] == []
    assert clean_state.credentials["google"]["status"] == "not_registered"

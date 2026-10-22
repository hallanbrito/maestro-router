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
    DEFAULT_GPT4O_MINI_PRICE_REFERENCE,
    DEFAULT_GPT4O_MINI_ESTIMATED_USAGE,
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
    """The public POST /v1/executions remains strictly faithful to docs/05-API.md."""
    resp = client.post(
        "/v1/executions",
        headers={"Content-Type": "application/json"},
        json={"task": "Teste de tarefa inicial sem chave configurada."},
    )
    # Without an API key, the external route has no adapter, resulting in 422 NO_ELIGIBLE_ROUTE or 500 config error
    assert resp.status_code in {422, 500}
    data = resp.json()
    assert "error" in data


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
    assert "trilha Free requer comprovação de custo zero" in data["explanation"]


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

"""Testes offline: nenhuma chamada real a GitHub, modelo ou MCP remoto."""
from unittest.mock import patch

from maestro_router.factory_mcp import (
    _maestro_admin_url, factory_issues, fallback_evidence, maestro_catalog,
)


def test_local_url_rejects_remote_host():
    for base in (
        "https://example.com", "http://169.254.169.254",
        "http://user@localhost:8000", "http://localhost:8000/other",
    ):
        try:
            _maestro_admin_url(base)
        except ValueError:
            continue
        raise AssertionError(f"URL nao foi bloqueada: {base}")


def test_catalog_redacts_all_unlisted_fields():
    secret = "CANARY_SECRET_DO_NOT_EXPOSE"
    fake = {
        "providers": [
            {"id": "groq", "implemented": False,
             "credential": {"status": "registered", "api_key": secret}},
        ],
        "routes": [
            {"route_id": "route-1", "provider": "groq", "model": "test-model",
             "enabled": True, "status": "blocked", "price_reference": secret},
        ],
    }
    with patch("maestro_router.factory_mcp._get_json", return_value=fake):
        result = maestro_catalog()
    assert result["status"] == "ok"
    assert secret not in repr(result)
    assert result["billing_verified"] is False


def test_issue_allowlist_blocks_untrusted_repo_without_network():
    with patch("maestro_router.factory_mcp._get_json") as get:
        result = factory_issues("third-party", 10)
        assert result["status"] == "invalid_request"
        get.assert_not_called()


def test_issues_exclude_pull_requests():
    with patch("maestro_router.factory_mcp._get_json", return_value=[
        {"number": 72, "title": "Mission", "html_url": "https://github.com/", "state": "open"},
        {"number": 71, "title": "PR", "pull_request": {}, "state": "open"},
    ]):
        result = factory_issues()
    assert [i["number"] for i in result["issues"]] == [72]


def test_fallback_requires_evidence_and_does_not_claim_ready():
    with patch("maestro_router.factory_mcp._get_json", side_effect=[
        {"state": "open", "html_url": "https://github.com/example/issues/61"},
        {"state": "open", "html_url": "https://github.com/example/pull/51",
         "draft": True, "merged": False},
    ]):
        result = fallback_evidence()
    assert result["fallback_integrated"] == "not_verified"
    assert result["poc_pr"]["merged"] is False


def test_network_fail_closed():
    with patch(
        "maestro_router.factory_mcp._get_json",
        side_effect=OSError("token=private"),
    ):
        assert maestro_catalog() == {
            "status": "unavailable", "source": "maestro-local", "verified": False,
        }
        assert factory_issues()["verified"] is False
        assert fallback_evidence()["verified"] is False

"""MCP local da fabrica: leitura do Maestro e GitHub, sem execucao de modelos.

Disponivel apenas via stdio. Requer o SDK mcp v2 apenas para executar.
Nenhuma ferramenta deste modulo modifica estado nem despacha trabalho.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

GITHUB_API = "https://api.github.com/repos/hallanbrito"
_ALLOWED_REPOS = {"CHDevFlow", "maestro-router"}
_MAX_RESPONSE_BYTES = 524_288


def _maestro_admin_url(base: str) -> str:
    """Aceita apenas o Control Center HTTP no loopback, sem URL arbitraria."""
    url = urlsplit(base)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "localhost"}
        or url.username is not None
        or url.password is not None
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
    ):
        raise ValueError("MAESTRO_LOCAL_URL deve apontar para HTTP no loopback")
    return f"{base.rstrip('/')}/admin/config"


def _get_json(url: str, *, github: bool = False) -> object:
    headers = {"Accept": "application/vnd.github+json" if github else "application/json"}
    if github:
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=4) as response:
        data = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(data) > _MAX_RESPONSE_BYTES:
        raise ValueError("Resposta excede limite")
    return json.loads(data)


def _safe_error(source: str) -> dict[str, object]:
    # Nao repassar excecoes HTTP ou bodies que possam revelar segredos.
    return {"status": "unavailable", "source": source, "verified": False}


def maestro_catalog() -> dict[str, object]:
    """Retorna somente metadados permitidos da configuracao local do Maestro."""
    try:
        url = _maestro_admin_url(
            os.environ.get("MAESTRO_LOCAL_URL", "http://127.0.0.1:8000")
        )
        data = _get_json(url)
        if not isinstance(data, dict):
            return _safe_error("maestro-local")
        providers = data.get("providers", [])
        routes = data.get("routes", [])
        if not isinstance(providers, list) or not isinstance(routes, list):
            return _safe_error("maestro-local")
        # Allowlist explicita: nunca devolver credenciais, preco bruto ou payloads.
        return {
            "status": "ok", "source": "maestro-local", "verified": True,
            "providers": [
                {
                    "id": p.get("id"), "implemented": p.get("implemented"),
                    "credential_status": p.get("credential", {}).get("status"),
                }
                for p in providers
                if isinstance(p, dict) and isinstance(p.get("credential"), dict)
            ],
            "routes": [
                {
                    "id": r.get("route_id"), "provider": r.get("provider"),
                    "model": r.get("model"), "enabled": r.get("enabled"),
                    "status": r.get("status"),
                }
                for r in routes if isinstance(r, dict)
            ],
            "billing_verified": False,
        }
    except (ValueError, TypeError, KeyError, HTTPError, URLError, TimeoutError, OSError):
        return _safe_error("maestro-local")


def factory_issues(project: str = "CHDevFlow", limit: int = 10) -> dict[str, object]:
    """Consulta Issues abertas; apenas repositorios explicitamente autorizados."""
    if project not in _ALLOWED_REPOS or type(limit) is not int or not 1 <= limit <= 20:
        return {"status": "invalid_request", "verified": False}
    source = f"github:{project}"
    try:
        data = _get_json(
            f"{GITHUB_API}/{project}/issues?state=open&per_page={limit}",
            github=True,
        )
        if not isinstance(data, list):
            return _safe_error(source)
        items = [
            {
                "number": item.get("number"), "title": item.get("title"),
                "url": item.get("html_url"), "state": item.get("state"),
            }
            for item in data
            if isinstance(item, dict) and "pull_request" not in item
        ]
        return {"status": "ok", "source": source, "verified": True, "issues": items}
    except (ValueError, TypeError, HTTPError, URLError, TimeoutError, OSError):
        return _safe_error(source)


def fallback_evidence() -> dict[str, object]:
    """Le Issue #61 e Draft PR #51; nunca afirma fallback integrado por inferencia."""
    source = "github:maestro-router"
    try:
        issue = _get_json(f"{GITHUB_API}/maestro-router/issues/61", github=True)
        pr = _get_json(f"{GITHUB_API}/maestro-router/pulls/51", github=True)
        if not isinstance(issue, dict) or not isinstance(pr, dict):
            return _safe_error(source)
        return {
            "status": "ok", "source": source, "verified": True,
            "fallback_integrated": "not_verified",
            "issue": {
                "number": 61, "state": issue.get("state"),
                "url": issue.get("html_url"),
            },
            "poc_pr": {
                "number": 51, "state": pr.get("state"),
                "draft": pr.get("draft"), "merged": pr.get("merged"),
                "url": pr.get("html_url"),
            },
        }
    except (ValueError, TypeError, HTTPError, URLError, TimeoutError, OSError):
        return _safe_error(source)


def create_server():
    """Importa SDK MCP somente quando o servidor e iniciado (opt-in)."""
    from mcp.server import MCPServer

    server = MCPServer("CH-Factory-ReadOnly")
    server.tool()(maestro_catalog)
    server.tool()(factory_issues)
    server.tool()(fallback_evidence)
    return server


if __name__ == "__main__":
    create_server().run()  # stdio; sem porta aberta e sem agendamento

# MCP-01 — Gateway local da fabrica (F1 read-only)

**Issue:** #70 · **Status:** implementado em branch de experimento, sem merge/ativacao.
**Autorizacao:** PO em 14/11/2026; custo incremental R$0; somente consultas.

## O que entrega

O modulo `src/maestro_router/factory_mcp.py` expoe **tres ferramentas MCP via stdio**:

| Tool | Fonte real | Restricoes |
| --- | --- | --- |
| `maestro_catalog` | `GET /admin/config` do Control Center local | Metadados allowlist; nenhuma chave/preco bruto; falha fechada |
| `factory_issues` | GitHub API GET, somente `hallanbrito/CHDevFlow` ou `hallanbrito/maestro-router` | Apenas Issues abertas (1 a 20); exclui PRs |
| `fallback_evidence` | GitHub Issue #61 + Draft PR #51 | **Nao** declara fallback integrado sem verificacao |

**Nao entrega:** worker de codigo, execucao/ativacao de modelos, leitura da fatura real, quota engine, fallback automatico, mutacao de Issues/Project, escrita, merge ou deploy.

## Execucao opt-in local

Requer **Python >=3.11**, checkout do Maestro e SDK MCP Python **v2**. O SDK nao e dependencia do runtime tradicional:

~~~bash
python3.11 -m venv .venv-mcp
.venv-mcp/bin/pip install "mcp>=2,<3"
PYTHONPATH=src .venv-mcp/bin/python -m maestro_router.factory_mcp
~~~

O processo fica aguardando JSON-RPC em `stdin`, sem pagina web nem porta de rede. Isso e normal para MCP stdio. Nao cole credenciais em arquivos versionados. Para GitHub privado, `GITHUB_TOKEN` pode ser fornecido pelo ambiente do processo (escopo minimo); os dois repositorios autorizados sao publicos e nao exigem token no caso comum.

Para `maestro_catalog`, o Control Center precisa estar disponivel localmente em `http://127.0.0.1:8000`. A variavel opcional `MAESTRO_LOCAL_URL` aceita apenas `http://localhost` ou `http://127.0.0.1` (com porta), e **nao** endpoints remotos. Servico ausente retorna `unavailable`, nunca dados inventados.

### Opcional: OpenCode v2

Adicione ao `opencode.jsonc` pessoal, substituindo os caminhos absolutos pelo ambiente real:

~~~json
{
  "mcp": {
    "servers": {
      "ch-factory": {
        "type": "local",
        "command": ["/CAMINHO/maestro-router/.venv-mcp/bin/python", "-m", "maestro_router.factory_mcp"],
        "cwd": "/CAMINHO/maestro-router",
        "environment": {"PYTHONPATH": "/CAMINHO/maestro-router/src"},
        "disabled": true,
        "protocol": "auto"
      }
    }
  }
}
~~~

Inicie com `disabled: true`. Ative manualmente apenas para o ensaio, com o menor numero possivel de MCPs para economizar tokens.

### Testes offline

~~~bash
PYTHONPATH=src python -m pytest -q tests/test_factory_mcp.py
~~~

Testam allowlist de repositorios, bloqueio de URLs remotas, redacao de segredos, filtro de PRs, honestidade do status do fallback e erros fail-closed. **Nao substituem** um teste de handshake MCP real ou homologacao de seguranca do servidor.

## Evolucao e gates

- **CHDevFlow cliente:** [CH-MCP-01](https://github.com/hallanbrito/CHDevFlow/issues/73), branch isolada; nao interfere em #72/F1 do AGY.
- **Fallback real:** [Issue #61](https://github.com/hallanbrito/maestro-router/issues/61), com dependencia de #56, #59 e #60. A [Draft PR #51](https://github.com/hallanbrito/maestro-router/pull/51) e somente POC.
- **MCP remoto ChatGPT:** nao habilitado. Exige desenho proprio de autenticação OAuth 2.1, autorizacao de escopos, HTTPS/tunel confiavel, auditoria e gate do PO. Nao expor o endpoint administrativo local publicamente.
- **Escritas e dispatch:** fora desta fatia; dependem de gate do PO, controle de identidade, rate limiting, idempotencia e permissao por ferramenta.

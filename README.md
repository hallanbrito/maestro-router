# Maestro Router

Maestro Router é uma plataforma open source para roteamento econômico,
controlável e explicável entre modelos de inteligência artificial. O repositório
contém a primeira fatia executável do MVP: validação de `POST /v1/executions` e
recusa normativa quando nenhuma rota configurada é admissível. Integrações e
execução de modelos ainda não estão implementadas.

Comece por [AGENTS.md](AGENTS.md) para o fluxo operacional ou por
[docs/INDEX.md](docs/INDEX.md) para localizar a fonte normativa de cada assunto.
A documentação aprovada está em [`docs/`](docs/); detalhes de arquitetura podem
ser encontrados pelo mapa em [ARCHITECTURE.md](ARCHITECTURE.md).

Os demais arquivos vazios da raiz são placeholders e não devem ser interpretados
como decisões já tomadas.

## Execução local

Requer Python 3.12.

```shell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m uvicorn --app-dir src maestro_router.api:app
```

O catálogo padrão em memória é vazio, portanto uma solicitação válida recebe a
recusa normativa `NO_ELIGIBLE_ROUTE`.

```shell
.venv\Scripts\python -m pytest
```

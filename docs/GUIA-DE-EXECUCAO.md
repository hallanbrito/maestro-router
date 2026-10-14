# Guia de execução local — Maestro Router

> Guia operacional de apoio, não normativo. O [contrato público](05-API.md), as [ADRs](decisions/) e o [índice das fontes normativas](INDEX.md) governam seus respectivos assuntos.

Este guia concentra os comandos, os modos de composição e as observações de configuração que anteriormente tornavam o README extenso.

**Atenção:** o aplicativo neutro não possui rotas por padrão. Para efetuar chamadas reais à OpenAI, é necessário configurar explicitamente o modo opcional e fornecer credenciais próprias. Chamadas reais podem gerar custos no provedor. Não versione chaves.

## Execução local

Requer Python 3.12.

Crie o ambiente e instale as dependências:

```shell
python -m venv .venv
```

Ative o ambiente no Linux ou macOS com `source .venv/bin/activate`; no
PowerShell, use `.venv\Scripts\Activate.ps1`. Depois instale as dependências:

```shell
python -m pip install -r requirements-dev.txt
```

Com o ambiente ativo, inicie o aplicativo neutro:

```shell
python -m uvicorn --app-dir src maestro_router.api:app
```

O catálogo e o registro de adaptadores padrão em memória são vazios, portanto
uma solicitação válida recebe a recusa normativa `NO_ELIGIBLE_ROUTE`.

### Composição OpenAI opcional

A composição operacional OpenAI possui dois modos de configuração:

1. **Modo Legado (Rota única)**: Exige que o ambiente contenha valores não brancos para `OPENAI_API_KEY`, `MAESTRO_OPENAI_MODEL` e `MAESTRO_OPENAI_ROUTE_ID`. Opcionalmente, o operador pode fornecer uma única referência estruturada e completa em `MAESTRO_OPENAI_PRICE_REFERENCE_JSON` (conforme a [ADR 0006](decisions/0006-operational-price-reference-configuration.md)) e uma previsão estática em `MAESTRO_OPENAI_ESTIMATED_USAGE_JSON` (conforme a [ADR 0007](decisions/0007-operator-supplied-pre-execution-estimate.md)).
2. **Modo Multirrota**: Ativado quando `MAESTRO_OPENAI_ROUTES_JSON` é fornecido. O valor é um objeto JSON de nível superior contendo exatamente o membro obrigatório `routes`; `routes` contém o array não vazio de rotas (conforme as ADRs [0008](decisions/0008-multiple-openai-route-configuration.md), [0009](decisions/0009-operational-routing-constraints.md), [0010](decisions/0010-operational-known-unavailability.md) e [0011](decisions/0011-operational-route-enablement.md)). Cada entrada exige os membros `route_id`, `model`, `price_reference` e `estimated_usage`, e aceita opcionalmente `capabilities` (array de strings), `quality_criteria` (array de objetos fechados com `criterion` e `evidence_references`), `known_unavailable` (booleano JSON estrito true/false) e `enabled` (booleano JSON estrito true/false, padrão true). Exige `OPENAI_API_KEY` e impede a presença simultânea das variáveis do modo legado.
3. **Restrições Operacionais de Roteamento**: Configuração opcional neutra do operador via `MAESTRO_ROUTING_CONSTRAINTS_JSON` em modo multirrota (conforme a [ADR 0009](decisions/0009-operational-routing-constraints.md)). Permite definir `required_capabilities`, `required_quality_criteria`, `allowed_route_ids`, `max_estimated_costs` e `defaults`. Suas regras combinam-se monotonicamente com as restrições da solicitação pública, de modo que uma requisição nunca enfraquece as políticas obrigatórias globais.

No modo multirrota, JSON ou estrutura superior inválidos e ambiguidades que
impedem identificar o universo com segurança invalidam todo o snapshot. A mesma
regra vale para duplicidade de `route_id`, `model` ou `price_reference.id` entre
identidades estruturalmente válidas. Identidade ausente ou estruturalmente
inválida também é global quando impede associar o erro com segurança a uma rota.
Somente uma falha local isolável, em uma entrada com `route_id` válido e único,
exclui apenas essa rota; se nenhuma rota válida restar, ou se houver entradas
habilitadas inválidas ou de habilitação indeterminada sem nenhuma rota habilitada
localmente válida (conforme o limiar de suficiência da [ADR 0011](decisions/0011-operational-route-enablement.md)),
a inicialização falha.

A composição é iniciada explicitamente como uma fábrica ASGI:

```shell
python -m uvicorn --factory --app-dir src maestro_router.bootstrap:create_openai_app_from_env
```

### Exemplo mínimo reproduzível

O modo legado permite validar o fluxo completo com uma única rota, sem preço ou
estimativa padrão. Defina os valores no ambiente; nunca versione a chave.

Linux ou macOS:

```shell
export OPENAI_API_KEY="sua-chave"
export MAESTRO_OPENAI_MODEL="modelo-disponivel-na-sua-conta"
export MAESTRO_OPENAI_ROUTE_ID="route-primary"
python -m uvicorn --factory --app-dir src maestro_router.bootstrap:create_openai_app_from_env
```

PowerShell:

```powershell
$env:OPENAI_API_KEY = "sua-chave"
$env:MAESTRO_OPENAI_MODEL = "modelo-disponivel-na-sua-conta"
$env:MAESTRO_OPENAI_ROUTE_ID = "route-primary"
python -m uvicorn --factory --app-dir src maestro_router.bootstrap:create_openai_app_from_env
```

Em outro terminal, envie uma solicitação:

```shell
curl -X POST http://127.0.0.1:8000/v1/executions \
  -H "Content-Type: application/json" \
  -d '{"task":"Resuma em uma frase.","context":"O Maestro escolhe uma rota válida antes de executar o modelo."}'
```

No PowerShell, use a sintaxe nativa equivalente:

```powershell
$body = @{ task = "Resuma em uma frase."; context = "O Maestro escolhe uma rota válida antes de executar o modelo." } | ConvertTo-Json -Compress
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/executions" -ContentType "application/json" -Body $body
```

Essa composição realiza uma chamada real ao provedor. Para desenvolvimento e
testes automatizados, use clientes controlados; a suíte oficial não acessa a
rede externa.

A composição usa somente as entradas documentadas acima. Variáveis próprias do
SDK, como `OPENAI_BASE_URL`, `OPENAI_ORG_ID`, `OPENAI_PROJECT_ID` e
`OPENAI_CUSTOM_HEADERS`, não são suportadas por esse bootstrap e não alteram o
cliente capturado no snapshot.

Para cada rota habilitada e válida, a estimativa pré-execução é calculada no
bootstrap (rotas desabilitadas válidas são materializadas com estimativa
indisponível e sem cálculo prévio, conforme a [ADR 0011](decisions/0011-operational-route-enablement.md))
e as alternativas são ordenadas por `route_id`. Se restarem múltiplos candidatos
válidos, a rota com menor estimativa é selecionada para execução, com desempate
determinístico. Estimativa e custo calculado não representam billing nem
comprovam economia entre provedores.

Com o ambiente ativo:

```shell
python -m pytest -q
```

# Maestro Router

Maestro Router é uma plataforma open source para roteamento econômico,
controlável e explicável entre modelos de inteligência artificial. O repositório
contém uma implementação incremental do MVP.

O estado executável atual cobre:

- validação pública de `POST /v1/executions`;
- elegibilidade não econômica;
- avaliação econômica anterior à seleção;
- seleção determinística e validada pela estratégia `lowest-estimated-cost`;
- fronteira neutra de execução com adaptadores associados manualmente em memória;
- primeiro adaptador externo para a OpenAI Responses API, construído e injetado
  explicitamente;
- composição operacional OpenAI opcional, explícita e separada do aplicativo
  padrão neutro, com referência de preço e previsão estática de uso opcionais
  fornecidas pelo operador;
- primeira política operacional de estimativa pré-execução, decimalmente exata
  e limitada a uma previsão configurada de `input_token` e `output_token`;
- normalização de `input_tokens` e `output_tokens` do adaptador OpenAI em uso
  neutro completo, parcial ou indisponível;
- primeira política neutra e decimalmente exata de cálculo de custo posterior,
  limitada a `input_token` e `output_token` e disponível somente com referência
  de preço explícita e contexto tarifário completo;
- projeção pública normalizada de sucesso e dos erros de execução;
- recusas normativas `NO_ELIGIBLE_ROUTE` e
  `INSUFFICIENT_ECONOMIC_INFORMATION`.

Ainda não estão implementados ou configurados por padrão:

- rota, provedora ou modelo padrão;
- gestão de credenciais e configuração operacional padrão;
- preço padrão ou configuração automática de referência de preço;
- timeout concreto, retry ou fallback;
- tabela ou atualização automática de preços.

O adaptador OpenAI recebe um cliente assíncrono oficial já construído e não é
registrado no aplicativo padrão. A composição opcional faz explicitamente essa
construção e a associação a uma rota. Os testes usam somente clientes
controlados, sem chamada de rede. Em sucesso, a estimativa usada na seleção é
preservada; o uso observado pelo adaptador OpenAI é publicado como `available`,
`uncertain` ou `unavailable`. O núcleo calcula `calculated_cost` somente quando
a rota selecionada possui uma referência neutra, explícita e completa para as
unidades aprovadas `input_token` e `output_token`; informação insuficiente mantém
o custo como `unavailable`. A composição OpenAI pode associar uma referência
fornecida pelo operador e, quando uma previsão estática de uso também estiver
configurada, produzir uma estimativa pré-execução `available` com a mesma moeda
e referência. Sem essa previsão, a estimativa permanece `unavailable`. Não há
preço padrão, tokenização, consulta ou atualização automática. Mesmo
configurado, o custo posterior só pode ficar disponível com uso completo e não
representa billing, cobrança ou prova de economia entre provedores.

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

O catálogo e o registro de adaptadores padrão em memória são vazios, portanto
uma solicitação válida recebe a recusa normativa `NO_ELIGIBLE_ROUTE`.

### Composição OpenAI opcional

A composição operacional OpenAI possui dois modos de configuração:

1. **Modo Legado (Rota única)**: Exige que o ambiente contenha valores não brancos para `OPENAI_API_KEY`, `MAESTRO_OPENAI_MODEL` e `MAESTRO_OPENAI_ROUTE_ID`. Opcionalmente, o operador pode fornecer uma única referência estruturada e completa em `MAESTRO_OPENAI_PRICE_REFERENCE_JSON` (conforme a [ADR 0006](docs/decisions/0006-operational-price-reference-configuration.md)) e uma previsão estática em `MAESTRO_OPENAI_ESTIMATED_USAGE_JSON` (conforme a [ADR 0007](docs/decisions/0007-operator-supplied-pre-execution-estimate.md)).
2. **Modo Multirrota**: Ativado quando `MAESTRO_OPENAI_ROUTES_JSON` é fornecido, contendo uma lista estruturada de rotas (conforme a [ADR 0008](docs/decisions/0008-multiple-openai-route-configuration.md)), cada uma com seu próprio ID, modelo, referência de preço e previsão de uso. Exige `OPENAI_API_KEY` e impede a presença simultânea das variáveis do modo legado.

A composição é iniciada explicitamente como uma fábrica ASGI:

```shell
python -m uvicorn --factory --app-dir src maestro_router.bootstrap:create_openai_app_from_env
```

Para cada rota válida, a estimativa pré-execução é calculada no bootstrap e as alternativas são ordenadas por `route_id`. Sem a previsão de uso, a estimativa da rota permanece `unavailable`. A rota com menor estimativa é selecionada para execução, com desempate determinístico. Estimativa e custo calculado não representam billing nem comprovam economia entre provedores.

```shell
.venv\Scripts\python -m pytest
```

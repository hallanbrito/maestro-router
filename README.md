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
  padrão neutro;
- normalização de `input_tokens` e `output_tokens` do adaptador OpenAI em uso
  neutro completo, parcial ou indisponível;
- primeira política neutra e decimalmente exata de cálculo de custo posterior,
  disponível somente com referência de preço explícita e contexto tarifário
  completo;
- projeção pública normalizada de sucesso e dos erros de execução;
- recusas normativas `NO_ELIGIBLE_ROUTE` e
  `INSUFFICIENT_ECONOMIC_INFORMATION`.

Ainda não estão implementados ou configurados por padrão:

- rota, provedora ou modelo padrão;
- gestão de credenciais e configuração operacional padrão;
- referência de preço ou preço padrão na composição OpenAI;
- timeout concreto, retry ou fallback;
- tabela ou atualização automática de preços.

O adaptador OpenAI recebe um cliente assíncrono oficial já construído e não é
registrado no aplicativo padrão. A composição opcional faz explicitamente essa
construção e a associação a uma rota. Os testes usam somente clientes
controlados, sem chamada de rede. Em sucesso, a estimativa usada na seleção é
preservada; o uso observado pelo adaptador OpenAI é publicado como `available`,
`uncertain` ou `unavailable`. O núcleo calcula `calculated_cost` somente quando
a rota selecionada possui uma referência neutra, explícita e completa para todo
o uso observado; informação insuficiente mantém o custo como `unavailable`. A
composição OpenAI não configura preço e, portanto, continua com custo
indisponível. Uso observado e custo calculado não comprovam economia entre
provedores.

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

A composição operacional OpenAI exige que o ambiente contenha valores não
brancos para `OPENAI_API_KEY`, `MAESTRO_OPENAI_MODEL` e
`MAESTRO_OPENAI_ROUTE_ID`. Ela é iniciada explicitamente como uma fábrica ASGI:

```shell
python -m uvicorn --factory --app-dir src maestro_router.bootstrap:create_openai_app_from_env
```

Essa composição contém uma única rota, sem capacidades, critérios de qualidade
ou estimativa econômica declarada. Ela não comprova comparação econômica entre
provedores. O uso retornado pela OpenAI é normalizado quando defensável, mas
`calculated_cost` permanece `unavailable` porque não existe referência de preço
configurada. Não há tabela automática nem preço padrão, e o uso não comprova
economia entre provedores.

```shell
.venv\Scripts\python -m pytest
```

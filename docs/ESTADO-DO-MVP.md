# Estado atual do MVP — Maestro Router

> Documento informativo, não normativo. Para contratos e regras aprovadas, consulte [docs/INDEX.md](INDEX.md) e suas fontes vinculadas.

**Situação:** o núcleo de roteamento e os testes estão implementados; a publicação da pré-release está pausada para auditoria. A integração externa executável é o adaptador opcional OpenAI. Não há adaptadores operacionais para outros provedores neste repositório.

As [notas da candidata v0.1.0-rc.1](releases/v0.1.0-rc.1.md) descrevem o escopo preparado para avaliação técnica. Não há release publicada.

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
  `INSUFFICIENT_ECONOMIC_INFORMATION`;
- configuração operacional de capacidades e critérios de qualidade por rota com
  referências de evidência, requisitos globais, allowlists operacionais,
  múltiplos tetos econômicos cumulativos e valores padrão com composição
  monotônica (ADR 0009);
- declaração operacional de indisponibilidade conhecida por rota (`known_unavailable`)
  com exclusão prévia à avaliação econômica sem chamadas externas (ADR 0010);
- habilitação operacional de rota (`enabled`) com desabilitação declarativa,
  precedência normativa de `disabled_route` e checagem de suficiência no bootstrap
  sem chamadas externas (ADR 0011).

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

Para colocar a aplicação em funcionamento, consulte o [Guia de execução local](GUIA-DE-EXECUCAO.md). O [contrato público da API](05-API.md), as [decisões de roteamento](06-DECISAO-DE-ROTEAMENTO.md) e as [ADRs](decisions/) prevalecem sobre este resumo quando aplicáveis.

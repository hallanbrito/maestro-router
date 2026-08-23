# ADR 0005 — Referência de preço e cálculo de custo pós-execução

## Contexto

O contrato público já separa a estimativa anterior à execução, o uso observado
e normalizado e o custo calculado posteriormente. A ADR 0004 iniciou essa
evolução ao definir a normalização neutra dos contadores primários de uso.

Na implementação atual, `input_token` representa o total de entrada observado,
`output_token` representa o total de saída observado e `calculated_cost`
permanece sempre `unavailable`. A composição OpenAI não possui preço nem método
de estimativa aprovado.

Esta ADR registra uma decisão arquitetural para implementação futura. Ela não
torna `calculated_cost` disponível nesta etapa.

## Decisão

### Separação econômica

Permanecem conceitos distintos:

- `estimate`: estimativa capturada antes da execução e usada na decisão;
- `usage`: uso observado e normalizado depois da tentativa externa;
- `calculated_cost`: cálculo posterior produzido somente quando uso, preço e
  contexto tarifário forem suficientes.

O custo posterior não participa da seleção já realizada, não provoca nova
decisão, não invalida retroativamente uma execução e não substitui a estimativa
anterior. Ele não comprova economia entre provedores e não representa cobrança,
fatura ou conciliação do provedor.

### Referência de preço neutra

O cálculo futuro usará uma referência de preço neutra, validada e imutável
durante o snapshot da execução. Ela será fornecida explicitamente por
configuração controlada pelo operador. Esta decisão não escolhe arquivo,
variável de ambiente, banco de dados, API nem outro mecanismo concreto.

Não haverá busca automática de preços na internet, tabela silenciosamente
embutida no código, preço padrão, atualização dinâmica durante uma execução nem
preferência comercial por provedor.

A referência terá identidade neutra e não branca, projetável como
`price_reference`, e identificará inequivocamente os fatos econômicos usados.
Conceitualmente, ela abrangerá:

- contexto de rota e modelo ao qual se aplica;
- moeda;
- unidades tarifáveis normalizadas;
- taxa decimal não negativa de cada unidade;
- base da taxa inteira, positiva e igual a uma potência de dez, como `1`,
  `1000` ou `1000000`;
- versão, vigência ou momento de verificação;
- fonte ou responsável pela manutenção;
- condições tarifárias necessárias para determinar sua aplicabilidade.

Essa descrição não cria novo schema público nem antecipa nomes de classes
Python.

### Snapshot e determinismo

A decisão, a execução e o cálculo posterior usarão o mesmo snapshot aplicável
de rota e referência econômica. A mesma referência, o mesmo contexto tarifário
e o mesmo uso normalizado produzirão o mesmo custo.

Quando `estimate.status` for `available` ou `uncertain`, um
`calculated_cost.status = available` somente poderá usar exatamente a mesma
`currency` e o mesmo `price_reference` da estimativa registrada antes da
execução. Se essa correspondência não puder ser assegurada, a primeira política
produzirá `calculated_cost.status = unavailable`, com razão sanitizada.

Quando a estimativa for `unavailable` e tiver sido aceita porque custo não era
indispensável, dados posteriores completos ainda poderão produzir custo com
uma referência configurada aplicável, conforme permitido por
`docs/05-API.md`. Em nenhum caso o custo posterior recalculará ou substituirá a
estimativa anterior.

Uma atualização de preços somente poderá afetar snapshots posteriores. Ela não
alterará retrospectivamente uma resposta já calculada.

### Precisão decimal

O cálculo futuro usará aritmética decimal exata e rejeitará ponto flutuante.
Quantidades e taxas serão não negativas. Não haverá conversão cambial implícita
nem arredondamento silencioso que altere o valor calculado. Valores seguirão a
gramática decimal pública definida em `docs/05-API.md`.

Na primeira implementação futura, `base_da_taxa` será um inteiro positivo e uma
potência de dez, como `1`, `1000` ou `1000000`. Essa limitação garante que
quantidades e taxas decimais finitas continuem representáveis como strings
decimais finitas. Se o resultado não puder ser representado exatamente pela
gramática pública, `calculated_cost` permanecerá `unavailable`. Outras formas
de base ou qualquer política de arredondamento dependerão de decisão futura
separada.

Para unidades independentes, a fórmula conceitual será equivalente à soma de:

```text
quantidade × taxa / base_da_taxa
```

Somente unidades que não produzam dupla contagem poderão participar da fórmula.

### Condições para `available`

Na primeira implementação futura, `calculated_cost.status = available` somente
poderá ocorrer quando todos estes fatos forem comprovados:

- o uso relevante está completo e defensável;
- todas as unidades tarifáveis aplicáveis estão conhecidas;
- não existe dupla contagem entre total e detalhamentos;
- todas as taxas necessárias existem;
- moeda, modelo, rota e contexto tarifário correspondem à referência;
- quando a estimativa possuir valor, moeda e referência correspondem exatamente
  às registradas antes da execução;
- a referência pertence ao mesmo snapshot da execução;
- nenhuma condição material de preço ficou sem representação;
- o resultado pode ser calculado exatamente pela política aprovada.

Valor zero somente será permitido quando uso e taxas demonstrarem custo
realmente zero.

### Informação insuficiente

A primeira implementação futura produzirá somente `available`, quando todas as
condições de completude forem satisfeitas, ou `unavailable`, em qualquer outro
caso. Embora o contrato público continue aceitando
`calculated_cost.status = uncertain`, esta política não produzirá número
aproximado, subtotal ou limite como se fosse o custo total.

`uncertain` permanecerá reservado para uma política futura específica que
defina quando existe valor aproximado defensável. Esta ADR não aprova essa
política. Consequentemente:

- uso `unavailable` produzirá custo `unavailable`;
- uso `uncertain` produzirá custo `unavailable` nesta primeira política;
- uso público `available` ainda poderá produzir custo `unavailable` quando não
  contiver todos os detalhes tarifários necessários;
- ausência de preço, incompatibilidade de referência ou contexto tarifário
  incompleto produzirá custo `unavailable`;
- toda indisponibilidade conterá razão objetiva e sanitizada.

### Cache e prevenção de dupla contagem

`input_token` já representa o total de entrada observado na implementação
atual, e `output_token`, o total de saída observado. A documentação oficial da
OpenAI serve somente como evidência de que categorias tarifárias adicionais
podem existir:

- [Prompt Caching — OpenAI API](https://developers.openai.com/api/docs/guides/prompt-caching)
- [Pricing — OpenAI API](https://developers.openai.com/api/docs/pricing)

Nenhum preço real é adotado por esta ADR. Uma implementação futura poderá
transportar detalhes neutros adicionais, como `cached_input_token` e
`cache_write_token`, sem importar tipos do SDK nem expor payload bruto.

Quando esses detalhes forem subconjuntos do total de entrada, o cálculo validará
sua relação com `input_token`. Para uma política que os trate como categorias
mutuamente exclusivas:

```text
ordinary_input_token =
    input_token
    - cached_input_token
    - cache_write_token
```

Esse cálculo somente será válido quando todos os valores necessários estiverem
presentes, forem inteiros não negativos, os subconjuntos forem comprovadamente
disjuntos, sua soma não exceder `input_token` e a referência econômica declarar
como cada categoria é tarifada.

A ausência de um detalhe não será convertida automaticamente em zero. Zero
somente poderá ser assumido quando a própria referência aplicável demonstrar
que a categoria não existe ou não se aplica naquele contexto.

`total_tokens` não participará da soma do custo, pois agregá-lo aos contadores de
entrada e saída produziria dupla contagem. Se houver saída, ferramenta,
modalidade, cache, faixa de volume, tier de serviço, multiplicador de contexto
ou qualquer outra categoria com preço distinto não representado, o custo
permanecerá `unavailable`.

### Identidade do modelo e contexto tarifário

Uma referência de preço somente produzirá custo `available` quando for
aplicável ao modelo e ao contexto realmente usados. Identificador mutável,
alias de modelo ou divergência entre a rota configurada e a identidade
tarifária efetiva não será tratado silenciosamente como correspondência exata.

Se a compatibilidade não puder ser comprovada, `calculated_cost` permanecerá
`unavailable`. Essa regra não exige alteração do contrato público nem exposição
do objeto bruto da provedora.

### Relação com a ADR 0004

Esta ADR especializa a futura evolução econômica iniciada pela ADR 0004. O
estado implementado pela ADR 0004 permanece verdadeiro: somente os contadores
primários estão normalizados; cache, gravação de cache e outros detalhes ainda
não são publicados nem transportados; e `calculated_cost` continua
`unavailable`.

Os novos detalhes e o cálculo não existem nesta etapa. Esta ADR apenas define
as condições que uma implementação posterior deverá satisfazer.

## Segurança e neutralidade

- Nenhum preço concede preferência ao provedor.
- Nenhum objeto do SDK pertence ao núcleo.
- Nenhum payload bruto é publicado.
- Nenhuma credencial, segredo, request ID externo ou mensagem interna é exposta.
- Razões públicas são sanitizadas.
- `price_reference` é um identificador econômico neutro, não um local para
  incluir segredo ou conteúdo bruto.

## Consequências

- Uma implementação posterior terá critérios determinísticos e conservadores
  para disponibilizar custo calculado.
- Informação tarifária incompleta permanecerá explícita como `unavailable`.
- O contrato público existente e a estimativa anterior serão preservados.
- A neutralidade entre provedores e a separação do SDK continuarão obrigatórias.
- `calculated_cost` permanece `unavailable` na implementação atual.

## Limites deliberados

Esta ADR não define nem implementa código de cálculo, preço real ou tabela de
preços, atualização automática de preços, formato operacional de configuração,
estimativa pré-execução, alteração do algoritmo de roteamento, novo schema
público, segundo provedor, múltiplas rotas operacionais, billing, faturamento ou
conciliação, conversão cambial, timeout concreto, retry, fallback, streaming,
persistência, observabilidade, monitoramento, banco de dados, Docker, CI/CD,
deployment, dashboard, agentes, memória ou workflows.

Esses limites não constituem roadmap nem promessa.

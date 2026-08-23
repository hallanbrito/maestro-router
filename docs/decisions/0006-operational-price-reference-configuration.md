# ADR 0006 — Configuração operacional da referência de preço

## Contexto

A ADR 0005 definiu uma política neutra e conservadora para a referência de
preço e o cálculo de custo pós-execução. A W13 implementou a primeira política
de cálculo exato, limitada às unidades `input_token` e `output_token`. Uma rota
pode carregar internamente uma `PriceReference`, mas a composição OpenAI atual
não associa referência de preço à sua rota.

Consequentemente, no bootstrap OpenAI publicado, `estimate` permanece
`unavailable` e `calculated_cost` continua `unavailable`, mesmo quando o uso é
normalizado. Ainda falta um mecanismo operacional aprovado para o operador
fornecer os fatos econômicos necessários.

Esta ADR decide exclusivamente esse mecanismo para uma implementação futura.
Ela não implementa configuração, parsing, validação ou qualquer outra
capacidade executável e não declara que a composição OpenAI já aceita preços.

## Decisão

### Mecanismo operacional

A composição OpenAI aceitará uma única variável de ambiente opcional:

```text
MAESTRO_OPENAI_PRICE_REFERENCE_JSON
```

Seu valor conterá um documento JSON estruturado com a referência de preço
fornecida e mantida pelo operador. Essa entrada será adicional a
`OPENAI_API_KEY`, `MAESTRO_OPENAI_MODEL` e `MAESTRO_OPENAI_ROUTE_ID`, que
continuarão obrigatórias para a composição OpenAI e conservarão seus
significados atuais.

Quando a variável opcional estiver ausente, o comportamento atual será
preservado integralmente: a rota não terá referência de preço, a estimativa
continuará `unavailable` e o custo posterior continuará `unavailable`.

Quando a variável estiver presente, inclusive com string vazia ou formada
somente por espaços, o documento inteiro deverá ser validado antes da
construção do cliente externo e da aplicação. JSON malformado, estruturalmente
inválido ou economicamente insuficiente impedirá a inicialização. Uma
configuração de preço explicitamente fornecida e inválida nunca produzirá
fallback silencioso para uma rota sem preço.

### Estrutura fechada e vinculação à rota

O valor de nível superior deverá ser um objeto JSON fechado contendo exatamente
estes membros, todos obrigatórios:

- `id`;
- `currency`;
- `version`;
- `source`;
- `rates`;
- `conditions`;
- `context_complete`;
- `units_exhaustive`;
- `no_double_counting`;
- `model_identity_exact`.

O documento operacional não conterá `route_id`, `provider` nem `model`. A
composição vinculará a referência ao mesmo snapshot da rota, usando:

- `route_id` de `MAESTRO_OPENAI_ROUTE_ID`;
- `provider` como o identificador interno fixo `openai`;
- `model` de `MAESTRO_OPENAI_MODEL`.

Essa vinculação evita duplicação e divergência silenciosa entre a rota
configurada e a referência associada. Ela não elimina a obrigação do operador
de confirmar que o identificador do modelo representa exatamente a identidade
tarifária aplicável.

### Validação do documento

Aplicam-se as seguintes regras:

- `id`, `version` e `source` serão strings não brancas;
- `id` será um identificador econômico neutro, opaco e seguro para exposição
  pública; não poderá conter segredo, credencial, payload bruto ou informação
  sensível;
- `currency` seguirá exatamente `^[A-Z]{3}$`;
- `conditions` será um array, possivelmente vazio, de strings únicas e não
  brancas;
- valores não serão corrigidos, aparados ou normalizados silenciosamente;
- igualdade e duplicidade serão verificadas de forma exata;
- campos ausentes ou desconhecidos serão inválidos;
- nomes de membros JSON duplicados serão inválidos em qualquer objeto, mesmo
  quando os valores forem iguais;
- o valor de nível superior deverá ser um objeto JSON;
- tipos JSON incorretos serão inválidos;
- `NaN`, infinito, notação que não pertença ao JSON padrão ou interpretação
  permissiva equivalente não serão aceitos.

A configuração será tratada como entrada não confiável, embora não seja uma
credencial.

### Tarifas

`rates` será um array contendo exatamente duas tarifas: uma para
`input_token` e outra para `output_token`. Cada tarifa será um objeto fechado
contendo exatamente `unit`, `rate` e `base`.

As unidades serão únicas e nenhuma outra unidade será aceita nesta primeira
configuração. A ordem das tarifas no JSON não influenciará o resultado.

`rate` será uma string decimal não negativa conforme a gramática pública já
aprovada. Número JSON de ponto flutuante não substituirá essa string. `base`
será um inteiro JSON positivo e igual a uma potência de dez; booleanos não
serão aceitos como inteiros. Tarifa, unidade ou campo ausente não será
convertido em zero, e nenhum preço padrão será criado.

Esta decisão não adota nem documenta preços reais de qualquer modelo ou
provedor.

### Declarações explícitas de completude

`context_complete`, `units_exhaustive`, `no_double_counting` e
`model_identity_exact` serão booleanos JSON explícitos com valor `true`. Eles
representam declarações controladas do operador de que:

- nenhuma condição tarifária material ficou de fora;
- `input_token` e `output_token` formam o conjunto tarifável completo da
  referência;
- as duas unidades não produzem dupla contagem;
- o modelo configurado corresponde exatamente à identidade tarifária
  declarada.

Se qualquer declaração estiver ausente, tiver tipo incorreto ou for `false`, a
referência não será aceita para essa composição operacional e a inicialização
falhará.

Essas declarações não constituem verificação automática de preços externos. O
Maestro validará a estrutura e a coerência interna; o operador continuará
responsável pela correção, vigência, origem e manutenção dos fatos informados.

### Validação antes da inicialização

As três entradas existentes e o JSON de preço serão validados antes da
construção de `AsyncOpenAI`. Configuração inválida impedirá o processo de
começar a atender solicitações, e nenhuma chamada de rede ocorrerá durante a
validação.

Erros de validação ou inicialização poderão identificar somente o nome seguro
da variável ou a categoria ou caminho estático do campo inválido. Mensagens de
validação, logs e exceções de inicialização não reproduzirão valores recebidos,
taxas, fonte, condições, conteúdo bruto do JSON ou credenciais.

As respostas públicas continuarão governadas exclusivamente por
`docs/05-API.md`. Quando a política produzir `calculated_cost.status =
available`, a projeção poderá conter somente os fatos econômicos aprovados pelo
contrato: `status`, valor calculado, moeda, identificador público e seguro
`price_reference` e hipóteses. Quando o custo permanecer `unavailable`, sua
razão será objetiva e sanitizada. Tarifas individuais, fonte, condições,
documento JSON bruto e credenciais nunca serão expostos.

A implementação futura continuará testável por meio de configurações e
clientes controlados, sem modificar o ambiente real do processo. Esta decisão
não antecipa uma assinatura Python definitiva.

### Snapshot e imutabilidade

O JSON será lido e validado uma única vez na composição. A referência neutra
será construída e associada à única rota OpenAI do snapshot. O adaptador OpenAI
não receberá preço, referência ou configuração econômica.

Alterações posteriores no ambiente não mudarão uma aplicação já criada. Uma
atualização de preço exigirá nova composição ou reinicialização do processo e
afetará somente snapshots posteriores. Respostas já calculadas não serão
alteradas retrospectivamente.

### Efeito econômico limitado

A referência operacional afetará somente o cálculo pós-execução já aprovado.
Mesmo com referência configurada:

- `estimate` continuará `unavailable`;
- a referência não participará da seleção da rota;
- não haverá estimativa pré-execução;
- `max_estimated_cost` continuará sem poder ser comprovado pela composição
  OpenAI;
- solicitações com teto econômico continuarão sujeitas a
  `INSUFFICIENT_ECONOMIC_INFORMATION`;
- o custo posterior somente poderá ficar `available` depois de uma execução
  bem-sucedida, quando o uso normalizado e todas as condições da política
  existente forem satisfeitos;
- uso ou contexto insuficiente continuará produzindo custo `unavailable`;
- o custo posterior não provocará nova seleção, retry, fallback ou segunda
  execução;
- o valor calculado não representará cobrança, fatura ou conciliação do
  provedor e não comprovará economia entre provedores.

### Neutralidade e responsabilidade

O mecanismo inicial é específico do bootstrap OpenAI porque essa é a única
composição externa operacional existente. A representação construída
continuará sendo a referência de preço neutra do núcleo. Isso não transforma a
OpenAI em provedor padrão ou conceitualmente obrigatório, não define o formato
geral e definitivo de configuração do Maestro e não concede preferência
econômica ou comercial a qualquer provedor.

Outros provedores ou múltiplas rotas exigirão decisão futura própria. O
operador será responsável por fornecer, verificar e atualizar os preços. O
Maestro não consultará automaticamente páginas de preços e não afirmará que a
referência corresponde à cobrança real do provedor.

### Relação com decisões anteriores

Esta ADR especializa a ADR 0003 somente para autorizar a nova entrada opcional
e estruturada de preço. Ela não altera as três variáveis obrigatórias já
aprovadas e não transforma JSON no formato geral de toda a configuração.

Ela fecha apenas o mecanismo concreto deixado deliberadamente aberto pela ADR
0005. Não altera a política de cálculo implementada, o contrato público nem o
algoritmo de roteamento e preserva todas as demais limitações das decisões
anteriores.

## Consequências

- Uma implementação posterior poderá associar uma referência completa à rota
  OpenAI sem embutir preços.
- A ausência da variável preservará compatibilidade com o bootstrap atual.
- Uma variável explicitamente fornecida e inválida falhará cedo.
- O operador ganhará controle explícito sobre os fatos econômicos.
- A configuração continuará determinística e imutável por snapshot.
- A estimativa pré-execução continuará sendo uma lacuna deliberadamente
  preservada.
- A implementação futura ainda dependerá de aprovação expressa do Product
  Owner.

## Limites deliberados

Esta etapa não inclui implementação, preços reais, tabela de preços embutida,
preço ou referência padrão, arquivo JSON, `.env`, YAML ou TOML, argumentos
adicionais de linha de comando, consulta automática à internet ou à OpenAI,
SDK ou API de preços, atualização, polling ou recarga dinâmica, múltiplas
referências, múltiplas rotas ou catálogo geral.

Também não inclui estimativa pré-execução; alteração de elegibilidade,
estratégia ou roteamento; cache pricing, reasoning tokens, `total_tokens`,
ferramentas, modalidades ou outras unidades; aliases tratados silenciosamente
como identidade exata; tiers, faixas, descontos, câmbio ou conversão de moeda;
billing, faturamento ou conciliação; endpoint administrativo; persistência ou
banco de dados; timeout, retry, fallback ou streaming; observabilidade,
monitoramento ou tracing; Docker, CI/CD, deployment ou infraestrutura;
dashboard, agentes, memória ou workflows; novas dependências; ou alteração do
schema público.

Esses limites não constituem roadmap nem promessa.

# API Pública do MVP do Maestro Router

## 1. Propósito e fontes

Este documento transforma os comportamentos aprovados no [Manifesto](00-MANIFESTO.md), na [Visão Geral](01-VISAO-GERAL.md), na [Proposta de Valor](02-PROPOSTA-DE-VALOR.md), na [Arquitetura Conceitual](03-ARQUITETURA.md) e nos [Casos de Uso](04-CASOS-DE-USO.md) no contrato técnico mínimo da API pública do MVP.

Os documentos `00–04` permanecem aprovados e não são redefinidos aqui. Em caso de conflito, prevalece o Manifesto. Este contrato descreve o que deverá ser implementado posteriormente; ele não afirma que a API já exista.

O objetivo é oferecer uma única operação pública capaz de receber uma tarefa, decidir uma rota válida, executar essa rota e devolver um resultado ou erro normalizado com explicação e informação econômica suficiente. A superfície foi mantida deliberadamente pequena.

## 2. Fronteira do contrato

### 2.1 API pública do Maestro

A aplicação cliente conhece somente:

- o endpoint público versionado;
- a representação comum de tarefa, contexto e restrições;
- o resultado normalizado;
- a decisão de seleção ou recusa;
- as informações econômicas e de uso normalizadas;
- a taxonomia de erros deste documento.

Identificar uma rota, seu provedor e seu modelo por strings neutras faz parte da explicabilidade e não torna o contrato dependente de um provedor.

### 2.2 Integrações internas com provedores

Router, Provider Registry, Cost Evaluation, Strategy Engine, Validation, configuração e adaptadores continuam responsabilidades internas. O Router coordena o fluxo completo, e, no fluxo normal, somente o adaptador da rota selecionada conversa com o provedor externo.

Não fazem parte do contrato público:

- payloads, parâmetros, headers, endpoints ou códigos nativos de provedores;
- mecanismos de autenticação de provedores;
- respostas ou erros externos brutos;
- registro de adaptadores;
- formato interno da configuração;
- lógica interna de elegibilidade, cálculo ou estratégia, além dos comportamentos observáveis definidos aqui.

Credenciais, tokens, chaves, valores resolvidos de segredos, stack traces e corpos brutos de respostas externas nunca podem aparecer em uma resposta pública, inclusive em mensagens de erro.

## 3. Decisões técnicas novas desta etapa

As decisões abaixo eram deliberadamente abertas em `00–04` e são fechadas pelo `05` porque são necessárias para tornar a fronteira pública implementável. Elas ficam destacadas para revisão antes da implementação.

| Decisão nova | Justificativa para o MVP |
| --- | --- |
| HTTP síncrono com JSON UTF-8 | Corresponde ao fluxo linear já aprovado e exige somente um modelo simples de solicitação e resposta. |
| Versionamento no caminho por `/v1` | Torna a versão inequívoca sem headers ou negociação adicional. |
| Um único endpoint, `POST /v1/executions` | Cobre decisão e execução sem criar endpoints auxiliares, recursos administrativos ou persistência pública. |
| Uma resposta JSON na mesma interação, sem streaming ou operação assíncrona | É a menor forma de entregar o resultado normalizado e as informações da decisão. |
| Tarefa, contexto e resultado públicos são textuais na v1 | Fecha uma representação comum mínima sem inventar multimodalidade nem adotar formatos de chat de um provedor. |
| Restrições públicas limitadas a capacidade, critérios de qualidade configurados, allowlist de rotas e teto de custo estimado | Representa somente dimensões sustentadas por `00–04`, sem criar um motor genérico de políticas. |
| Objetos de entrada são fechados: campos desconhecidos, `null` e nomes de membros JSON duplicados são inválidos; identificadores usam igualdade exata | Evita ignorar, sobrescrever ou alterar silenciosamente uma restrição. |
| Valores monetários e de uso são strings decimais; moeda usa três letras ASCII maiúsculas e não há conversão cambial implícita | Evita ambiguidade de ponto flutuante e comparação econômica sem base declarada. |
| Decisão, economia e erro acompanham a resposta da própria operação | Atende à explicabilidade sem exigir consulta posterior, retenção ou dashboard. |
| Configuração validada é pré-condição externa à API pública | Preserva o UC-01 sem inventar API administrativa, painel, banco de dados ou mecanismo de configuração. |

Nenhuma dessas decisões escolhe linguagem, framework, biblioteca HTTP, armazenamento ou infraestrutura.

## 4. Protocolo e endpoint

### 4.1 Operação pública

```http
POST /v1/executions
Content-Type: application/json
```

O corpo é um objeto JSON conforme a seção 5. O media type deve ser `application/json`; o parâmetro opcional `charset`, quando presente, deve indicar UTF-8, sem distinção de caixa. Toda resposta possui `Content-Type: application/json` e usa um dos status HTTP definidos nas seções 7 e 9.

A operação é síncrona: dentro da mesma interação, o Maestro valida a entrada, forma uma decisão, executa a rota selecionada quando houver decisão válida e devolve um resultado ou erro final. A operação não implica retenção da execução e não cria um recurso consultável posteriormente.

O contrato v1 não define streaming, jobs assíncronos, polling, callbacks ou webhooks.

### 4.2 Versionamento mínimo

`v1` faz parte do caminho. O contrato não usa header adicional de versão nem negociação de versão. Uma mudança incompatível no significado ou na obrigatoriedade dos campos exige outra versão de caminho; este documento não define ciclo de vida de versões futuras.

### 4.3 Superfície deliberadamente ausente

Não existem no contrato do MVP endpoints de configuração, provedores, modelos, catálogo, administração, usuários, tenants, autenticação, billing, histórico, saúde, métricas ou monitoramento. Também não existe compatibilidade com a API da OpenAI ou de qualquer outro provedor.

## 5. Solicitação

### 5.1 Estrutura

```json
{
  "task": "Resuma o contexto em três frases.",
  "context": "Texto que deverá ser resumido.",
  "constraints": {
    "required_capabilities": [
      "text_generation",
      "summarization"
    ],
    "required_quality_criteria": [
      "summary_faithfulness_accepted"
    ],
    "allowed_route_ids": [
      "route-text-a",
      "route-text-b"
    ],
    "max_estimated_cost": {
      "amount": "0.0100",
      "currency": "USD"
    }
  }
}
```

| Campo | Tipo | Obrigatório | Significado e ausência |
| --- | --- | --- | --- |
| `task` | string com ao menos um caractere não branco | Sim | Instrução ou objetivo textual da execução. Não é um array de mensagens nem um payload externo. |
| `context` | string com ao menos um caractere não branco | Não | Material textual adicional necessário à tarefa. Ausência significa que nenhum contexto adicional foi fornecido; o Maestro não inventa um. |
| `constraints` | objeto | Não | Restrições adicionais da solicitação. Ausência ou `{}` mantém somente restrições obrigatórias e valores padrão da configuração. |
| `constraints.required_capabilities` | array não vazio de strings únicas | Não | Capacidades neutras que toda rota admissível deve declarar. |
| `constraints.required_quality_criteria` | array não vazio de strings únicas | Não | Critérios de qualidade configurados que toda rota admissível deve declarar como satisfeitos. |
| `constraints.allowed_route_ids` | array não vazio de strings únicas | Não | Conjunto máximo de rotas que a solicitação permite considerar. |
| `constraints.max_estimated_cost` | objeto monetário | Não | Limite por solicitação aplicado à estimativa anterior à execução. |
| `constraints.max_estimated_cost.amount` | string decimal não negativa | Sim quando o objeto pai existe | Valor máximo estimado na moeda indicada. |
| `constraints.max_estimated_cost.currency` | string | Sim quando o objeto pai existe | Código de moeda com exatamente três letras ASCII maiúsculas, conforme `^[A-Z]{3}$`. A configuração determina quais códigos são suportados. |

### 5.2 Regras gerais de validação

- `task`, `context` e identificadores usam Unicode, são sensíveis a maiúsculas e minúsculas e não podem conter somente espaços.
- Identificadores são opacos. A API não atribui semântica a partes do identificador e não corrige valores desconhecidos.
- Identificadores são comparados pela sequência exata de caracteres depois da decodificação JSON, sem trim, alteração de caixa ou normalização Unicode implícita. A mesma igualdade exata determina duplicatas nos arrays.
- Strings textuais são preservadas como recebidas; a validação de conteúdo não remove silenciosamente espaços significativos.
- `null` não substitui ausência. Um campo opcional deve ser omitido quando não houver valor; se presente com `null`, a solicitação é inválida.
- Campos desconhecidos em qualquer objeto da solicitação tornam a solicitação inválida. Não existe campo genérico para extensões, metadados ou payload nativo.
- Nomes de membros repetidos no mesmo objeto JSON tornam a solicitação inválida, mesmo que os valores repetidos sejam iguais. O Maestro não adota a interpretação do primeiro ou do último valor.
- Arrays presentes devem ser não vazios e não podem repetir o mesmo identificador.
- A string decimal segue `^(0|[1-9][0-9]*)(\.[0-9]+)?$`: aceita `0` ou um inteiro positivo sem zeros iniciais, opcionalmente seguido de `.` e uma ou mais casas decimais. Sinal, vírgula, notação exponencial, `NaN` e infinito são inválidos.
- Um limite monetário igual a `0` é válido quando intencional; ele não representa informação ausente.
- Identificadores estruturalmente válidos, mas inexistentes na configuração, não são adivinhados nem corrigidos. A restrição simplesmente não será satisfeita por uma rota que não declare o identificador.
- A solicitação não escolhe estratégia, não fornece credenciais e não contém parâmetros de geração próprios de provedor.

O contrato não fixa um limite universal de tamanho para os textos porque a capacidade aplicável pertence às rotas configuradas. Uma rota incapaz de atender ao tamanho ou à natureza da tarefa é inelegível; o Maestro não trunca a entrada silenciosamente.

### 5.3 Semântica das restrições

#### Capacidades obrigatórias

Cada valor de `required_capabilities` é um identificador neutro definido na configuração. Uma rota só permanece elegível se declarar todas as capacidades solicitadas.

#### Critérios de qualidade obrigatórios

Cada valor de `required_quality_criteria` identifica um critério de aceitação previamente definido e sustentado pelas evidências aplicáveis na configuração. A v1 trata o critério como satisfeito ou não satisfeito pela rota; ela não inventa uma escala universal de qualidade nem recebe pesos ou scores da aplicação.

Uma rota só permanece elegível se sua configuração validada declarar que satisfaz todos os critérios solicitados. Métricas, benchmarks, limiares concretos e processo de validação desses identificadores permanecem fora do contrato público.

#### Allowlist de rotas

`allowed_route_ids` é sempre restritiva. Seu conteúdo é intersectado com as rotas configuradas, habilitadas e válidas. Informar o ID de uma rota desativada, inválida ou inexistente não a habilita.

A allowlist é a representação mínima de preferências obrigatórias por solicitação. Preferências flexíveis, pesos e ranqueamento por solicitação não fazem parte da v1; a comparação continua responsabilidade da estratégia configurada.

#### Limite de custo estimado

`max_estimated_cost` limita a estimativa por execução antes da chamada externa. Não é orçamento acumulado, crédito, reserva, billing nem garantia de que o custo calculado posteriormente ou a cobrança final do provedor ficará abaixo do valor.

Uma rota só satisfaz o limite quando uma estimativa `available` demonstra, na mesma moeda, que o valor não o excede. Como o estado `uncertain` da v1 não representa um limite superior, ele não prova conformidade com `max_estimated_cost`; nesse caso, a rota é economicamente não avaliável. O MVP não converte moedas. Uma estimativa em moeda diferente, sem base comum já configurada, também é economicamente não comparável.

### 5.4 Combinação com a configuração

As restrições obrigatórias são formadas de maneira monotônica em relação às rotas habilitadas e aos limites obrigatórios da configuração: a solicitação pode reduzir esse conjunto permitido, nunca habilitar rota desativada nem enfraquecer requisito obrigatório.

Valores padrão não são restrições obrigatórias. Um padrão é usado somente quando a solicitação omite a dimensão correspondente; um valor explícito ocupa o lugar do padrão, mas continua subordinado a todas as restrições obrigatórias. Portanto, a monotonicidade não compara a solicitação com o resultado hipotético de um valor padrão que deixou de ser aplicável.

| Dimensão | Combinação observável |
| --- | --- |
| Rotas habilitadas | A solicitação somente filtra o conjunto previamente configurado e habilitado. |
| Capacidades | Requisitos obrigatórios da configuração e da solicitação são acumulados. |
| Qualidade | Critérios obrigatórios da configuração e da solicitação são acumulados. |
| Allowlists | Conjuntos obrigatórios aplicáveis são intersectados. |
| Limites econômicos na mesma moeda | Prevalece cada limite aplicável; na prática, a rota precisa satisfazer o mais restritivo. |
| Limites econômicos em moedas sem base comparável | Nenhuma conversão é presumida; a rota fica economicamente não avaliável para a decisão que dependa desses limites. |
| Valores padrão | Suprem somente a ausência de uma definição correspondente na solicitação. |
| Disponibilidade conhecida | É fato interno de elegibilidade. A solicitação não pode declarar uma rota disponível nem reverter indisponibilidade conhecida. |

Se a aplicação informar um valor menos restritivo que um limite obrigatório da configuração, o limite obrigatório permanece intacto. O endpoint não aceita override de estratégia, rota desativada, critério obrigatório ou limite global.

## 6. Comportamento observável da operação

A implementação deve preservar esta ordem:

1. validar mídia, JSON e schema da solicitação;
2. confirmar que existe configuração indispensável suficientemente válida;
3. combinar restrições da configuração e da solicitação;
4. excluir rotas incompatíveis com capacidade, qualidade, disponibilidade conhecida, preferências obrigatórias ou validade da própria rota;
5. estimar e aplicar condições econômicas somente às alternativas que passaram pela elegibilidade não econômica;
6. comparar somente alternativas elegíveis e economicamente comparáveis quando custo for indispensável;
7. aplicar a estratégia configurada e formar seleção ou recusa explicável;
8. validar coerência da decisão;
9. somente depois de uma seleção válida, acionar, no fluxo normal, a integração externa da rota selecionada;
10. normalizar resultado, uso ou erro;
11. calcular o custo posterior quando houver dados suficientes e compor a resposta pública.

Uma alternativa incompatível nunca se torna elegível por ser mais barata. Nenhum provedor é chamado em caso de solicitação inválida, configuração indispensável inválida, ausência de rota, insuficiência econômica indispensável ou decisão incoerente.

## 7. Resposta de sucesso

Uma execução com resultado normalizado válido usa `200 OK`, inclusive quando o uso ou o custo posterior estiver indisponível ou incerto.

O corpo possui exatamente estas estruturas conceituais:

```json
{
  "result": {
    "content": "Resultado textual normalizado."
  },
  "decision": {
    "outcome": "selected",
    "route": {
      "id": "route-text-a",
      "provider": "provider-a",
      "model": "model-text-a"
    },
    "strategy": {
      "id": "lowest-estimated-cost",
      "applied": true
    },
    "applied_constraints": [],
    "reason": "Razão objetiva da seleção.",
    "factors": [
      {
        "category": "economics",
        "description": "Fato determinante da seleção."
      }
    ]
  },
  "economics": {
    "estimate": {
      "status": "available",
      "amount": "0.002300",
      "currency": "USD",
      "price_reference": "pricing-text-a-2026-08",
      "assumptions": []
    },
    "usage": {
      "status": "available",
      "items": [
        {
          "unit": "input_token",
          "quantity": "310"
        }
      ]
    },
    "calculated_cost": {
      "status": "available",
      "amount": "0.000310",
      "currency": "USD",
      "price_reference": "pricing-text-a-2026-08",
      "assumptions": []
    }
  }
}
```

### 7.1 Resultado normalizado

| Campo | Tipo | Obrigatório | Regra |
| --- | --- | --- | --- |
| `result` | objeto | Sim em `200 OK` | Representa o resultado válido da execução. |
| `result.content` | string | Sim | Conteúdo textual normalizado. Pode ser vazio somente se isso for um resultado válido da execução; o Maestro não fabrica conteúdo. |

O resultado não contém resposta externa bruta, identificador externo opaco sem normalização nem campos próprios de um provedor.

Respostas públicas não usam `null`. Campos condicionais são omitidos ou representados pelos estados explícitos definidos neste contrato.

### 7.2 Decisão selecionada

| Campo | Tipo | Obrigatório | Regra |
| --- | --- | --- | --- |
| `decision.outcome` | string constante `selected` | Sim | Indica que uma rota válida foi selecionada. |
| `decision.route` | objeto | Sim | Identifica uma única rota. |
| `decision.route.id` | string não branca | Sim | ID neutro e único da rota na configuração aplicável. |
| `decision.route.provider` | string não branca | Sim | Identificador neutro do provedor associado. |
| `decision.route.model` | string não branca | Sim | Identificador neutro do modelo associado. |
| `decision.strategy.id` | string não branca | Sim | Identificador da estratégia configurada. Não define seu algoritmo. |
| `decision.strategy.applied` | booleano `true` | Sim | Em uma seleção válida, a estratégia foi efetivamente aplicada. |
| `decision.applied_constraints` | array | Sim | Restrições efetivas relevantes para compreender a decisão; pode ser vazio. |
| `decision.reason` | string não branca | Sim | Resumo objetivo de por que a rota foi escolhida. |
| `decision.factors` | array não vazio | Sim | Fatos determinantes, sem raciocínio interno. |

Cada item de `applied_constraints` possui:

| Campo | Tipo | Obrigatório | Valores |
| --- | --- | --- | --- |
| `source` | string | Sim | `request` ou `configuration`. |
| `category` | string | Sim | `route`, `capability`, `quality`, `availability`, `preference` ou `economics`. |
| `description` | string não branca | Sim | Descrição factual e sanitizada da restrição aplicada. |

Toda restrição da solicitação e toda restrição de configuração que tenha sido determinante devem ser representadas. Restrições configuradas não determinantes podem ser omitidas para evitar telemetria extensa.

Cada item de `factors` possui:

| Campo | Tipo | Obrigatório | Valores |
| --- | --- | --- | --- |
| `category` | string | Sim | `route`, `capability`, `quality`, `availability`, `preference`, `economics`, `configuration`, `strategy` ou `tie_breaker`. |
| `description` | string não branca | Sim | Fato ou critério objetivo que explica a seleção ou recusa. |
| `references` | array não vazio de strings únicas | Não | IDs neutros de evidências ou referências necessárias para compreender o fator. |

Se um desempate for efetivamente usado, ao menos um fator com categoria `tie_breaker` deve identificar a regra concreta aplicada. Se não houver desempate, não é necessário criar um fator para dizer que ele não ocorreu.

`reason`, `factors` e `references` não expõem chain-of-thought, prompts internos, scores ocultos, dados secretos ou detalhes brutos de provedor. Eles comunicam somente fatos, critérios, referências e a razão objetiva suficientes para compreender a decisão.

## 8. Informações econômicas e de uso

`economics` é obrigatório em toda resposta de sucesso e em todo erro ocorrido depois de uma rota válida ter sido selecionada. Sempre que `economics` existir, seus três campos `estimate`, `usage` e `calculated_cost` são obrigatórios. Informação ausente é representada pelo `status` correspondente, nunca pela omissão de um desses campos.

Os três campos separam estes conceitos:

- `estimate`: estimativa registrada antes da execução;
- `usage`: uso normalizado conhecido depois da tentativa externa;
- `calculated_cost`: custo calculado pelo Maestro depois da execução quando os dados forem suficientes.

### 8.1 Estimativa e custo calculado

`estimate` e `calculated_cost` usam o mesmo formato discriminado por `status`.

| `status` | Campos obrigatórios | Campos que não aparecem | Significado |
| --- | --- | --- | --- |
| `available` | `amount`, `currency`, `price_reference`, `assumptions` | `reason` | Existe valor defensável com os dados disponíveis. |
| `uncertain` | `amount`, `currency`, `price_reference`, `assumptions`, `reason` | — | Existe valor numérico, mas uma limitação material conhecida afeta sua precisão. |
| `unavailable` | `reason` | `amount`, `currency`, `price_reference`, `assumptions` | Não existe valor numérico defensável. |

Regras dos campos:

- `amount` segue a mesma gramática decimal não negativa da solicitação;
- `currency` segue `^[A-Z]{3}$` e identifica um código de moeda suportado pela configuração;
- `price_reference` é um identificador não vazio e neutro da referência econômica configurada efetivamente usada; ele identifica de forma inequívoca o registro com base de preço, moeda, versão ou vigência e fonte ou responsável por sua manutenção;
- `assumptions` é um array, possivelmente vazio, de strings não brancas com as hipóteses relevantes;
- `reason` é uma string não branca que explica a incerteza ou indisponibilidade.

No estado `uncertain`, o valor é aproximado e não pode ser consumido como exato. Se nem mesmo um valor aproximado defensável existir, o estado correto é `unavailable`.

A estimativa retornada é a que sustentou a decisão antes da execução; ela não é recalculada retrospectivamente a partir do uso real. Quando custo for indispensável por estratégia, uma estimativa `unavailable` não sustenta a seleção. Sem teto obrigatório, uma estimativa `uncertain` somente sustenta a seleção se a estratégia configurada puder considerá-la comparável segundo as hipóteses declaradas; caso contrário, a rota é economicamente não avaliável. Com `max_estimated_cost` da solicitação ou limite equivalente obrigatório da configuração, somente uma estimativa `available` pode demonstrar conformidade na v1.

Quando custo não for indispensável para uma decisão específica, o contrato consegue representar uma estimativa `unavailable`, mas essa ausência deve permanecer explícita e não pode ser descrita como influência econômica positiva.

O custo calculado usa o uso normalizado e a referência de preço aplicável à decisão. Quando a estimativa possuir valor, o custo calculado deve usar a mesma moeda e `price_reference` que sustentaram a rota; se isso não puder ser assegurado, o custo deve ser `uncertain` ou `unavailable`, com a razão correspondente. Se uma estimativa `unavailable` puder ser aceita porque custo não era indispensável, dados posteriores suficientes ainda podem produzir `calculated_cost` com a referência configurada aplicável.

### 8.2 Uso normalizado

`usage` também é discriminado por `status`.

| `status` | Campos obrigatórios | Campos que não aparecem | Significado |
| --- | --- | --- | --- |
| `available` | `items` | `reason` | O uso relevante está suficientemente conhecido. |
| `uncertain` | `items`, `reason` | — | Existem quantidades normalizadas, mas elas são parciais ou materialmente incertas. |
| `unavailable` | `reason` | `items` | Não existe uso normalizável defensável. |

`items` é um array não vazio. Cada item possui:

| Campo | Tipo | Obrigatório | Regra |
| --- | --- | --- | --- |
| `unit` | string não branca | Sim | Unidade neutra configurada, como `input_token` ou `output_token`; não é o nome bruto de um campo externo. |
| `quantity` | string decimal não negativa | Sim | Quantidade conhecida ou, no estado `uncertain`, quantidade aproximada ou parcial. |

Uma mesma unidade aparece no máximo uma vez; quantidades da mesma unidade são agregadas. Uso `unavailable` não contém lista vazia nem quantidades iguais a zero inventadas.

Se o uso for `unavailable`, o custo calculado também deve ser `unavailable`. Se o uso for `uncertain`, o custo calculado não pode ser `available`; ele será `uncertain` quando houver valor aproximado defensável ou `unavailable` quando não houver.

### 8.3 Limites econômicos

- Moedas diferentes não são comparadas nem convertidas silenciosamente.
- Ausência de estimativa, uso ou custo nunca é representada por `0`, string vazia ou `null`.
- Um valor `0` só é permitido quando os dados e a referência econômica demonstrarem custo ou uso realmente zero.
- O custo calculado pode ser maior que a estimativa ou que o limite prévio sem invalidar retroativamente um resultado já obtido; a divergência permanece visível nos valores e nas hipóteses.
- Estimativa e custo calculado não são cobrança, fatura, conciliação, crédito ou garantia da cobrança final do provedor.

## 9. Recusas e erros

### 9.1 Envelope comum

Toda resposta não bem-sucedida contém `error`:

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "A solicitação é inválida.",
    "issues": [
      {
        "path": "/task",
        "message": "O campo deve ser uma string com ao menos um caractere não branco."
      }
    ]
  }
}
```

| Campo | Tipo | Obrigatório | Regra |
| --- | --- | --- | --- |
| `error.code` | string enumerada na seção 9.3 | Sim | Código semântico estável do erro. |
| `error.message` | string não branca | Sim | Resumo sanitizado e compreensível. |
| `error.issues` | array não vazio | Condicional | Detalhes seguros necessários para corrigir ou compreender o erro. |
| `error.issues[].path` | string em JSON Pointer | Não | Caminho público relacionado ao problema; não identifica arquivo interno ou segredo. |
| `error.issues[].message` | string não branca | Sim | Descrição sanitizada do problema. |

Nenhum erro contém `result`. `decision` e `economics` aparecem somente nas condições definidas abaixo.

`issues` é obrigatório em `INVALID_REQUEST`, `INVALID_CONFIGURATION` e `INVALID_DECISION`. Para erro de campo, cada problema deve identificar seu `path`. Para JSON malformado, mídia inválida, configuração ou incoerência sem caminho público, `path` pode ser omitido, mas a mensagem deve identificar de forma sanitizada o dado, a categoria ou a inconsistência relevante. Em recusas, os impedimentos ficam em `decision.factors`; nos erros de execução, `issues` permanece opcional.

Os envelopes são:

| Situação | Campos de nível superior |
| --- | --- |
| Resultado válido | `result`, `decision`, `economics` |
| Recusa antes da execução | `error`, `decision`; sem `result` e sem `economics` |
| Erro antes de uma decisão válida | `error`; sem `result`, `decision` ou `economics` |
| Erro depois de uma seleção válida | `error`, `decision`, `economics`; sem `result` |

### 9.2 Decisão recusada

`NO_ELIGIBLE_ROUTE` e `INSUFFICIENT_ECONOMIC_INFORMATION` são recusas válidas do roteamento e incluem uma decisão com este formato:

```json
{
  "outcome": "refused",
  "strategy": {
    "id": "lowest-estimated-cost",
    "applied": false
  },
  "applied_constraints": [],
  "reason": "Razão objetiva da recusa.",
  "factors": [
    {
      "category": "capability",
      "description": "Fato determinante da recusa."
    }
  ]
}
```

As regras de `strategy`, `applied_constraints`, `reason` e `factors` são as mesmas da seção 7.2, com estas diferenças:

- `outcome` é a constante `refused`;
- `route` não aparece e não recebe `null`;
- `strategy.applied` informa se a estratégia chegou a ser executada; pode ser `false` quando todas as rotas foram excluídas antes da comparação;
- `factors` identifica impedimentos suficientes para compreender a recusa;
- não existe `economics` de uma rota selecionada; fatos econômicos determinantes ficam nos fatores e em suas referências.

Quando um valor econômico conhecido for determinante para a recusa, os fatores devem identificar estimativa, moeda e `price_reference` suficientes para compreendê-lo. Quando a ausência econômica for determinante, os fatores devem declarar a indisponibilidade ou incerteza e sua razão, sem fabricar um valor.

Nenhum provedor é chamado em uma recusa. As restrições não são relaxadas, rotas desativadas não são habilitadas e dados ausentes não são inventados para evitar o erro.

### 9.3 Taxonomia mínima

| `error.code` | HTTP | Significado | `decision` / `economics` | Chamada externa |
| --- | ---: | --- | --- | --- |
| `INVALID_REQUEST` | `400 Bad Request` | JSON ou campos ausentes, desconhecidos, nulos, vazios ou inválidos. | Não aparecem. | Não |
| `INVALID_REQUEST` | `415 Unsupported Media Type` | O media type é diferente de `application/json` ou declara charset incompatível com UTF-8. | Não aparecem. | Não |
| `INVALID_CONFIGURATION` | `500 Internal Server Error` | Configuração global indispensável inválida ou insuficiente impede uma decisão confiável. | Não há decisão válida. | Não |
| `NO_ELIGIBLE_ROUTE` | `422 Unprocessable Content` | Em uma configuração global suficientemente válida, nenhuma rota habilitada e válida satisfaz as restrições aplicáveis. | `decision.outcome = refused`; sem `economics`. | Não |
| `INSUFFICIENT_ECONOMIC_INFORMATION` | `422 Unprocessable Content` | Havia alternativas que passaram pela elegibilidade não econômica, mas nenhuma pôde ser avaliada quando custo era indispensável. | `decision.outcome = refused`; sem `economics`. | Não |
| `INVALID_DECISION` | `500 Internal Server Error` | A seleção produzida é incoerente, incompleta ou insuficientemente justificável. | A seleção inválida não é publicada como decisão válida. | Não |
| `EXECUTION_FAILED` | `502 Bad Gateway` | A integração da rota selecionada falhou por razão diferente de indisponibilidade ou timeout. | `decision.outcome = selected` e `economics` aparecem; sem `result`. | Pode ter ocorrido |
| `EXECUTION_UNAVAILABLE` | `503 Service Unavailable` | A indisponibilidade foi descoberta ao tentar executar a rota selecionada. | `decision.outcome = selected` e `economics` aparecem; sem `result`. | Pode ter ocorrido |
| `EXECUTION_TIMEOUT` | `504 Gateway Timeout` | A execução da rota selecionada excedeu o timeout aplicável. | `decision.outcome = selected` e `economics` aparecem; sem `result`. | Pode ter ocorrido |

Informação de uso ou custo posterior `unavailable` ou `uncertain` não é erro quando já existe resultado normalizado válido; a resposta continua sendo `200 OK`.

### 9.4 Precedência e distinções

1. Entrada estruturalmente inválida produz `INVALID_REQUEST`.
2. Configuração global ausente, malformada, contraditória ou estruturalmente insuficiente para iniciar uma decisão confiável produz `INVALID_CONFIGURATION`, nunca uma falsa ausência de rota.
3. Erro isolado de configuração exclui somente a rota afetada. Se erros estruturais de configuração forem determinantes a ponto de impedir uma conclusão confiável para a solicitação, o resultado é `INVALID_CONFIGURATION`.
4. `NO_ELIGIBLE_ROUTE` pressupõe configuração global suficientemente válida. Rotas válidas incompatíveis com capacidade, qualidade, preferência, disponibilidade conhecida ou limite econômico conhecido produzem esse código quando nenhuma restar.
5. Ausência ou não comparabilidade econômica declarada em rotas estruturalmente válidas não é, por si só, configuração inválida. Se essas rotas passaram pela elegibilidade não econômica, mas nenhuma puder ser avaliada quando custo for indispensável, o resultado é `INSUFFICIENT_ECONOMIC_INFORMATION`.
6. Uma seleção incoerente produz `INVALID_DECISION` e não autoriza execução.
7. Somente depois de decisão válida podem ocorrer os três erros de execução.

Indisponibilidade conhecida antes da decisão é fator de elegibilidade e pode culminar em `NO_ELIGIBLE_ROUTE`. Indisponibilidade descoberta durante a execução é `EXECUTION_UNAVAILABLE`. Um preço conhecido acima do limite elimina a rota; preço indispensável ausente ou incompatível produz insuficiência econômica.

Erros externos são normalizados e sanitizados. A API não repassa código, mensagem, payload, header, endpoint, credencial ou identificador secreto do provedor.

## 10. Exemplos normativos

Os nomes de rotas, provedores, modelos, estratégias, preços e evidências abaixo são fictícios. Eles demonstram o contrato e não formam um catálogo obrigatório.

### 10.1 Solicitação válida

```json
{
  "task": "Resuma o contexto em três frases.",
  "context": "O Maestro Router escolhe uma rota compatível antes de executar a tarefa. A elegibilidade precede a comparação econômica. A decisão deve continuar explicável.",
  "constraints": {
    "required_capabilities": [
      "text_generation",
      "summarization"
    ],
    "required_quality_criteria": [
      "summary_faithfulness_accepted"
    ],
    "allowed_route_ids": [
      "route-text-a",
      "route-text-b"
    ],
    "max_estimated_cost": {
      "amount": "0.0100",
      "currency": "USD"
    }
  }
}
```

### 10.2 Execução bem-sucedida

Resposta `200 OK` à solicitação anterior:

```json
{
  "result": {
    "content": "O Maestro Router seleciona uma rota compatível antes da execução. Ele verifica elegibilidade antes de comparar custos. A escolha permanece explicável para a aplicação."
  },
  "decision": {
    "outcome": "selected",
    "route": {
      "id": "route-text-a",
      "provider": "provider-a",
      "model": "model-text-a"
    },
    "strategy": {
      "id": "lowest-estimated-cost",
      "applied": true
    },
    "applied_constraints": [
      {
        "source": "request",
        "category": "capability",
        "description": "A rota precisava declarar text_generation e summarization."
      },
      {
        "source": "request",
        "category": "quality",
        "description": "A rota precisava satisfazer summary_faithfulness_accepted."
      },
      {
        "source": "request",
        "category": "route",
        "description": "Somente route-text-a e route-text-b podiam ser consideradas."
      },
      {
        "source": "request",
        "category": "economics",
        "description": "A estimativa não podia exceder USD 0.0100."
      }
    ],
    "reason": "Após a elegibilidade, route-text-a apresentou a menor estimativa comparável entre as rotas permitidas.",
    "factors": [
      {
        "category": "quality",
        "description": "A configuração validada declarou que route-text-a satisfaz o critério de fidelidade exigido.",
        "references": [
          "evidence-summary-a-2026-07"
        ]
      },
      {
        "category": "economics",
        "description": "A estimativa de route-text-a foi USD 0.002300 e ficou abaixo do limite aplicável."
      },
      {
        "category": "economics",
        "description": "A estimativa comparável de route-text-b foi USD 0.003100.",
        "references": [
          "pricing-text-b-2026-08"
        ]
      }
    ]
  },
  "economics": {
    "estimate": {
      "status": "available",
      "amount": "0.002300",
      "currency": "USD",
      "price_reference": "pricing-text-a-2026-08",
      "assumptions": [
        "A estimativa considerou 300 input_token e 500 output_token.",
        "A referência precifica 1000 input_token em USD 0.001 e 1000 output_token em USD 0.004."
      ]
    },
    "usage": {
      "status": "available",
      "items": [
        {
          "unit": "input_token",
          "quantity": "310"
        },
        {
          "unit": "output_token",
          "quantity": "86"
        }
      ]
    },
    "calculated_cost": {
      "status": "available",
      "amount": "0.000654",
      "currency": "USD",
      "price_reference": "pricing-text-a-2026-08",
      "assumptions": []
    }
  }
}
```

O custo calculado do exemplo corresponde a `310 / 1000 × 0.001 + 86 / 1000 × 0.004 = 0.000654`. Esse cálculo ilustra a referência fictícia; não representa preço real de provedor.

### 10.3 Recusa por ausência de rota elegível

Solicitação válida:

```json
{
  "task": "Analise o documento.",
  "constraints": {
    "required_capabilities": [
      "document_analysis"
    ],
    "allowed_route_ids": [
      "route-text-a",
      "route-text-b"
    ]
  }
}
```

Resposta `422 Unprocessable Content`:

```json
{
  "error": {
    "code": "NO_ELIGIBLE_ROUTE",
    "message": "Nenhuma rota configurada, habilitada e válida satisfaz as restrições aplicáveis."
  },
  "decision": {
    "outcome": "refused",
    "strategy": {
      "id": "lowest-estimated-cost",
      "applied": false
    },
    "applied_constraints": [
      {
        "source": "request",
        "category": "capability",
        "description": "A rota precisava declarar document_analysis."
      },
      {
        "source": "request",
        "category": "route",
        "description": "Somente route-text-a e route-text-b podiam ser consideradas."
      }
    ],
    "reason": "Todas as rotas permitidas foram excluídas antes da comparação econômica.",
    "factors": [
      {
        "category": "capability",
        "description": "route-text-a não declarou document_analysis."
      },
      {
        "category": "availability",
        "description": "route-text-b estava conhecida como indisponível antes da decisão."
      }
    ]
  }
}
```

Nenhum provedor é chamado nesse fluxo.

### 10.4 Erro de solicitação

Solicitação inválida:

```json
{
  "task": "   ",
  "constraints": {
    "max_estimated_cost": {
      "amount": 0.01,
      "currency": "usd"
    }
  }
}
```

Resposta `400 Bad Request`:

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "A solicitação é inválida.",
    "issues": [
      {
        "path": "/task",
        "message": "O campo deve conter ao menos um caractere não branco."
      },
      {
        "path": "/constraints/max_estimated_cost/amount",
        "message": "O valor deve ser uma string decimal não negativa."
      },
      {
        "path": "/constraints/max_estimated_cost/currency",
        "message": "A moeda deve usar três letras maiúsculas."
      }
    ]
  }
}
```

Nenhuma decisão é formada e nenhum provedor é chamado.

### 10.5 Resultado válido com uso e custo posterior indisponíveis

Resposta `200 OK`:

```json
{
  "result": {
    "content": "Resultado textual normalizado e válido."
  },
  "decision": {
    "outcome": "selected",
    "route": {
      "id": "route-text-a",
      "provider": "provider-a",
      "model": "model-text-a"
    },
    "strategy": {
      "id": "lowest-estimated-cost",
      "applied": true
    },
    "applied_constraints": [],
    "reason": "route-text-a era a única rota elegível e possuía estimativa comparável, por isso foi selecionada pela estratégia configurada.",
    "factors": [
      {
        "category": "route",
        "description": "Nenhuma outra rota permaneceu elegível para a decisão."
      },
      {
        "category": "economics",
        "description": "A estimativa de route-text-a era USD 0.002300 e estava disponível antes da execução."
      }
    ]
  },
  "economics": {
    "estimate": {
      "status": "available",
      "amount": "0.002300",
      "currency": "USD",
      "price_reference": "pricing-text-a-2026-08",
      "assumptions": [
        "A estimativa considerou 300 input_token e 500 output_token."
      ]
    },
    "usage": {
      "status": "unavailable",
      "reason": "A execução retornou resultado sem informação de uso normalizável."
    },
    "calculated_cost": {
      "status": "unavailable",
      "reason": "Não foi possível calcular o custo sem uso suficiente."
    }
  }
}
```

O resultado continua válido. Nenhum campo econômico ausente foi convertido em `0`.

## 11. Configuração como pré-condição

O UC-01 é uma pré-condição operacional da API pública, não um endpoint.

Antes de atender solicitações, o Maestro precisa receber por mecanismo externo a este contrato uma configuração validada com rotas habilitadas, associações de adaptadores, capacidades, critérios de qualidade e evidências, condições conhecidas, dados econômicos, estratégia, restrições obrigatórias, valores padrão, referências a credenciais e parâmetros operacionais indispensáveis.

Este documento não escolhe formato, arquivo, variáveis de ambiente, banco de dados, precedência, recarga, API administrativa, painel ou serviço remoto de configuração. Também não define mecanismo concreto de gestão de segredos.

Os identificadores usados pela aplicação em capacidades, critérios de qualidade e allowlists são acordados com o responsável pela configuração fora de `POST /v1/executions`. Não existe endpoint público de descoberta no MVP.

Uma falha local de rota exclui apenas essa rota quando ainda for possível formar decisão confiável com as demais. Uma configuração global indispensável inválida ou um conjunto de falhas que impeça decisão confiável produz `INVALID_CONFIGURATION`. Mensagens públicas identificam somente fatos seguros e nunca incluem valores secretos.

Dados econômicos malformados, contraditórios ou estruturalmente inválidos seguem a regra de configuração. Em contraste, uma rota estruturalmente válida pode declarar informação econômica ausente, incerta ou não comparável; se essa condição eliminar todas as alternativas quando custo for indispensável, o resultado público é `INSUFFICIENT_ECONOMIC_INFORMATION`, não `INVALID_CONFIGURATION`.

## 12. Retry, fallback e idempotência

Este contrato não define:

- quantidade de tentativas;
- retry automático, backoff ou condições de repetição;
- política, ordem ou critérios de fallback;
- histórico público de tentativas;
- valor ou mecanismo concreto de timeout;
- chave de idempotência ou deduplicação.

`POST /v1/executions` não oferece garantia de idempotência. A aplicação não deve presumir que repetir uma solicitação após falha de transporte seja seguro ou incapaz de repetir uma execução externa.

Uma rota no fluxo normal não significa proibir retry ou fallback por definição. Essas políticas continuam deliberadamente abertas. Ao mesmo tempo, o contrato não autoriza fan-out, respostas concorrentes, comparação de respostas, consenso, votação ou enfraquecimento de restrições como recuperação. Os códigos de execução permitem comunicar uma falha sem fechar agora qualquer política de recuperação.

## 13. Comportamentos fora do contrato público e do MVP

Não fazem parte deste contrato:

- agentes, memória, planejamento automático ou workflows;
- orquestração, fan-out, cadeias de modelos, comparação de respostas, consenso ou votação;
- marketplace, plugins avançados ou plataforma de automações;
- execução distribuída, filas, mensageria ou cache;
- usuários, tenants, permissões ou políticas remotas;
- CRUD de provedores, modelos, rotas ou preços;
- autenticação pública específica do Maestro;
- dashboard, observabilidade completa, monitoramento, tracing ou retenção obrigatória;
- billing, faturamento, cobrança, créditos ou conciliação financeira;
- Docker, CI/CD, cloud ou deployment;
- linguagem, framework, biblioteca HTTP, banco de dados, ORM ou mecanismo de persistência.

Essas exclusões não constituem roadmap nem promessa futura.

> Implemente apenas o necessário. Não adicione Docker, CI/CD, monitoramento, documentação extensa, observabilidade ou outras melhorias de infraestrutura sem minha autorização.

## 14. Critérios mínimos para testes de contrato

| Cenário | Resultado obrigatório |
| --- | --- |
| Campo obrigatório ausente, `null`, tipo incorreto, array vazio, duplicata ou campo desconhecido | `INVALID_REQUEST`; nenhuma chamada externa. |
| Solicitação tenta permitir uma rota desativada | A rota permanece excluída; a solicitação não altera a configuração. |
| Rota mais barata viola capacidade ou qualidade obrigatória | A rota é excluída antes da comparação econômica. |
| Indisponibilidade conhecida elimina a última rota | `NO_ELIGIBLE_ROUTE`; nenhuma chamada externa; fator de disponibilidade na recusa. |
| Custo é indispensável e nenhuma alternativa restante possui informação comparável | `INSUFFICIENT_ECONOMIC_INFORMATION`; nenhuma chamada externa. |
| Existe teto obrigatório e a única estimativa restante é `uncertain` | `INSUFFICIENT_ECONOMIC_INFORMATION`; a estimativa sem limite superior não prova conformidade. |
| Estratégia retorna rota fora do conjunto elegível ou sem explicação suficiente | `INVALID_DECISION`; nenhuma chamada externa. |
| Seleção válida e execução bem-sucedida | `200 OK`, uma rota identificada, resultado normalizado, estratégia, razão, fatores e economia explícita. |
| Resultado válido sem uso suficiente | `200 OK`, uso e custo calculado `unavailable`; nenhum valor zero inventado. |
| Uso parcial ou custo materialmente impreciso | Estado `uncertain`, valor aproximado quando defensável e `reason` obrigatório. |
| Falha depois da seleção | Código de execução apropriado, decisão selecionada e economia já conhecida preservadas; sem `result`. |
| Qualquer erro externo contém segredo ou payload nativo | A resposta deve sanitizar e normalizar o erro antes de entregá-lo. |

## 15. Decisões consolidadas

### 15.1 Decisões herdadas de `00–04`

- A aplicação usa uma API única e independente de provedor.
- O Router coordena validação, elegibilidade, avaliação econômica, estratégia, decisão e execução.
- Adaptadores isolam formatos e autenticação próprios dos provedores.
- Somente rotas configuradas, habilitadas e suficientemente válidas participam.
- Restrições obrigatórias da configuração não podem ser enfraquecidas pela solicitação; valores padrão apenas suprem ausências.
- Elegibilidade antecede comparação econômica, e custo só diferencia alternativas compatíveis.
- A estratégia é simples, configurada, explícita e explicável.
- Uma única rota é selecionada no fluxo normal, e execução externa ocorre somente depois de decisão válida.
- A aplicação recebe resultado ou erro normalizado e fatos suficientes para compreender seleção ou recusa.
- Estimativa anterior e custo calculado posterior são conceitos distintos; ausência e incerteza permanecem explícitas.
- Custo calculado não é billing nem garantia de cobrança final.
- Falhas não autorizam dados inventados, restrições relaxadas ou exposição de segredos.

### 15.2 Decisões fechadas pelo `05`

- A API pública v1 usa HTTP síncrono e JSON UTF-8.
- Existe somente `POST /v1/executions`, sem streaming, consulta posterior ou endpoint auxiliar.
- Tarefa, contexto e resultado normalizado são textuais.
- A solicitação possui somente `task`, `context` e `constraints`; campos desconhecidos, valores `null` e nomes de membros JSON duplicados são inválidos.
- As restrições públicas são capacidades obrigatórias, critérios de qualidade configurados, allowlist de rotas e teto de custo estimado por execução.
- A solicitação não escolhe a estratégia e disponibilidade conhecida não é declarada pelo cliente.
- IDs são neutros, opacos e comparados por igualdade exata; dinheiro e uso usam strings decimais; moeda segue `^[A-Z]{3}$` e não há câmbio implícito.
- Sucesso, decisão selecionada, decisão recusada, informação econômica, uso e erros possuem estruturas discriminadas neste documento.
- `available`, `uncertain` e `unavailable` distinguem conhecimento econômico e de uso sem usar zero ou `null` como ausência.
- O mapeamento mínimo de códigos semânticos e status HTTP fica definido.
- Uma resposta válida continua sendo `200 OK` quando uso ou custo posterior estiver indisponível ou incerto.
- Configuração validada permanece fora da API pública e não gera endpoint administrativo.
- A operação não oferece garantia de idempotência.

## 16. Decisões deliberadamente em aberto

Permanecem abertas somente decisões internas ou operacionais que não tornam ambíguo o contrato público:

- catálogo inicial de provedores, modelos e rotas;
- vocabulário concreto de capacidades e critérios de qualidade;
- metodologia, métricas, limiares, evidências e benchmarks de qualidade;
- quantidade, nomes, algoritmos, parâmetros, pesos e regras concretas de desempate das estratégias;
- método interno de estimar uso e custo antes da execução;
- origem, atualização e governança dos preços, preservada a representação pública aqui definida;
- forma de determinar disponibilidade conhecida sem criar monitoramento obrigatório;
- valores e mecanismo concreto de timeout;
- políticas de retry e fallback;
- formato, origem, precedência, recarga e armazenamento da configuração;
- mecanismo concreto de gestão e resolução de segredos;
- eventual retenção interna de decisões, sem dependência da API pública;
- linguagem, framework, biblioteca HTTP, banco de dados, ORM, empacotamento, infraestrutura e implantação.

Essas aberturas não autorizam alterar os schemas, relaxar restrições, expor detalhes de provedor ou inventar informação econômica.

## 17. Rastreabilidade com os casos de uso

| Caso de uso | Cobertura pelo contrato |
| --- | --- |
| **UC-01 — Preparar o Maestro** | Seção 11 define configuração validada como pré-condição e `INVALID_CONFIGURATION` como manifestação pública, sem criar API administrativa. |
| **UC-02 — Executar uma tarefa sob restrições** | `POST /v1/executions`, schema da seção 5, composição monotônica de restrições, ordem da seção 6 e resposta normalizada das seções 7 e 8. |
| **UC-03 — Recusar sem rota admissível** | `NO_ELIGIBLE_ROUTE`, `INSUFFICIENT_ECONOMIC_INFORMATION`, decisão `refused`, fatores determinantes e garantia de nenhuma chamada externa. |
| **UC-04 — Compreender decisão e impacto econômico** | Identificação de rota, provedor, modelo, estratégia, razão, fatores, estimativa, referência de preço, hipóteses, uso, custo calculado, indisponibilidade e incerteza. |

O contrato mantém a fronteira pública independente de provedor, não enfraquece restrições e não antecipa funcionalidades ou infraestrutura fora do MVP.

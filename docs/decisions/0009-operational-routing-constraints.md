# ADR 0009 — Configuração operacional das restrições de roteamento

## 1. Título e status

* **Título:** Configuração operacional das restrições de roteamento
* **Status:** Aprovada (decisão exclusivamente documental e decisória da W19 para orientar a implementação futura na W20)
* **Data:** 2026-09-07
* **Decisores:** Hallan (Product Owner) e ChatGPT Work

## 2. Contexto

O Maestro Router foi concebido para oferecer uma camada neutra, controlável e explicável de roteamento entre modelos de inteligência artificial. Os documentos normativos de fundação (`docs/00-MANIFESTO.md` a `docs/04-CASOS-DE-USO.md`), o contrato técnico público (`docs/05-API.md`) e a especificação algorítmica (`docs/06-DECISAO-DE-ROTEAMENTO.md`) já estabelecem que a decisão de roteamento é governada por restrições de capacidade, qualidade, disponibilidade, allowlists de rotas e limites econômicos.

A ADR 0008 e sua implementação posterior permitem configurar múltiplas rotas OpenAI com preços e previsões de uso individuais por meio de `MAESTRO_OPENAI_ROUTES_JSON`. No entanto, a composição em tempo de execução ainda não dispõe de um mecanismo operacional para declarar as capacidades e qualidades oferecidas por essas rotas, nem para receber políticas obrigatórias e valores padrão mantidos pelo operador. A W19 é exclusivamente documental e decisória, não implementando comportamento executável.

## 3. Problema G01

A lacuna G01 — formalizada no `README.md` e ratificada pela auditoria da PR #14 — define a ausência documental e executável de um esquema operacional para:

1. Declarar as capacidades oferecidas por cada rota configurada;
2. Declarar os critérios de qualidade satisfeitos por cada rota configurada, acompanhados de suas respectivas referências de evidência;
3. Configurar requisitos globais do operador para capacidades obrigatórias e critérios de qualidade obrigatórios;
4. Configurar allowlists obrigatórias do operador;
5. Configurar múltiplos tetos econômicos do operador e tratar sua cumulatividade em moedas distintas sem conversão cambial;
6. Configurar valores padrão (`defaults`) operacionais para suprir ausências na solicitação pública;
7. Estabelecer a composição monotônica exata entre as restrições da configuração e as restrições da solicitação, assegurando que uma requisição nunca enfraqueça as regras do operador.

Esta ADR resolve documentalmente a lacuna G01, fixando o modelo conceitual, os schemas e os invariantes normativos antes de qualquer alteração executável de código.

## 4. Estado atual

### 4.1 O que já está implementado

* **Filtragem pura no núcleo (`src/maestro_router/routing.py`):** O algoritmo de roteamento implementa a sequência completa de filtros não econômicos (`enabled`, `invalid_route`, `allowed_route_ids`, `required_capabilities`, `required_quality_criteria`, `known_unavailable`), a avaliação de teto econômico e a estratégia determinística `lowest-estimated-cost` com desempate por `route.id`.
* **Contrato da solicitação pública (`src/maestro_router/contracts.py`):** A estrutura `RequestConstraints` já aceita `required_capabilities`, `required_quality_criteria`, `allowed_route_ids` e `max_estimated_cost`.
* **Explicabilidade pública (`src/maestro_router/contracts.py`):** O modelo `AppliedConstraint` já suporta `source = "request"` e `source = "configuration"`, além das categorias públicas aprovadas (`route`, `capability`, `quality`, `availability`, `preference`, `economics`).
* **Composição multirrota básica (`src/maestro_router/bootstrap.py`):** O bootstrap operacional valida e compõe múltiplas rotas OpenAI via `MAESTRO_OPENAI_ROUTES_JSON`, conforme a ADR 0008.

### 4.2 O que ainda está ausente

* **Capacidades e qualidades nas rotas configuradas:** Em `bootstrap.py`, todas as rotas são instanciadas com `capabilities=frozenset()` e `quality_criteria=frozenset()`. Não há campos em `MAESTRO_OPENAI_ROUTES_JSON` para preenchê-los.
* **Associação entre critérios e evidências:** Não há formato operacional para vincular critérios de qualidade às suas referências de evidência em tempo de configuração.
* **Governança global e restrições do operador:** Não existe variável operacional para capturar requisitos obrigatórios de capacidade, qualidade, allowlists ou tetos do operador.
* **Valores padrão do operador:** Não há mecanismo para declarar ou aplicar defaults quando a requisição omite restrições.
* **Múltiplos tetos econômicos:** O código avalia apenas o limite escalar único fornecido na solicitação pública.
* **Composição monotônica configurada:** A função `route_request` recebe apenas as restrições da requisição e não projeta restrições globais de configuração em `AppliedConstraint`.

## 5. Decisão

Fica aprovado o modelo operacional mínimo, explícito, fechado, validável, determinístico e imutável durante o snapshot para a configuração de restrições de roteamento, estruturado em duas variáveis operacionais complementares:

1. **Extensão de `MAESTRO_OPENAI_ROUTES_JSON`:** Adição de dois membros opcionais e fechados em cada objeto de rota: `capabilities` e `quality_criteria`.
2. **Nova variável neutra `MAESTRO_ROUTING_CONSTRAINTS_JSON`:** Um documento JSON fechado e opcional contendo exclusivamente as políticas de governança global do operador: requisitos obrigatórios, allowlist global, múltiplos tetos econômicos e valores padrão.

Nenhum comportamento executável é entregue pela W19. Esta decisão é estritamente normativa e direciona a implementação futura na W20.

## 6. Escopo

### 6.1 Dentro do escopo da decisão

* Schema conceitual dos campos adicionais no objeto de rota de `MAESTRO_OPENAI_ROUTES_JSON`.
* Schema conceitual da nova variável `MAESTRO_ROUTING_CONSTRAINTS_JSON`.
* Regras de validação estrita, fail-fast global e isolamento de falhas locais.
* Algoritmo formal de composição monotônica entre configuração e requisição.
* Tratamento determinístico de valores padrão e preservação da origem (`source`).
* Avaliação cumulativa de múltiplos tetos e impacto da ausência de conversão cambial.
* Projeção em `AppliedConstraint` e `DecisionFactor` sem alteração do contrato público `05-API.md`.
* Preservação da compatibilidade integral com a ADR 0008 e com o modo legado de rota única.

### 6.2 Fora do escopo da decisão

* Implementação de parsers, validadores ou classes executáveis na W19.
* Definição de vocabulário universal ou catálogo taxonômico para capacidades ou qualidades.
* Metodologia de avaliação científica, métricas, scores, limiares ou testes de benchmark.
* Auditoria material ou validação do conteúdo das evidências.
* Conversão cambial, orçamentos acumulados, controle financeiro ou conciliação de faturas.
* Variáveis operacionais para outros provedores ou extensão para o modo legado de rota única.
* Alteração da API pública `POST /v1/executions` ou do algoritmo de roteamento.
* Banco de dados, serviços remotos de configuração, interfaces administrativas ou recarga dinâmica.

## 7. Mecanismo operacional

Uma implementação futura poderá aceitar, em conjunto com o ambiente multirrota da ADR 0008, a variável opcional:

```text
MAESTRO_ROUTING_CONSTRAINTS_JSON
```

Seu valor será um único documento JSON fechado, mantido pelo operador, capturado uma única vez durante a inicialização junto a `MAESTRO_OPENAI_ROUTES_JSON` e `OPENAI_API_KEY`.

Regras de ativação e precedência:

* `MAESTRO_ROUTING_CONSTRAINTS_JSON` será opcional. Sua ausência manterá o comportamento multirrota puro da ADR 0008 (sem restrições obrigatórias adicionais do operador e sem valores padrão).
* Quando presente, inclusive como string vazia ou formada somente por espaços, a nova variável exigirá obrigatoriamente a presença de `MAESTRO_OPENAI_ROUTES_JSON`. A presença de `MAESTRO_ROUTING_CONSTRAINTS_JSON` sem o modo multirrota será uma configuração global inválida que impedirá a inicialização da aplicação.
* A coexistência de `MAESTRO_ROUTING_CONSTRAINTS_JSON` com qualquer uma das quatro variáveis legadas de rota única (`MAESTRO_OPENAI_MODEL`, `MAESTRO_OPENAI_ROUTE_ID`, `MAESTRO_OPENAI_PRICE_REFERENCE_JSON`, `MAESTRO_OPENAI_ESTIMATED_USAGE_JSON`) será ambígua e provocará erro global na inicialização.
* O modo legado de rota única permanecerá completamente inalterado e não consumirá restrições operacionais configuradas.

## 8. Extensão conceitual de `MAESTRO_OPENAI_ROUTES_JSON`

A ADR 0009 especializa a ADR 0008 permitindo dois novos campos opcionais em cada objeto do array `routes`:

* `capabilities`: array opcional de identificadores de capacidade neutros e opacos oferecidos pela rota.
* `quality_criteria`: array opcional de objetos estruturados declarando os critérios de qualidade satisfeitos pela rota e suas respectivas referências de evidência.

Cada entrada de `routes` permanecerá um objeto fechado. Os quatro campos aprovados pela ADR 0008 (`route_id`, `model`, `price_reference`, `estimated_usage`) continuarão rigorosamente obrigatórios.

Regras normativas dos campos novos de rota:

* Ambos os campos são individualmente opcionais. Sua omissão representará conjuntos vazios de capacidades e critérios de qualidade (`frozenset()`), preservando a validade estrita de configurações da ADR 0008.
* Quando presentes, devem ser arrays não vazios.
* Não são aceitos membros desconhecidos no objeto da rota.
* `capabilities` deve conter strings não brancas, formadas por sequências Unicode bem formadas, sem surrogates isolados. Identificadores duplicados no mesmo array são inválidos.
* `quality_criteria` deve conter objetos fechados com exatamente dois membros obrigatórios:
  * `criterion`: string não branca, opaca, sem surrogates isolados, identificando o critério satisfeito.
  * `evidence_references`: array não vazio de strings não brancas, opacas e únicas, sem surrogates isolados, identificando as referências das evidências que sustentam a declaração.
* Nomes de membros duplicados em qualquer nível JSON do objeto de rota são inválidos.
* O mesmo `criterion` não pode ser repetido em mais de um objeto da mesma rota.
* Identificadores de capacidades, critérios e evidências são opacos e comparados por igualdade exata de caracteres, sem trim, sem conversão de caixa e sem normalização Unicode implícita.
* A ordem em que capacidades, critérios ou referências são declarados nos arrays não confere prioridade, peso ou preferência.

## 9. Schema conceitual de `MAESTRO_ROUTING_CONSTRAINTS_JSON`

O documento de restrições globais será um objeto JSON fechado de nível superior contendo exclusivamente os seguintes membros opcionais:

```json
{
  "required_capabilities": [
    "capability-identifier"
  ],
  "required_quality_criteria": [
    "quality-criterion-identifier"
  ],
  "allowed_route_ids": [
    "route-identifier"
  ],
  "max_estimated_costs": [
    {
      "amount": "0.0100",
      "currency": "USD"
    }
  ],
  "defaults": {
    "required_capabilities": [
      "default-capability"
    ],
    "required_quality_criteria": [
      "default-criterion"
    ],
    "allowed_route_ids": [
      "default-route"
    ],
    "max_estimated_cost": {
      "amount": "0.0200",
      "currency": "USD"
    }
  }
}
```

Regras normativas do documento global:

* O objeto de nível superior deve conter ao menos um membro. Um documento vazio `{}` é inválido.
* Todos os membros de nível superior são individualmente opcionais.
* Campos desconhecidos tornam o documento globalmente inválido.
* Nomes de membros duplicados em qualquer objeto JSON tornam o documento globalmente inválido.
* `null` não substitui ausência e é inválido em qualquer posição.
* Arrays presentes devem ser não vazios e não podem conter itens repetidos.
* Strings devem ser não brancas e não conter surrogates isolados.
* `required_capabilities`: array não vazio de strings únicas com capacidades exigidas para todas as decisões do snapshot.
* `required_quality_criteria`: array não vazio de strings únicas com critérios de qualidade exigidos para todas as decisões do snapshot.
* `allowed_route_ids`: array não vazio de strings únicas com o conjunto máximo de rotas que o operador autoriza o Maestro a considerar.
* `max_estimated_costs`: array não vazio de objetos de limite monetário (`amount` e `currency`). Cada moeda pode aparecer no máximo uma vez nesse array; a repetição da mesma moeda na configuração global é um erro de configuração inválida.
* `defaults`: objeto fechado opcional que define valores a serem utilizados quando a solicitação pública omitir a dimensão correspondente. Se presente, deve conter ao menos um membro interno. Suas quatro propriedades internas (`required_capabilities`, `required_quality_criteria`, `allowed_route_ids` e `max_estimated_cost`) são individualmente opcionais e espelham a estrutura e validação de `RequestConstraints` de `docs/05-API.md`.

## 10. Exemplos sanitizados

### 10.1 Exemplo completo de rota estendida em `MAESTRO_OPENAI_ROUTES_JSON`

O documento de exemplo abaixo ilustra uma rota completa e sanitizada respeitando simultaneamente as ADRs 0006, 0007, 0008 e 0009:

```json
{
  "routes": [
    {
      "route_id": "route-a",
      "model": "operator-model-a",
      "price_reference": {
        "id": "operator-price-reference-a",
        "currency": "USD",
        "version": "operator-version-a",
        "source": "operator-source-a",
        "rates": [
          {
            "unit": "input_token",
            "rate": "7.0000",
            "base": 1000000
          },
          {
            "unit": "output_token",
            "rate": "15.0000",
            "base": 1000000
          }
        ],
        "conditions": [
          "operator-condition-a"
        ],
        "context_complete": true,
        "units_exhaustive": true,
        "no_double_counting": true,
        "model_identity_exact": true
      },
      "estimated_usage": {
        "input_token": 1000,
        "output_token": 200,
        "applicability_confirmed": true
      },
      "capabilities": [
        "capability-a",
        "capability-b"
      ],
      "quality_criteria": [
        {
          "criterion": "criterion-a",
          "evidence_references": [
            "evidence-a"
          ]
        }
      ]
    }
  ]
}
```

### 10.2 Exemplo completo de `MAESTRO_ROUTING_CONSTRAINTS_JSON`

```json
{
  "required_capabilities": [
    "capability-a"
  ],
  "required_quality_criteria": [
    "criterion-a"
  ],
  "allowed_route_ids": [
    "route-a",
    "route-b"
  ],
  "max_estimated_costs": [
    {
      "amount": "1.0000",
      "currency": "USD"
    }
  ],
  "defaults": {
    "required_capabilities": [
      "capability-b"
    ],
    "max_estimated_cost": {
      "amount": "0.5000",
      "currency": "USD"
    }
  }
}
```

## 11. Regras de validação

A configuração operacional é tratada como entrada externa não confiável do operador. A validação obedece às seguintes regras:

1. **Sem adivinhação:** Nenhum valor é inferido, completado, truncado ou normalizado silenciosamente.
2. **Sem chamadas externas:** Nenhuma validação realiza chamadas de rede ou consultas a provedores externos.
3. **Imutabilidade:** As entradas são validadas estritamente antes da instanciação de clientes, adaptadores ou aplicação.
4. **Sanitização estrita:** Falhas de validação emitem mensagens que identificam o nome da variável, o índice da rota e o caminho conceitual do campo com erro, sem reproduzir valores brutos, identificadores externos, evidências, preços ou credenciais.

## 12. Erros globais

Qualquer um dos seguintes erros invalida o snapshot inteiro e impede a inicialização da aplicação (`InvalidRuntimeConfigurationError`), antes de qualquer atendimento de requisição:

1. Presença de `MAESTRO_ROUTING_CONSTRAINTS_JSON` sem `MAESTRO_OPENAI_ROUTES_JSON`.
2. Presença de `MAESTRO_ROUTING_CONSTRAINTS_JSON` simultaneamente com qualquer variável do modo legado de rota única.
3. String vazia, em branco ou JSON malformado em `MAESTRO_ROUTING_CONSTRAINTS_JSON`.
4. Objeto de nível superior de `MAESTRO_ROUTING_CONSTRAINTS_JSON` vazio `{}` ou com tipo incorreto.
5. Membro desconhecido no objeto de nível superior de `MAESTRO_ROUTING_CONSTRAINTS_JSON`.
6. Membro JSON duplicado em qualquer nível de `MAESTRO_ROUTING_CONSTRAINTS_JSON`.
7. Qualquer membro presente contendo `null`, tipo incorreto, string vazia/em branco ou surrogate Unicode isolado.
8. Arrays vazios quando presentes em `required_capabilities`, `required_quality_criteria`, `allowed_route_ids` ou `max_estimated_costs`.
9. Identificador duplicado dentro de qualquer coleção de `MAESTRO_ROUTING_CONSTRAINTS_JSON`.
10. Moeda duplicada no array `max_estimated_costs`.
11. Objeto `defaults` vazio `{}`, com campos desconhecidos, ou com dimensões internas inválidas.
12. Erro estrutural ou de unicidade em `MAESTRO_OPENAI_ROUTES_JSON` conforme aprovado na ADR 0008 (`routes` ausente/vazio, duplicidade de `route_id`, `model` ou `price_reference.id`, ou `route_id` inválido/em branco).
13. Cenário em que todas as rotas configuradas foram isoladas por erros locais e nenhuma rota localmente válida restou no snapshot.

## 13. Erros isoláveis por rota

Uma falha restrita aos novos campos de uma rota específica é isolável e exclui apenas aquela rota, desde que a entrada possua um `route_id` válido, não branco, sem surrogates e único em todo o documento, e que ao menos uma outra rota permaneça plenamente válida no snapshot.

Constituem falhas isoláveis por rota:

1. Campo `capabilities` não sendo array, sendo array vazio, contendo itens que não sejam strings não brancas válidas, ou contendo capacidades duplicadas na mesma rota.
2. Campo `quality_criteria` não sendo array, sendo array vazio, ou contendo membro que não seja objeto JSON fechado.
3. Membro de `quality_criteria` contendo campos desconhecidos, campos duplicados ou omitindo `criterion` ou `evidence_references`.
4. `criterion` em branco, não string, contendo surrogate isolado, ou duplicado dentro da mesma rota.
5. `evidence_references` ausente, não sendo array, sendo array vazio, contendo itens que não sejam strings não brancas válidas, ou contendo referências duplicadas dentro do mesmo critério.
6. Critério de qualidade declarado sem nenhuma referência de evidência válida associada.

Tratamento da rota afetada:

* A rota afetada não é construída como executável e não participa do catálogo executável.
* Seu `route_id` é registrado entre os identificadores com falha de configuração local (`configuration_invalid_route_ids`).
* Durante o roteamento, a rota é considerada excluída com o motivo primário `invalid_route` e categoria `configuration`, permitindo que a decisão explique objetivamente a exclusão sem invalidar as demais rotas válidas.
* A rota inválida não recebe fallback silencioso e não é convertida em rota sem capacidades ou sem critérios de qualidade.

## 14. Snapshot e imutabilidade

1. **Captura única:** A fábrica da aplicação captura as variáveis do ambiente uma única vez no bootstrap. Ambas as variáveis (`MAESTRO_OPENAI_ROUTES_JSON` e `MAESTRO_ROUTING_CONSTRAINTS_JSON`) são parseadas e validadas a partir dessa captura única.
2. **Congelamento imutável:** Todas as rotas válidas, associações, capacidades, qualidades, referências de evidência, requisitos obrigatórios globais, allowlist global, múltiplos tetos, defaults e fatos econômicos serão materializados em estruturas imutáveis ou cópias defensivas equivalentes. Na implementação Python atual, `tuple` e `frozenset` são opções possíveis, mas esta ADR não transforma tipos concretos da linguagem em requisito arquitetural.
3. **Independência de ambiente:** Alterações posteriores nas variáveis de ambiente do processo não afetam uma aplicação já inicializada.
4. **Determinismo:** O mesmo par de documentos JSON produzirá sempre o mesmo snapshot ordenado (ordenado por `route_id` via valores escalares Unicode). A mesma solicitação avaliada contra o mesmo snapshot produzirá deterministicamente a mesma decisão, os mesmos fatores e a mesma explicação.

## 15. Composição monotônica

A formação das restrições efetivas é a primeira etapa interna da decisão de roteamento e combina as definições da configuração e da solicitação conforme a regra da não degradação: a solicitação pode apenas restringir ainda mais o universo de candidatos, nunca enfraquecer requisitos obrigatórios nem habilitar rotas não autorizadas.

### 15.1 Capacidades efetivas

As capacidades exigidas para a tarefa resultam da união das capacidades obrigatórias globais com a exigência da solicitação (ou o default, se a solicitação omitir):

$$\mathcal{C}_{\text{efetiva}} = \mathcal{C}_{\text{config\_obrigatória}} \cup \begin{cases} \mathcal{C}_{\text{solicitação}}, & \text{se presente} \\ \mathcal{C}_{\text{default}}, & \text{se omitida e default configurado} \\ \emptyset, & \text{caso contrário} \end{cases}$$

Uma rota só permanece elegível se declarar todas as capacidades de $\mathcal{C}_{\text{efetiva}}$.

### 15.2 Critérios de qualidade efetivos

Os critérios de qualidade exigidos resultam da união dos critérios obrigatórios globais com a exigência da solicitação (ou o default, se a solicitação omitir):

$$\mathcal{Q}_{\text{efetiva}} = \mathcal{Q}_{\text{config\_obrigatória}} \cup \begin{cases} \mathcal{Q}_{\text{solicitação}}, & \text{se presente} \\ \mathcal{Q}_{\text{default}}, & \text{se omitida e default configurado} \\ \emptyset, & \text{caso contrário} \end{cases}$$

Uma rota só permanece elegível se declarar e comprovar todos os critérios de $\mathcal{Q}_{\text{efetiva}}$.

### 15.3 Allowlist efetiva

As allowlists operam por interseção restritiva:

$$\mathcal{A}_{\text{efetiva}} = \begin{cases} \mathcal{A}_{\text{config\_obrigatória}} \cap \mathcal{A}_{\text{solicitação}}, & \text{se ambas estiverem presentes} \\ \mathcal{A}_{\text{config\_obrigatória}} \cap \mathcal{A}_{\text{default}}, & \text{se apenas config e default estiverem presentes} \\ \mathcal{A}_{\text{config\_obrigatória}}, & \text{se apenas config estiver presente} \\ \mathcal{A}_{\text{solicitação}}, & \text{se apenas solicitação estiver presente} \\ \mathcal{A}_{\text{default}}, & \text{se apenas default estiver presente} \\ \text{todas as rotas habilitadas}, & \text{se nenhuma allowlist for definida} \end{cases}$$

Regras adicionais de allowlist:

* A presença de uma rota em qualquer allowlist não a habilita se ela estiver desativada, localmente inválida ou conhecida como indisponível.
* Identificadores de rota inexistentes em qualquer allowlist não são corrigidos e não criam rotas; eles simplesmente não encontram correspondência.
* Se a interseção $\mathcal{A}_{\text{efetiva}}$ resultar em conjunto vazio, o resultado do roteamento será deterministicamente a recusa `NO_ELIGIBLE_ROUTE`.

### 15.4 Tetos econômicos efetivos

Todos os tetos obrigatórios configurados e o teto da solicitação (ou teto default) são aplicáveis cumulativamente.

Seja $\mathcal{T}$ o conjunto de todos os tetos aplicáveis. Para cada moeda $M$ presente em $\mathcal{T}$, o teto efetivo correspondente a essa moeda é dado pelo menor valor aplicável:

$$\text{Teto}_{\text{efetivo}}(M) = \min \{ \text{limite.amount} \mid \text{limite} \in \mathcal{T} \land \text{limite.currency} = M \}$$

## 16. Valores padrão

* **Substituição de ausência:** Valores padrão atuam estritamente quando a solicitação omite o campo correspondente em `request.constraints`. Se a solicitação fornecer um valor explícito (mesmo que seja um conjunto unitário diferente do padrão), o valor da solicitação substitui inteiramente o valor padrão daquela dimensão.
* **Subordinação às restrições obrigatórias:** O valor assumido por um default combina-se monotonicamente com as restrições obrigatórias da configuração. Um default nunca substitui nem cancela uma restrição obrigatória global.
* **Default econômico:** Se a configuração global definir `defaults.max_estimated_cost` e a solicitação omitir `constraints.max_estimated_cost`, o teto padrão assume o papel do teto da solicitação e combina-se cumulativamente com os tetos de `max_estimated_costs`.
* **Origem documental:** Uma restrição ativada via valor padrão tem sua origem classificada como `source = "configuration"`, pois sua existência decorre da governança operacional definida pelo operador.

## 17. Múltiplos tetos e moedas

1. **Sem conversão cambial:** O Maestro Router não realiza conversão de moedas, não consulta taxas de câmbio e não assume paridade monetária.
2. **Cumulatividade estrita:** Cada rota candidata deve demonstrar conformidade com todos os tetos aplicáveis.
3. **Avaliação por rota diante de múltiplos tetos:**
   * **Admissível:** Uma estimativa `available` na moeda $M$, com base comparável, cujo valor seja menor ou igual a todos os tetos aplicáveis na moeda $M$, e para a qual não existam tetos aplicáveis em moedas distintas sem comprovação.
   * **Violação Conclusiva:** Uma estimativa `available` na moeda $M$ que exceda qualquer teto aplicável na moeda $M$. A violação de um único teto basta para excluir a rota imediatamente.
   * **Indeterminada:** A rota possui estimativa na moeda $M_1$, mas existe um teto obrigatório aplicável na moeda $M_2$ (com $M_1 \neq M_2$). Como o Maestro não converte moedas e o teto em $M_2$ é obrigatório, a rota não consegue comprovar conformidade com o teto em $M_2$ e permanece economicamente indeterminada.
4. **Precedência na decisão:**
   * Se nenhuma rota for comprovadamente admissível e ao menos uma rota permanecer indeterminada, o resultado será `INSUFFICIENT_ECONOMIC_INFORMATION`.
   * Somente quando todas as rotas elegíveis apresentarem violação conclusiva em seus respectivos tetos o resultado será `NO_ELIGIBLE_ROUTE`.
   * O operador deve ser consciente de que configurar tetos obrigatórios em moedas distintas para rotas cotadas em moeda única inviabilizará a seleção econômica, culminando em recusa por informação econômica insuficiente.

## 18. Preservação da origem e explicabilidade

A explicabilidade das decisões utiliza exclusivamente o contrato público existente em `docs/05-API.md`, sem criar campos ou enums adicionais.

1. **Projeção em `decision.applied_constraints`:**
   * Cada restrição determinante mantém sua origem explícita:
     * `source = "request"`: restrições explícitas informadas pela aplicação cliente.
     * `source = "configuration"`: restrições obrigatórias globais, exclusões por rota desabilitada/indisponível/inválida, ou restrições ativadas a partir de valores padrão.
   * Não é permitida a criação de origens sintéticas como `source = "combined"`. Se uma capacidade foi exigida tanto pela configuração global quanto pela requisição, ambas são projetadas como itens distintos em `applied_constraints`.
   * A redução interna de tetos na mesma moeda não apaga a origem de cada limite: tanto o teto da requisição quanto o teto da configuração são mantidos na explicação se tiverem sido determinantes.
2. **Projeção em `decision.factors`:**
   * Fatores explicativos usam as categorias públicas já aprovadas para `DecisionFactor`:
     * `route`;
     * `capability`;
     * `quality`;
     * `availability`;
     * `preference`;
     * `economics`;
     * `configuration`;
     * `strategy`;
     * `tie_breaker`.
     (Essa especificação aplica-se estritamente às categorias de `DecisionFactor`; `configuration` não é adicionada às categorias de `AppliedConstraint`, cujo contrato em `docs/05-API.md` permanece distinto e inalterado).
   * Quando referências forem necessárias para compreender um fator determinante de qualidade, `DecisionFactor.references` será preenchido com as `evidence_references` aplicáveis da rota. A projeção não expõe o conteúdo bruto das evidências e não torna `references` obrigatório em fatores nos quais essas referências não sejam necessárias para compreender a decisão. Permanece preservada separadamente a regra operacional de que todo critério declarado pela rota deve possuir ao menos uma referência configurada.

## 19. Compatibilidade com a ADR 0008

* **Compatibilidade retrospectiva:** Qualquer documento JSON válido sob a ADR 0008 continua plenamente válido sob a ADR 0009. Os campos `capabilities` e `quality_criteria` nas rotas são opcionais; sua ausência equivale a conjuntos vazios.
* **Invariantes preservados da ADR 0008:**
  * Os campos `route_id`, `model`, `price_reference` e `estimated_usage` continuam obrigatórios em cada rota.
  * Unicidade estrita de `route_id`, `model` e `price_reference.id` em todo o documento multirrota.
  * `OPENAI_API_KEY` continua sendo variável de ambiente obrigatória, separada e mantida fora dos JSONs.
  * Compartilhamento de um único cliente `AsyncOpenAI` e de um único adaptador `OpenAIResponsesAdapter` entre todas as rotas OpenAI do snapshot.
  * Nenhuma credencial é aceita ou serializada em JSON, catálogo ou mensagens de erro.
  * Uma única execução externa ocorre por solicitação pública atendida.

## 20. Relação com a API pública

* A fronteira pública descrita em `docs/05-API.md` não é alterada.
* Nenhum endpoint novo é criado.
* O schema da requisição `POST /v1/executions` permanece inalterado.
* O schema da resposta de sucesso e dos envelopes de recusa e erro permanece inalterado.
* As novas definições operacionais pertencem exclusivamente à fronteira interna entre o operador e o bootstrap do Maestro Router.

## 21. Relação com o algoritmo de roteamento

* A especificação algorítmica de `docs/06-DECISAO-DE-ROTEAMENTO.md` é estritamente preservada.
* A sequência e precedência dos filtros de elegibilidade não econômica permanecem intocadas:
  1. Habilitação (`enabled`);
  2. Validade local da rota (`invalid_route`);
  3. Allowlists (`route_not_allowed`);
  4. Capacidades (`incompatible_capability`);
  5. Qualidade (`unsatisfied_quality`);
  6. Disponibilidade conhecida (`known_unavailability`).
* A avaliação econômica continua ocorrendo somente sobre candidatos aprovados em todos os filtros não econômicos.
* A estratégia do MVP continua sendo exclusivamente `lowest-estimated-cost`, com desempate lexicográfico por `route.id` em ordem de escalares Unicode.

## 22. Consequências positivas

* **Resolução documental de G01:** Fecha a especificação necessária para governança de restrições operacionais sem ambiguidades de arquitetura.
* **Neutralidade e controle:** A implementação futura permitirá ao operador impor requisitos mínimos de capacidade e qualidade sem depender das restrições enviadas pelas aplicações clientes.
* **Auditabilidade por evidências:** O schema aprovado exige que cada critério de qualidade declarado seja acompanhado de referências explícitas de evidência.
* **Isolamento de falhas:** A implementação futura poderá isolar rotas com capacidades ou critérios de qualidade malformados, desde que o restante da configuração preserve um universo confiável e ao menos uma rota localmente válida.
* **Evolução segura:** Prepara a base exata para a implementação executável na W20, sem improvisações em tempo de código.

## 23. Consequências negativas

* **Aumento da complexidade de validação no bootstrap:** O validador da composição multirrota deverá analisar dois documentos JSON interdependentes, verificar unicidades de identificadores e cruzar regras de integridade interna.
* **Rigidez cambial:** O acúmulo de múltiplos tetos em moedas distintas resultará frequentemente em recusa `INSUFFICIENT_ECONOMIC_INFORMATION` caso as rotas não tenham cotações multi-moeda correspondentes.
* **Volume de configuração:** A declaração estruturada de critérios de qualidade com evidências exige JSONs mais extensos e detalhados mantidos pelo operador.

## 24. Riscos

* **Risco de configuração de tetos incompatíveis:** O operador pode acidentalmente configurar tetos em moedas distintas acreditando que haverá conversão cambial.
  *Mitigação:* Documentação explícita de que moedas não são convertidas e que a falta de correspondência torna a rota indeterminada.
* **Risco de ambiguidade de origem:** Confundir defaults com restrições obrigatórias na telemetria.
  *Mitigação:* Regras de projeção estritas fixando `source = "configuration"` para defaults e proibindo origens sintéticas combinadas.

## 25. Alternativas rejeitadas

1. **Incorporar políticas globais dentro de `MAESTRO_OPENAI_ROUTES_JSON`:** rejeitada porque acoplaria a política global a uma entrada nominalmente específica da OpenAI e dificultaria sua reutilização em futuras composições, sem que isso signifique que a alternativa violaria automaticamente a neutralidade do núcleo.
2. **Omitir configuração global e fechar apenas capacidades por rota:** Rejeitada por deixar a lacuna G01 sem resolução completa e adiar decisões de defaults e monotonicidade.
3. **Critérios de qualidade sem referência de evidência associada:** rejeitada porque o Product Owner aprovou associação explícita por critério, fortalecendo a auditabilidade e evitando declarações operacionais sem sustentação identificável.
4. **Estrutura separada para catálogo de evidências desvinculada dos critérios:** Rejeitada por adicionar complexidade relacional desnecessária ao MVP e risco de referências órfãs.
5. **Permitir moedas duplicadas no array global de tetos:** Rejeitada por criar ambiguidade na declaração do operador; a duplicação deve falhar cedo.
6. **Exigir uma única moeda em `max_estimated_costs`:** rejeitada porque o Product Owner aprovou a presença de tetos globais em moedas diferentes, com aplicação cumulativa e indeterminação quando não houver base comparável.
7. **Eliminar valores padrão (`defaults`):** Rejeitada por ignorar o requisito aprovado desde a arquitetura conceitual (`docs/03-ARQUITETURA.md`, seção 10).
8. **Aplicar a nova configuração ao modo legado de rota única:** rejeitada nesta fatia porque o modo legado não possui o novo schema de metadados por rota e seu suporte ampliaria a W20 além do mínimo aprovado. Configurações legadas permanecem inalteradas quando a nova variável está ausente.
9. **Adotar YAML, TOML, arquivo externo, banco de dados ou serviço remoto:** rejeitada para esta fatia por simplicidade, coerência com a composição operacional existente e ausência de necessidade demonstrada.
10. **Conversão cambial implícita ou orçamentos acumulados:** Rejeitada por estar categoricamente fora do escopo do MVP.
11. **Alteração do contrato público ou acréscimo de campos na API:** Rejeitada por desrespeitar a precedência rígida de `docs/05-API.md`.

## 26. Responsabilidades do operador

O operador é exclusivamente responsável por:

1. Escolher e manter a consistência dos identificadores opacos de capacidades, critérios e evidências.
2. Declarar com fidelidade as capacidades técnicas suportadas por cada rota.
3. Afirmar critérios de qualidade para uma rota somente quando possuir evidências empíricas defensáveis que sustentem a afirmação.
4. Manter as referências de evidências válidas, catalogadas e auditáveis externamente fora do Maestro Router.
5. Configurar allowlists, múltiplos tetos e valores padrão coerentes com a política orçamentária e operacional de seu ambiente.
6. Compreender que a definição de tetos em moedas incompatíveis com as estimativas das rotas resultará em recusas por insuficiência econômica.
7. Reinicializar ou recompor a aplicação sempre que atualizar o conteúdo das variáveis de ambiente.

O Maestro Router valida a integridade estrutural e a coerência declarada. Ele não consulta modelos ou provedores para auditar capacidades, não avalia a qualidade metodológica dos benchmarks e não garante economia financeira universal.

## 27. Limites deliberados

A ADR 0009 não inclui:

* Implementação de código, testes executáveis ou dependências novas na W19.
* Tokenizadores ou estimativas dinâmicas de uso dependentes da tarefa.
* Consulta a preços em tempo real ou tabelas de preços remotas.
* Retry, fallback, timeout dinâmico, streaming ou execução concorrente de modelos.
* Gestão de contas, usuários, permissões, tenants ou interfaces administrativas.
* Persistência de histórico de decisões ou plataforma de observabilidade.
* Suporte a múltiplos provedores além da OpenAI na composição de runtime atual.

Esses limites deliberados não constituem compromisso de roadmap futuro.

## 28. Itens ainda abertos

Permanecem deliberadamente abertos para decisões e fases posteriores:

* O vocabulário definitivo e universal de capacidades.
* O catálogo padronizado de critérios de qualidade da indústria.
* A metodologia, métricas de corte e limiares estatísticos para aceitação de evidências.
* O ciclo de vida temporal, expiração e auditoria automatizada das evidências.
* O modelo de configuração operacional definitivo para múltiplos provedores externos heterogêneos.
* Recarga dinâmica de configuração em tempo de execução sem reinicialização.
* Conversão cambial automatizada pós-MVP.

## 29. Critérios objetivos para a futura W20

A futura implementação executável na W20 deverá satisfazer os seguintes critérios objetivos sem inventar regras de produto ou de arquitetura:

1. **Captura única e determinística:** Capturar `MAESTRO_OPENAI_ROUTES_JSON` e `MAESTRO_ROUTING_CONSTRAINTS_JSON` uma única vez no bootstrap.
2. **Parsing fechado:** Implementar parsing estrito de ambos os documentos JSON utilizando detecção de chaves duplicadas e rejeição de campos desconhecidos.
3. **Compatibilidade regressiva:** Assegurar que os 420 testes existentes continuem passando sem regressão e que configurações válidas sob a ADR 0008 continuem operacionais.
4. **Isolamento local:** Implementar o isolamento de rotas com `capabilities` ou `quality_criteria` malformados, marcando-as como `invalid_route` e preservando as rotas válidas restantes.
5. **Composição monotônica:** Implementar a lógica exata de composição para capacidades (união), qualidades (união), allowlists (interseção) e tetos (cumulatividade com redução ao menor na mesma moeda).
6. **Aplicação de defaults:** Preencher restrições omitidas na solicitação exclusivamente a partir do objeto `defaults` configurado, classificando a origem como `source = "configuration"`.
7. **Explicabilidade pública inalterada:** Integrar as novas restrições em `AppliedConstraint` e `DecisionFactor` sem alterar as classes públicas em `src/maestro_router/contracts.py`.
8. **Imutabilidade e ausência de chamadas de rede:** Garantir que nenhuma validação realize chamadas de rede e que o catálogo gerado seja congelado em estruturas imutáveis.
9. **Cobertura de testes forte:** Adicionar testes automatizados abrangentes com pytest cobrindo cenários válidos, erros globais, isolamento local, combinação monotônica, múltiplos tetos e valores padrão.

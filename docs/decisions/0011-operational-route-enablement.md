# ADR 0011 — Habilitação operacional de rotas

## 1. Título e status

* **Título:** Habilitação operacional de rotas (Operational Route Enablement)
* **Status:** Aprovada (decisão formal aprovada por Hallan em sessão em 2026-09-20 e ratificada em adendo de PO)
* **Data:** 2026-09-20
* **Decisores:** Hallan (Product Owner) e Codex (Arquiteto)

## 2. Contexto

O Maestro Router implementa uma tomada de decisão neutra, determinística, controlável e explicável para roteamento entre modelos de IA. No núcleo neutro (`src/maestro_router/routing.py`), o modelo `Route` já suportava o atributo booleano `enabled` (com padrão `True`), e a cadeia de filtragem pura já previa a exclusão `disabled_route` na primeira posição da ordem normativa de filtros não econômicos.

As decisões anteriores estruturaram a composição multirrota OpenAI via `MAESTRO_OPENAI_ROUTES_JSON` ([ADR 0008](0008-multiple-openai-route-configuration.md)), restrições operacionais e capacidades/qualidade ([ADR 0009](0009-operational-routing-constraints.md)) e a declaração de indisponibilidade conhecida por rota `known_unavailable` ([ADR 0010](0010-operational-known-unavailability.md)). No entanto, no bootstrap operacional (`src/maestro_router/bootstrap.py`), todas as rotas configuradas eram instanciadas fixando `enabled=True`.

Faltava um mecanismo operacional estático para que o operador pudesse desabilitar explicitamente rotas individuais diretamente no snapshot de inicialização, distinguindo rotas operacionalmente desabilitadas (`disabled_route`) de rotas conhecidamente indisponíveis (`known_unavailable`) e de falhas sintáticas ou estruturais de configuração (`invalid_route`).

## 3. Decisão aprovada

Fica aprovada a habilitação operacional de rotas conforme os requisitos deliberados e ratificados:

1. **Campo opcional por rota:** Cada objeto no array `routes` de `MAESTRO_OPENAI_ROUTES_JSON` aceita o campo opcional `enabled`.
2. **Booleano JSON estrito:** O valor deve ser estritamente um booleano JSON (`true` ou `false`). Tipos alternativos (incluindo `null`, números como `0`, `1`, `0.0`, `1.0`, strings como `"true"`, `"false"`, listas ou objetos) e chaves duplicadas (como `false`/`false`, `true`/`true`, `false`/`true`, `true`/`false`) são rejeitados na validação sintática da rota.
3. **Semântica dos valores e omissão:**
   - **Ausente (omitido):** Assume valor padrão `true` (rota operacionalmente habilitada).
   - **`true`:** Rota operacionalmente habilitada, o que significa autorização para concorrer SOMENTE se o restante da configuração e os filtros forem satisfeitos, não garantia de execução.
   - **`false`:** Rota operacionalmente desabilitada na configuração (`disabled_route`).
   - **Inválido ou duplicado:** Constitui "habilitação indeterminada". **NUNCA** presumir `false` nem `true`. Trata-se de falha local que impede que a rota seja considerada válida ou habilitada.
4. **Validação completa mesmo quando desabilitada:** A presença de `enabled: false` não isenta a rota de nenhuma validação estrutural, identidade única de `route_id`, unicidade global de `model` e `price_reference.id`, referências completas de preço (`price_reference`), previsão de uso (`estimated_usage`), capacidades, critérios de qualidade ou `known_unavailable`. Rotas inválidas jamais podem ser fabricadas ou materializadas com dados substitutos.
5. **Avaliação econômica para rotas desabilitadas:**
   - Não se calcula a estimativa de pré-execução (`calculate_pre_execution_amount`) no bootstrap para rotas com `enabled: false` (embora preço e uso sejam plenamente validados).
   - A rota materializada no snapshot carrega internamente `estimate` com `status = "unavailable"` e razão objetiva (`"A rota está desabilitada na configuração."`), sem publicar fatos econômicos da rota excluída.
   - A rota desabilitada nunca entra no conjunto de candidatas à avaliação econômica e jamais é selecionada ou executada externamente.
6. **Preservação de metadados neutros e projeção normativa:**
   - Para rotas cujo `route_id` é válido e único, cujo `enabled` foi estritamente comprovado como `false`, mas que contenham falha de validação local (ex.: preço ou capacidade malformados), preserva-se o identificador em um metadado neutro adicional no catálogo: `configuration_disabled_invalid_route_ids`, validado como subconjunto de `configuration_invalid_route_ids` e sem sobrepor o catálogo executável.
   - Para esses identificadores, projeta-se a exclusão normativa `disabled_route` em vez de `invalid_route`, mantendo a precedência normativa de que a desabilitação antecede a validade da rota na ordem de filtros.
   - **Ordem normativa de exclusão:** Conforme [06-DECISAO-DE-ROTEAMENTO.md](../06-DECISAO-DE-ROTEAMENTO.md), preserva-se: `disabled_route` -> `invalid_route` -> `route_not_allowed` -> `incompatible_capability` -> `unsatisfied_quality` -> `known_unavailability` -> avaliação econômica. A projeção pública é a descrita no item 8 e no contrato normativo.
   - **Autorização operacional vs. indisponibilidade:** Os campos `enabled` e `known_unavailable` são independentes; pode haver `enabled: false` e `known_unavailable: true` simultaneamente, caso em que `disabled_route` prevalece. O campo `known_unavailable` é um fato declarativo de indisponibilidade cuja exclusão (`known_unavailability`) só é avaliada se a rota sobreviver aos filtros anteriores. Rotas com `known_unavailable: true` só são consideradas localmente válidas se todos os seus demais campos forem plenamente válidos.
7. **Checagem de suficiência no bootstrap (fail-fast antes do cliente):**
   - **Nenhuma rota válida:** Se nenhuma rota no documento for localmente válida, a inicialização falha sanitizada com `InvalidRuntimeConfigurationError` (mantendo a regra da ADR 0008).
   - **Sem habilitada válida com presença de habilitadas inválidas ou indeterminadas:** Se existirem entradas habilitadas (ou de habilitação indeterminada) e nenhuma rota habilitada for localmente válida, a inicialização falha imediatamente com `InvalidRuntimeConfigurationError` sanitizado (materialização operacional de `INVALID_CONFIGURATION`). Uma rota válida desabilitada **não** pode resgatar rotas habilitadas inválidas ou entradas com `enabled` indeterminado.
   - **Todas as rotas válidas desabilitadas:** Se todas as rotas válidas forem desabilitadas e não houver rotas habilitadas inválidas nem indeterminadas (podendo haver rotas desabilitadas inválidas isoladas), a aplicação inicializa com sucesso. Solicitações publicamente válidas recebem a recusa normativa `NO_ELIGIBLE_ROUTE` (código HTTP 422) com zero chamadas externas a provedores (enquanto requisições inválidas continuam retornando `INVALID_REQUEST` 400).
   - **Ao menos uma rota habilitada válida:** Permite isolar normalmente falhas locais (sejam habilitadas inválidas, desabilitadas inválidas ou indeterminadas).
   - **Indisponibilidade não se confunde com autorização operacional:** Rotas com `known_unavailable: true` e `enabled: true` continuam sendo rotas habilitadas (autorizadas a concorrer), cumprindo o limiar de suficiência de inicialização, mas SOMENTE se forem localmente válidas em todos os seus demais campos de configuração.
8. **Explicabilidade pública e determinismo:**
   - A exclusão por `disabled_route` projeta `category = "route"` em `DecisionFactor` (sem atributo `source`) e `category = "route"` com `source = "configuration"` em `AppliedConstraint`.
   - O catálogo materializado é ordenado por ID e a mesma decisão/explicação é rigorosamente preservada sob qualquer permutação das entradas de configuração no snapshot (rotas materializadas são avaliadas ordenadas por ID, e IDs inválidos isolados não materializados são adicionados subsequentemente ordenados por ID; não há promessa de ordenação global intercalada de fatores entre essas duas categorias).

## 4. Tabela de regras e casos operacionais

| Cenário de rotas no snapshot | Habilitadas válidas | Desabilitadas válidas | Habilitadas inválidas / Indeterminadas | Desabilitadas inválidas | Resultado do Bootstrap | Comportamento em tempo de execução |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Padrão multirrota** | $\ge 1$ | 0 | 0 | 0 | Sucesso | Concorre na seleção conforme filtros e elegibilidade (não há garantia de execução) |
| **Com desabilitada válida** | $\ge 1$ | $\ge 1$ | 0 | 0 | Sucesso | Desabilitada excluída (`disabled_route`), habilitada concorre conforme filtros |
| **Falha isolada em habilitada** | $\ge 1$ | $\ge 0$ | $\ge 1$ | $\ge 0$ | Sucesso | Inválidas isoladas (`invalid_route`), desabilitadas isoladas (`disabled_route`), habilitadas válidas concorrem |
| **Todas válidas desabilitadas** | 0 | $\ge 1$ | 0 | 0 | Sucesso | Recusa normativa `NO_ELIGIBLE_ROUTE` (422), zero chamadas externas |
| **Desabilitada válida + desabilitada inválida** | 0 | $\ge 1$ | 0 | $\ge 1$ | Sucesso | Recusa normativa `NO_ELIGIBLE_ROUTE` (422), zero chamadas externas |
| **Desabilitada válida + habilitada inválida** | 0 | $\ge 1$ | $\ge 1$ | $\ge 0$ | **Falha no startup** (`InvalidRuntimeConfigurationError`) | Aplicação não inicializa; cliente HTTP não é construído |
| **Desabilitada válida + enabled indeterminado** | 0 | $\ge 1$ | $\ge 1$ | $\ge 0$ | **Falha no startup** (`InvalidRuntimeConfigurationError`) | Aplicação não inicializa; cliente HTTP não é construído |
| **Apenas desabilitadas inválidas** | 0 | 0 | 0 | $\ge 1$ | **Falha no startup** (`InvalidRuntimeConfigurationError`) | Aplicação não inicializa (preserva ADR 0008) |
| **Ambiguidade global** (duplicidade de `route_id`, `model` ou `price_reference.id`) | Qualquer | Qualquer | Qualquer | Qualquer | **Falha no startup** (`InvalidRuntimeConfigurationError`) | Aplicação não inicializa (`enabled=false` jamais mascara ambiguidade global) |

## 5. Limites e guardrails

- **Sem sondagem dinâmica ou recarga:** O estado habilitado/desabilitado é estritamente estático no snapshot de inicialização. Não há health checks, probes, recarga automática ou alteração em tempo de execução.
- **Snapshot imutável e determinístico:** A reconfiguração requer nova composição/inicialização da aplicação.
- **Sem retry, failover ou fallback:** Desabilitação não é acionada por falhas de execução externa nem provoca fallback automático para outros modelos.
- **Modo legado inalterado:** O modo de rota única legado (`MAESTRO_OPENAI_MODEL` / `MAESTRO_OPENAI_ROUTE_ID`) permanece inalterado e não suporta o campo `enabled`.
- **Nenhuma variável separada:** Nenhum novo nome de variável de ambiente é introduzido; o controle pertence exclusivamente ao objeto de rota de `MAESTRO_OPENAI_ROUTES_JSON`.
- **API pública inalterada:** Nenhum endpoint, schema ou contrato público da v1 ([05-API.md](../05-API.md)) sofre alteração.
- **Sem novas dependências:** Nenhuma dependência externa, infraestrutura ou biblioteca adicional é incorporada.

## 6. Alternativas consideradas

- **Alternativa A (Aprovada):** Booleano `enabled` opcional por rota em `MAESTRO_OPENAI_ROUTES_JSON`, com separação estrita entre falso comprovado, omissão/verdadeiro e indeterminado, acompanhado de projeção normativa e checagem de suficiência no bootstrap.
- **Alternativa B (Rejeitada):** Lista separada de IDs desabilitados em variável externa (ex.: `MAESTRO_DISABLED_ROUTES_JSON`). Rejeitada por introduzir correlação entre variáveis distintas, exigir validação de integridade referencial e complexidade operacional sem benefício técnico.

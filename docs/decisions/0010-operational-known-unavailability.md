# ADR 0010 — Indisponibilidade conhecida operacional

## 1. Título e status

* **Título:** Indisponibilidade conhecida operacional
* **Status:** Aprovada (decisão aprovada por Hallan em 2026-09-20, alternativa A: booleano por rota)
* **Data:** 2026-09-20
* **Decisores:** Hallan (Product Owner) e Codex (Arquiteto)

## 2. Contexto

O Maestro Router baseia sua tomada de decisão em critérios objetivos, determinísticos e explicáveis. No núcleo neutro (`src/maestro_router/routing.py`), o modelo de rota já suporta o atributo booleano `known_unavailable` e o pipeline de roteamento já executa o filtro correspondente: rotas marcadas como conhecidamente indisponíveis são excluídas do universo elegível antes da avaliação econômica.

No modelo de explicabilidade pública ([05-API.md](../05-API.md) e [06-DECISAO-DE-ROTEAMENTO.md](../06-DECISAO-DE-ROTEAMENTO.md)), a categoria `availability` existe tanto em fatores de decisão (`factors`) quanto em restrições aplicadas (`applied_constraints`). Contudo, o campo `source = "configuration"` pertence exclusivamente a `applied_constraints`, uma vez que `DecisionFactor` não possui atributo de fonte (`source`).

A [ADR 0008](0008-multiple-openai-route-configuration.md) estabeleceu a configuração multirrota OpenAI via `MAESTRO_OPENAI_ROUTES_JSON`, e a [ADR 0009](0009-operational-routing-constraints.md) introduziu restrições operacionais e capacidades/critérios de qualidade por rota. Esta ADR especializa diretamente o schema multirrota da [ADR 0008](0008-multiple-openai-route-configuration.md) após a extensão da [ADR 0009](0009-operational-routing-constraints.md), exclusivamente na adição do campo opcional `known_unavailable` no objeto de rota de `MAESTRO_OPENAI_ROUTES_JSON`. Em `src/maestro_router/bootstrap.py`, todas as rotas eram instanciadas com `known_unavailable=False` fixo. Faltava um mecanismo operacional estático para que o operador declarasse indisponibilidade conhecida no snapshot multirrota, sem necessidade de alterar o núcleo neutro ou introduzir mecanismos dinâmicos de sondagem.

## 3. Decisão aprovada

O operador poderá declarar indisponibilidade conhecida diretamente em cada rota do snapshot multirrota:

1. **Campo opcional por rota:** Cada objeto no array `routes` de `MAESTRO_OPENAI_ROUTES_JSON` aceita o campo opcional `known_unavailable`.
2. **Booleano JSON estrito:** O valor deve ser estritamente um booleano JSON (`true` ou `false`). Tipos alternativos (incluindo `null`, números `0` ou `1`, strings `"true"` ou `"false"`, listas ou objetos) são rejeitados na validação sintática da rota.
3. **Semântica de omissão ou valor `false`:** Omitir o campo ou declará-lo explicitamente como `false` (`known_unavailable: false`) possuem semântica idêntica no snapshot: ambos representam estritamente a *ausência de conhecimento prévio de indisponibilidade*, e **não** constituem garantia de disponibilidade, saúde operacional ou funcionamento da rota.
4. **Comportamento em `true`:** A rota é incluída como estruturalmente válida no catálogo da aplicação (não é tratada como `invalid_route`). Durante a etapa de elegibilidade do roteamento, se a rota sobreviver a todos os filtros anteriores da ordem normativa, ela é excluída por indisponibilidade conhecida (`known_unavailability`). Caso a rota seja eliminada por um filtro prévio (como restrições de rota, capacidade ou qualidade), prevalece o primeiro motivo determinante e não se promete exclusão por disponibilidade. Quando a exclusão por disponibilidade for o motivo determinante aplicado, ela projeta `category = "availability"` em `DecisionFactor` (sem campo `source`) e `category = "availability"` com `source = "configuration"` em `AppliedConstraint`.
5. **Tratamento de erros e isolamento local:**
   - Tipo inválido ou chave duplicada em `known_unavailable` constituem falhas locais da rota correspondente, desde que a identidade (`route_id` válido e único) e os invariantes estruturais globais sejam respeitados. A rota com falha local é marcada como inválida (`invalid_route`) e excluída do conjunto elegível.
   - Caso nenhuma rota localmente válida reste no catálogo, a inicialização falha de forma sanitizada com `InvalidRuntimeConfigurationError`. O caminho `routes[i].known_unavailable` é emitido especificamente quando essa falha for a reportada pelo validador, preservando-se outros caminhos, erros e a ordem de preferência/precedência de validação existente quando a ausência de rotas válidas decorrer de outras razões.
6. **Todas as rotas válidas indisponíveis:** Se todas as rotas válidas forem configuradas com `known_unavailable: true`, a aplicação inicializa com sucesso. Solicitações publicamente válidas que cheguem a esse estado recebem a recusa normativa `NO_ELIGIBLE_ROUTE` (código HTTP 422) sem realizar nenhuma chamada externa a provedores (enquanto solicitações publicamente inválidas continuam sendo rejeitadas com `INVALID_REQUEST` e código HTTP 400). Na recusa `NO_ELIGIBLE_ROUTE`, os fatores de decisão explicam a exclusão de cada rota segundo o primeiro motivo determinante na ordem de filtragem (podendo ser `route` por allowlist, `capability` por capacidade ausente ou `quality` por qualidade insatisfeita, caso a rota falhe antes de ser avaliada quanto à disponibilidade).
7. **Integridade das validações globais e econômicas:** A declaração `known_unavailable: true` não isenta a rota de validação estrutural completa, unicidade de modelo e referências de preço/uso válidas.
8. **Precedência estrita de filtros:** Conforme [06-DECISAO-DE-ROTEAMENTO.md](../06-DECISAO-DE-ROTEAMENTO.md), preserva-se a ordem normativa completa de filtragem antes da avaliação econômica:
   1. Habilitação (`disabled_route`, sob categoria `route` e fonte `configuration`; registra-se que o bootstrap multirrota atual fixa `enabled = True` para todas as rotas);
   2. Validade local da configuração (`invalid_route`, sob categoria `configuration` em fatores e `route` com fonte `configuration` em restrições aplicadas);
   3. Allowlists e preferências obrigatórias (`route_not_allowed`, sob categoria `route`);
   4. Capacidades (`incompatible_capability`, sob categoria `capability`);
   5. Qualidade (`unsatisfied_quality`, sob categoria `quality`);
   6. Disponibilidade conhecida (`known_unavailability`, sob categoria `availability`);
   7. Avaliação econômica (`economics`).
9. **Modo legado inalterado:** O modo de rota única legado (`MAESTRO_OPENAI_MODEL` / `MAESTRO_OPENAI_ROUTE_ID`) permanece inalterado e sem suporte a `known_unavailable`.
10. **Nenhuma variável separada:** Não são adicionadas novas variáveis de ambiente; o controle é exclusivo de `MAESTRO_OPENAI_ROUTES_JSON`.

## 4. Limites e guardrails

- **Sem sondagem dinâmica:** A indisponibilidade é estritamente operacional e declarativa no snapshot de inicialização. Não há health checks, polling, probes de conectividade ou consultas periódicas a provedores.
- **Imutabilidade e determinismo:** O snapshot é imutável após a inicialização. Qualquer mudança na disponibilidade exige nova composição/recomposição da aplicação.
- **Sem retry ou fallback:** Falhas de execução não alteram dinamicamente o status de disponibilidade.
- **Núcleo neutro inalterado:** O algoritmo de decisão e as estruturas de contrato do núcleo neutro (`src/maestro_router/routing.py` e `src/maestro_router/contracts.py`) permanecem inalterados, pois já suportavam o filtro e os atributos necessários.
- **API pública e economia inalteradas:** Os contratos de requisição e resposta da API pública v1 ([05-API.md](../05-API.md)), bem como o pipeline e regras de cálculo econômico ([06-DECISAO-DE-ROTEAMENTO.md](../06-DECISAO-DE-ROTEAMENTO.md)), não sofrem qualquer modificação.
- **Sem dependências adicionais ou infraestrutura:** A solução não introduz novas dependências de software, bibliotecas de terceiros, bancos de dados, cache compartilhado, agentes de monitoramento ou serviços externos.

## 5. Alternativas consideradas

- **Alternativa A (Aprovada):** Booleano `known_unavailable` por rota dentro de `MAESTRO_OPENAI_ROUTES_JSON`. Co-localiza a declaração estática com a identidade e demais atributos da rota, mantendo isolamento local de falhas simples e schema direto.
- **Alternativa B (Rejeitada para esta W):** Configuração operacional separada (como lista de IDs de rotas indisponíveis em uma variável ou documento isolado, por exemplo `MAESTRO_UNAVAILABLE_ROUTES_JSON` ou membro isolado em `MAESTRO_ROUTING_CONSTRAINTS_JSON`). Rejeitada para esta W por exigir correlação e referências cruzadas entre documentos distintos, validação de integridade referencial (rotas referenciadas inexistentes) e maior complexidade operacional sem necessidade técnica comprovada no momento.

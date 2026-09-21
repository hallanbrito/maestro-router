# Decisões arquiteturais

Este diretório contém decisões que especializam a documentação normativa do
Maestro Router. Elas registram o contexto e o escopo de cada fatia no momento em
que foi aprovada; referências a uma “implementação futura” preservam esse
contexto histórico e não substituem o estado executável atual.

| ADR | Assunto |
| --- | --- |
| [0001](0001-neutral-provider-execution.md) | Execução neutra entre provedores |
| [0002](0002-openai-responses-adapter.md) | Adaptador OpenAI Responses |
| [0003](0003-minimal-runtime-configuration.md) | Configuração mínima de runtime |
| [0004](0004-provider-usage-normalization.md) | Normalização de uso do provedor |
| [0005](0005-post-execution-cost-calculation.md) | Cálculo de custo após a execução |
| [0006](0006-operational-price-reference-configuration.md) | Referência operacional de preço |
| [0007](0007-operator-supplied-pre-execution-estimate.md) | Estimativa fornecida pelo operador |
| [0008](0008-multiple-openai-route-configuration.md) | Múltiplas rotas OpenAI |
| [0009](0009-operational-routing-constraints.md) | Restrições operacionais de roteamento |
| [0010](0010-operational-known-unavailability.md) | Indisponibilidade conhecida por rota |
| [0011](0011-operational-route-enablement.md) | Habilitação operacional de rotas |

Consulte [docs/INDEX.md](../INDEX.md) para a precedência e a finalidade das
fontes do projeto. O estado atual do runtime é resumido no
[Mapa do Sistema](../maps/SYSTEM-MAP.md).

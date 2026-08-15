# Mapa do sistema

> **Mapa de navegação técnica não normativo.** Esta visão resume o fluxo do sistema e não substitui a [arquitetura normativa](../03-ARQUITETURA.md) nem os contratos especializados.

```mermaid
flowchart TD
    A["POST /v1/executions"] --> B{"Validação pública"}
    B -->|inválida| X["INVALID_REQUEST<br/>sem execução externa"]
    B -->|válida| C["Catálogo / Provider Registry"]
    C --> D["Roteamento"]
    D --> E["Elegibilidade<br/>restrições e condições conhecidas"]
    E --> F{"Resta rota elegível?"}
    F -->|não| R1["NO_ELIGIBLE_ROUTE<br/>sem execução externa"]
    F -->|sim| G["Avaliação econômica<br/>estimativas e tetos"]
    G --> H{"Decisão econômica possível?"}
    H -->|não| R2["INSUFFICIENT_ECONOMIC_INFORMATION<br/>sem execução externa"]
    H -->|sim| I["Estratégia<br/>lowest-estimated-cost"]
    I --> J["Rota selecionada<br/>e decisão validada"]
    J --> K["Fronteira neutra de adaptador"]
    K --> L["Adaptador injetado<br/>uma única rota"]
    L --> M["Resultado normalizado"]
    M --> N["economics<br/>estimate preservada<br/>usage e custo indisponíveis"]
    N --> O["Resposta à aplicação<br/>resultado + decisão + economia"]
```

## Fluxo principal

A API valida a solicitação, consulta alternativas neutras, aplica elegibilidade antes da economia e usa a estratégia configurada para selecionar exatamente uma rota. Só uma decisão válida permite acionar o adaptador associado. Nesta fatia, esse fluxo é provado por adaptadores controlados e injetados nos testes; não existe integração com provedor real.

## Fluxo de recusa

- `NO_ELIGIBLE_ROUTE`: nenhuma rota comprova as restrições aplicáveis.
- `INSUFFICIENT_ECONOMIC_INFORMATION`: o custo é indispensável, mas os fatos econômicos não permitem decidir.

Ambas encerram o fluxo sem chamar provedor e preservam uma explicação objetiva. Casos limítrofes e a precedência entre erros pertencem aos contratos normativos.

## Estado atual do MVP

| Estado | Capacidade | Situação no repositório |
| --- | --- | --- |
| ✅ Implementado | Validação pública de `POST /v1/executions` | Schema fechado, JSON UTF-8 e erros de entrada. |
| ✅ Implementado | Elegibilidade não econômica | Filtros atuais, ordem normativa e recusa `NO_ELIGIBLE_ROUTE`. |
| ✅ Implementado | Avaliação econômica anterior à seleção | Estados de estimativa, tetos, comparabilidade e recusas `NO_ELIGIBLE_ROUTE` e `INSUFFICIENT_ECONOMIC_INFORMATION`. |
| ✅ Implementado | Seleção determinística | Estratégia `lowest-estimated-cost`, candidato único, comparação decimal, desempate por `route.id` e validação interna. |
| ✅ Implementado | Fronteira neutra de execução | Contrato assíncrono, associação manual em memória, execução única da rota selecionada e normalização de sucesso ou erro, provados com adaptador controlado nos testes. |
| 🟡 Próxima etapa | Primeiro adaptador externo | Nenhum adaptador de produção, SDK, credencial ou chamada de rede existe no repositório. |
| ⚪ Futuro | Uso e custo calculado | `usage` e `calculated_cost` posteriores à execução ainda não implementados. |

Esses marcadores descrevem o estado observado do repositório; não criam compromissos de roadmap.

## Onde se aprofundar

- [Arquitetura](../03-ARQUITETURA.md): componentes, responsabilidades, fronteiras e fluxo.
- [Casos de Uso](../04-CASOS-DE-USO.md): fluxos observáveis e recusas.
- [API Pública v1](../05-API.md): endpoint, schemas, respostas e erros.
- [Decisão de Roteamento](../06-DECISAO-DE-ROTEAMENTO.md): filtros, economia, estratégia, desempate e invariantes.

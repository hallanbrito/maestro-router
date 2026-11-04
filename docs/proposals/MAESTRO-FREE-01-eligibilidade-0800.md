# MAESTRO-FREE-01 — Contrato proposto de elegibilidade comprovada da Trilha 0800

- **Estado:** PROPOSTA CH-1 DOCUMENTAL — **não implementada e não normativa** até aprovação e integração por gate específico.
- **Emissão:** 03/11/2026.
- **Origem:** [Issue #39](https://github.com/hallanbrito/maestro-router/issues/39); direção de produto na [Issue #32](https://github.com/hallanbrito/maestro-router/issues/32) e [PR #34 — ADR 0014 integrada à master](https://github.com/hallanbrito/maestro-router/pull/34).
- **Baseline histórica de elaboração:** `master@f7f900a0d5104fc6fdf5622226b5c6bb5c7c6fce`. A ADR 0014 foi integrada separadamente à `master` em 04/11/2026 pelo PR #34 (merge `9d20727e34d37c71ccd56e6587f49d5525999e74`); este contrato CH-1 permanece em proposta, não implementado e sujeito a gate próprio.
- **Autonomia:** CH-1, documento somente. Nenhuma chamada externa de modelo, alteração de runtime, credencial real, merge, release ou gasto adicional autorizado.

## 1. Problema e limite de compatibilidade

A trilha Free atual no Control Center (ADR 0012) usa **tarifa zero declarada pelo operador**, com avisos de que não comprova condições de faturamento. A ADR 0014, já integrada como direção de produto, estabelece uma política futura mais forte: **permitir envio somente quando houver evidência válida e suficiente de ausência de cobrança adicional para a operação concreta**, na origem de credenciais correta. A compatibilidade com o contrato público `POST /v1/executions` (docs/05-API.md) e com a única estratégia atual `lowest-estimated-cost` (docs/06-DECISAO-DE-ROTEAMENTO.md) deve ser preservada.

Esta proposta especifica **um gate futuro**, não cria uma nova estratégia de roteamento, nem modifica os comportamentos atuais. Não introduzir `track`, `proof`, `tier` ou `quota` como campos da API pública v1 por inferência deste texto.

## 2. Vocabulário: conceitos que não podem ser confundidos

| Conceito | O que prova | O que **não** prova |
| --- | --- | --- |
| Tarifa zero **declarada** no catálogo local | Intenção/configuração do operador | Cobrança real zero da conta ou gratuidade do método de execução |
| Página oficial de preços com Free Tier | Possibilidade de gratuidade para modelo/operação/condições descritas | Elegibilidade, tier, saldo ou cota restante do projeto específico |
| Rate limit / cota de volume | Limite operacional para um escopo e janela definidos | Ausência de cobrança por chamada nem direito a usar saldo pago |
| API key válida ou listagem de modelos | Possibilidade de autenticar/listar certo catálogo | Compatibilidade com a operação de execução ou cobertura gratuita |
| Assinatura de produto de chat | Acesso ao produto nos termos do plano | Autorização de usar a API genérica sem cobrança |
| Crédito promocional ou saldo pré-pago | Possível abatimento de fatura ou cobertura temporária | Gratuidade estrutural; **não** autoriza gastar créditos na 0800 |
| Custo pré-estimado no Maestro | Estimativa econômica a partir de dados fornecidos | Fatura efetiva ou condição oficial de Free Tier do provedor |

**Política proposta:** a Trilha 0800 não usa créditos promocionais, saldo pago ou orçamento econômico como fallback. Uma estimativa de `0` **sozinha** nunca aprova execução.

## 3. Invariante de autorização e prova

**Regra central proposta:** `PERMITIR` somente quando, para a **mesma execução**, todas as condições abaixo forem satisfeitas por evidências autenticáveis e ainda vigentes; caso contrário, `RECUSAR_SEM_CHAMADA`.

1. **Permissão do operador:** escolha explícita da trilha Free e autorização para a origem de conta/projeto. A escolha não altera permissões do provedor.
2. **Identidade e escopo:** vínculo não ambíguo entre credencial autorizada e provedor, projeto/organização/conta de billing, tier, região quando relevante, modelo e método/endpoint **realmente executado pelo adaptador**. Não inferir identidade por nome de chave.
3. **Condição oficial de custo:** fonte oficial aplicável àquele modelo, operação, modalidade e ferramentas opcionais, demonstrando ausência de cobrança adicional. Recursos acessórios faturáveis tornam a evidência insuficiente, mesmo se tokens textuais forem gratuitos.
4. **Elegibilidade da origem:** comprovação atual de que o projeto/conta é abrangido por esse benefício. Uma página pública não satisfaz esta condição.
5. **Disponibilidade/cota:** capacidade restante comprovável na unidade real do provedor (por exemplo, projeto e janela, se assim definido), suficiente para **o pior caso limitado e admissível** da requisição, considerando reserva e concorrência; se não houver meio confiável, recusar.
6. **Frescor e integridade:** validade, versão, horário de observação, origem, digest/identificador da operação e eventual política de revogação verificáveis; qualquer mudança relevante invalida a prova.
7. **Isolamento de saída:** decisão sobre gratuidade e autorização acontecem **antes** do despacho. Não mudar para Econômica, não usar outro provedor, outra chave ou tentativa paga por conta própria.

**Limite explícito:** não foi comprovada aqui a existência de uma API oficial que exponha, de modo atômico e confiável, todos esses dados para cada provedor. Se alguma condição não puder ser observada/verificada em uma futura implementação, o resultado deve ser recusa; jamais simular comprovação.

## 4. Estados de avaliação propostos (não normativos)

Os nomes abaixo são candidatos para testes futuros, não estados existentes no runtime nem contrato aprovado para implementação.

| Estado de avaliação | Gatilho | Resultado permitido |
| --- | --- | --- |
| `ELIGIVEL_COMPROVADO` | Todos os critérios simultaneamente satisfeitos, prova vinculada à chamada e reserva válida | `PERMITIR` apenas a chamada delimitada |
| `DESCONHECIDO` | Tier, identidade, preços, tools, prova ou cota insuficientes/ausentes | `RECUSAR_SEM_CHAMADA` |
| `INELEGIVEL` | Prova de tier/modalidade/conta paga ou incompatível | `RECUSAR_SEM_CHAMADA` |
| `COTA_ESGOTADA` | Capacidade insuficiente na janela ou reserva negada | `RECUSAR_SEM_CHAMADA` |
| `EVIDENCIA_EXPIRADA` | TTL vencido, mudança de modelo/projeto/endpoint, revogação ou digest divergente | `RECUSAR_SEM_CHAMADA` |
| `FALHA_CONSULTA` | Erro, timeout, resposta inconsistente ou indisponibilidade da verificação permitida | `RECUSAR_SEM_CHAMADA` |

Nenhum estado é autorização para retry ou fallback automático. Falha do provedor **após** despacho não comprova custo zero retroativamente; o registro deve preservar a distinção entre autorização prévia, uso observado e cobrança real desconhecida.

## 5. Estrutura de evidências sugerida (apenas ilustrativa)

Os campos abaixo descrevem **dados internos prospectivos**, não um payload aceito pelo runtime atual e **não** um schema público da API v1.

````json
{
  "schema": "maestro.free-evidence/proposal-0.1",
  "route_id": "route-exemplo",
  "provider": "provedor-exemplo",
  "account_scope_ref": "alias-opaco-nao-secreto",
  "project_scope_ref": "alias-opaco",
  "operation": "modelo-e-metodo-exatos",
  "billing_tier": "comprovado-por-fonte-autorizada",
  "official_policy_ref": "uri-ou-id-de-fonte-oficial",
  "free_eligibility_ref": "evidencia-autenticavel-atual",
  "quota_scope_ref": "unidade-real-da-cota",
  "quota_reservation_ref": "reserva-atomica-se-suportada",
  "request_digest": "sha256-ilustrativo",
  "observed_at": "2026-11-03T00:00:00Z",
  "expires_at": "2026-11-03T00:00:01Z",
  "verification_status": "NOT_VERIFIED"
}
````

O exemplo acima é **deliberadamente inelegível**: `NOT_VERIFIED` e dados de demonstração **não** conferem autoridade. Nunca registrar token, segredo, identidade de cobrança sensível, resposta bruta de provedor ou prova que não foi obtida.

Implementação futura deverá escolher versão, serialização canônica, mecanismo de confirmação de identidade, tratamento de relógio/replay e política de reserva **somente após auditoria do provedor e decisão do PO**.

## 6. Algoritmo conceitual fail-closed (não executável)

````text
avaliar_0800(missao, rota, identidade, evidencias):
    exigir_selecao_0800_explicita()
    conferir_permissao_escopo_e_conta()
    conferir_compatibilidade_real_do_metodo_e_modelo()
    validar_politica_oficial_sem_cobranca_adicional()
    validar_beneficio_atual_da_conta_projeto()
    validar_capacidade_suficiente_e_reserva_concorrente()
    validar_integridade_frescor_digest_e_restricoes()
    se qualquer etapa for falsa, incerta ou indisponivel:
        retornar RECUSAR_SEM_CHAMADA, motivo_sanitizado
    permitir SOMENTE a execucao delimitada; sem fallback pago
````

A ordem de verificação e os detalhes de atomicidade são itens de projeto, não comportamento implementado. Nenhuma consulta de prova pode executar geração por engano ou elevar permissões. Um resultado `PERMITIR` não é garantia universal de fatura zero quando as condições externas não são totalmente verificáveis.

## 7. Matriz de testes offline para uma futura implementação

Todos os cenários são **projetados**, não executados. Usar mocks/fixtures de fontes autorizadas e instrumentos que comprovem `provider_calls=0` nas recusas.

| ID | Cenário de fixture | Resultado exigido |
| --- | --- | --- |
| FREE-001 | Evidências completas, atuais, escopo exato e cota/reserva suficientes | Permitir somente rota delimitada |
| FREE-002 | Tarifa local 0, sem prova oficial | Recusar, 0 chamadas |
| FREE-003 | Free Tier anunciado, tier de projeto desconhecido | Recusar, 0 chamadas |
| FREE-004 | Modelo elegível, método/endpoint real não comprovado | Recusar, 0 chamadas |
| FREE-005 | API key válida e modelo listado, sem prova de cobrança | Recusar, 0 chamadas |
| FREE-006 | Assinatura de chat, sem autorização oficial específica de API | Recusar, 0 chamadas |
| FREE-007 | Crédito promocional, sem gratuidade comprovada | Recusar, 0 chamadas |
| FREE-008 | Cota esgotada | Recusar, 0 chamadas |
| FREE-009 | Sem acesso confiável à cota restante | Recusar, 0 chamadas |
| FREE-010 | Rate limit compartilhado por projeto; duas chaves da mesma origem | Não duplicar franquia; recusar se insuficiente |
| FREE-011 | Reservas concorrentes disputam último saldo da janela | Não autorizar ambas sem prova de capacidade |
| FREE-012 | Prova expirada/revogada ou mudança de escopo | Recusar, 0 chamadas |
| FREE-013 | Falha/timeout/JSON inválido no verificador | Recusar, 0 chamadas |
| FREE-014 | Ferramenta acessória potencialmente faturável | Recusar, 0 chamadas |
| FREE-015 | Rota gratuita inelegível, rota paga disponível | Recusar sem fallback para paga |
| FREE-016 | Estimativa do Maestro igual a zero, sem evidência oficial de Free | Recusar, 0 chamadas |
| FREE-017 | Modelo suportado somente por outra API do mesmo provedor | Recusar, 0 chamadas |
| FREE-018 | Identidade/projeto divergente entre prova e credencial | Recusar, 0 chamadas |
| FREE-019 | Dados sensíveis em resposta de erro simulado | Sanitizar resposta/log; 0 vazamentos |
| FREE-020 | Repetição do mesmo digest após consumo/expiração de reserva | Sem aprovação reaproveitada indevidamente |

**Gate de teste CH-2 futuro:** validar cobertura, não alteração da API v1, ausência de envio em todas as recusas, idempotência sob concorrência, e instrumentos que contem chamadas aos adaptadores reais. Cenários simulados não demonstram elegibilidade real de qualquer conta.

## 8. Questões abertas para investigação antes de escrever código

- Para quais provedores e APIs existe sinal **oficial** de elegibilidade gratuita por projeto/conta e de cota atual, sem gerar cobrança? Quais operações de consulta são autorizadas e realmente sem custo?
- É possível reservar quota de forma atômica? Caso contrário, quais condições tornam impossível prometer não ultrapassar a franquia sob concorrência?
- A política do provedor distingue métodos (Responses/Interactions/generateContent), região, batch, cache e ferramentas com cobrança separada?
- Qual o limite máximo de tokens e de chamadas por missão que permita verificação conservadora? Como lidar com variabilidade da contagem e políticas mutáveis?
- A unidade de quota é projeto, organização, conta, chave, modelo ou outra? Como impedir contagem duplicada?
- Existe mecanismo de revogação/TTL e que evidência auditável poderá ser guardada sem armazenar segredos?
- Como integrar o gate administrativo sem alterar a API v1 e sem inventar critérios de qualidade ou latência?

**Sem resposta verificável a qualquer questão essencial: manter `RECUSAR_SEM_CHAMADA`.**

## 9. Referências e limites factuais

- [ADR 0012 — camada administrativa](../decisions/0012-control-center-local-admin-layer.md): implementação atual de Free declarada.
- [ADR 0013 — adaptador Google Interactions](../decisions/0013-google-gemini-interactions-adapter.md): integrações sem garantia automática de quota/preço.
- [Issue #32 / PR #34 — ADR 0014](https://github.com/hallanbrito/maestro-router/pull/34): política de produto aprovada e integrada à `master` em 04/11/2026; capacidades futuras ainda não implementadas.
- [OpenAI — cobrança ChatGPT versus API](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform): produtos têm sistemas de cobrança separados.
- [Google — Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing): condições oficiais variam por modalidade/modelo e por ferramenta.
- [Google — Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits): limites variam por projeto/tier e janela; rate limit não é prova de preço.

As fontes oficiais são referências mutáveis e **não** atestam nenhuma conta, cota ou operação real do usuário. O documento não afirma elegibilidade atual de OpenAI, Gemini ou qualquer outro provedor.

## 10. RUC simplificado e próxima decisão

- **Mudança:** uma especificação Markdown nova em branch própria; a ADR 0014 foi integrada separadamente pelo PR #34.
- **Código, UI, SDK, endpoints, testes, workflows:** nenhum alterado.
- **Validação desta fatia:** inspeção do diff e referências documentais; **nenhum teste automatizado de runtime executado**.
- **Risco dominante:** falsa sensação de gratuidade. Mitigação proposta: prova completa, atual e vinculada à chamada ou recusa preventiva.
- **Decisão pendente:** auditoria documental independente e homologação explícita do PO. Apenas após isso será possível discutir uma fatia CH-2 de implementação, com critérios de viabilidade próprios.
- **Merge/release/deploy:** não autorizados nesta missão.

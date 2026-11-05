# MAESTRO-FREE-02-R1 — Roteamento preferencial gratuito, recuperação e continuidade

**Estado:** PROPOSTA DOCUMENTAL CH-1 / NÃO IMPLEMENTADA / AGUARDANDO_AUDITORIA_CHATGPT E PO  
**Data:** 05/11/2026 · **Issue:** [#42](https://github.com/hallanbrito/maestro-router/issues/42)  
**Branch de proposta:** `docs/maestro-free-02-r1` · **Baseline de elaboração (`master`):** `18668ebc32b2520bf69c17852e28743617e97703`  
**Autorização:** direção de produto e especificação CH-1 aprovadas pelo PO. Não autoriza código de runtime, chamadas a provedores, cobrança, merge, release ou deploy.

> **Status normativo:** este texto **propõe** rever a [ADR 0014](../decisions/0014-three-routing-tracks-policy.md) e o [contrato FREE-01](MAESTRO-FREE-01-eligibilidade-0800.md); **não modifica** nenhuma dessas normas. Os comportamentos atuais do Maestro prevalecem até decisão PO e mudanças integradas sob novo gate.

## 1. Problema e proposta de valor

A política Free/0800 anterior só permitiria enviar uma chamada mediante prova suficiente de que ela **não gerará cobrança adicional** para a conta concreta. Na prática, provedores podem não oferecer consulta completa, confiável e atômica de faturamento, franquias, quotas e condições da conta. Uma política dependente de prova impossível pode inviabilizar o roteamento.

**Nova direção de produto proposta:** oferecer uma trilha **“0800 — Preferencialmente Gratuita”** que prioriza alternativas com gratuidade declarada ou franquia informada, com informação clara de que **custos adicionais podem ocorrer**, sujeita a consentimento e restrições efetivamente configuradas pelo operador. A estratégia deve procurar alternativas elegíveis diante de falhas recuperáveis sem prometer tarifa zero, cota infinita ou continuidade do raciocínio interno.

**Aviso sugerido para a interface:**
> “Esta trilha prioriza opções gratuitas e franquias disponíveis, mas não garante ausência de cobrança. O valor e a disponibilidade dependem de cada provedor, conta, modelo e operação. O Maestro não conhece necessariamente sua fatura.”

A expressão `0800` é **nome comercial da preferência**, não atestado de faturamento. Não apresentar `estimated_cost=0`, tarifa de catálogo `0`, assinatura ou API key válida como prova de gratuidade real.

## 2. Estado real e fronteiras existentes

| Capacidade | Estado na `master` consultada | Consequência nesta proposta |
| --- | --- | --- |
| `POST /v1/executions` | API v1 pública com schema fechado | Não introduzir campos públicos de sessão, consentimento ou trilha sem contrato/versão própria |
| Catálogo e roteamento neutro | Implementado; seleção determinística `lowest-estimated-cost` | Reutilizar a elegibilidade atual, sem refazer o núcleo |
| Restrições/custos estimados | Implementados para fatos declarados, sem fatura real | Preservar limites e distinção entre estimativa e cobrança |
| Adaptadores externos | OpenAI Responses e Gemini Interactions sem estado, mais adaptadores controlados | POC usa **somente mocks**; novas credenciais e provedores ficam fora |
| Execução | Uma rota por requisição; não existe ciclo genérico de fallback | Orquestrador de tentativas é **candidato futuro**, sem execução nesta CH-1 |
| Continuidade de conversa entre trocas de rota | Não há protocolo público de sessão/handoff demonstrado | POC usa envelope de histórico sintético **em memória**, sem persistência |

Fontes internas: [API v1](../05-API.md), [decisão de roteamento](../06-DECISAO-DE-ROTEAMENTO.md), [mapa do sistema](../maps/SYSTEM-MAP.md), [ADR 0014](../decisions/0014-three-routing-tracks-policy.md), [FREE-01](MAESTRO-FREE-01-eligibilidade-0800.md).

## 3. Dois comportamentos de risco econômico — escolha explícita

A denominação “0800” não concede, por si só, permissão para gastar.

| Política candidata | Preferência | Tratamento de risco |
| --- | --- | --- |
| `prefer_free` (trilha comercial 0800) | Ordenar rotas com oferta/franquia gratuita **declarada**, elegibilidade técnica e disponibilidade observável | Requer **ciência explícita de potencial cobrança** para habilitar a trilha. Qualquer rota paga exige **opt-in financeiro separado**, escopo permitido e teto estimado |
| `strict_no_additional_cost` (opção restritiva futura) | Exigir comprovação suficiente para custo adicional zero | Preserva a intenção estrita do FREE-01: sem prova, **não enviar**; recusar em vez de relaxar |
| `economic` / `intelligent` | Permanecem políticas distintas | Não reinterpretar a seleção atual como otimização já implementada de qualidade/latência |

**Termos distintos:** (a) aceitação do **risco** de cobrança não assegura que a execução tenha autorização econômica; (b) autorização econômica define limites de rotas e teto de custo estimado; (c) a estimativa local **não é um teto garantido de faturamento** do provedor. Sempre permitir revogação do consentimento para solicitações futuras; não fabricar consentimento por resposta de modelo, comentários ou configuração implícita.

**Padrões iniciais propostos:** `allow_paid_fallback=false`, `max_attempts=2`, `allowlisted_route_ids` explícito, timeout total finito e orçamento estimado por solicitação quando houver opt-in financeiro. Sem autorização para custo adicional, não escolher rotas com cobrança conhecida ou possibilidade de cobrança não aceita; se a proteção não puder ser cumprida, recusar. Os valores finais exigem estudo e gate de implementação, não são parâmetros disponíveis hoje.

## 4. Modelo conceitual do orquestrador de tentativas

Fluxo prospectivo (não executável):

```text
solicitação validada + restrições imutáveis + consentimento vigente
  → snapshot de rotas permitidas e estados observáveis
  → ordenar candidatas preferencialmente gratuitas
  → selecionar rota A (router canônico)
  → pré-flight: escopo, modelo, orçamento estimado, timeout, janela
  → chamada permitida (somente em implementação futura autorizada)
       ├─ sucesso completo: finalizar, registrar provedor e uso conhecido
       ├─ falha inequivocamente recuperável antes da resposta:
       │    excluir rota tentada temporariamente, reavaliar B sob os MESMOS limites
       └─ resultado parcial, cancelado ou indeterminado:
            não repetir automaticamente; registrar estado e devolver erro seguro
```

**Invariantes:**
1. Fallback é **nova decisão entre rotas já permitidas**, não exceção aos limites, autenticação, capacidades, modelos compatíveis, orçamento ou consentimento.
2. Tentativas têm rastreio por `execution_id` e `attempt_id`, ordem, estado, versão do catálogo, motivos sanitizados e tempo. Sem logs de credenciais/payloads sensíveis.
3. Falha recuperável não significa gratuidade: tentativas fracassadas **podem** ter consumido tokens ou gerado cobrança.
4. Não repetir automaticamente chamadas com **efeitos externos**, escrita, ferramentas, stream parcialmente entregue, ou resultado de execução duvidoso sem chave de idempotência/garantia verificável.
5. Prazos, cancelamento humano e quantidade de tentativas pertencem à operação completa, não são reiniciados por cada troca.
6. A política não pode aumentar permissões no curso da execução ou mudar silenciosamente da Free para Econômica/Inteligente.

### Tabela conceitual de falhas

| Evento | Resultado prospectivo |
| --- | --- |
| `429` e limite/cooldown verificável | Registrar indisponibilidade temporária; tentar B elegível se não houver resposta parcial e houver autorização |
| Falha temporária `5xx` ou de conexão | Tentativa B **somente** quando o resultado anterior for seguramente recuperável; caso indeterminado, bloquear replay |
| `401/403` | Não circular credenciais entre provedores; marcar aquela origem como inelegível e exigir correção/novo escopo |
| Capacidade/contexto incompatível | Excluir rota antes de envio; jamais truncar histórico sem política aprovada |
| Resposta parcial/stream já entregue | Não reexecutar automaticamente para evitar duplicação e inconsistência |
| Uso de ferramenta com efeito, resposta incerta | Parar em `INDETERMINATE`; eventual retomada exige garantia de idempotência ou revisão humana |
| Todas as rotas exauridas / orçamento incerto | Recusa explicável, sem fallback pago silencioso |

## 5. Continuidade de sessão: o que significa “não perder o fio”

O sistema só consegue transferir **dados que recebeu e tem permissão de conservar**: mensagens de usuário/assistente, respostas de ferramentas autorizadas, resumos explícitos, identificador de tarefa e checkpoints observáveis.

**Envelope conceitual de POC (inteiramente sintético; NÃO é campo da API v1):**

```json
{
  "schema": "maestro.context-envelope/proposal-0.1",
  "execution_id": "demo-exec-001",
  "session_ref": "demo-session-local",
  "messages": [
    {"role": "user", "content": "Explique a etapa 1"},
    {"role": "assistant", "content": "Etapa 1 registrada"}
  ],
  "checkpoint": {
    "last_complete_message_index": 1,
    "summary_source": "observed-messages-only"
  },
  "tool_effects_pending": false,
  "consent_scope": "synthetic-offline"
}
```

- Nunca afirmar que consegue preservar **raciocínio oculto**, memória própria de um provedor ou contexto não fornecido ao Maestro.
- `sticky route` significa preferir modelo previamente bem-sucedido **enquanto elegível**; falha recuperável permite reavaliar, não “clonar” estado interno.
- A POC mantém o histórico apenas **na memória de teste**; persistência, retenção, cifragem, múltiplos clientes, política de privacidade e exclusão exigem gates próprios.
- Truncamento/resumo automático e transição entre janelas incompatíveis não são autorizados por esta proposta.
- A futura API precisa deliberar se a sessão permanece no cliente ou terá versão pública própria; não adicionar `session_id` à v1 fechada por inferência.

## 6. Plano de POC offline para gate CH-2 futuro

**Hipótese validável:** com dois adaptadores mockados (A e B), o orquestrador proposto consegue selecionar rota autorizada, detectar falha recuperável, refazer a seleção sem relaxar restrições e encaminhar o histórico explícito ao B, **sem qualquer chamada de rede**.

**Componentes de teste sugeridos, não implementados:**
- `FakeRouteCatalog`: duas rotas, capacidades, estado de disponibilidade, custo estimado e preferências declaradas.
- `FakeProviderA` e `FakeProviderB`: resultados determinísticos, 429, indisponibilidade, resposta parcial e erro indeterminado.
- `FakeConsentStore`: opt-in/opt-out, teto estimado e permissões por origem, sem credenciais reais.
- `InMemoryContextEnvelope`: duas mensagens sintéticas e checkpoint rastreável.
- `AttemptLedger`: trilha de tentativas, custo conhecido/desconhecido e motivo de troca.

**Matriz de critérios de aceite para futura implementação:**

| ID | Cenário de mock | Resultado exigido |
| --- | --- | --- |
| F02-01 | A gratuita declarada e disponível | A selecionada; 1 tentativa |
| F02-02 | A responde 429 antes de conteúdo | B elegível selecionada; máximo 2 tentativas |
| F02-03 | A falha temporariamente, B fora da allowlist | Recusa; B nunca chamada |
| F02-04 | B tem custo pago conhecido, sem opt-in financeiro | Recusa; zero tentativas em B |
| F02-05 | Usuário aceitou risco, mas não autorizou rota paga | Não interpretar risco como autorização econômica |
| F02-06 | Teto estimado seria ultrapassado na segunda tentativa | Recusa antes do segundo envio |
| F02-07 | A já emitiu conteúdo parcial | Nenhum replay automático |
| F02-08 | Resultado indeterminado ou ferramenta com efeito externo | `INDETERMINATE`; sem repetição |
| F02-09 | A indisponível e B elegível, histórico sintético presente | B recebe exatamente o contexto permitido |
| F02-10 | Resumo/estado interno não disponível | Nenhuma alucinação de memória ou contexto oculto |
| F02-11 | Cancelamento ou timeout total | Interromper tentativas e devolver estado explícito |
| F02-12 | Todas as rotas esgotadas/cooldown | Recusa com motivo sanitizado |
| F02-13 | Credencial de A falha autenticação | Não repassar segredo a B |
| F02-14 | Mudança de consentimento antes do fallback | Reavaliar; negar quando revogado |
| F02-15 | Repetição da mesma chamada com idempotência incerta | Não duplicar efeitos |
| F02-16 | A retorna uso sem dados de faturamento | Marcar `billing_actual=UNKNOWN`, sem alegar zero |
| F02-17 | Rota muda capacidade ou versão de modelo | Reavaliar restrições sem diminuir requisitos |
| F02-18 | Opt-in e preço conhecido para B | Mesmo autorizado, respeitar orçamento estimado e registrar risco real |

**Definição de pronto da POC futura:** todos os testes reproduzíveis offline; contador de chamadas externas reais `=0`; nenhum segredo; documentação de incompatibilidades da API v1; revisão independente e RUC; PR separada sem merge automático. A prova de conceito **não será executada neste gate CH-1**.

## 7. Revisões normativas propostas, separadas da implementação

### ADR 0014 — revisão futura

- Reenquadrar a antiga “Free rigorosamente grátis” para uma **preferência gratuita** com aviso obrigatório e consentimento explícito.
- Preservar como **modo restritivo opcional** a política `strict_no_additional_cost` de evidência forte.
- Especificar autorização econômica e fallback pago como escolhas distintas; custos adicionais são risco real, não benefício garantido.
- Adicionar futura orquestração de tentativas e continuidade observável **sem afirmar que já estão implementadas**.

### FREE-01 — revisão futura

- Manter as regras existentes como especificação da **opção restritiva**, não como pré-condição inevitável de toda execução da Trilha 0800 preferencial.
- Reutilizar estados `DESCONHECIDO`, `COTA_ESGOTADA`, `EVIDENCIA_EXPIRADA` como fatos observáveis quando disponíveis; falta de prova não deve ser apresentada como prova positiva de gratuidade.
- Não reescrever histórico nem renomear contratos em runtime por antecipação.

### API pública e versões

- `POST /v1/executions` e formatos atuais **intocados** nesta proposta.
- Eventual configuração administrativa local pode fazer composição interna apenas quando não enfraquecer regras nem expor campos públicos inválidos; qualquer nova semântica observável e persistência de sessão necessita revisão específica de contratos.
- Não confundir seleção `lowest-estimated-cost` hoje com recurso de retry/fallback ainda inexistente.

## 8. Riscos e decisões ainda abertas

1. Como comprovar ao operador o teto **estimado** quando o provedor divulga cobrança posterior, quotas compartilhadas ou preço ausente? Limitar e sinalizar incerteza; **nunca prometer hard cap de fatura externa**.
2. Qual política de retenção do histórico e dados pessoais é aceitável? Exige desenho separado, consentimento e avaliação de segurança.
3. O que fazer quando token foi consumido antes de um 5xx/timeout? Registrar resultado `UNKNOWN` e bloquear replays inseguros.
4. Como distinguir falha do modelo, do adaptador, da conta e do provedor sem criar falsos positivos de indisponibilidade global?
5. Como preservar a versão e a compatibilidade da API v1 fechada sem ampliar implicitamente o contrato?
6. Quais atributos de qualidade/latência serão demonstrados por evidência suficiente para qualquer nova estratégia?

Esses itens não são autorização para implementar soluções presumidas; requerem escolha explícita do PO antes de CH-2.

## 9. RUC/1.0 — MAESTRO-FREE-02-R1 (CH-1)

| Campo | Registro |
| --- | --- |
| Identificação | Issue #42; proposta da Trilha 0800 preferencial; CH-1 |
| Baseline | `master@18668ebc32b2520bf69c17852e28743617e97703` |
| Artefato | Somente este arquivo Markdown em branch de documentação e Draft PR |
| Motivação | Roteamento útil com transparência de risco, evitando bloqueio por impossibilidade de comprovar faturamento zero |
| Fontes internas | ADR 0014, FREE-01, 05-API, 06-Decisão de Roteamento, mapa do sistema |
| Validações planejadas | Escopo de um arquivo; tabelas, blocos e cenários revisáveis; CI documental quando disponível |
| Execução nesta missão | **Nenhuma POC, modelo ou teste de runtime executado** |
| Custos adicionais | **Nenhuma chamada de API de modelo**; somente operações GitHub autorizadas |
| Limitações | Política, mocks, orçamento e handoff são **propostos**, não executáveis na `master` atual |
| Parecer de saída | `AGUARDANDO_AUDITORIA_CHATGPT / AGUARDANDO_PO / SEM_MERGE` |

**Próximo gate:** decidir sobre revisão normativa ADR/FREE e autorizar, se desejado, POC **offline** separada. Nenhum worker ou missão de código é disparado por este documento.

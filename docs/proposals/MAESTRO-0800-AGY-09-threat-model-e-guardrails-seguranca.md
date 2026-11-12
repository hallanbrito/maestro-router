# MAESTRO-0800-AGY-09 — Threat Model e Guardrails de Segurança 0800

> **Status:** PROPOSTA DE SEGURANÇA E GUARDRAILS / CH-2 CÓDIGO E TESTES OFFLINE  
> **Data:** 12/11/2026 · **Origem:** [Issue #62](https://github.com/hallanbrito/maestro-router/issues/62) · **Épico:** [Issue #52](https://github.com/hallanbrito/maestro-router/issues/52)  
> **Baseline:** `master@31a2f1c0db505a70359fac6a9ccf80804f5f7dd3`  
> **Branch de trabalho:** `feat/maestro-0800-agy-09-seguranca-0800`  
> **Princípios Inegociáveis:** Zero chamadas externas pagas, zero custo (R$ 0,00), zero segredos versionados, testes 100% offline via fakes determinísticos, sem alterações que quebrem a API v1 pública ou a branch `master`.

---

## 1. Contexto e Objetivos da Ordem de Serviço

A [ADR 0014](../decisions/0014-three-routing-tracks-policy.md) estabelece a política mandatória para a **Trilha 0800 / Free**: executar requisições exclusivamente por rotas que possuam **evidência suficiente de não gerar cobrança adicional** para a conta, projeto ou credencial em uso. A ausência de comprovação técnica exige recusa antes do envio (*fail-closed*), sem jamais realizar fallback pago implícito.

A presente entrega (**AGY-09 — Issue #62**) implementa os controles e a suíte de testes de segurança cobrindo cinco eixos essenciais:
1. **Credenciais e Higiene de Segredos:** Armazenamento restrito a ambiente/memória com escopo estrito; redaction compulsória em erros, headers, stdout e representações; scanner de segredos em diffs e relatórios;
2. **Duplo Gate de Ativação e Revogação:** Separação entre aprovação administrativa de elegibilidade no laboratório (Gate 1) e consentimento de execução pelo operador (Gate 2); garantia de que *conta sem cartão de crédito NÃO constitui autorização de gastos*; suporte a revogação instantânea;
3. **Egress Seguro e Mitigação de SSRF:** Validação de esquemas estritamente HTTPS e hostnames oficiais (OpenAI, Groq, Alibaba Singapore Internacional, Google Gemini); bloqueio de IPs privados, loopback, metadados de nuvem e endpoints domésticos chineses de outra jurisdição; ferramentas pagas/browsing desabilitadas por padrão;
4. **Política No-Cost Fallback e Anti-Bypass de Quotas:** Fallback admitido unicamente entre rotas 0800 permitidas; bloqueio de escalada para rotas pagas sem autorização financeira explícita; proibição de rotação de múltiplas chaves da mesma organização para contornar quotas; fail-closed em falhas indeterminadas;
5. **Suíte de Testes Negativos Offline:** Cobertura de respostas 401 (não autorizado), 403 (franquia esgotada / `AllocationQuota.FreeTierOnly` / região bloqueada), 429 (rate limit), injeção de prompt nas entradas, logs sanitizados e zero execuções sem consentimento.

---

## 2. Threat Model: Vetores de Ameaça e Mitigações

| ID Ameaça | Vetor de Ataque / Risco Operacional | Impacto Potencial | Mitigação Implementada (Guardrail) |
| :---: | :--- | :--- | :--- |
| **T-01** | **Vazamento de Chaves em Logs ou Erros:** Mensagens de erro de SDK ou exceções de rede contendo `api_key` ou cabeçalhos de autorização expostos em logs, stdout ou JSON de erro. | Comprometimento de credenciais corporativas. | **M-01 — Redactor Compulsório & Scanner:** Função `redact_sensitive_text` sanitiza tokens conhecidos (`sk-...`, `gsk_...`, `AIza...`, Bearer); `scan_diff_for_secrets` inspeciona diffs. |
| **T-02** | **Presunção Indevida de Gratuidade ("Conta sem Cartão"):** Operador ou sistema presume que uma conta sem cartão cadastrado tem autorização de consumo ou garantia de custo zero. | Cobrança inesperada pós-paga, bloqueio de conta ou passivo contratual. | **M-02 — Duplo Gate com Regra Anti-Presunção:** Gate 1 exige prova documental/console de Free Tier ativo; flag `no_credit_card` rejeita categoricamente autorização de gastos sem comprovação formal. |
| **T-03** | **SSRF e Egress para Endpoints Maliciosos/Internos:** Requisição direcionada para IP de loopback (`127.0.0.1`), metadata service (`169.254.169.254`), rede interna (`10.0.0.0/8`) ou URL arbitrária. | Exfiltração de dados locais de host, credenciais de metadados de nuvem ou pivoteamento de rede. | **M-03 — Validador Estrito de Egress:** Bloqueio de qualquer IP numérico, esquema não HTTPS ou domínio fora da allowlist oficial de provedores aprovados. |
| **T-04** | **Incompatibilidade de Região / Jurisdição (Alibaba):** Envio de chave ou tráfego para `dashscope.aliyuncs.com` (site doméstico China) em vez do endpoint internacional em Cingapura (`ap-southeast-1`). | Faturamento em moeda diferente, desconformidade de termos e falha de autorização. | **M-04 — Validação de Região e Base URL:** Bloqueio explícito do host doméstico; aceitação exclusiva de `dashscope-intl.aliyuncs.com` ou subdomínio `ap-southeast-1`. |
| **T-05** | **Escalada Não Autorizada para Rota Paga (Fallback Pago):** Falha transitória (429/503) em modelo gratuito desencadeia redirecionamento silencioso para modelo tarifado pago. | Prejuízo financeiro e violação do consentimento do operador (ADR 0014). | **M-05 — Fallback Restrito a Custo Zero:** Rotas pagas são estritamente excluídas do conjunto elegível a menos que haja consentimento financeiro explícito com teto monetário estrito. |
| **T-06** | **Bypass Malicioso de Quota via Rotação de Chaves:** Sistema rotaciona múltiplas chaves pertencentes ao mesmo projeto/organização para contornar limites de taxa (rate limits). | Violação dos termos de serviço do provedor, suspensão de organização e perda de controle. | **M-06 — Anti-Bypass de Quota:** Bloqueio formal de rotação de credenciais sob a mesma organização para fins de contorno de cota. |
| **T-07** | **Injeção de Prompt / Escape de Fronteira em Entradas:** Cargas úteis em `task` ou `context` tentando sobrescrever instruções do roteador, injetar cabeçalhos HTTP ou extrair variáveis de ambiente. | Desvio de rota, comportamento inseguro do sistema. | **M-07 — Sanitização e Isolamento de Entrada:** Validação estrita de tipos, rejeição de caracteres inválidos/surrogates, e garantia de que payloads são dados inertes, nunca instruções do sistema. |
| **T-08** | **Repetição de Falha com Efeito Colateral Incerto:** Falha parcial de rede ou timeout após início de resposta sendo re-executada em outro provedor. | Consumo duplicado de quota, respostas concorrentes ou custos ocultos. | **M-08 — Fail-Closed em Estado Indeterminado:** Se `content_started=True` ou falha for desconhecida/incerta, a requisição é encerrada como `indeterminate`, sem retentativa. |

---

## 3. Especificação dos Guardrails Técnicos

### 3.1. Duplo Gate de Ativação e Revogação
- **Gate 1 (Aprovação Administrativa de Laboratório):**
  - Entidade: `ProviderGateState`.
  - Requisitos: `provider_id`, `model_id`, `verified_free_tier=True`, `scope` documentado e `approved_by_operator=True`.
  - Invariante inegociável: `no_credit_card_attached=True` sem `verified_free_tier=True` gera rejeição explícita `SecurityPolicyError("Ausência de cartão de crédito não comprova gratuidade nem autoriza execução")`.
- **Gate 2 (Consentimento de Execução do Operador):**
  - Entidade: `ExecutionConsent`.
  - Requisitos: `risk_acknowledged=True`, `allowed_route_ids` (conjunto fechado), `paid_fallback_authorized=False` (por padrão), `max_estimated_brl=Decimal('0')`.
  - Revogação: método `revoke()` invalida imediatamente a autorização. Qualquer retentativa subsequente aborta como `blocked`.

### 3.2. Validador de Egress e SSRF
- **Regras de Validação:**
  1. Esquema: **exclusivamente `https`**. `http://`, `file://`, `ftp://` disparam `SSRFSecurityError`.
  2. Endereços IP: qualquer representação IPv4/IPv6 (ex: `127.0.0.1`, `10.0.0.1`, `169.254.169.254`, `[::1]`) dispara `SSRFSecurityError`.
  3. Domínios locais: `localhost`, `.local`, `.internal` disparam `SSRFSecurityError`.
  4. Portas: somente porta 443 (padrão HTTPS) permitida.
  5. Allowlist canônica de provedores:
     - OpenAI: `api.openai.com`
     - Groq: `api.groq.com`
     - Alibaba International: `dashscope-intl.aliyuncs.com` ou `*.ap-southeast-1.maas.aliyuncs.com`
     - Google Gemini: `generativelanguage.googleapis.com`
  6. Rejeição de endpoint doméstico Alibaba: `dashscope.aliyuncs.com` rejeitado como violação de região.

### 3.3. Sanitização de Erros e Logs
- Nenhum valor sensível pode transitar para exceções ou saídas de log.
- Reconhecimento do código `403 AllocationQuota.FreeTierOnly` do Alibaba como término seguro de cota, com parada estrita (*fail-closed*).
- Tratamento de `401 Unauthorized` como falha de autenticação irrecuperável localmente, proibindo envio do mesmo payload a terceiros com outras credenciais.

---

## 4. RUC/1.0 — Relatório Unificado de Conformidade

### 4.1. Identificação
- **Missão:** MAESTRO-0800 AGY-09 [P0] · [Issue #62](https://github.com/hallanbrito/maestro-router/issues/62).
- **Executor:** AGY (Antigravity).
- **Baseline:** `master@31a2f1c0db505a70359fac6a9ccf80804f5f7dd3`.
- **Branch:** `feat/maestro-0800-agy-09-seguranca-0800`.
- **Regime:** Testes 100% offline, zero chamadas externas, custo R$ 0,00.

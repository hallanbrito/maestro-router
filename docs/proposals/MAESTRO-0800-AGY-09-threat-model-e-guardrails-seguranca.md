# MAESTRO-0800-AGY-09 — Threat Model e Guardrails de Segurança 0800 (Revisão R1)

> **Status:** PROPOSTA DE SEGURANÇA E GUARDRAILS / CH-2 CÓDIGO E TESTES OFFLINE (PÓS-REVISÃO R1)  
> **Data:** 13/11/2026 · **Origem:** [Issue #62](https://github.com/hallanbrito/maestro-router/issues/62) · **Draft PR:** [#69](https://github.com/hallanbrito/maestro-router/pull/69) · **Épico:** [Issue #52](https://github.com/hallanbrito/maestro-router/issues/52)  
> **Baseline:** `master@31a2f1c0db505a70359fac6a9ccf80804f5f7dd3`  
> **Branch de trabalho:** `feat/maestro-0800-agy-09-seguranca-0800`  
> **Princípios Inegociáveis:** Zero chamadas externas de rede, zero custo (R$ 0,00), zero segredos versionados ou expostos, testes 100% offline via executor fake determinístico, sem alterações na API pública v1 (`docs/05-API.md`), sem modificações na branch `master` e sem antecipar a AGY-03.

---

## 1. Contexto, Limitações e Escopo Operacional

A [ADR 0014](../decisions/0014-three-routing-tracks-policy.md) estabelece a política mandatória para a **Trilha 0800 / Free**: executar requisições exclusivamente por rotas que possuam **evidência suficiente de não gerar cobrança adicional** para a conta, projeto ou credencial em uso. A ausência de comprovação técnica exige recusa antes do envio (*fail-closed*), sem jamais realizar fallback pago implícito.

### Declaração de Limitações e Não-Acoplamento ao Runtime de Produção (R1-01)
- **Componentes Offline:** Os guardrails implementados em `src/maestro_router/security.py` constituem primitivas arquiteturais de segurança demonstradas offline. **Não estão acoplados ao runtime de produção** (`POST /v1/executions` ou `Control Center`) nesta fatia, mantendo o escopo estrito da Issue #62.
- **Executor Fake Determinístico:** A verificação dos gates no fluxo de execução é comprovada via `DeterministicOffline0800Executor`, garantindo que zero tentativas ou retentativas ocorram sem autorização válida.
- **Dependência Documental AGY-01 (R1-03):** A verificação operacional em tempo real de quotas junto aos provedores depende da homologação formal da especificação de elegibilidade (PR #67 / AGY-01, atualmente em Draft). Na presente fatia, define-se o contrato formal de evidência offline (`FreeTierEvidence`) e a vinculação estrita de escopo, sem inventar chamadas ou simuladores não homologados de APIs de quotas dos provedores.

---

## 2. Threat Model: Vetores de Ameaça e Mitigações

| ID Ameaça | Vetor de Ataque / Risco Operacional | Impacto Potencial | Mitigação Implementada (Guardrail) |
| :---: | :--- | :--- | :--- |
| **T-01** | **Vazamento de Chaves em Logs ou Erros:** Mensagens de erro de SDK ou exceções de rede contendo `api_key` ou cabeçalhos de autorização expostos em logs, stdout ou JSON de erro. | Comprometimento de credenciais corporativas. | **M-01 — Redactor Compulsório & Scanner:** Função `redact_sensitive_text` sanitiza tokens conhecidos (`sk-...`, `gsk_...`, `AIza...`, Bearer); `scan_diff_for_secrets` é utilitário estático local que gera metadados com fingerprints criptográficos SHA-256, **sem expor fragmentos de texto puro**. |
| **T-02** | **Presunção Indevida de Gratuidade ("Conta sem Cartão"):** Operador ou sistema presume que uma conta sem cartão cadastrado tem autorização de consumo ou garantia de custo zero. | Cobrança inesperada pós-paga, bloqueio de conta ou passivo contratual. | **M-02 — Duplo Gate com Regra Anti-Presunção:** Gate 1 exige contrato formal de evidência (`FreeTierEvidence`) verificado; flag `no_credit_card_attached=True` sem evidência verificada rejeita categoricamente (`SecurityPolicyError`). |
| **T-03** | **SSRF e Egress para Endpoints Maliciosos/Internos:** Requisição direcionada para IP de loopback (`127.0.0.1`), metadata service (`169.254.169.254`), rede interna (`10.0.0.0/8`), URLs com credenciais (userinfo) ou portas não padrão. | Exfiltração de dados locais de host, credenciais de metadados de nuvem ou pivoteamento de rede. | **M-03 — Validador Estático de Egress:** Validação estritamente estática de URL/host: esquema exclusivamente HTTPS, bloqueio de userinfo, portas != 443, IPs numéricos e domínios fora da allowlist oficial. *(Nota: não realiza DNS/TLS/redirecionamentos em tempo real).* |
| **T-04** | **Incompatibilidade de Região / Jurisdição (Alibaba):** Envio de chave ou tráfego para `dashscope.aliyuncs.com` (site doméstico China) em vez do endpoint internacional em Cingapura (`ap-southeast-1`). | Faturamento em moeda diferente, desconformidade fiscal e falha de autorização. | **M-04 — Validação Estrita de Região (Sem Bypass):** Bloqueio incondicional do host doméstico `dashscope.aliyuncs.com` sem flag de bypass; aceitação exclusiva de `dashscope-intl.aliyuncs.com` ou subdomínios dedicados `ap-southeast-1`. |
| **T-05** | **Escalada Não Autorizada para Rota Paga (Fallback Pago):** Falha transitória (429/503) em modelo gratuito desencadeia redirecionamento silencioso para modelo tarifado pago. | Prejuízo financeiro e violação do consentimento do operador (ADR 0014). | **M-05 — Isolamento Econômico 0800 Estrito:** A Trilha 0800 proíbe categoricamente qualquer rota paga (`economic_tier="paid"`) ou custo estimado > R$ 0,00; eliminação de defaults de omissão do chamador; **zero fallback pago**. |
| **T-06** | **Bypass Malicioso de Quota via Rotação de Chaves:** Sistema rotaciona múltiplas chaves pertencentes à mesma organização/escopo para contornar limites de taxa (rate limits). | Violação dos termos de serviço do provedor, suspensão de organização e perda de controle. | **M-06 — Anti-Bypass de Quota com Hashing:** Detector armazena apenas hashes SHA-256 das chaves (sem chaves em texto puro); bloqueia rotação de chaves dentro do mesmo escopo compartilhado de quota, permitindo apenas escopos independentes comprovados. |
| **T-07** | **Injeção de Prompt / Escape de Fronteira em Entradas:** Cargas úteis em `task` ou `context` tentando sobrescrever instruções do roteador, injetar comandos ou extrair segredos. | Desvio de rota ou comportamento inseguro. | **M-07 — Integridade Unicode e Encapsulamento de Dados Inertes:** Validação de Unicode e rejeição de surrogates isolados (`0xD800–0xDFFF`); encapsulamento de entradas como payloads de dados inertes (`encapsulate_user_payload`). *(Nota: reconhecida a limitação de que validação Unicode não é defesa semântica completa contra prompt injection).* |
| **T-08** | **Repetição de Falha com Efeito Colateral Incerto:** Falha parcial de rede ou timeout após início de resposta sendo re-executada em outro provedor. | Consumo duplicado de quota, respostas concorrentes ou custos ocultos. | **M-08 — Fail-Closed em Estado Indeterminado:** Se `content_started=True` ou falha for desconhecida/incerta, a requisição é encerrada como `indeterminate`, sem retentativa. |

---

## 3. Especificação dos Guardrails Pós-Revisão R1

### 3.1. Contrato de Evidência e Gate 1 (R1-03)
- **`FreeTierEvidence`:** Contrato que formaliza a prova documental (`evidence_type`, `source_reference`, `account_or_project_id`, `is_verified`).
- **`Gate1OperatorApproval`:**
  - Requisitos: `provider_id`, `model_id`, `scope`, `evidence: FreeTierEvidence`, `operator_approved=True`.
  - Invariante de escopo: o escopo da aprovação deve corresponder exatamente ao escopo da evidência.
  - Invariante anti-presunção: `no_credit_card_attached=True` sem evidência válida e verificada resulta em `SecurityPolicyError`.

### 3.2. Gate 2 e Isolamento Econômico 0800 (R1-02, R1-07)
- **`Gate2ExecutionConsent`:**
  - Requisitos: `risk_acknowledged=True`, `allowed_route_ids`.
  - Remoção completa de parâmetros que permitiam tolerância a fallback pago ou teto monetário nesta trilha (ADR 0014: **zero fallback pago**).
  - Método `validate_for_route(route_id, *, economic_tier, estimated_cost)`: **sem defaults**. O chamador deve informar explicitamente a classificação econômica e o custo estimado; qualquer valor diferente de `"free"` / `"free_tier"` / `"0800"` ou custo diferente de `Decimal("0")` resulta em `SecurityPolicyError`.
  - **Revogação (`revoke()`):** Invalida o consentimento em memória. Atua como barreira pré-execução: qualquer tentativa ou retry subsequente é rejeitado imediatamente com `ConsentRevokedError`. *(Limitação declarada: não cancela conexões de socket de rede que já tenham sido transmitidas).*

### 3.3. Vinculação Estrita de Escopo (R1-03)
- **`validate_route_dual_gate(route, gate1, consent)`:**
  - Valida conformidade econômica no Gate 2.
  - Valida qualificação no Gate 1.
  - Verifica correspondência exata entre a rota candidata e a aprovação de laboratório:
    - `route.provider_id == gate1.provider_id`
    - `route.model_id == gate1.model_id`
    - `route.scope == gate1.scope`
  - Qualquer divergência dispara `ScopeMismatchError`.

### 3.4. Validação Estática de Egress e SSRF (R1-04)
- Validação estritamente estática:
  1. Esquema: **exclusivamente `https`**.
  2. Proibição de credenciais em URLs (`userinfo` / `@`).
  3. Rejeição de IPs literais (IPv4, IPv6, loopback, link-local metadata `169.254.169.254`, RFC1918, formatos octais/hexadecimais).
  4. Rejeição de domínios locais (`localhost`, `.local`, `.internal`, `.corp`, etc.).
  5. Portas: rejeição de portas malformadas e de qualquer porta diferente de 443.
  6. **Alibaba:** Rejeição incondicional de `dashscope.aliyuncs.com` (sem parâmetro de escape ou bypass). Allowlist restrita a `dashscope-intl.aliyuncs.com` e `*.ap-southeast-1.maas.aliyuncs.com`.
  7. Allowlist canônica de OpenAI (`api.openai.com`), Groq (`api.groq.com`) e Google Gemini (`generativelanguage.googleapis.com`).

### 3.5. Scanner e Anti-Rotação de Quota (R1-05)
- **Scanner:** `SecretFinding` armazena apenas `secret_type`, `line_number`, `fingerprint` (SHA-256) e `match_length`. Não armazena nem expõe fragmentos de credenciais em texto puro.
- **Anti-Quota-Bypass:** `QuotaBypassDetector` armazena exclusivamente hashes SHA-256 das chaves por `(provider_id, quota_scope)`. Rejeita rotação de chaves sob o mesmo escopo compartilhado após falhas de quota, permitindo rotas comprovadamente independentes (`is_independent_scope=True`).

### 3.6. Defesa de Entrada e Limitação Declarada (R1-06)
- Função `validate_unicode_input_safety`: verifica conformidade Unicode, tipos e rejeita surrogates isolados (`0xD800–0xDFFF`).
- Função `encapsulate_user_payload`: empacota a entrada como payload de dados inerte (`{"role": "user", "content": ..., "is_inert_data": True}`), prevenindo confusão de fronteira com instruções de controle do sistema.
- **Limitação declarada:** A higienização Unicode não é defesa semântica completa contra ataques de injeção de prompt; a separação estrutural de fronteiras é a mitigação do sistema.

### 3.7. Executor Fake Determinístico (R1-01)
- **`DeterministicOffline0800Executor`:**
  - Demonstra em ambiente de testes offline que nenhuma tentativa é despachada sem autorização válida de Gate 1 e Gate 2.
  - Revalida o consentimento antes de cada tentativa de fallback.
  - Interrompe a execução com estado `blocked` caso o consentimento seja revogado antes de um retry.

---

## 4. RUC/1.0 — Relatório Unificado de Conformidade

### 4.1. Identificação
- **Missão:** MAESTRO-0800 AGY-09 [P0] — Correção R1 · [Issue #62](https://github.com/hallanbrito/maestro-router/issues/62) · [PR #69](https://github.com/hallanbrito/maestro-router/pull/69).
- **Executor:** AGY (Antigravity).
- **Baseline:** `master@31a2f1c0db505a70359fac6a9ccf80804f5f7dd3`.
- **Branch:** `feat/maestro-0800-agy-09-seguranca-0800`.
- **Regime:** Testes 100% offline, zero chamadas externas de rede, custo R$ 0,00.

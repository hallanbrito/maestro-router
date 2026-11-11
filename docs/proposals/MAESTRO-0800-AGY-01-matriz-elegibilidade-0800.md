# MAESTRO-0800-AGY-01 — Matriz de Elegibilidade 0800, Alibaba Free Quota Only e Escopos

> **Status:** PROPOSTA CH-1 DOCUMENTAL / NÃO NORMATIVA / SEM IMPLEMENTAÇÃO DE RUNTIME  
> **Data:** 11/11/2026 · **Origem:** [Issue #54](https://github.com/hallanbrito/maestro-router/issues/54) · **Épico:** [Issue #52](https://github.com/hallanbrito/maestro-router/issues/52)  
> **Baseline conferida:** `master@31a2f1c0db505a70359fac6a9ccf80804f5f7dd3`  
> **Branch de trabalho:** `docs/maestro-0800-agy-01-elegibilidade-0800`  
> **Limite de autorização:** entrega estritamente documental. Não realiza chamadas externas a modelos, não provisiona credenciais, não altera o runtime em `src/`, não modifica contratos públicos da v1 (`docs/05-API.md`) e não autoriza merge, release ou deploy.

---

## 1. Resumo Executivo e Contexto

A [ADR 0014](../decisions/0014-three-routing-tracks-policy.md) estabelece como política mandatória para a **Trilha 0800 / Free** o uso exclusivo de rotas com **evidência suficiente de não gerar cobrança adicional** para a conta, projeto ou credencial em uso. Na ausência de prova técnica ou capacidade verificável, a regra é a recusa estrita antes do envio (*fail-closed*).

A proposta documental anterior [MAESTRO-FREE-01](MAESTRO-FREE-01-eligibilidade-0800.md) definiu o vocabulário e o contrato conceitual de prova de gratuidade. A presente entrega (**AGY-01**) consolida a parametrização factual dos três provedores autorizados para a Operação MAESTRO-0800:
1. **Alibaba Cloud Model Studio:** verificação da conta promocional de 90 dias, ativação da salvaguarda nativa **Free Quota Only** e tratamento do erro `403 AllocationQuota.FreeTierOnly`;
2. **Groq:** parametrização dos **10 modelos permitidos** na allowlist da organização do Product Owner (PO), separando Chat (3), Safety (3), ASR (2) e TTS (2), com seus respectivos tetos operacionais;
3. **Google Gemini Developer API:** enquadramento do adaptador existente na baseline sob confirmação de tier no console do Google AI Studio.

---

## 2. Checklist do Operador: Alibaba Cloud Model Studio (Singapore / International)

Para assegurar conformidade estrita com a ADR 0014 sem intervenção autônoma do agente em contas corporativas, o Product Owner (PO) deve executar o checklist abaixo no console do Alibaba Cloud antes de habilitar chamadas reais.

### 2.1. Parâmetros de Infraestrutura e Região
- [ ] **Região de Operação:** Selecionar **Singapore (`ap-southeast-1`)** no seletor de região do Model Studio.
- [ ] **Deployment Scope:** Confirmar o endpoint internacional (*International Site*). Base URL de compatibilidade OpenAI:
  - Global/Padrão: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
  - Workspace dedicado: `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`
- [ ] **Workspace & API Key:** Obter a `DASHSCOPE_API_KEY` vinculada exclusivamente ao Workspace configurado em Singapore. Nunca usar chaves vinculadas ao site doméstico da China (`dashscope.aliyuncs.com`), pois os esquemas de faturamento e regras de faturas diferem.

### 2.2. Verificação de Franquia Promocional (90 Dias por Modelo)
- [ ] **Painel de Quotas:** Acessar *Model Studio Console > User Center / Free Quota* (ou *Model Square*).
- [ ] **Data de Ativação:** Registrar a data em que o benefício do modelo foi acionado.
- [ ] **Prazo de Expiração:** Confirmar o limite de **90 dias** a partir da data de ativação individual de cada modelo. Modelos ativados em datas distintas expiram em momentos distintos.
- [ ] **Saldo Restante:** Verificar o saldo numérico de tokens disponíveis por modelo (ex: cota padrão de 1.000.000 tokens de teste).

### 2.3. Habilitação Obrigatória: Free Quota Only (Salvaguarda Antifaturamento)
A documentação oficial da Alibaba Cloud esclarece que a funcionalidade **Free Quota Only** vem **desativada por padrão**. Quando desativada, o esgotamento do free tier transfere o consumo automaticamente para a modalidade pós-paga (*pay-as-you-go*), faturando a conta.

- [ ] **Ativação no Console:**
  1. No console do Model Studio, localizar a seção de configuração de cotas gratuitas (*Free Quota Settings*).
  2. Localizar os modelos Qwen pretendidos.
  3. Marcar a chave **Free Quota Only** para **ON (Habilitado)** para todos os modelos que farão parte do catálogo do Maestro.
- [ ] **Janela de Propagação:** Aguardar de 5 a 10 minutos após a ativação no console antes de qualquer requisição. A Alibaba Cloud alerta que a propagação da flag nos clusters de inferência não é instantânea.
- [ ] **Comportamento em Esgotamento:** Confirmar documentalmente que, com Free Quota Only ativo, ao atingir saldo zero ou data de expiração, a API responderá com:
  - **Código HTTP:** `403 Forbidden`
  - **Código de Erro:** `AllocationQuota.FreeTierOnly`
  - **Efeito:** A requisição é interrompida no gateway da Alibaba sem gerar cobrança financeira.

### 2.4. Limites de Contas e Serviços Acessórios
- [ ] **Conta Primária vs RAM Users:** Confirmar que chaves criadas por RAM users consomem da cota compartilhada da conta primária.
- [ ] **Exclusão de Serviços Pagos:** O Maestro Router **não** deve acionar:
  - Model Fine-Tuning / Treinamento;
  - Batch Inference Jobs;
  - Model Studio Storage / File Uploads;
  - Plugins, Web Search integrada ou terceiros;
  - Modelos de terceiros hospedados no Model Studio (apenas Qwen oficial elegível).

---

## 3. Catálogo Groq: 10 Modelos Autorizados da Allowlist

Conforme determinação do PO em 11/11/2026, a organização Groq possui exatamente **10 modelos permitidos**. O modelo `allam-2-7b` (que figura na tabela pública de limites gerais da Groq) **NÃO** faz parte da allowlist autorizada da organização e está expressamente classificado como **INELEGÍVEL**.

### 3.1. Divisão por Modalidade e Tetos Operacionais da Organização

| # | Identificador do Modelo | Modalidade | Limite RPM | Limite RPD | Limite TPM | Limite TPD / Tempo |
| :-: | :--- | :--- | :-: | :-: | :-: | :-: |
| 1 | `openai/gpt-oss-120b` | Chat Geral | 30 | 1.000 | 8.000 | 200.000 tokens |
| 2 | `openai/gpt-oss-20b` | Chat Geral | 30 | 1.000 | 8.000 | 200.000 tokens |
| 3 | `qwen/qwen3.8-27b` | Chat Geral | 30 | 1.000 | 8.000 | 200.000 tokens |
| 4 | `meta-llama/llama-prompt-guard-2-22m` | Moderação / Guard | 30 | 14.400 | 15.000 | 500.000 tokens |
| 5 | `meta-llama/llama-prompt-guard-2-86m` | Moderação / Guard | 30 | 14.400 | 15.000 | 500.000 tokens |
| 6 | `openai/gpt-oss-safeguard-20b` | Moderação / Guard | 3 | 1.000 | 2.000 | 200.000 tokens |
| 7 | `whisper-large-v3` | Áudio ASR (Transcrição) | 20 | 2.000 | — | 7.200 s/h · 28.800 s/d |
| 8 | `whisper-large-v3-turbo` | Áudio ASR (Transcrição) | 20 | 2.000 | — | 7.200 s/h · 28.800 s/d |
| 9 | `canopylabs/orpheus-arabic-saudi` | Áudio TTS (Síntese) | 10 | 100 | 1.200 | 3.600 tokens |
| 10 | `canopylabs/orpheus-v1-english` | Áudio TTS (Síntese) | 10 | 100 | 1.200 | 3.600 tokens |

### 3.2. Regras de Engenharia de Escopo e Invariantes da Groq
1. **Compartilhamento de Cota de Organização:**
   - Na PR #51, a classe `SlidingQuota` utilizou escopos isolados (`groq-org-20b` e `groq-org-120b`). **Isso constitui risco de vazamento de quota.**
   - O motor de cotas do Maestro deve tratar o limite organizacional como agregado hierárquico: se a organização Groq atingir o teto de RPM da conta, **todos** os modelos de chat da Groq devem ser retidos localmente.
2. **Heterogeneidade de Unidades:**
   - Chat e Safety utilizam `tokens_per_minute` (TPM) e `tokens_per_day` (TPD).
   - ASR (Whisper) utiliza **segundos de áudio processados** (`seconds_per_hour` e `seconds_per_day`).
   - O motor de reservas não pode converter segundos em tokens por heurística arbitrária.
3. **Advertência Econômica (ADR 0014):**
   - A ausência de cartão cadastrado na Groq previne cobrança imediata em faturas bancárias, mas a alteração de plano ou inserção futura de dados de faturamento na organização pode ativar *pay-as-you-go*. A trilha 0800 deve rastrear os limites informados como tetos intransponíveis.

---

## 4. Google Gemini Developer API: Situação do Terceiro Provedor

O Maestro Router já possui um adaptador homologado em sua baseline para a Google Gemini Interactions API ([`GoogleGeminiInteractionsAdapter`](../../src/maestro_router/adapters/google.py)), implementado de forma sem estado (`store=False`, `automatic_continuation=False`).

### 4.1. Condição Atual de Elegibilidade
- **Classificação:** `PENDENTE DE VERIFICAÇÃO LOCAL`.
- **Fato Observado:** A documentação pública do Google Gemini Developer API descreve uma modalidade gratuita (*Free Tier*) com limites por projeto (ex: 15 RPM, 1.000.000 TPM, 1.500 RPD para a família Flash).
- **Fato Não Observado / Risco:** O Maestro não conhece o projeto associado à `GEMINI_API_KEY` do operador. Se o projeto do Google Cloud tiver uma conta de faturamento (*Billing Account*) associada e o *Pay-as-you-go* estiver habilitado, exceder o Free Tier ou utilizar modelos específicos pode gerar débito imediato na fatura do Google Cloud.
- **Checklist para o PO:**
  - [ ] Acessar o Google AI Studio (*Get API key*).
  - [ ] Verificar se o projeto está configurado como **Free Tier** (onde dados podem ser usados para treinamento do modelo e há limites rígidos de taxa) ou se está vinculado ao faturamento do Google Cloud.
  - [ ] Registrar o ID do modelo pretendido (ex: `gemini-2.5-flash` ou `gemini-1.5-flash`).

---

## 5. Matriz Geral de Elegibilidade 0800

| Provedor / Origem | Modelo ID Exato | Modalidade / Método | Escopo / Região | Limites Operacionais Declarados | Mecanismo de Garantia 0800 | Estado de Elegibilidade | Fonte Oficial & Referência |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **Alibaba Model Studio** | Catálogo Qwen elegível na conta (ex: Qwen 2.5) | Chat / `POST .../chat/completions` | Singapore (`ap-southeast-1`) / Workspace | Saldo da conta promocional (ex: 1M tokens) | `Free Quota Only: ON` -> `403 AllocationQuota.FreeTierOnly` | `EVIDENCIA_VERIFICADA` (Documental) / `PENDENTE` (Console PO) | [Alibaba Help Free Quota](https://www.alibabacloud.com/help/en/model-studio/new-free-quota) · 11/11/2026 |
| **Groq** | `openai/gpt-oss-120b` | Chat Geral / `POST /openai/v1/chat/completions` | Organização PO | 30 RPM · 1k RPD · 8k TPM · 200k TPD | Limite local estrito de organização + Free Tier Groq | `EVIDENCIA_VERIFICADA` (Allowlist PO) | [Groq Rate Limits](https://console.groq.com/docs/rate-limits) · 11/11/2026 |
| **Groq** | `openai/gpt-oss-20b` | Chat Geral / `POST /openai/v1/chat/completions` | Organização PO | 30 RPM · 1k RPD · 8k TPM · 200k TPD | Limite local estrito de organização + Free Tier Groq | `EVIDENCIA_VERIFICADA` (Allowlist PO) | [Groq Rate Limits](https://console.groq.com/docs/rate-limits) · 11/11/2026 |
| **Groq** | `qwen/qwen3.8-27b` | Chat Geral / `POST /openai/v1/chat/completions` | Organização PO | 30 RPM · 1k RPD · 8k TPM · 200k TPD | Limite local estrito de organização + Free Tier Groq | `EVIDENCIA_VERIFICADA` (Allowlist PO) | [Groq Rate Limits](https://console.groq.com/docs/rate-limits) · 11/11/2026 |
| **Groq** | `meta-llama/llama-prompt-guard-2-22m` | Moderação / `POST /openai/v1/chat/completions` | Organização PO | 30 RPM · 14.4k RPD · 15k TPM · 500k TPD | Limite local estrito de organização + Free Tier Groq | `EVIDENCIA_VERIFICADA` (Allowlist PO) | [Groq Rate Limits](https://console.groq.com/docs/rate-limits) · 11/11/2026 |
| **Groq** | `meta-llama/llama-prompt-guard-2-86m` | Moderação / `POST /openai/v1/chat/completions` | Organização PO | 30 RPM · 14.4k RPD · 15k TPM · 500k TPD | Limite local estrito de organização + Free Tier Groq | `EVIDENCIA_VERIFICADA` (Allowlist PO) | [Groq Rate Limits](https://console.groq.com/docs/rate-limits) · 11/11/2026 |
| **Groq** | `openai/gpt-oss-safeguard-20b` | Moderação / `POST /openai/v1/chat/completions` | Organização PO | 3 RPM · 1k RPD · 2k TPM · 200k TPD | Limite local estrito de organização + Free Tier Groq | `EVIDENCIA_VERIFICADA` (Allowlist PO) | [Groq Rate Limits](https://console.groq.com/docs/rate-limits) · 11/11/2026 |
| **Groq** | `whisper-large-v3` | ASR / `POST /openai/v1/audio/transcriptions` | Organização PO | 20 RPM · 2k RPD · 7.2k s/h · 28.8k s/d | Limite local de áudio + Free Tier Groq | `EVIDENCIA_VERIFICADA` (Allowlist PO) | [Groq Speech-to-Text](https://console.groq.com/docs/speech-to-text) · 11/11/2026 |
| **Groq** | `whisper-large-v3-turbo` | ASR / `POST /openai/v1/audio/transcriptions` | Organização PO | 20 RPM · 2k RPD · 7.2k s/h · 28.8k s/d | Limite local de áudio + Free Tier Groq | `EVIDENCIA_VERIFICADA` (Allowlist PO) | [Groq Speech-to-Text](https://console.groq.com/docs/speech-to-text) · 11/11/2026 |
| **Groq** | `canopylabs/orpheus-arabic-saudi` | TTS / `POST /openai/v1/audio/speech` | Organização PO | 10 RPM · 100 RPD · 1.2k TPM · 3.6k TPD | Limite local de síntese + Free Tier Groq | `EVIDENCIA_VERIFICADA` (Allowlist PO) | [Groq Text-to-Speech](https://console.groq.com/docs/text-to-speech) · 11/11/2026 |
| **Groq** | `canopylabs/orpheus-v1-english` | TTS / `POST /openai/v1/audio/speech` | Organização PO | 10 RPM · 100 RPD · 1.2k TPM · 3.6k TPD | Limite local de síntese + Free Tier Groq | `EVIDENCIA_VERIFICADA` (Allowlist PO) | [Groq Text-to-Speech](https://console.groq.com/docs/text-to-speech) · 11/11/2026 |
| **Groq** | `allam-2-7b` | Chat Geral | Fora da Allowlist PO | — | Rota NÃO autorizada na organização | `INELEGÍVEL` | Despacho PO Épico #52 · 11/11/2026 |
| **Google Gemini** | `gemini-2.5-flash` (ou equivalente) | Interactions / `interactions.create` | Google Cloud Project | 15 RPM · 1.000.000 TPM · 1.500 RPD | Free Tier Developer API sem faturamento ativo | `PENDENTE` (Console PO) | [Google Gemini Pricing](https://ai.google.dev/gemini-api/docs/pricing) · 11/11/2026 |

---

## 6. RUC/1.0 — Relatório Unificado de Conformidade

### 6.1. Identificação
- **Missão:** MAESTRO-0800 AGY-01 · [Issue #54](https://github.com/hallanbrito/maestro-router/issues/54).
- **Executor:** AGY (Antigravity).
- **Revisão Externa:** ChatGPT / Codex.
- **Ambiente:** Worktree git isolado; `LIVE_GITHUB` + `LOCAL_REPO`.
- **Baseline:** `master@31a2f1c0db505a70359fac6a9ccf80804f5f7dd3`.
- **Branch:** `docs/maestro-0800-agy-01-elegibilidade-0800`.
- **Data:** 11/11/2026.

### 6.2. Evidências Verificáveis
| ID | Classe e Fonte | Fato Observado / Limite |
| :---: | :--- | :--- |
| **E01** | `OBSERVADO` · [Documentação Oficial Alibaba Cloud](https://www.alibabacloud.com/help/en/model-studio/new-free-quota) | "Free Quota Only" desabilitado por padrão; ao esgotar cota com a flag ativa, retorna `403 AllocationQuota.FreeTierOnly` sem cobrar. |
| **E02** | `OBSERVADO` · [Alibaba Error Codes](https://www.alibabacloud.com/help/en/model-studio/error-code) | Especificação técnica de erro 403 e tratamento de quotas. |
| **E03** | `DECLARADO` · Despacho do PO na [Issue #55](https://github.com/hallanbrito/maestro-router/issues/55) e [Issue #52](https://github.com/hallanbrito/maestro-router/issues/52) | Allowlist de 10 modelos da organização Groq com limites exatos em RPM, RPD, TPM, TPD e segundos; exclusão expressa de `allam-2-7b`. |
| **E04** | `OBSERVADO` · Código da Baseline [`src/maestro_router/adapters/google.py`](../../src/maestro_router/adapters/google.py) | Adaptador Gemini sem estado existente; dependência de verificação do tier no Google AI Studio. |
| **E05** | `OBSERVADO` · Execução de Testes Locais | `PYTHONPATH=. pytest -q` executado na baseline: **765 passed**, 50 warnings, 0 falhas. |
| **E06** | `OBSERVADO` · Invocação de Provedores | Zero chamadas a APIs externas realizadas; custo adicional R$ 0,00. |

### 6.3. Conclusão e Próximo Passo
A documentação comprova os requisitos de elegibilidade e salvaguarda antifaturamento, fornecendo ao PO o checklist operacional sem exigir ou registrar segredos.

Com a entrega desta proposta documental e abertura de PR Draft:
👉 **Próxima tarefa recomendada na esteira:** **AGY-02 — [Issue #55](https://github.com/hallanbrito/maestro-router/issues/55):** *Catálogo Groq — 10 modelos da allowlist com capacidades e limites*.

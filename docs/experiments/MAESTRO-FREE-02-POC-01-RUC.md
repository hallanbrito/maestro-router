# MAESTRO-FREE-02-POC-01 — Experimento offline de fallback (RUC/1.0)

**Estado:** PROVA DE CONCEITO ISOLADA / CH-2 / SEM INTEGRAÇÃO DE RUNTIME / AGUARDANDO_AUDITORIA_CHATGPT E PO  
**Data:** 05/11/2026 · **Issue:** [#44](https://github.com/hallanbrito/maestro-router/issues/44) · **Proposta documental de origem:** [#43](https://github.com/hallanbrito/maestro-router/pull/43)  
**Branch:** `ch/maestro-free02-poc01` · **Baseline `master`:** `18668ebc32b2520bf69c17852e28743617e97703`  
**Executor:** ChatGPT, em tarefa separada da esteira AGY/CHDevFlow #54.

## 1. Objetivo

Demonstrar, sem APIs externas, que uma rota simulada **A** pode falhar por limite (sinal abstrato equivalente a HTTP 429) e a rota **B** continuar a operação com as mesmas mensagens observáveis, **somente** se permanecer dentro das permissões, orçamento estimado, requisitos técnicos, tempo total e quantidade de tentativas.

A POC **não implementa** o Maestro Free em produção, não modifica `POST /v1/executions` e não afirma prova de gratuidade real. A trilha 0800 preferencial deve informar que a cobrança depende do provedor; ciência de risco e autorização financeira são decisões distintas.

## 2. Arquivos e isolamento

| Caminho | Finalidade |
| --- | --- |
| `experiments/free02_offline_poc.py` | Orquestrador simples e inteiramente local com `FakeAdapter`, rotas sintéticas, consentimento reavaliado a cada tentativa e RUC/ledger em memória |
| `tests/test_free02_offline_poc.py` | Testes com resultados sintéticos; cenários F02-01 a F02-18 + seis limites complementares |
| `docs/experiments/MAESTRO-FREE-02-POC-01-RUC.md` | Este registro, documentação de comportamento e limitações |

**Restrições técnicas:** só biblioteca-padrão Python no código de POC; `pytest` já é dependência de desenvolvimento do repositório. Os adaptadores não fazem rede, não recebem chaves, não escrevem dados nem importam as integrações reais.

## 3. Executar localmente

Na raiz do repositório:

```bash
python -m pytest -q tests/test_free02_offline_poc.py
```

O código de produção não importa `experiments/` nem é alterado por esta PR. O `pytest` padrão do CI inclui os testes adicionados por residirem em `tests/`.

## 4. Contratos sintéticos

- `Message`: mensagem observável com `role` e `content`; histórico imutável transferido à outra rota sem conversão nem geração de memória oculta.
- `Route`: id, oferta `free_declared` ou `paid_known`, custo *estimado* decimal, capacidades e habilitação. A oferta declarada **não comprova a fatura**.
- `Consent`: ciência do risco, lista de rotas permitidas, opt-in financeiro separado, teto **estimado** e cancelamento.
- `FakeAdapter`: apenas captura mensagens sintéticas em memória e devolve sucesso ou `FakeFailure` predefinido.
- `Attempt`/`Result`: registro de rota e resultado de cada tentativa, teto estimado acumulado, `billing_actual="UNKNOWN"`.

**Invariantes testadas:** `max_attempts` de até 2, rota nunca repetida, no máximo uma resposta final, rechecagem de consentimento antes do fallback, orçamento estimado acumulado, allowlist e capacidades preservadas. Falha após conteúdo parcial, resultado incerto ou possível efeito externo encerra em `indeterminate` sem retry. Erros de autenticação não iniciam fallback. Após a correção R1, o limite temporal é checado antes da tentativa e após o retorno bem-sucedido do adaptador; não há cancelamento preemptivo de chamada em curso nesta POC.

## 5. Resultados dos testes

**Teste local isolado executado em 05/11/2026:** `python -m pytest -q tests/test_free02_offline_poc.py` → **24 passed**. Também executado `python -m compileall -q experiments tests` → **PASS**. Estes resultados aplicam-se aos arquivos da POC preparados para esta PR e não à suíte integral do repositório.

| Casos | Resultado esperado, verificado localmente |
| --- | --- |
| F02-01 e F02-02 | A completa em uma tentativa; ou falha rate-limit e B completa em duas |
| F02-03..F02-06 | Allowlist, consentimento financeiro e teto impedem fallback indevido |
| F02-07..F02-08 | Conteúdo parcial ou resposta indeterminada não dispara replay |
| F02-09..F02-10 | B recebe exatamente o mesmo histórico explícito de A, sem memória oculta |
| F02-11..F02-15 | Cancelamento, exaustão, autenticação, revogação e possíveis efeitos externos interrompem fluxo |
| F02-16..F02-18 | Fatura real permanece `UNKNOWN`; capacidade inadequada bloqueia; opt-in financeiro com teto permite simulação paga |
| Complementares (6) | Falta de ciência do risco, uma única tentativa, timeout antes de chamada, ID repetido, estimativa positiva declarada gratuita e teto infinito são recusados |

**CI do novo HEAD:** consultar e registrar no comentário da Draft PR após publicação. Este arquivo **não presume PASS antecipado**.

## 6. Limites e riscos

- Não há chamadas de rede, API, geração de tokens reais, sessão persistida, HTTP/stream real ou ferramenta com efeito externo.
- O experimento **não reutiliza automaticamente** o router canônico, nem comprova compatibilidade de request/response com a API pública v1. A integração real exigiria contrato e auditoria próprios.
- `FakeFailure("rate_limit")` representa o efeito de um 429, **não** um cliente HTTP.
- Custos são valores **fictícios e estimados**. Nem `0` estimado nem sucesso da POC garantem cobrança real zero.
- O orçamento da POC calcula apenas a soma de estimativas das tentativas iniciadas; a cobrança externa de tentativas incompletas pode ser desconhecida.
- O timeout impede o início de novas chamadas após o prazo e, na correção R1, impede classificar como sucesso uma resposta tardia. Não interrompe um adapter já rodando. Retries com efeito externo são proibidos; proteção real demanda protocolo de idempotência verificável.
- Não existe consentimento persistido, política de retenção ou controles de dados pessoais de produção nesta etapa.
- O RUC de código e testes foi elaborado pelo mesmo executor da POC: **exige revisão independente** antes de qualquer autorização de integração.

## 7. RUC/1.0 — Evidências e deliberação

| Campo | Registro |
| --- | --- |
| Identificação | MAESTRO-FREE-02-POC-01, Issue #44, CH-2 |
| Missão autorizada | POC local com dois provedores mockados, fallback em limite, histórico, permissão e testes offline |
| Baseline | `master@18668ebc32b2520bf69c17852e28743617e97703` |
| Teste executado | `python -m pytest -q tests/test_free02_offline_poc.py`: 24 PASS; `compileall`: PASS |
| Verificação remota | CI e SHA final a registrar no comentário da PR após leitura real |
| Custo adicional de modelos | R$ 0: nenhuma chamada externa de modelo |
| Arquivos | Dois arquivos Python isolados e este Markdown |
| Exclusões | Sem modificações de runtime/API v1/ADR 0014/FREE-01/PR #43/AGY/Project |
| Limitações | Apenas mocks, sem prova de faturamento, quotas reais ou continuidade do pensamento interno |
| Estado | `AGUARDANDO_AUDITORIA_CHATGPT / AGUARDANDO_PO / SEM_MERGE` |

**Próximo gate:** revisão independente dos arquivos e da CI no HEAD exato; PO decide se a POC pode ser integrada como experimento. Não autoriza provedor real, fallback produtivo, merge, deploy nem nova missão automaticamente.

## RUC/1.0 — Correção R1 da Issue #46 (05/11/2026)

### 1. Identificação

Missão `MAESTRO-FREE-02-POC-01-R1`, executor Codex, autonomia CH-2 autorizada pelo PO na [Issue #46](https://github.com/hallanbrito/maestro-router/issues/46). Fonte: repositório local e PR #45 consultada no GitHub. Branch `ch/maestro-free02-poc01`; HEAD inicial auditado `f3d638f2d86d52f8ff8bd6478e60223e777fbffa`; base `master@18668ebc32b2520bf69c17852e28743617e97703`. Commit de código e testes: `e58983d94eb9e6865de50c95615ccd69e5372688`. O SHA do commit que contém este próprio registro não pode constar literalmente nele sem alterar o SHA; o HEAD final e a CI correspondente serão registrados nos comentários da PR #45 e da Issue #46 após a publicação.

### 2. Resumo executivo

Quatro achados da auditoria foram reproduzidos no HEAD inicial e corrigidos somente na POC. Resposta após o prazo e exceção inesperada terminam em `indeterminate`, com tentativa registrada, sem resposta entregue nem fallback. Timeout não finito/não positivo e ID de rota inválido são rejeitados. A PR permanece Draft e a decisão do PO continua pendente.

### 3. Consultas e atividades realizadas

- Conferidos branch, HEAD, árvore limpa, PR aberta em Draft e base `master`; criado worktree isolado para preservar o checkout existente.
- Adicionados quatro testes adversariais (dez casos parametrizados) e executados antes da correção: **6 falhas e 28 sucessos**. As falhas cobriram prazo tardio, exceção `RuntimeError`, `NaN`/`Infinity`, ID numérico e ID branco; zero, negativo e ID vazio já eram rejeitados.
- Aplicadas apenas as quatro correções autorizadas em `experiments/free02_offline_poc.py`, com os testes correspondentes em `tests/test_free02_offline_poc.py`.

### 4. Evidências verificáveis

| ID | Classe | Fonte | Fato e limite |
| --- | --- | --- | --- |
| E01 | OBSERVADO | HEAD inicial + `pytest` local | Os 24 testes originais passaram; os casos adversariais novos produziram 6 falhas antes da correção. |
| E02 | OBSERVADO | Commit `e58983d94eb9e6865de50c95615ccd69e5372688` | A checagem pós-retorno, a captura de `Exception`, a validação finita do timeout e a validação de ID estão no simulador isolado. |
| E03 | OBSERVADO | `pytest` local no worktree | Testes específicos: **34 passed**. Suíte backend completa: **765 passed, 50 warnings** de depreciação em bibliotecas de teste. |
| E04 | OBSERVADO | `git diff --check`, `compileall`, `master...HEAD` | Sem erro de whitespace ou sintaxe; somente os três arquivos autorizados compõem a PR. |

### 5. Verificações e resultados

| Critério | Resultado | Evidência |
| --- | --- | --- |
| Quatro reproduções falham antes e passam depois | PASSOU | E01, E03 |
| 24 testes anteriores preservados | PASSOU | E01, E03 |
| Exceção sanitizada com tentativa registrada, sem fallback | PASSOU | E02, E03 |
| Resposta tardia sem `completed` nem fallback | PASSOU | E02, E03 |
| Timeout inválido e ID inválido rejeitados | PASSOU | E02, E03 |
| Suíte backend completa offline | PASSOU | `python -m pytest -q`: 765 passed |
| CI do HEAD final publicado | NÃO_EXECUTADO | Aferir após push e registrar no GitHub. |

O processo padrão da suíte parou em 18% dentro do sandbox no `TestClient` com `MockTransport`; um teste isolado confirmou espera no portal assíncrono. A mesma suíte foi executada integralmente fora desse sandbox e passou em 9,28 s. Os testes usam fakes/transportes locais; não houve chamada a provedor real.

### 6. Riscos e bloqueios

O adaptador síncrono não é cancelado em curso. `indeterminate` conserva a incerteza sobre resposta tardia ou exceção; não afirma que não houve execução, custo ou efeito externo. A POC não prova cobrança, quota ou comportamento produtivo. A revisão do próprio executor não substitui auditoria independente.

### 7. Alterações realizadas

Somente `experiments/free02_offline_poc.py`, `tests/test_free02_offline_poc.py` e este RUC. Nenhuma dependência, runtime, API pública, ADR, PR #43, missão AGY #54, deploy ou merge foi alterado. Custo adicional de modelos: R$ 0, pois nenhuma API de modelo foi chamada.

### 8. Recomendação técnica

**PARCIAL até aferição da CI do HEAD final;** após essa verificação, encaminhar a PR Draft à auditoria ChatGPT. O resultado local cobre os quatro achados da Issue #46, sem homologar integração.

### 9. Decisão necessária do PO

**PENDENTE:** avaliar a auditoria independente e decidir o destino da PR #45. Estado de entrega: `AGUARDANDO_AUDITORIA_CHATGPT / AGUARDANDO_PO / SEM_MERGE`.

# MAESTRO-FREE-03 — Arquitetura proposta de integração do fallback ao runtime

> **Status:** PROPOSTA CH-1 / APENAS DOCUMENTAÇÃO / NÃO NORMATIVA / SEM IMPLEMENTAÇÃO
>
> **Data:** 05/11/2026 · **Origem:** [Issue #48](https://github.com/hallanbrito/maestro-router/issues/48) · **Baseline conferida:** `master@31a2f1c0db505a70359fac6a9ccf80804f5f7dd3`
>
> **Limite de autorização:** entrega arquitetural documental. Não modifica contratos, ADRs, runtime, Control Center, testes, pipelines ou credenciais. Não autoriza merge, release, deploy, chamada a provedores reais ou gastos adicionais.

## 1. Resumo de decisão e resultado esperado

**Problema:** o Maestro já seleciona uma rota elegível e a executa uma única vez. A [POC offline FREE-02](../experiments/MAESTRO-FREE-02-POC-01-RUC.md), integrada à `master` pela PR #45, demonstra fallback de A para B com adaptadores fake, mas não está conectada ao núcleo produtivo. A proposta [FREE-02-R1](MAESTRO-FREE-02-R1-roteamento-preferencial-fallback.md) define continuidade observável, guardas econômicas e limites conceituais.

**Proposta de arquitetura:** acrescentar, somente em futuro gate, um **Attempt Orchestrator** neutro entre decisão de elegibilidade e fronteira de despacho. Ele reavaliaria candidatos autorizados antes de cada tentativa e devolveria **um único resultado final**. O orquestrador **não** integra esta entrega, **não** pode usar os modelos reais por mera existência da POC e não modifica hoje a estratégia `lowest-estimated-cost`.

**Recomendação para primeira fatia futura (CH-2):** demonstrar um *integration seam* totalmente offline, usando `RouteCatalog`, `route_request` e dois `ExecutionAdapter` simulados, mantendo a v1 idêntica e sem ligar nada no `/admin/executions`. Só após evidência, revisão normativa e autorização separada considerar execução via Control Center local com opt-in real. Nunca ativar fallback global por padrão.

**Gate normativo crítico:** a [ADR 0014](../decisions/0014-three-routing-tracks-policy.md) estabelece que a Trilha Free deve **comprovar ausência de cobrança adicional**; a FREE-02-R1 propõe uma modalidade “0800 — Preferencialmente Gratuita”, com **risco de cobrança admitido**. São requisitos diferentes e potencialmente incompatíveis. **Nenhuma engenharia deve tratar a proposta nova como substituição tácita da norma vigente.** O PO precisará deliberar nome, regras, consentimentos e eventual revisão normativa antes de ativação.

## 2. Levantamento do código real — fronteiras verificadas

| Componente presente hoje | Fato observado na baseline | Consequência para integração |
| --- | --- | --- |
| [`contracts.py`](../../src/maestro_router/contracts.py) | `ExecutionRequest` fechado (`task`, `context`, `constraints`); `extra=forbid`; sucesso contém `result`, `decision` selecionada e `economics`; erros de execução 502/503/504 | Não adicionar `track`, `session_id`, `attempts`, `consent` ou novos códigos na v1 por inferência |
| [`api.py`](../../src/maestro_router/api.py) | `create_app` expõe `POST /v1/executions`; faz validação, snapshot de adaptadores, `route_request` e `_execute_selection` para uma rota | Não alterar a rota pública; qualquer plano de refatoração exige testes de contrato |
| [`routing.py`](../../src/maestro_router/routing.py) | `route_request` filtra configuração/capacidade/qualidade/allowlist/disponibilidade/custo e retorna seleção validada ou recusa; `_select_lowest_cost` escolhe um candidato com desempate por ID | Reutilizar filtros e validações; não implementar seleção alternativa paralela que os ignore |
| [`execution.py`](../../src/maestro_router/execution.py) | `TextExecutionRequest` contém tarefa + contexto opcional, `ExecutionAdapter.execute` é assíncrono, `TextExecutionResult` traz texto/uso/modelo; erros neutros são `ExecutionUnavailableError`, `ExecutionTimeoutError`, `ExecutionFailedError` | Preservar a porta neutra; resultado parcial/efeitos de chamada não são hoje metadados tipados suficientes para retry seguro |
| [`api.py::_execute_selection`](../../src/maestro_router/api.py) | Executa um adaptador e converte diretamente resultado/erro em `JSONResponse` e apresentação pública de uma rota | **Seam futuro:** separar execução neutra do mapeamento HTTP; não reutilizar `JSONResponse` como resultado de uma tentativa |
| [`bootstrap.py`](../../src/maestro_router/bootstrap.py) | Configura rotas/credenciais, compõe adaptador OpenAI e desabilita retries do SDK no bootstrap | Não habilitar retry oculto no SDK; injeção e política de adaptadores exigem gate |
| [`control_center.py`](../../src/maestro_router/control_center.py) | O `POST /admin/executions` usa trilhas e chama `route_request` + `_execute_selection`; a Free hoje filtra tarifa zero declarada. Há `/admin/preview` e sessão/CSRF locais | Eventual ativação administrativa só por opt-in explícito e nova revisão, sem contaminar a API v1 |
| [`economics.py`](../../src/maestro_router/economics.py) | Estimativa prévia e custo calculado pós-execução usam `Decimal` e referências do operador; custo calculado **não é faturamento real** | Preservar moeda, escopo e incerteza; não prometer cobrança zero com tarifa local zero |
| [`adapters/openai.py`](../../src/maestro_router/adapters/openai.py) e [`adapters/google.py`](../../src/maestro_router/adapters/google.py) | Traduzem várias classes de falha externa para erros neutros; o adaptador Google usa `store=False` na operação Interactions | Normalização atual é insuficiente para concluir com certeza se houve efeito remoto ou consumo antes da falha |
| [`experiments/free02_offline_poc.py`](../../experiments/free02_offline_poc.py) | `simulate` com fakes, até 2 tentativas, consentimento rechecado, teto estimado, deadline e estados `completed/blocked/indeterminate` | É **material de aprendizagem**, não plug-in pronto do runtime; seus modelos de entrada e adaptadores diferem dos contratos reais |

**Compatibilidade vigente:** [`docs/05-API.md`](../05-API.md), em especial seções 6, 12 e 13, não promete retry, fallback, sessões, idempotência nem histórico público de tentativas. [`docs/06-DECISAO-DE-ROTEAMENTO.md`](../06-DECISAO-DE-ROTEAMENTO.md) governa a seleção canônica e não a recuperação após erro externo. [ADR 0012](../decisions/0012-control-center-local-admin-layer.md) separa as trilhas administrativas da API v1. Nenhuma dessas fontes foi alterada nesta missão.

## 3. Ponto de extensão proposto — uma única fonte de elegibilidade

Fluxo **prospectivo**, não implementado:

```text
Cliente/controlador autorizado
  → validação estrita (v1 intacta / interface futura separada)
  → snapshot imutável: catálogo + adapters + restrições + consentimentos
  → verificação de autorização econômica e capacidade/contexto
  → seleção canônica validada (route_request)
  → [AttemptOrchestrator, futuro, desabilitado por padrão]
       ├─ AttemptLedger (somente metadados sanitizados)
       ├─ Deadline / orçamento ESTIMADO da operação inteira
       ├─ Dispatch por ExecutionAdapter neutro
       ├─ resultado completo → finalizar UMA resposta
       ├─ erro comprovadamente seguro antes de resposta/efeito
       │    → marcar rota tentada e reavaliar rotas restantes com
       │      as mesmas restrições + consentimento ainda válido
       └─ parcial, desconhecido, auth ou sem prova → PARAR
  → Presenter HTTP compatível (v1, quando fallback desativado)
```

### 3.1 Contratos internos candidatos, não APIs existentes

- `AttemptPolicySnapshot`: teto global de tentativas (candidato `2`), prazo total, rotas permitidas, capacidades, critérios de qualidade, regras monetárias, política comercial com versão, sinalizações de continuação e consentimento explícito. **Nunca derivar autorização financeira da presença de API key.**
- `ExecutionAttempt`: `execution_ref`, `attempt_index`, `route_id`, versão do snapshot, marca de início/fim e desfecho sanitizado; identificadores **não** constituem uma API pública aprovada nem persistência autorizada.
- `NeutralAttemptOutcome`: `complete`, `safe_to_reselect`, `indeterminate`, `blocked`, acompanhado de evidência sobre entrega parcial/efeito; não confundir 429 genérico com prova suficiente de replay seguro.
- `AttemptOrchestrator`: conduz uma **sequência** de escolhas canônicas; não possui SDK, credenciais nem formato HTTP.
- `ExecutionPresenter`: produz **uma** resposta ao cliente; sem modificar `ExecutionSuccessResponse` ou `ExecutionErrorResponse` públicos sem revisão de contrato.
- `ContextEnvelope`: mensagens efetivamente observáveis e autorizadas, checkpoint completo e referências de efeitos; nunca pensamento oculto, estado proprietário ou memória indisponível.

**Seam recomendado:** o novo orquestrador chamaria uma função neutra de despacho que retorna dado tipado, **não** a função atual `_execute_selection` que já materializa HTTP. A refatoração desse ponto precisa de testes reproduzindo integralmente as respostas v1 antes de qualquer ativação de fallback.

### 3.2 Reeleição sem falsear motivos

A API interna atual `route_request` não oferece um parâmetro semântico próprio para rotas **já tentadas**. Reutilizar `locally_invalid_route_ids` para isso falsearia a auditoria como configuração inválida. Uma futura fatia deve definir exclusões de tentativas separadas (ex.: `excluded_attempt_route_ids`, razão `already_attempted`) **somente mediante nova revisão**; preservar as regras de `OperationalConstraints`, allowlist, teto, moeda, capacidade e desempate. Não mutar o catálogo global, não trocar credenciais implicitamente e não transformar erro de um projeto em bloqueio de outro sem evidência do escopo da cota.

## 4. Invariantes e segurança econômica

1. **Uma operação, no máximo uma resposta final**; nunca fan-out, votação, comparação paralela, “melhor resposta” concorrente ou repetição infinita.
2. **Limites globais**: duas tentativas como ponto de partida da POC, uma tentativa por rota, deadline monotônico da operação inteira e cancelamento reavaliado antes de nova tentativa. Prazo vencido durante chamada retorna estado seguro e **não prova** que o provedor cancelou trabalho/faturamento.
3. **Consentimento revogável**: ciência de cobrança possível é distinta de autorização explícita de executar rota conhecida como paga; esta exige allowlist, teto estimado positivo, moeda coerente e escopo de conta/projeto. Se faltar qualquer elemento: fail-closed.
4. **Free estrita vs preferencial**: na Free governada pela ADR 0014, ausência de prova de gratuidade para conta/projeto/endpoint/quota implica **sem chamada**. A modalidade “preferencialmente gratuita” não pode se apropriar da mesma garantia nem ser habilitada sem decisão do PO para riscos/cobrança.
5. **Orçamento de tentativas**: estimativa `Decimal` acumulada **antes** de cada despacho, incluindo tentativas fracassadas iniciadas; dados indisponíveis, moedas distintas sem mecanismo aprovado ou uso desconhecido **não** devem ser tratados como zero nem permitidos por conversão monetária inventada. Teto estimado não é trava de fatura real.
6. **Snapshot consistente**: catálogo, associações `adapter_id`, qualidade, política, restrições e versão de consentimento formam um conjunto auditável. Revalidar permissão antes da segunda tentativa sem permitir ampliar o escopo originalmente aprovado.
7. **Credenciais e privacidade**: apenas o adaptador vê segredos, por origem autorizada; histórico não é log persistente implícito; telemetria limita-se a IDs opacos, status, estimativas e códigos sanitizados, sem conteúdo, chaves, prompt ou tokens secretos.
8. **Idempotência e efeitos**: nenhum fallback após resposta parcial, ferramenta de escrita, outcome ambíguo ou timeout cuja ausência de efeito não seja comprovada. Uma chave idempotente só é útil se o provedor ou a aplicação **realmente** garantirem deduplicação no escopo correto.
9. **Continuidade realista**: transferir exclusivamente mensagens textuais completas fornecidas/observadas e consentidas; verificar capacidade, limites de janela, formato de ferramentas e checkpoint. Sem resumo/truncamento automático, memória oculta ou `previous_interaction_id` implícito.
10. **Separação de camadas**: código normativo/v1 continua single-attempt até gate; o projeto não ganha acesso à API nem autorização de cobrança ao integrar esta documentação.

## 5. Matriz de falhas — comportamento futuro a validar

| Situação observável | Reeleger B? | Regra de estado/registro |
| --- | --- | --- |
| A retorna sucesso completo e verificado | **Não** | Encerrar `completed`, uma saída |
| A responde 429 antes de gerar conteúdo, com **prova de ausência de efeito** | **Candidato** | Rechecar consentimento, disponibilidade, limites e elegibilidade de B |
| A retorna indisponibilidade 5xx ou conexão perdida sem prova de ausência de efeito | **Não** | `indeterminate`, registrar tentativa; não usar status isolado como autorização |
| A termina após o deadline global | **Não** | `indeterminate`, nunca `completed`; não prometer cancelar chamada remota |
| A retornou conteúdo parcial, streaming, resultado de ferramenta ou side effect incerto | **Não** | `indeterminate`, sem replay ou entrega duplicada |
| A tem falha de autenticação/autorização 401/403 | **Não automaticamente** | Bloqueio sanitizado, sem circular credenciais |
| B não está na allowlist / é incompatível / não há contexto completo | **Não** | Recusa/estado bloqueado, razões verificáveis |
| B é paga sem opt-in separado ou sem teto comparável | **Não** | Nenhum fallback pago silencioso |
| Consentimento revogado, timeout, orçamento exaurido ou sem rota restante | **Não** | Terminar, sem nova chamada |
| Exceção inesperada de adaptador | **Não** | `indeterminate` sanitizado com ledger; não vazar stacktrace |
| Quota “zero” declarada, sem prova de tier/escopo de cobrança real | **Não** na Free estrita | Não confundir declaração local com elegibilidade comprovada |

**Lacuna operacional concreta:** os adaptadores atuais achatam erros externos em classes neutras suficientes para a v1 (por exemplo, `ExecutionUnavailableError`), mas **não fornecem sinal tipado confiável de ausência de efeito ou consumo**. Uma classificação com `safe_to_reselect` só poderá ser afirmada por contrato interno novo e prova por implementação/testes. Até lá, o fallback em cenário ambíguo deve permanecer bloqueado.

## 6. API e Control Center — alternativas e recomendação

| Opção | Vantagem | Limite / decisão |
| --- | --- | --- |
| **A — Experimento interno com adapters fake** (**recomendada primeiro**) | Aprende a integrar seleção e despacho sem rede nem alterar a v1 | Requer CH-2 separado; sem produção, UI ou permissões financeiras |
| **B — Opt-in exclusivo no Control Center local** (futuro) | Já existe `POST /admin/executions` protegido por sessão/CSRF e trilhas | Precisa revisar aderência ADR 0012/0014, comportamento da Free, consentimentos e contrato administrativo; **não** habilitar hoje |
| **C — Nova versão explícita de API** (futuro) | Permite sessão, attempts, idempotência e autorização com contrato próprio | Requer proposta de API v2, autenticação, privacidade, testes e aprovação PO; **não** adicionar campos à v1 |
| **D — Habilitar fallback silencioso no `POST /v1/executions` atual** | Alteração aparente menor | **Rejeitada**: ausência de opt-in verificável, semântica pública de seleção única e riscos de custo/idempotência |

**Escolha proposta para o próximo gate:** opção **A**, com registro de interface interna **somente em testes/offline**. A escolha entre Free estrita e “preferencialmente gratuita”, campos administrativos, semântica de custo, reeleição e eventuais mudanças normativas permanece **pendente do PO**. Não definir versão pública nova automaticamente.

## 7. Fases futuras sugeridas (NÃO autorizadas por este documento)

| Fase | Entrega mínima verificável | Portão |
| --- | --- | --- |
| **F03-A — Seam offline** | Prova de separação tipada `route_request` → execução neutra fake → presenter, sem rede; compatibilidade de respostas v1 quando desligado | Nova Issue CH-2, testes e revisão PO |
| **F03-B — Reeleição segura offline** | A 429 inequívoco → reavalia B sem mudar restrições; ledger, deadline, orçamento estimado e exceções | Nova autorização e auditabilidade de falhas |
| **F03-C — Política e consentimento** | Deliberar ADR 0014 × FREE-02, forma de aceite, fonte da elegibilidade e contrato administrativo/local ou versão de API | Gate normativo explícito PO |
| **F03-D — Adaptadores reais em ambiente controlado** | Só se houver prova de idempotência/efeito, limite econômico, privacidade, autorização da origem e testes específicos de cada provedor | Gate separado para chamadas externas, credenciais e custos |
| **F03-E — Release e UX** | Homologação funcional ponta-a-ponta, mensagens claras de risco e recusa, segurança, rollback e critérios operacionais | Gate de release/deploy separado |

### 7.1 Cenários mínimos de teste de uma futura F03-A/F03-B

- **T01:** modo legado off mantém `POST /v1/executions` com exatamente o mesmo schema, status e apenas um `ExecutionAdapter.execute`.
- **T02:** erro conhecido de A antes de conteúdo e com evidência de segurança permite reeleição de B elegível; histórico explícito preservado.
- **T03:** custo de A + B contabilizado no limite **estimado**, sem status de cobrança real fabricado.
- **T04:** sem prova de gratuidade na Free estrita → nenhum adaptador chamado.
- **T05:** falta de consentimento financeiro / B fora da allowlist → não chama B.
- **T06:** resultado parcial, possível escrita, timeout, indisponibilidade ambígua e exceção inesperada → sem fallback.
- **T07:** cancelar/revogar entre A e B → no máximo uma tentativa já iniciada; novo despacho vedado.
- **T08:** requisito/capacidade, moeda não comparável, indisponibilidade conhecida e motivo de rota previamente tentada geram exclusões distintas e explicáveis.
- **T09:** dois modelos não recebem memória interna/segredo; apenas mensagens observáveis autorizadas; janela incompatível bloqueia.
- **T10:** nenhuma alteração de configuração global, de ordenação canônica e de cálculo de `usage`/custo posterior.
- **T11:** ID, metadados e razões sanitizadas em ledger; não persistir payloads nem credenciais.
- **T12:** budget, deadline e máximo de tentativas aplicam-se globalmente, incluindo tentativas falhas.

**Testes automáticos atuais** (FREE-02) não comprovam T01–T12 na integração real; estes são **critérios propostos**, não resultados executados.

## 8. Riscos, dependências e decisões reservadas ao PO

| ID | Dependência/risco | Situação hoje | Decisão a tomar antes de código real |
| --- | --- | --- | --- |
| D01 | Conflito Free estrita × Free preferencial | **Aberto; duas direções diferentes nos documentos** | Definir produtos/trilhas, nome e autorização econômica; se cabível, propor revisão ADR e FREE-01 |
| D02 | Semântica de compatibilidade da API v1 | Fechada, uma resposta de uma rota | Preservar v1 ou especificar nova API; não alterar por inferência |
| D03 | Tipo seguro de erro e evidência de não-efeito | Ausente em `ExecutionAdapter` | Definir sinalização e provas, sem tratar qualquer 429 como automaticamente seguro |
| D04 | Origem de elegibilidade gratuita e quota | Não verificada pelo Maestro | Fail-closed sem atestado aplicável a conta/projeto/método/janela |
| D05 | Fonte e escopo de consentimento financeiro | Não existe no `ExecutionRequest` v1 | Aprovar opt-in específico e revogação, sem aceitar por padrão |
| D06 | Limites persistentes, ledger e dados pessoais | POC somente em memória | Decidir retenção/eliminação, segurança e observabilidade |
| D07 | Continuidade em sistemas de contexto diferentes | Somente mensagens explícitas na POC | Aprovar envelope/formatos, tamanho, truncamento e validação |
| D08 | Cancelamento e idempotência reais | Não há garantia pública | Aprovar modelos de erro sem replay inseguro |
| D09 | Ranking “prefer_free” e exclusões de tentativas | `lowest-estimated-cost` atual seleciona uma rota | Não alterar estratégia nem falsear exclusão como `invalid_route` |
| D10 | Custos agregados em erro | `economics` pública descreve uma rota | Aprovar apresentação e contabilidade conservadora sem violar v1 |

**Risco transversal:** uma POC limpa com fakes **não** prova compatibilidade com comportamento de provider, quota, billing, streaming, cancelamento ou idempotência. Sem demonstração técnica e gate explícito, não habilitar.

## 9. RUC/1.0 — Evidências e estado da missão FREE-03

| Campo | Registro |
| --- | --- |
| Missão | MAESTRO-FREE-03 · Issue #48 · CH-1 |
| Data e deadline solicitada | 05/11/2026 · antes de 17h20, America/Fortaleza |
| Baseline inspecionada | `master@31a2f1c0db505a70359fac6a9ccf80804f5f7dd3` |
| Fonte técnica | `api.py`, `contracts.py`, `execution.py`, `routing.py`, `bootstrap.py`, `control_center.py`, `economics.py`, `adapters/openai.py`, `adapters/google.py` |
| Fonte documental | API v1, decisão de roteamento, ADRs 0012/0014, FREE-01, FREE-02-R1 e RUC FREE-02 |
| Método | Leitura direta do HEAD e delimitação de pontos de extensão; comparação de semântica pública, consentimentos e riscos |
| Alterações permitidas | Somente este documento de proposta em nova Draft PR |
| Testes | Nenhum teste de runtime necessário/alegado por esta mudança exclusivamente documental; aferir CI da PR após publicar |
| Custo de modelos | R$ 0; nenhuma chamada de IA por provedor no runtime |
| Fora de escopo | Código, novas dependências, alterações normativas, UI, merge, release, deploy, credenciais, chamadas pagas |
| Decisão normativa | **Pendente**: conflito Free estrita × preferencialmente gratuita e requisitos de opt-in |
| Estado | `ARQUITETURA_CH1_DOCUMENTADA / AGUARDANDO_CI_E_AUDITORIA / AGUARDANDO_PO / SEM_MERGE` |

**Critério de saída:** aprovação documental em gate de revisão não é autorização de implementar, integrar ao runtime ou aceitar riscos financeiros. Nenhuma missão CH-2 é criada automaticamente por este texto.

---
*Documento de arquitetura proposta — descrição do sistema atual e direção futura claramente separadas; sujeito a auditoria e decisão do PO.*

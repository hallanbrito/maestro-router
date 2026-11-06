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
- `ContextEnvelope`: **DTO inteiramente interno e sintético à POC**, não campo público nem contrato implementado. Deve representar mensagens completas em ordem, seus papéis e proveniência, checkpoint completo verificável, escopo/versão de consentimento, referências a efeitos pendentes e requisitos de compatibilidade da rota B. Nunca transportar pensamento oculto, estado proprietário ou memória indisponível.

**Seam recomendado:** o novo orquestrador chamaria uma função neutra de despacho que retorna dado tipado, **não** a função atual `_execute_selection` que já materializa HTTP. A refatoração desse ponto precisa de testes reproduzindo integralmente as respostas v1 antes de qualquer ativação de fallback.

**Fronteira atual do histórico:** `ExecutionRequest` e `TextExecutionRequest` carregam somente `task` e `context: str | None`; não carregam mensagens com papéis, proveniência ou checkpoint. Na POC, fakes A e B devem receber um envelope sintético construído **fora** da v1. O teste deve registrar a entrada de A, o último checkpoint completo e a tradução recebida por B, comparando ordem, papéis, conteúdo e proveniência sem concatenar tudo em `context` e perder semântica. Cada adapter fake declara se representa esses elementos e a janela necessária; se não puder representar integralmente dados autorizados, se houver perda, janela incompatível, efeito pendente ou conteúdo sem consentimento para B, bloquear o despacho. Nenhum teste pode inferir transferência de memória oculta, estado proprietário ou sessão remota. O DTO real, seu formato e sua integração aos adapters exigem gate de implementação separado.

### 3.2 Reeleição sem falsear motivos

A API interna atual `route_request` não oferece um parâmetro semântico próprio para rotas **já tentadas**. Reutilizar `locally_invalid_route_ids` para isso falsearia a auditoria como configuração inválida. Uma futura fatia deve definir exclusões de tentativas separadas (ex.: `excluded_attempt_route_ids`, razão `already_attempted`) **somente mediante nova revisão**; preservar as regras de `OperationalConstraints`, allowlist, teto, moeda, capacidade e desempate. Não mutar o catálogo global, não trocar credenciais implicitamente e não transformar erro de um projeto em bloqueio de outro sem evidência do escopo da cota.

## 4. Invariantes e segurança econômica

1. **Uma operação, no máximo uma resposta final**; nunca fan-out, votação, comparação paralela, “melhor resposta” concorrente ou repetição infinita.
2. **Limites globais**: duas tentativas como ponto de partida da POC, uma tentativa por rota, deadline monotônico da operação inteira e cancelamento reavaliado antes de nova tentativa. Prazo vencido durante chamada retorna estado seguro e **não prova** que o provedor cancelou trabalho/faturamento.
3. **Consentimento revogável**: ciência de cobrança possível é distinta de autorização explícita de executar rota conhecida como paga; esta exige allowlist, teto estimado positivo, moeda coerente e escopo de conta/projeto. Se faltar qualquer elemento: fail-closed.
4. **Free estrita vs preferencial**: na Free governada pela ADR 0014, ausência de prova de gratuidade para conta/projeto/endpoint/quota implica **sem chamada**. A modalidade “preferencialmente gratuita” não pode se apropriar da mesma garantia nem ser habilitada sem decisão do PO para riscos/cobrança.
5. **Orçamento de tentativas**: estimativa `Decimal` acumulada **antes** de cada despacho, incluindo tentativas fracassadas iniciadas; dados indisponíveis, moedas distintas sem mecanismo aprovado ou uso desconhecido **não** devem ser tratados como zero nem permitidos por conversão monetária inventada. Teto estimado não é trava de fatura real.
6. **Snapshot consistente**: catálogo, associações `adapter_id`, qualidade, política, restrições e versão de consentimento formam um conjunto auditável. Revalidar permissão antes da segunda tentativa sem permitir ampliar o escopo originalmente aprovado. Revogação impede **tentativas futuras**; não desfaz despacho já iniciado. Um protocolo candidato de versão/lease de consentimento deve coordenar, de modo serializável, a revogação com a transição `AUTHORIZED -> DISPATCH_STARTED` no **limite exato do despacho** de B: uma pré-verificação isolada não basta. Se a revogação vencer antes dessa transição, B não inicia; se o despacho vencer, a tentativa já está iniciada e a revogação só impede novos despachos. Sem garantia dessa coordenação, falhar fechado e não iniciar B. Durante chamada *in-flight*, não alegar cancelamento remoto; se o resultado/efeito for indeterminado, registrar `indeterminate` e não repetir. O mecanismo concreto de sincronização exige gate próprio.
7. **Credenciais e privacidade**: apenas o adaptador vê segredos, por origem autorizada; histórico não é log persistente implícito; telemetria limita-se a IDs opacos, status, estimativas e códigos sanitizados, sem conteúdo, chaves, prompt ou tokens secretos.
8. **Idempotência e efeitos**: nenhum fallback após resposta parcial, ferramenta de escrita, outcome ambíguo ou timeout cuja ausência de efeito não seja comprovada. Uma chave idempotente só é útil se o provedor ou a aplicação **realmente** garantirem deduplicação no escopo correto.
9. **Continuidade realista**: transferir exclusivamente mensagens textuais completas fornecidas/observadas e consentidas; verificar capacidade, limites de janela, formato de ferramentas e checkpoint. Sem resumo/truncamento automático, memória oculta ou `previous_interaction_id` implícito.
10. **Separação de camadas**: código normativo/v1 continua single-attempt até gate; o projeto não ganha acesso à API nem autorização de cobrança ao integrar esta documentação.

**Custo e revogação:** uma tentativa já despachada pode consumir recursos mesmo se a autorização for revogada logo depois. Não há garantia de cancelamento remoto, de reversão de efeitos ou de faturamento zero. O ledger deve distinguir pré-verificação, `DISPATCH_STARTED`, chamada *in-flight* e resultado completo/indeterminado, sem expor payload.

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

- **T01:** com o orquestrador desabilitado, comparar antes/depois do seam o `POST /v1/executions` pela matriz abaixo, usando catálogo/adapters fake determinísticos, sem rede. Comparar status, `Content-Type: application/json`, envelope, códigos, campos condicionais e ausência de campos extras/`null`; preservar precedência mídia → JSON/schema → configuração → decisão → execução. Em cada caso contar despachos: zero para validação, configuração e recusa; exatamente um para sucesso ou erro após seleção. Não aceitar campos `attempts`, `session_id`, `consent` ou `track` na v1.
- **T02:** erro conhecido de A antes de conteúdo e com prova de não-efeito permite reeleição de B elegível; comparar em adapters fake o envelope sintético autorizado antes/depois da tradução, com papéis, ordem, proveniência e checkpoint completos. Perda ou incompatibilidade bloqueia B; nenhuma ampliação da v1.
- **T03:** custo de A + B contabilizado no limite **estimado**, sem status de cobrança real fabricado.
- **T04:** sem prova de gratuidade na Free estrita → nenhum adaptador chamado.
- **T05:** falta de consentimento financeiro / B fora da allowlist → não chama B.
- **T06:** resultado parcial, possível escrita, timeout, indisponibilidade ambígua e exceção inesperada → sem fallback.
- **T07:** corrida adversarial determinística: pausar B entre pré-verificação e transição `AUTHORIZED -> DISPATCH_STARTED`, revogar consentimento e liberar a barreira; provar zero chamadas a B. Inverter a ordem para provar que revogação após `DISPATCH_STARTED` não cancela nem desfaz a tentativa já enviada, mas impede a próxima; sem sincronização verificável, bloquear B.
- **T08:** requisito/capacidade, moeda não comparável, indisponibilidade conhecida e motivo de rota previamente tentada geram exclusões distintas e explicáveis.
- **T09:** dois adapters fake recebem somente mensagens sintéticas observáveis e autorizadas; nenhum recebe memória interna/segredo. Conferir papéis, ordem, proveniência, checkpoint e consentimento; janela incompatível, efeitos pendentes, conteúdo não autorizado ou tradução com perda bloqueiam B.
- **T10:** nenhuma alteração de configuração global, de ordenação canônica e de cálculo de `usage`/custo posterior. `sticky route` desabilitada na F03-A; eventual afinidade futura requer gate e testes que preservem `lowest-estimated-cost` e todas as restrições.
- **T11:** ID, metadados e razões sanitizadas em ledger; não persistir payloads nem credenciais.
- **T12:** budget, deadline e máximo de tentativas aplicam-se globalmente, incluindo tentativas falhas.

**Testes automáticos atuais** (FREE-02) não comprovam T01–T12 na integração real; estes são **critérios propostos**, não resultados executados.

#### Matriz proposta de compatibilidade v1 para T01 (antes/depois, não executada)

| Caso fake determinístico | HTTP e envelope idênticos antes/depois | Invariantes observáveis |
| --- | --- | --- |
| Sucesso | `200`; exatamente `result`, `decision`, `economics` | `result.content`; `decision.outcome=selected`, `decision.route` com `id/provider/model`, estratégia e razões; `economics.estimate/usage/calculated_cost` com estados e projeção de valores conforme dados fake; exatamente uma execução |
| JSON/schema inválidos | `400 INVALID_REQUEST`; somente `error` com `issues` | JSON malformado, UTF-8 inválido, nome de membro JSON duplicado, `null`, campo extra em qualquer nível, array duplicado e valor monetário inválido; Unicode válido preservado e comparado exatamente, sem normalização implícita, surrogate isolado recusado; zero execução |
| Mídia inválida | `415 INVALID_REQUEST`; somente `error` com `issues` | Tipo diferente de `application/json` ou charset incompatível; precede análise do corpo; zero execução |
| Sem rota / economia insuficiente | `422 NO_ELIGIBLE_ROUTE` ou `422 INSUFFICIENT_ECONOMIC_INFORMATION`; exatamente `error`, `decision` | `decision.outcome=refused`, sem `decision.route`, `result` ou `economics`; fatores distinguem inelegibilidade de falta de base econômica; zero execução |
| Configuração ou decisão inválida | `500 INVALID_CONFIGURATION` ou `500 INVALID_DECISION`; somente `error` com `issues` | Nenhuma seleção inválida publicada; zero execução |
| Falha de execução | `502 EXECUTION_FAILED`; exatamente `error`, `decision`, `economics` | Sem `result`; decisão da rota selecionada e `estimate` mantidas; `usage`/`calculated_cost` indisponíveis quando não há dados defensáveis; exatamente uma execução |
| Indisponibilidade na execução | `503 EXECUTION_UNAVAILABLE`; exatamente `error`, `decision`, `economics` | Mesmo contrato pós-seleção, código distinto; exatamente uma execução |
| Timeout na execução | `504 EXECUTION_TIMEOUT`; exatamente `error`, `decision`, `economics` | Mesmo contrato pós-seleção, código distinto; exatamente uma execução |

Em todas as linhas, validar schemas fechados da [API v1](../05-API.md), omissão de opcionais ausentes (sem `null`), strings decimais/moeda, ausência de payload externo e distinção entre estimativa, custo calculado e cobrança. A matriz é **plano de regressão para gate futuro**, não evidência de testes executados nesta PR.

## 8. Riscos, dependências e decisões reservadas ao PO

| ID | Dependência/risco | Situação hoje | Decisão a tomar antes de código real |
| --- | --- | --- | --- |
| D01 | Conflito Free estrita × Free preferencial | **Aberto; duas direções diferentes nos documentos** | Definir produtos/trilhas, nome e autorização econômica; se cabível, propor revisão ADR e FREE-01 |
| D02 | Semântica de compatibilidade da API v1 | Fechada, uma resposta de uma rota | Preservar v1 ou especificar nova API; não alterar por inferência |
| D03 | Tipo seguro de erro e evidência de não-efeito | Ausente em `ExecutionAdapter` | Definir sinalização e provas, sem tratar qualquer 429 como automaticamente seguro |
| D04 | Origem de elegibilidade gratuita e quota | Não verificada pelo Maestro | Fail-closed sem atestado aplicável a conta/projeto/método/janela |
| D05 | Fonte e escopo de consentimento financeiro | Não existe no `ExecutionRequest` v1; sincronização de revogação/dispatch inexistente | Aprovar opt-in, revogação e mecanismo serializável no limite do despacho; sem garantia, não iniciar B |
| D06 | Limites persistentes, ledger e dados pessoais | POC somente em memória | Decidir retenção/eliminação, segurança e observabilidade |
| D07 | Continuidade em sistemas de contexto diferentes | `ExecutionRequest`/`TextExecutionRequest` só têm `task` e `context: str | None`; envelope da POC é sintético | Decidir DTO interno real, tradução fiel, tamanho, compatibilidade e validação em gate separado; não ampliar v1 |
| D08 | Cancelamento e idempotência reais | Não há garantia pública | Aprovar modelos de erro sem replay inseguro |
| D09 | Ranking “prefer_free”, `sticky route` e exclusões de tentativas | `lowest-estimated-cost` atual seleciona uma rota; [FREE-02-R1, seção 5](MAESTRO-FREE-02-R1-roteamento-preferencial-fallback.md) propõe afinidade com rota bem-sucedida | `sticky route` é decisão futura pendente, desabilitada/não assumida na F03-A; eventual preferência requer gate e testes, nunca sobrepõe elegibilidade, autorização, custo, critérios ou `lowest-estimated-cost`; não falsear exclusão como `invalid_route` |
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

### 9.1 RUC/1.0 — Correção documental FREE-03-R1 / Issue #50

#### 1. Identificação

**Missão:** MAESTRO-FREE-03-R1 · [Issue #50](https://github.com/hallanbrito/maestro-router/issues/50) · executor Codex · CH-2 documental autorizado pelo PO na Issue e retomada autorizada no [comentário de desbloqueio](https://github.com/hallanbrito/maestro-router/issues/50#issuecomment-6668272643). **Ambiente:** worktree local isolado; `LIVE_GITHUB` + `LOCAL_REPO` · 06/11/2026, America/Fortaleza · `run_id` local: não aplicável. **Baseline:** Draft PR #49, `master@31a2f1c0db505a70359fac6a9ccf80804f5f7dd3`, HEAD inicial `f9092ece90b37c374fd513d5b5808ae71db5f29b`. **Parecer nesta etapa:** `PARCIAL`, até CI do novo HEAD e auditoria externa.

#### 2. Resumo executivo

Correção proposta dos 3 P2 e 1 P3 em um único Markdown. Nenhuma implementação de fallback ou teste futuro foi executado por este documento. A PR deve permanecer Draft, sem merge.

#### 3. Consultas e atividades realizadas

Conferidos Issue #50, auditoria da PR #49, `docs/05-API.md`, ADR 0014, FREE-02-R1 e contratos/fluxos pertinentes em `api.py`, `contracts.py`, `execution.py` e `control_center.py`. Editado somente este documento. Verificações locais e CI do novo HEAD são registradas abaixo segundo sua efetiva execução; o resultado remoto final também deve constar na Issue e PR.

#### 4. Evidências verificáveis

| ID | Classe e fonte | Fato e limite |
| --- | --- | --- |
| R1-E01 | `OBSERVADO` · Git local e [PR #49](https://github.com/hallanbrito/maestro-router/pull/49) | Baseline/HEAD iniciais acima; PR aberta em Draft antes da edição R1. |
| R1-E02 | `OBSERVADO` · [auditoria #6667770454](https://github.com/hallanbrito/maestro-router/pull/49#issuecomment-6667770454) e diff R1 | 3 P2 + 1 P3 descritos; a correção cobre matriz v1, envelope sintético, corrida de revogação e `sticky route`. A auditoria citada não homologa esta revisão. |
| R1-E03 | `OBSERVADO` · [CI anterior #42097374471](https://github.com/hallanbrito/maestro-router/actions/runs/42097374471) | `completed/success` no HEAD **inicial** `f9092ec`; não valida o diff R1. |
| R1-E04 | `DECLARADO` · [relato da tentativa anterior](https://github.com/hallanbrito/maestro-router/issues/50#issuecomment-6668236480) | `pytest` local inconclusivo por ausência de módulo em `/usr/bin/python3` e timeout em ambiente virtual; não é PASS nem falha comprovada da suíte. |

#### 5. Verificações e resultados

| Critério | Estado nesta revisão do Markdown | Evidência/limite |
| --- | --- | --- |
| Quatro achados documentais | `PASSOU` na conferência do executor, sujeito a auditoria | Seções 3.1, 4, 7.1 e D05/D07/D09; critérios futuros explicitamente não executados. |
| Integridade do diff e links relativos | `PASSOU` nesta revisão local | `git diff --check` sem erro; `git diff --name-only origin/master` aponta só este Markdown; 19 links locais resolvem para arquivos existentes. Conferir novamente após commit. |
| `pytest` local | `NÃO_EXECUTADO` nesta retomada | Tentativa anterior inconclusiva; o desbloqueio da Issue dispensa repetição para esta edição apenas documental. |
| CI no novo HEAD | `NÃO_EXECUTADO` neste registro pré-publicação | Gate obrigatório após push; resultado e SHA final devem constar na Issue/PR. |

#### 6. Riscos e bloqueios

Sem prova de não-efeito remoto, sem sincronização de consentimento ou com contexto incompatível, B permanece bloqueado. O conflito ADR 0014 × FREE-02 e a decisão de implementar DTO/afinidade continuam abertos. CI do novo HEAD pendente neste registro pré-publicação.

#### 7. Alterações realizadas

Apenas `docs/proposals/MAESTRO-FREE-03-arquitetura-integracao-runtime.md`: quatro correções e este RUC. Nenhum arquivo de código, teste, norma, dependência ou workflow alterado; nenhum provedor real acionado.

#### 8. Recomendação técnica

`PARCIAL` antes da CI e da auditoria. Após CI verde, encaminhar o mesmo HEAD à revisão técnica externa; esta autoverificação do executor não equivale a auditoria independente nem homologação.

#### 9. Decisão necessária do PO

**PENDENTE:** decidir aceite documental após nova auditoria e, em gates futuros separados, política Free estrita/preferencial, DTO real, protocolo de revogação e eventual `sticky route`. Sem autorização de merge ou implementação por este RUC.

---
*Documento de arquitetura proposta — descrição do sistema atual e direção futura claramente separadas; sujeito a auditoria e decisão do PO.*

# Método C.H. de Execução — Protocolo Econômico de Engenharia

## 1. Objetivo

Este documento estabelece o protocolo de engenharia do Maestro Router para a execução de fatias de trabalho incrementais (Ws). Seu foco exclusivo é a governança do processo de desenvolvimento, orientando a interação entre os papéis envolvidos para garantir:

- Alta qualidade arquitetural e conformidade irrestrita com a documentação do projeto;
- Rastreabilidade ponta a ponta de cada decisão, inspeção e alteração;
- Independência estrita da revisão técnica antes da integração em branch principal;
- Economia responsável de contexto, franquia de chamadas e consumo de tokens;
- Utilização sistemática do menor modelo de linguagem suficiente para cada etapa;
- Escalada de capacidade condicionada estritamente à evidência técnica demonstrada;
- Eliminação de duplicações de esforço, de contexto e de código.

Este protocolo governa apenas o processo de trabalho de engenharia do Maestro Router. Ele não rege o comportamento de produto em tempo de execução, não substitui nem altera os documentos normativos do repositório, não cria itens de roadmap ou novas funcionalidades e não modifica decisões arquiteturais (ADRs). Suas diretrizes aplicam-se a todas as próximas Ws, ressalvada decisão explícita e documentada do Product Owner para uma tarefa específica.

Este protocolo é uma especialização operacional do Método Ágil C.H., cuja origem histórica e princípios gerais estão publicados em https://github.com/hallanbrito/metodo-ch. A versão histórica v0.1 permanece independente deste protocolo operacional, não havendo redefinição retroativa do Método C.H. nem conversão de práticas específicas do Maestro Router em princípios universais do método.

O protocolo adota formalmente o seguinte princípio orientador:

> "Usar a menor capacidade suficiente para satisfazer os requisitos de qualidade da etapa e escalar somente diante de evidência de necessidade."

Trata-se de uma política de processo de engenharia inspirada em princípios econômicos de eficiência e controle de recursos operacionais, não se confundindo com as regras ou invariantes do algoritmo interno de roteamento do produto Maestro Router.

## 2. Papéis e autoridades

O processo de engenharia organiza-se em quatro papéis de responsabilidades bem delimitadas:

- **Hallan / Product Owner (PO):**
  - Detém autoridade final e soberana sobre o produto e sobre o repositório.
  - Aprova novas decisões conceituais e arquiteturais.
  - Autoriza explicitamente gates humanos de aprovação, transições de estado críticas e o merge final na branch `master`.
  - Não atua como ponte manual de mensageria nem repassador de prompts entre Codex e AGY; a orquestração operacional é executada diretamente pelas ferramentas via terminal.

- **ChatGPT (Auditor Independente e Consultor):**
  - Auxilia no planejamento inicial e estratégico e revisa artefatos conceituais quando solicitado pelo Product Owner.
  - Realiza a auditoria independente e externa da Pull Request real no GitHub, verificando diretamente na plataforma o diff final, a branch base, a branch head e a preservação dos invariantes normativos antes de qualquer integração.
  - Não substitui a autoridade do Product Owner e jamais realiza merge de forma autônoma; sua autorização técnica é pré-requisito, mas o merge só ocorre após a autorização expressa e soberana de Hallan.

- **Codex (Orquestrador e Fiscal Técnico):**
  - Atua como a mente de governança e orquestração técnica da tarefa.
  - Investiga o repositório buscando a menor alteração necessária e suficiente.
  - Lê exclusivamente o contexto governante indispensável para a fatia de trabalho.
  - Identifica proativamente lacunas e ambiguidades; diante de decisões humanas abertas ou arquiteturais relevantes, interrompe o fluxo e reporta formalmente a pendência.
  - Elabora instruções técnicas cirúrgicas, comanda e fiscaliza a execução do AGY no terminal.
  - Executa a revisão dirigida das alterações e a verificação de invariantes, evitando retrabalho e não repetindo o papel de implementação atribuído ao executor.

- **AGY (Executor Operacional Especializado):**
  - Recebe instruções técnicas precisas e comandos diretamente pelo terminal via CLI.
  - Implementa fatias de código, alterações pontuais e correções estritamente delegadas.
  - Não toma decisões de produto nem altera diretrizes arquiteturais por iniciativa própria.
  - Conclui sua atuação devolvendo resultados verificáveis, relatórios de execução, logs e status objetivos.

## 3. Fluxo padrão de uma W

Toda fatia incremental de trabalho (W) segue rigorosamente a sequência de 19 etapas operacionais:

1. **Iniciação e autorização:** Hallan / Product Owner define o objetivo da W e autoriza o início da investigação ou trabalho.
2. **Sincronização e base:** Codex confirma que a base local está limpa e sincronizada com a `master` mais recente antes de ramificar.
3. **Leitura seletiva governante:** Codex lê `AGENTS.md`, consulta `docs/INDEX.md` e lê somente os documentos normativos e arquivos indispensáveis para o escopo da W.
4. **Análise de lacunas:** Codex mapeia a menor intervenção necessária e verifica se a alteração pretendida colide com contratos ou invariantes existentes.
5. **Gate de decisão arquitetural:** Se for identificada uma nova decisão arquitetural, divergência normativa ou ambiguidade de produto relevante, o fluxo é interrompido imediatamente com emissão do relatório C.H. com estado `STATUS: AGUARDANDO DECISÃO DO PRODUCT OWNER`.
6. **Decisão do Product Owner:** Hallan analisa a questão e emite a decisão formal que destrava a sequência do trabalho.
7. **Instrução cirúrgica ao AGY:** Codex formula o plano detalhado de execução e monta o comando cirúrgico para invocação direta do AGY via terminal.
8. **Invocação do AGY:** Codex chama a CLI do AGY em modo headless com redirecionamento de logs para arquivo temporário.
9. **AGY implementa:** AGY executa as modificações de código ou documentação e executa os testes pertinentes à fatia.
10. **Codex faz revisão dirigida:** Codex avalia a saída, inspeciona os logs e revisa o diff das alterações produzidas contra as diretrizes normativas e invariantes do sistema.
11. **Correções retornam preferencialmente ao AGY:** Se forem encontrados defeitos ou desvios, Codex instrui novas rodadas pontuais ao AGY até a completa conformidade.
12. **Executar validações:** Executam-se os testes focados, seguidos da suíte integral cabível e checagens estáticas (formatação, linting, integridade de documentação).
13. **Criar Draft PR:** Codex ou o executor abre a Pull Request em modo Draft no GitHub, contendo a descrição estruturada da W.
14. **Emitir STATUS: AGUARDANDO VALIDAÇÃO CHATGPT + PRODUCT OWNER:** O fluxo atinge o marco formal emitindo `STATUS: AGUARDANDO VALIDAÇÃO CHATGPT + PRODUCT OWNER`.
15. **ChatGPT audita a PR real:** ChatGPT examina a PR real no GitHub (comparando base, head, escopo, diff completo, contratos e ausência de regressões).
16. **Hallan fornece AUTORIZADO final:** Hallan analisa o parecer da auditoria e emite explicitamente a mensagem `AUTORIZADO`.
17. **Revalidar HEAD/estado:** Codex/Auditor revalida se o HEAD da branch de trabalho e a branch `master` não divergiram durante a avaliação.
18. **Merge:** Realiza-se o merge aprovado na `master`.
19. **Nova master torna-se base da próxima W:** Estabelece-se a base limpa e atualizada para o ciclo de trabalho seguinte.

## 4. Política econômica de modelos

A escolha de modelos para condução e auxílio das etapas de engenharia adota uma hierarquia estrita de quatro classes econômicas. Os modelos citados são referências operacionais de capacidade sujeitas à disponibilidade, sendo governados pelo princípio da menor capacidade suficiente:

- **Classe E0 (Mecânica e Focada):**
  - *Modelo de referência:* GPT-5.6 Luna.
  - *Aplicação:* Tarefas estritamente mecânicas, inspeções pontuais de sintaxe, extração de texto, classificação simples, pequenas checagens repetitivas e formatação de artefatos.

- **Classe E1 (Padrão de Engenharia):**
  - *Modelo de referência:* GPT-5.6 Terra (com nível de raciocínio / reasoning baixo).
  - *Aplicação:* É o padrão obrigatório para o início e condução de toda W rotineira. Utilizado para investigação técnica habitual, decisões locais governadas pelas normas vigentes, elaboração de instruções cirúrgicas para o AGY, revisão dirigida de diffs, documentação e redação de Pull Requests.

- **Classe E2 (Complexa e Aprofundada):**
  - *Modelo de referência:* GPT-5.6 Sol (com reasoning baixo ou médio).
  - *Aplicação:* Acionada exclusivamente quando a classe E1 se mostrar comprovadamente insuficiente para lidar com complexidades arquiteturais multifacetadas, diagnóstico de bugs não reprodutíveis ou obscuros, resolução de conflitos intrincados de mesclagem ou análises profundas de impacto sistêmico.

- **Classe E3 (Excepcional e de Alto Risco):**
  - *Modelo de referência:* GPT-6 Astra.
  - *Aplicação:* Reservada exclusivamente para situações extremas de impasse conceitual intransponível, problemas de causa desconhecida com risco crítico de quebra ou redesenho fundamental após esgotamento das classes inferiores. Jamais deve ser utilizada como modelo padrão ou inicial de uma W.

### Regras de escalada e retrocesso

1. **Vedação de escalada preventiva:** É proibido iniciar uma tarefa ou escalar de classe com base em suposições ou comodismo técnico. Toda escalada requer evidência concreta de insuficiência da classe atual.
2. **Registro prévio obrigatório:** Antes de transitar de E1 para E2, ou de E2 para E3, deve-se registrar no relatório da W:
   - O problema exato encontrado;
   - A evidência objetiva de incapacidade ou limitação da classe corrente;
   - O motivo técnico fundamentado da necessidade de maior capacidade.
3. **Escalada transitória e retorno econômico:** A escalada restringe-se exclusivamente à etapa difícil. Uma vez superado o obstáculo analítico, o fluxo retorna obrigatoriamente à classe mais econômica (E1 ou E0) para o restante da execução.
4. **Raciocínio não substitui clareza:** O aumento de capacidade ou de parâmetros de reasoning não supre instrução deficiente, falta de contexto normativo, carência de permissões adequadas ou requisitos ambíguos.

## 5. Orçamento de contexto

A preservação da janela de contexto e o controle do consumo de tokens constituem disciplina técnica obrigatória:

- **Não carregar o repositório por inteiro:** É terminantemente proibido injetar pastas inteiras, diretórios de fontes completos ou realizar varreduras exaustivas sem foco estrito.
- **Roteamento ordenado:** Toda consulta contextual inicia pela leitura de `AGENTS.md` e de `docs/INDEX.md`, os quais direcionam exatamente para os documentos normativos específicos da tarefa.
- **Leitura estrita de fontes governantes:** Documentos conceituais que não impactam a fatia corrente não devem ser carregados para o contexto de trabalho.
- **Localização cirúrgica:** Deve-se priorizar ferramentas de busca rápida (como `git grep` ou busca textual) para mapear símbolos, funções ou arquivos antes de solicitar a leitura na íntegra de qualquer módulo de código.
- **Avaliação de diffs em camadas:**
  - Inspecionar primeiramente resumos de alteração através de `git diff --stat` ou listagem por `git diff --name-only`;
  - Verificar a integridade e espaçamento com `git diff --check`;
  - Analisar os hunks e contratos afetados de forma modular;
  - A revisão do diff integral é obrigatória no gate final da entrega, mas deve ser executada sem repetições redundantes na mesma sessão.
- **Sumarização de saídas de teste:** Testes unitários e relatórios de execução devem ser apresentados em formato resumido, destacando o quantitativo de sucessos e o stack trace restrito aos pontos exatos de falha.
- **Reaproveitamento e reinicialização de sessão:** Sessões poluídas com discussões descartáveis, saídas de erro extensas ou contexto sem utilidade residual devem ser encerradas, iniciando-se uma nova sessão com contexto limpo e conciso.

## 6. Codex -> AGY

A articulação entre Codex e AGY obedece a um padrão direto de comando e controle pelo terminal:

- **Comunicação automatizada por terminal:** Codex envia instruções, scripts e chamadas diretamente à CLI do AGY no terminal do sistema. O Product Owner não deve atuar como intermediário manual copiando e colando prompts.
- **Execução headless e desassistida:** A invocação do AGY deve ser feita preferencialmente em modo headless validado, minimizando interrupções interativas e permitindo automação de rotinas de modificação e teste.
- **Canalização de saídas e logs:** A saída de comandos extensos não deve poluir a interface do orquestrador. As saídas devem ser redirecionadas para arquivos temporários controlados, analisando-se prioritariamente o exit status e extraindo apenas excertos relevantes para a tomada de decisão.
  - *Exemplo conceitual de invocação:*
    ```bash
    agy ... --print > /tmp/agy-wXX.log 2>&1
    ```
  - *Ressalva contratual:* O caminho `/tmp/` e os formatos de arquivo de log têm caráter estritamente ilustrativo e operacional, não constituindo interface pública nem contrato perene do produto.
- **Princípio do privilégio mínimo de ferramentas:** Permissões amplas concedidas ao executor só devem ser ativadas quando forem comprovadamente suportadas pela ferramenta, estritamente necessárias para a tarefa, limitadas ao escopo da W e enquadradas nos guardrails de segurança.

## 7. Política de revisão

A conformidade do código e da documentação assenta-se em uma cadeia de revisão técnica e independente dividida em quatro níveis:

1. **Nível AGY (Executor):** Responsável pela implementação do código, execução preliminar de testes locais e ajustes imediatos de falhas decorrentes de sua própria edição.
2. **Nível Codex (Orquestrador e Fiscal):** Responsável por verificar a adequação arquitetural, o cumprimento dos padrões de codificação, a aderência aos contratos e a invariância dos documentos normativos, realizando a revisão dirigida do diff e preparando a Draft PR.
3. **Nível ChatGPT (Auditor Independente):** Responsável por realizar a auditoria externa e independente da Pull Request real publicada no GitHub. A análise contempla a consistência entre base e head, a restrição ao escopo da W, a integridade do diff completo, os riscos operacionais e a validação dos critérios de aceitação.
4. **Nível Hallan / PO (Autoridade Final):** Avalia as recomendações das instâncias anteriores e decide soberanamente sobre a autorização de merge ou necessidade de revisões adicionais.

Sob nenhuma hipótese a busca por economia de tokens ou agilidade operacional justificará a supressão de qualquer um dos gates de revisão.

## 8. Testes e validação

A bateria de verificação do Maestro Router segue um protocolo em etapas graduais:

- **Focados primeiro:** Toda modificação deve ser acompanhada prioritariamente pela execução de testes pontuais e unitários diretamente ligados ao trecho alterado.
- **Validação integral antes da PR:** Antes da submissão da Pull Request final, executa-se a suíte completa de testes pertinentes para certificar a ausência de regressões colaterais.
- **Checagem de integridade de dependências:** Validação periódica do ambiente de execução (utilizando ferramentas como `uv pip check` ou equivalente).
- **Compilação e sintaxe estática:** Verificação de sintaxe de todos os arquivos modificados (como `python -m compileall`).
- **Validação formal de diff:** Execução de `git diff --check` para prevenir introdução de espaços em branco espúrios, conflitos de mesclagem esquecidos ou quebras de convenção de formatação.
- **Validação documental:** Quando a tarefa envolver modificações em `docs/`, verificar a atualização correspondente de `docs/INDEX.md` e a consistência de links relativos.
- **Vedação de chamadas externas reais:** Os testes automatizados em hipótese alguma realizam chamadas reais a APIs externas ou provedores de modelos durante a validação da W.
- **Linha de base (baseline) versus resultado final:** Todo ciclo de teste deve confrontar a situação prévia com o estado posterior, garantindo que nenhum teste que passava anteriormente tenha sido degradado.
- **Não execução integral por alteração trivial:** Não se deve rodar a suíte inteira do sistema após cada edição microscópica ou pontual; a suíte integral é reservada para marcos de consolidação e encerramento da fatia de trabalho.

## 9. Git/GitHub

A gestão de versão e repositório adota práticas de integração contínua rigorosas:

- **Branch principal protegida:** A branch `master` deve permanecer estável e conter apenas código validado e aprovado.
- **Integração limpa:** A integração preserva histórico limpo e rastreável. O squash merge é a estratégia atualmente utilizada para consolidar uma W aprovada em um único commit na `master`. Eventual mudança futura de estratégia não altera os gates de auditoria independente, revalidação de HEAD e autorização humana do Product Owner.
- **Proibição de descartes silenciosos:** É terminantemente vedado o uso de `git reset --hard`, descartes silenciosos de commits ou limpezas destrutivas sem autorização explícita e justificada.
- **Branches de trabalho dedicadas:** Toda W deve ser concebida e desenvolvida em sua própria branch temática, isolada das demais atividades.
- **Commits atômicos e descritivos:** As mensagens de commit devem refletir com precisão a menor alteração lógica introduzida.
- **Draft PR mandatória:** Ao ser enviada para o GitHub, a Pull Request deve ser aberta inicialmente no formato Draft, sinalizando que a entrega encontra-se em fase de validação e auditoria.
- **Bloqueio de auto-merge e gates automáticos:** É proibido marcar a PR como "Ready for review" ou acionar auto-merge antes da conclusão de todos os gates formais de auditoria e revisão.
- **Condição estrita para merge:** O merge no GitHub só pode ocorrer após a auditoria independente satisfatória do ChatGPT e o comando expresso `AUTORIZADO` emitido pelo Product Owner.
- **Revalidação de SHA e HEAD:** Antes de efetivar a mesclagem, o orquestrador deve revalidar o estado do HEAD e, quando suportado, utilizar a trava de SHA esperado (`--expected-commit-sha`) para prevenir race conditions no repositório.

## 10. Relatório padrão C.H.

A comunicação formal entre os papéis durante as fatias de trabalho adota o formato padronizado C.H., estruturado nas seguintes seções:

- **C — Contextualização:** Descrição concisa do objetivo da W, da demanda do PO e dos arquivos normativos lidos.
- **H — Hipótese / Arquitetura:** Solução técnica planejada, premissas adotadas e garantia de conformidade com os contratos do sistema.
- **E — Execução:** Ações práticas realizadas, delegações feitas ao AGY e modificações implementadas.
- **V — Verificação:** Resultados dos testes focados e integrados, checagens estáticas e conformidade do diff.
- **G — Git / GitHub:** Nome da branch, SHA dos commits relevantes, status da Pull Request e estado da base.
- **D — Decisão pendente:** Dúvidas, ambiguidades identificadas ou autorizações humanas requeridas para prosseguimento.

### Estados padronizados do relatório

O relatório deve apresentar em destaque um dos seguintes estados operacionais:

- `STATUS: AGUARDANDO DECISÃO DO PRODUCT OWNER`
- `STATUS: AGUARDANDO VALIDAÇÃO CHATGPT + PRODUCT OWNER`

Em tarefas estritamente operacionais ou de baixa complexidade, o relatório pode assumir formato sucinto, preservando a concisão sem omitir os dados de verificação e decisão.

## 11. Métrica de eficiência

Para fins de acompanhamento qualitativo da eficiência do processo de engenharia, cada W relevante pode registrar de forma leve em seu relatório de conclusão:

- O modelo de linguagem utilizado pelo Codex;
- O nível de raciocínio (reasoning) adotado;
- O quantitativo de rodadas de instrução/correção delegadas ao AGY;
- O status da bateria de testes na linha de base e no estado final;
- A eventual ocorrência de escalada de classe de modelo e sua motivação técnica.

Essa métrica possui natureza puramente operacional e qualitativa. O projeto não implementa telemetria automatizada, tabelas em banco de dados, servidores de métricas ou dashboards internos para essa finalidade. O Product Owner pode, a seu critério exclusivo, acompanhar os registros de consumo diretamente no painel de sua conta de provedor.

## 12. Guardrails

O compromisso com a economia de recursos, contexto e tokens jamais sobrepõe a segurança do repositório e a qualidade do código. Fica formalmente estabelecido que este protocolo de engenharia:

- Não autoriza redução da cobertura de testes nem relaxamento das suítes de validação;
- Não permite ocultar, ignorar ou mascarar falhas de compilação, de execução ou de linting;
- Não autoriza alterações em decisões de arquitetura, contratos públicos de API ou invariantes normativos;
- Não introduz novas promessas de produto, funcionalidades fora do escopo ou compromissos de roadmap;
- Não autoriza a criação de infraestrutura não aprovada, como observabilidade externa, instrumentação ou pipelines pesados de CI/CD;
- Não permite a adição de dependências de software voltadas unicamente a medir consumo ou impor telemetria interna;
- Não permite expor segredos, tokens de acesso, chaves privadas de API ou credenciais de qualquer espécie;
- Não autoriza, sob qualquer pretexto, subordinar a correção técnica, a segurança e a conformidade do sistema a metas de redução de custo operacional.

## 13. Evolução do protocolo

Este protocolo de engenharia é um artefato vivo que pode evoluir conforme a maturidade do projeto e das ferramentas de suporte:

- Toda alteração substantiva nas regras, papéis, fluxos ou gates estabelecidos neste documento depende de aprovação formal e explícita do Product Owner.
- As revisões do protocolo são realizadas diretamente neste documento (`docs/07-METODO-CH-EXECUCAO.md`).
- A evolução deste processo não deve ser registrada como uma ADR (Architecture Decision Record) de produto, assegurando a separação definitiva entre decisões arquiteturais do sistema e procedimentos de fluxo de trabalho de engenharia.
- Caso novos modelos de linguagem sejam disponibilizados no mercado, eles poderão ser adotados como referências equivalentes para as classes E0 a E3, desde que preservados irrestritamente o princípio da menor capacidade suficiente, a exigência de justificação documentada para escaladas e os gates de auditoria estabelecidos.

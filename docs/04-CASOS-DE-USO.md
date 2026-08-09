# Casos de Uso do MVP do Maestro Router

## 1. Propósito

Este documento transforma o escopo e a arquitetura conceitual já aprovados em casos de uso observáveis do MVP. Ele descreve como uma aplicação cliente e o responsável pela configuração ou integração interagem conceitualmente com o Maestro Router, quais resultados esperam e como as principais falhas devem se manifestar.

Os casos de uso expressam o comportamento esperado do MVP; não afirmam que essas capacidades já estejam implementadas. Também não definem contrato técnico, formato de configuração ou escolhas de tecnologia. Esses assuntos permanecem para documentos e decisões posteriores.

As fontes aprovadas deste documento são o [Manifesto](00-MANIFESTO.md), a [Visão Geral](01-VISAO-GERAL.md), a [Proposta de Valor](02-PROPOSTA-DE-VALOR.md) e a [Arquitetura Conceitual](03-ARQUITETURA.md). Em caso de conflito, prevalece o Manifesto. Este documento não amplia nem redefine essas fontes.

## 2. Fronteira e atores

O Maestro fica entre a aplicação cliente e os provedores ou modelos externos. A aplicação interage somente pela API única; os detalhes próprios de cada provedor permanecem isolados pelos adaptadores. A forma concreta dessa API ainda não é definida aqui.

| Ator ou participante | Papel nos casos de uso |
| --- | --- |
| **Aplicação cliente** | Ator principal dos fluxos de execução. Fornece a tarefa, o contexto necessário e as restrições aplicáveis; recebe o resultado ou erro e as informações necessárias para compreender a decisão. |
| **Responsável pela configuração ou integração** | Ator principal da preparação do Maestro. Declara as alternativas e os dados necessários para que elas possam ser avaliadas e acionadas de forma válida. Esse papel não pressupõe painel administrativo, sistema de contas nem um tipo específico de usuário. |
| **Provedor ou modelo externo** | Sistema participante acionado pelo adaptador somente depois da seleção de uma rota. Executa a tarefa e pode fornecer resultado, informações de uso ou erro. Não escolhe a rota. |

O usuário que define limites, preferências ou requisitos não precisa ser um ator direto do Maestro. Essas restrições chegam pela aplicação cliente ou pela configuração aplicável. Cadastro de usuários ou tenants e gestão do ciclo de vida de suas políticas não pertencem ao MVP.

## 3. Regras comuns aos casos de uso

Nos fluxos abaixo, o Router continua coordenando o processo completo; o Provider Registry descreve as alternativas; o Cost Evaluation trata estimativas e custo calculável; o Strategy Engine toma a decisão segundo a estratégia configurada; Validation verifica coerência e explicabilidade; e somente o adaptador selecionado conversa com o provedor externo. Essas responsabilidades internas não são atores nem se transformam em casos de uso próprios.

- Apenas alternativas configuradas, habilitadas e suficientemente válidas podem participar de uma decisão.
- Restrições obrigatórias da configuração e restrições da solicitação se acumulam. A solicitação pode restringir o conjunto permitido, mas não habilitar uma rota desativada nem enfraquecer um limite obrigatório. Valores padrão apenas suprem ausências.
- Elegibilidade antecede comparação. Alternativas incompatíveis com requisitos de capacidade, qualidade, disponibilidade conhecida ou preferências obrigatórias são excluídas antes da comparação econômica.
- Custo é considerado somente entre alternativas compatíveis com os demais requisitos. Economia não transforma uma rota incompatível em elegível nem garante a opção universalmente mais barata.
- A estratégia aplicada é simples, explícita, configurada e justificável. Seu nome, algoritmo, parâmetros, pesos, limiares e regra concreta de desempate não são definidos neste documento.
- No fluxo normal, uma solicitação produz uma decisão e é executada por uma única rota selecionada. Não há fan-out, comparação de respostas, consenso, votação ou coordenação de múltiplos modelos.
- As informações da decisão e do impacto econômico ficam disponíveis à aplicação, mas sua organização, serialização, entrega e eventual retenção pertencem ao contrato técnico ou a decisões posteriores.
- Nenhum erro autoriza o Maestro a adivinhar dados, ocultar incerteza ou reduzir silenciosamente restrições para obter uma resposta.
- Neutralidade entre provedores, critérios explícitos e evidências adequadas devem sustentar as decisões. O MVP não inclui julgamento automático da qualidade da resposta nem uma plataforma de benchmarks.

## 4. Casos de uso

### UC-01 — Preparar o Maestro para decidir e executar

**Objetivo:** disponibilizar alternativas e critérios suficientes para que o Maestro possa avaliar rotas, tomar uma decisão justificável e acionar a alternativa selecionada.

**Ator principal:** responsável pela configuração ou integração.

**Participantes secundários:** nenhum necessário.

**Pré-condições:**

- o responsável conhece as alternativas que pretende disponibilizar e possui as informações necessárias para descrevê-las;
- critérios de capacidade e qualidade usados na elegibilidade possuem base declarada e referências às evidências disponíveis quando aplicáveis;
- referências de acesso necessárias podem ser fornecidas sem incorporar valores secretos aos dados de domínio, de preço, de estratégia ou de decisão.

**Gatilho:** o responsável pretende tornar uma ou mais alternativas disponíveis para decisões do Maestro ou ajustar uma configuração existente.

**Fluxo principal:**

1. O responsável declara as rotas habilitadas, identificando de forma neutra o provedor, o modelo e a integração associada.
2. Para cada rota, informa as capacidades, os critérios de qualidade, as referências às evidências disponíveis e as condições conhecidas necessárias à elegibilidade.
3. Fornece informações econômicas suficientes para que o custo relevante possa ser estimado ou calculado, mantendo identificáveis a referência de preço e as hipóteses utilizadas.
4. Define a estratégia a ser aplicada e somente os parâmetros indispensáveis ao seu funcionamento.
5. Declara as restrições obrigatórias, os valores padrão e os parâmetros operacionais essenciais que devam participar do fluxo.
6. Fornece referências às credenciais necessárias, mantendo os valores secretos fora das informações de decisão e das mensagens de erro.
7. O Maestro valida a completude e a coerência dos dados antes que eles participem de uma decisão.
8. As partes válidas da configuração ficam aptas a sustentar elegibilidade, avaliação econômica, seleção e execução.

**Fluxos alternativos e exceções:**

- **Configuração global indispensável inválida ou ausente:** o Maestro impede o fluxo afetado e identifica o dado inválido ou ausente, sem adivinhar um valor e sem expor segredos.
- **Erro restrito a uma rota:** a rota não participa da decisão e o motivo fica explícito; outras rotas válidas não precisam ser invalidadas por consequência.
- **Dados econômicos insuficientes:** a rota é marcada como não comparável e não participa de uma decisão que dependa de custo. A ausência não é substituída por um valor inventado.
- **Integração ou associação de rota insuficiente:** a rota não fica apta à execução até que a inconsistência seja corrigida.

**Pós-condições:**

- somente dados validados e rotas suficientemente válidas podem participar das decisões correspondentes;
- limitações ou exclusões conhecidas permanecem identificáveis;
- a configuração não torna qualquer provedor uma dependência conceitual permanente do Maestro.

**Critérios de aceitação observáveis:**

- uma configuração válida permite identificar quais alternativas estão habilitadas e quais fatos serão usados para avaliá-las;
- um erro global indispensável impede o fluxo correspondente antes de qualquer execução externa da tarefa;
- um erro isolado torna somente a rota afetada inelegível e informa a razão;
- uma solicitação posterior não consegue habilitar uma rota desativada nem enfraquecer uma restrição obrigatória;
- mensagens de validação e informações da decisão não revelam valores secretos.

### UC-02 — Executar uma tarefa sob restrições

**Objetivo:** obter a execução de uma tarefa por uma rota selecionada de forma econômica e explicável, sem violar as restrições aplicáveis.

**Ator principal:** aplicação cliente.

**Participantes secundários:** provedor ou modelo externo associado à rota selecionada.

**Pré-condições:**

- existe configuração validada suficiente para iniciar a avaliação da solicitação;
- as alternativas potencialmente aplicáveis estão descritas por conceitos comuns e independentes dos formatos dos provedores;
- a aplicação consegue apresentar a tarefa pela fronteira única do Maestro.

**Gatilho:** a aplicação apresenta uma tarefa, o contexto necessário e as restrições aplicáveis.

**Fluxo principal:**

1. O Maestro recebe a solicitação pela API única e verifica se a tarefa, o contexto necessário e as restrições possuem a estrutura mínima exigida.
2. O Maestro combina as restrições da solicitação com os limites obrigatórios e valores padrão da configuração, sem permitir enfraquecimento de requisitos.
3. São identificadas as alternativas configuradas e habilitadas que podem ser candidatas à tarefa.
4. Alternativas incompatíveis com capacidade, qualidade, disponibilidade conhecida ou preferências obrigatórias são excluídas com razões identificáveis.
5. Para as alternativas restantes, o impacto econômico é estimado com as informações disponíveis e com suas hipóteses declaradas.
6. Alternativas que excedam limites econômicos obrigatórios são excluídas. Quando o limite ou a estratégia depender de custo, alternativas sem informação econômica suficiente também não participam da comparação.
7. A estratégia configurada compara somente as alternativas elegíveis e economicamente comparáveis para aquela decisão e seleciona uma rota, apresentando o critério determinante, a razão objetiva e, quando aplicável, a regra de desempate utilizada.
8. O Maestro verifica se a seleção está sustentada pelos fatos disponíveis e se pode ser explicada antes de prosseguir.
9. No fluxo normal, somente a rota selecionada é acionada. O adaptador correspondente traduz a solicitação comum, acessa o provedor ou modelo e normaliza o resultado, as informações de uso ou o erro.
10. Quando houver dados de uso suficientes, o impacto econômico da execução é calculado com a referência de preço aplicável.
11. O resultado da execução e as informações necessárias para compreender a decisão e seu impacto econômico ficam disponíveis à aplicação.

**Fluxos alternativos e exceções:**

- **Solicitação inválida:** o Maestro recusa a solicitação antes de qualquer chamada externa e identifica os dados necessários que estejam ausentes ou inválidos.
- **Configuração insuficiente para a solicitação:** o fluxo termina antes da chamada externa e indica a insuficiência; o Maestro não completa dados por suposição.
- **Indisponibilidade conhecida antes da decisão:** a rota afetada é excluída e o fluxo continua somente se restar alternativa elegível.
- **Informação econômica insuficiente:** a rota não participa quando um limite obrigatório ou a estratégia depender dessa informação. Se nenhuma alternativa comparável restar, aplica-se o UC-03.
- **Nenhuma rota elegível:** aplica-se o UC-03, sem chamada a provedor.
- **Decisão incoerente ou insuficientemente justificável:** o Maestro não executa a rota como se a decisão fosse válida; a inconsistência fica explícita.
- **Falha, indisponibilidade ou timeout durante a execução:** o erro é normalizado e as informações já produzidas sobre a decisão e a execução permanecem disponíveis. Qualquer comportamento posterior depende de políticas de retry ou fallback ainda não definidas.
- **Uso insuficiente após resposta válida:** a resposta continua disponível, enquanto o custo posterior é identificado como indisponível ou incerto, sem ser inventado.

**Pós-condições:**

- em caso de sucesso, a aplicação recebe o resultado normalizado de uma execução pela rota selecionada e consegue relacioná-lo à decisão tomada;
- o custo calculável e as incertezas econômicas conhecidas ficam disponíveis;
- em caso de falha, nenhuma resposta ou informação econômica inexistente é apresentada como válida ou exata.

**Critérios de aceitação observáveis:**

- nenhuma alternativa incompatível com uma restrição obrigatória é escolhida por ser economicamente mais favorável;
- a estratégia recebe somente alternativas elegíveis para aquela decisão;
- a execução normal aciona uma única rota selecionada, sem comparar respostas de múltiplos modelos;
- a aplicação consegue identificar a rota selecionada e a razão objetiva da escolha;
- falhas não enfraquecem silenciosamente limites de custo, capacidade, qualidade, disponibilidade ou preferência;
- a independência da aplicação em relação aos formatos específicos dos provedores é preservada pela fronteira comum.

### UC-03 — Recusar uma solicitação sem rota admissível

**Objetivo:** obter uma recusa clara quando nenhuma alternativa puder satisfazer as restrições ou sustentar a decisão exigida, em vez de executar uma rota incompatível.

**Ator principal:** aplicação cliente.

**Participantes secundários:** nenhum provedor ou modelo externo é acionado.

**Pré-condições:**

- a solicitação é estruturalmente válida o suficiente para alcançar a avaliação de rotas;
- nenhuma execução externa foi iniciada.

**Gatilho:** depois da aplicação das restrições e dos requisitos da decisão, nenhuma alternativa permanece elegível ou os dados indispensáveis não permitem formar uma decisão válida.

**Fluxo principal:**

1. O Maestro conclui que não existe rota capaz de atender ao conjunto de restrições aplicáveis.
2. A ausência de rota é verificada contra os fatos disponíveis para evitar uma recusa incoerente ou sem fundamento identificável.
3. O Maestro encerra o fluxo sem chamar qualquer provedor ou modelo.
4. A aplicação recebe um erro compreensível e as razões determinantes da recusa, incluindo as restrições ou ausências que impediram a decisão.

**Fluxos alternativos e exceções:**

- **Todas as rotas violam ao menos uma restrição obrigatória:** a recusa identifica os impedimentos determinantes sem relaxá-los.
- **Nenhuma rota possui custo avaliável quando a decisão depende dele:** o Maestro informa que não pode decidir economicamente; não escolhe uma rota por palpite.
- **Indisponibilidade conhecida elimina as últimas alternativas:** a indisponibilidade participa da explicação da recusa sem pressupor monitoramento ativo de saúde.
- **A causa real é uma configuração indispensável inválida:** o resultado é caracterizado como erro de configuração, e não disfarçado como simples ausência de rota.

**Pós-condições:**

- nenhuma execução externa ocorreu;
- as restrições permanecem intactas;
- a aplicação dispõe de informação suficiente para distinguir incompatibilidade, ausência econômica relevante, indisponibilidade conhecida ou erro de configuração.

**Critérios de aceitação observáveis:**

- nenhuma chamada externa é realizada quando não há rota elegível;
- a recusa indica por que a solicitação não pôde ser atendida;
- o Maestro não habilita, inventa ou escolhe uma alternativa fora do conjunto configurado para evitar a falha;
- custo menor, conveniência operacional ou ausência de dados não substitui uma restrição obrigatória.

### UC-04 — Compreender a decisão e o impacto econômico

**Objetivo:** permitir que a aplicação compreenda a rota escolhida, os fatores determinantes e o impacto econômico conhecido ou calculável da execução.

**Ator principal:** aplicação cliente.

**Participantes secundários:** provedor ou modelo externo como fonte eventual de informações de uso. Critérios, evidências e referências econômicas vêm da configuração previamente preparada, sem exigir nova interação com seu responsável.

**Pré-condições:**

- houve uma tentativa de decisão, com rota selecionada ou recusa fundamentada;
- os fatos usados na avaliação foram preservados no contexto da interação em grau suficiente para explicá-la.

**Gatilho:** a decisão é concluída ou a execução termina com resultado ou erro.

**Fluxo principal:**

1. O Maestro torna disponível a identificação da rota selecionada, incluindo provedor e modelo, ou informa que nenhuma rota foi selecionada.
2. Torna disponíveis a estratégia aplicada, as restrições e os critérios obrigatórios considerados e a razão objetiva da escolha ou da recusa.
3. Quando necessários para compreender ou validar a decisão, ficam disponíveis as alternativas elegíveis comparadas, exclusões determinantes e referências às evidências aplicadas.
4. A informação econômica determinante inclui, quando aplicável, a estimativa, a referência de preço, a moeda e as hipóteses relevantes.
5. Após a execução, ficam disponíveis seu status ou erro normalizado, o uso normalizado e o custo calculado quando existirem dados suficientes.
6. Qualquer informação ausente ou incerta é identificada como tal, sem precisão fabricada.

**Fluxos alternativos e exceções:**

- **Resposta válida sem uso suficiente:** o resultado permanece disponível e o custo posterior é indicado como indisponível ou incerto.
- **Falha durante a execução:** a explicação da seleção continua disponível junto ao erro normalizado e aos fatos de execução conhecidos.
- **Detalhes comparativos desnecessários:** o Maestro pode disponibilizar somente o conjunto suficiente para compreender a decisão; este caso de uso não exige telemetria ou documentação extensa.

**Pós-condições:**

- a aplicação consegue responder qual rota foi escolhida, qual estratégia decidiu, por que a rota venceu ou por que nenhuma rota foi possível e como o custo influenciou a decisão;
- dados econômicos posteriores são distinguíveis entre calculados, indisponíveis e incertos;
- nenhuma forma específica de consulta posterior, persistência ou apresentação é pressuposta.

**Critérios de aceitação observáveis:**

- rota, estratégia, restrições determinantes e razão objetiva podem ser identificadas quando houve seleção;
- a influência econômica é compreensível pelas informações e hipóteses disponíveis;
- resultado ou erro de execução não apaga as informações necessárias para explicar a decisão;
- ausência de uso ou custo não é apresentada como valor zero nem como dado exato;
- as informações expostas não incluem credenciais nem exigem dashboard, monitoramento ou plataforma de observabilidade.

## 5. Limites do MVP

Estes casos de uso não incluem:

- agentes ou múltiplos agentes;
- memória;
- planejamento automático;
- workflows;
- orquestração, fan-out ou cadeias de múltiplos modelos;
- comparação de respostas de múltiplos modelos;
- consenso ou votação;
- marketplace;
- plugins avançados;
- plataforma de automações;
- execução distribuída;
- dashboard completo;
- observabilidade completa, monitoramento ou tracing;
- billing ou faturamento;
- Docker;
- CI/CD.

Os exemplos anteriores de chatbot, SaaS, análise de documentos, automação empresarial e produtos multi-tenant são contextos em que uma aplicação pode usar o Maestro. Eles não são funcionalidades nem casos de uso próprios do MVP.

A ausência de orquestração de múltiplos modelos no fluxo normal não define uma proibição de retry ou fallback. Essas políticas permanecem deliberadamente em aberto. Da mesma forma, os itens fora do MVP não formam automaticamente um roadmap nem uma promessa futura.

> Implemente apenas o necessário. Não adicione Docker, CI/CD, monitoramento, documentação extensa, observabilidade ou outras melhorias de infraestrutura sem minha autorização.

## 6. Decisões consolidadas

- A aplicação cliente interage com o Maestro por uma API única e independente de provedor; o responsável pela configuração ou integração prepara as alternativas; provedores e modelos externos apenas participam da execução da rota selecionada.
- Configuração válida precisa fornecer as alternativas habilitadas e os fatos indispensáveis de elegibilidade, economia, estratégia e execução, sem expor valores secretos.
- Restrições obrigatórias da configuração não podem ser enfraquecidas pela solicitação; valores padrão apenas suprem ausências.
- Elegibilidade ocorre antes da comparação econômica, e custo somente diferencia alternativas compatíveis com os demais requisitos.
- Uma estratégia econômica simples, configurada e explicável seleciona uma rota no fluxo normal.
- A execução normal usa uma única rota selecionada e não coordena nem compara respostas de múltiplos modelos.
- Solicitações inválidas, configuração global indispensável inválida, insuficiência que não deixe rota válida, ausência de rota elegível e decisões economicamente impossíveis encerram o fluxo antes da execução externa da tarefa.
- Falhas de configuração ou execução não permitem relaxar silenciosamente restrições nem inventar dados.
- A aplicação deve poder compreender a rota ou recusa, a estratégia, os fatores determinantes e o impacto econômico conhecido ou calculável.
- Estimativas e custos calculados comunicam suas referências, hipóteses e incertezas; custo calculado não é billing nem garantia de cobrança final.
- Informações insuficientes de uso ou custo permanecem explicitamente indisponíveis ou incertas.

## 7. Decisões deliberadamente em aberto

- catálogo inicial de provedores, modelos e rotas;
- quantidade, nomes, definições específicas e algoritmos das estratégias do MVP;
- critérios detalhados de elegibilidade, pesos, limiares e regras concretas de desempate;
- metodologia, métricas, origem e processo de validação das evidências e benchmarks de qualidade;
- método de estimar uso antes da execução e forma concreta de representar estimativas;
- fonte, atualização e representação concreta dos preços;
- forma de determinar disponibilidade sem criar monitoramento complexo;
- valores e mecanismo concreto de timeout;
- políticas de retry e fallback;
- formato, origem, precedência, recarga e armazenamento da configuração;
- mecanismo concreto de configuração e gestão de segredos;
- protocolo, endpoints, rotas, estruturas, schemas, headers, códigos de erro e demais detalhes do contrato da API única;
- organização e forma de entrega das informações da decisão, inclusive se ficam juntas ou separadas do resultado;
- eventual retenção ou persistência das decisões;
- linguagem, framework, banco de dados, empacotamento, infraestrutura e topologia de implantação.

Esses pontos permanecem abertos para o contrato técnico, evidências posteriores ou decisões de implementação. Não constituem requisitos futuros obrigatórios. O próximo passo documental previsto é [05-API.md](05-API.md).

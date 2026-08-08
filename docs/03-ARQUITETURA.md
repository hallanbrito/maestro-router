# Arquitetura Conceitual do MVP do Maestro Router

Este documento transforma o [Manifesto](00-MANIFESTO.md), a [Visão Geral](01-VISAO-GERAL.md) e a [Proposta de Valor](02-PROPOSTA-DE-VALOR.md) em uma arquitetura técnica conceitual para o MVP.

Ele define responsabilidades, fronteiras e fluxo. Não define tecnologias, classes, protocolos, infraestrutura nem afirma que as capacidades descritas já estejam implementadas. Em caso de conflito, o Manifesto prevalece; a Visão Geral e a Proposta de Valor o complementam sem redefini-lo.

## 1. Objetivo da arquitetura

A arquitetura do MVP deve ser a menor estrutura capaz de:

- receber de uma aplicação uma tarefa e as restrições relevantes;
- identificar alternativas de rota configuradas que possam executar essa tarefa;
- eliminar rotas incompatíveis com as restrições do contexto;
- comparar economicamente as alternativas elegíveis;
- aplicar uma estratégia simples e explícita para escolher uma rota;
- encaminhar a solicitação para execução pela rota selecionada;
- devolver uma resposta comum à aplicação;
- informar qual rota foi escolhida, por que foi escolhida e como o custo participou da decisão.

Essa estrutura precisa resolver quatro problemas centrais: evitar que a aplicação dependa dos detalhes de um provedor, concentrar a decisão de rota em um lugar compreensível, tratar custo como parte explícita da decisão e preservar as restrições definidas pelo usuário.

O MVP valida roteamento, não orquestração. Em sua execução normal, cada solicitação produz uma decisão de rota sem coordenar múltiplos modelos. Políticas de retry ou fallback permanecem deliberadamente em aberto.

Neste documento, **alternativa de rota** é uma opção configurada que associa provedor, modelo e condições conhecidas para ser avaliada. **Rota selecionada** é a escolha contextual produzida para uma solicitação depois dessa avaliação.

## 2. Princípios arquiteturais

### Simplicidade

Cada responsabilidade existe porque é necessária ao fluxo principal. Uma separação conceitual não implica um serviço, processo ou implantação independente. A arquitetura do MVP não requer distribuição.

### Separação de responsabilidades e baixo acoplamento

Decisão de rota, avaliação econômica, descrição das alternativas, integração com provedores e interface externa possuem limites próprios. Uma mudança em um adaptador ou em dados de preço não deve obrigar mudanças na lógica central.

### Independência e neutralidade de provedores

O núcleo trabalha com conceitos comuns e avalia todas as rotas pelos mesmos critérios. Nenhum provedor ocupa posição obrigatória ou recebe preferência implícita.

### Controle do usuário

Restrições de custo, capacidade, qualidade, disponibilidade e preferências aplicáveis limitam a decisão. A arquitetura não pode relaxá-las silenciosamente para conseguir executar uma rota.

### Custo explícito, não absoluto

Custo participa da elegibilidade, da comparação e da explicação. A alternativa de menor preço só pode ser escolhida entre rotas que já atendam aos demais requisitos; o Maestro não promete sempre a menor despesa possível.

### Qualidade validável e evidência

Critérios de capacidade e qualidade usados na decisão devem ser declarados e sustentados por evidências adequadas ao caso de uso. O núcleo consome esses fatos; ele não presume qualidade pela reputação do modelo nem cria, no MVP, uma plataforma automática de benchmarks.

### Decisões compreensíveis

A seleção deve produzir fatos suficientes para reconstruir sua razão. Estratégias opacas ou que não consigam explicar os fatores determinantes não são compatíveis com o MVP.

### Modularidade e extensibilidade controlada

Novos provedores entram pelas bordas e novas estratégias respeitam a mesma fronteira neutra. Essa capacidade de extensão não justifica antecipar um sistema genérico de plugins.

### Open source e execução sob controle do usuário

A arquitetura deve ser compatível com o caráter open source do projeto, não pressupõe um serviço proprietário obrigatório e preserva a possibilidade de execução local.

### Evolução incremental e documentação honesta

O MVP só contém o necessário para provar o roteamento econômico. Possibilidades futuras não geram componentes vazios nem são apresentadas como capacidades atuais.

## 3. Arquitetura de alto nível

Os componentes abaixo são responsabilidades lógicas. Eles podem coexistir em uma única unidade de execução; o diagrama não representa microserviços nem determina topologia de implantação.

~~~mermaid
flowchart LR
    A[Aplicação] -->|tarefa e restrições| I[API única]
    I --> R[Router / núcleo]
    R <-->|alternativas candidatas| G[Provider Registry]
    R <-->|estimativas e custo| C[Cost Evaluation]
    R <-->|contexto e decisão| S[Strategy Engine]
    R <-->|fatos e explicação| V[Validation]
    R <-->|solicitação e resultado comuns| D[Adaptador selecionado]
    D <-->|formato específico| P[Provedor / modelo]
    K[Configuração] -.-> G
    K -.-> C
    K -.-> S
    K -.-> D
    K -.-> R
    R -->|fatos da execução e da decisão| I
    I -->|informações disponíveis| A
~~~

O fluxo principal passa pela API única e pelo Router. O Router consulta descrições de rotas, obtém informações econômicas, solicita uma decisão à estratégia configurada, valida os fatos que explicam essa decisão e aciona o adaptador correspondente à rota escolhida no fluxo normal.

Configuração fornece dados ao fluxo, mas não toma decisões. Provedores e modelos ficam fora da fronteira do Maestro e só são acessados por seus adaptadores.

## 4. Responsabilidades dos componentes

| Componente | Responsabilidade | Recebe | Produz | Pode se comunicar com |
| --- | --- | --- | --- | --- |
| **API única** | Oferecer à aplicação uma entrada e uma saída independentes de provedor. | Tarefa, contexto e restrições em uma representação comum. | Resultado da execução ou erro e informações necessárias para compreender a decisão, disponíveis à aplicação. | Aplicação e Router. |
| **Router / núcleo** | Coordenar validação, elegibilidade, avaliação econômica, decisão, execução e composição do resultado. | Solicitação comum e configuração validada necessária ao fluxo. | Resultado da execução ou erro estruturado e fatos necessários para compreender a decisão. | API única, Provider Registry, Cost Evaluation, Strategy Engine, Validation e o adaptador selecionado. |
| **Provider Registry** | Representar as alternativas de rota disponíveis sem executar chamadas nem escolher uma delas. | Definições configuradas de provedores, modelos, adaptadores, capacidades, critérios de qualidade, referências às evidências disponíveis e condições conhecidas. | Descritores neutros das alternativas candidatas. | Router e configuração. |
| **Cost Evaluation** | Estimar e comparar o impacto econômico antes da execução e calcular o custo relevante depois dela quando houver dados suficientes. | Características da solicitação, rotas candidatas, dados de preço e, após a chamada, uso normalizado. | Estimativas comparáveis, hipóteses utilizadas e custo calculado após a execução. | Router e configuração de preços. |
| **Strategy Engine** | Aplicar a estratégia configurada a alternativas elegíveis segundo critérios explícitos. | Restrições, descritores neutros das rotas e avaliações econômicas. | Rota escolhida ou indicação de que nenhuma rota é possível, sempre com razões. | Router e configuração da estratégia. |
| **Validation** | Verificar se a decisão está completa e justificável pelos fatos disponíveis e formar seu resumo explicável. | Restrições aplicadas, alternativas avaliadas, decisão, base econômica, referências e limitações das evidências relevantes e status ou erro normalizado da execução. | Informações da decisão com razões e eventuais lacunas declaradas. | Router. |
| **Adaptador de provedor** | Isolar autenticação, formatos, endpoints, respostas, informações de uso e erros específicos de um provedor. | Solicitação comum, identificação da rota e acesso seguro às credenciais necessárias. | Chamada específica ao provedor e resultado, uso ou erro normalizados para o núcleo. | Router, configuração estritamente operacional e provedor externo correspondente. |
| **Configuração** | Declarar e validar estruturalmente as opções e limites necessários sem incorporar lógica de decisão. | Definições mantidas pelo usuário e referências a segredos externos. | Rotas, preços, estratégia, restrições e parâmetros operacionais validados. | Componentes que consomem cada parte da configuração. |

**Validation** não é um avaliador automático da qualidade da resposta, uma plataforma de benchmarks ou um sistema de observabilidade. No MVP, sua função é assegurar que os dados usados e produzidos pela decisão sejam coerentes e suficientes para explicá-la.

As comunicações seguem estas regras:

- a aplicação se comunica apenas com a API única e não acessa diretamente adaptadores ou provedores;
- o Strategy Engine não chama provedores e não recebe credenciais;
- o Cost Evaluation não escolhe a rota;
- o Provider Registry descreve alternativas, mas não executa nem ranqueia;
- adaptadores não aplicam regras de roteamento;
- somente o Router coordena o fluxo completo.

## 5. Fluxo de uma requisição

1. A aplicação envia a tarefa, o contexto necessário e as restrições aplicáveis pela API única.
2. A API valida a estrutura mínima da entrada e a converte para a representação comum do Maestro.
3. O Router confirma que a configuração já validada contém os dados necessários à solicitação e combina limites obrigatórios com suas restrições. Valores padrão apenas preenchem ausências; não substituem nem enfraquecem restrições explícitas.
4. O Provider Registry fornece as alternativas de rota configuradas e habilitadas, descritas por fatos neutros como provedor, modelo, capacidades, condições conhecidas e referência de preço.
5. O Router forma um conjunto preliminar eliminando alternativas incompatíveis com capacidade, qualidade, disponibilidade conhecida ou preferências obrigatórias. Essa análise usa dados explícitos; não exige uma chamada adicional a outro modelo.
6. O Cost Evaluation estima o custo das rotas restantes com as informações disponíveis e declara as hipóteses da estimativa. O Router então elimina as alternativas que excedam limites econômicos obrigatórios ou cujo custo não possa ser avaliado quando esse limite ou a estratégia depender dele.
7. O Strategy Engine aplica a estratégia configurada aos candidatos elegíveis e retorna uma única rota ou a impossibilidade de escolher, sempre com os critérios determinantes e as razões.
8. Validation verifica se a escolha, ou a ausência dela, está sustentada pelos fatos e contém a explicação necessária. Se não houver rota, o Router encerra o fluxo sem chamar um provedor e mantém disponíveis as razões do erro; caso contrário, consolida as informações iniciais da decisão e continua.
9. No fluxo normal, o Router encaminha a solicitação comum ao adaptador associado à rota escolhida.
10. O adaptador traduz a solicitação, realiza a chamada ao provedor e normaliza a resposta, as informações de uso ou o erro.
11. Quando houver dados de uso suficientes, o Cost Evaluation calcula o custo da execução usando a referência de preço aplicável. Ausência ou incerteza permanece explícita.
12. O Router torna disponíveis status, uso e custo da execução para compor as informações da decisão, e Validation verifica sua completude final. O resultado do modelo e as informações necessárias para compreender a decisão ficam disponíveis à aplicação, sem que esta arquitetura determine como serão organizados ou entregues pela API.

O caminho normal permanece linear: analisar restrições, decidir uma rota, executar um modelo e responder. Não há planejamento, fan-out, cadeia de modelos nem workflow escondido nesse fluxo.

## 6. Abstração de provedores

### Core do Maestro

O núcleo conhece apenas conceitos neutros necessários ao roteamento:

- solicitação e resposta comuns;
- restrições e preferências;
- rota, provedor e modelo identificados de forma neutra;
- capacidades e condições comparáveis;
- estimativa, uso e custo;
- decisão e erro normalizados.

O núcleo decide a partir desses conceitos e coordena uma execução. Ele não conhece payloads, cabeçalhos, endpoints, bibliotecas, códigos de erro ou mecanismos de autenticação próprios de um provedor.

### Integrações e adaptadores

Cada adaptador concentra apenas o necessário para conversar com seu provedor:

- traduzir a solicitação comum para o formato externo;
- aplicar a autenticação sem expor o segredo ao restante da lógica;
- realizar a chamada;
- traduzir resposta, uso e erro para a representação comum;
- traduzir apenas as rotas cujos modelos e capacidades estejam declarados no Provider Registry.

Adicionar um provedor requer um adaptador e suas definições de rota e preço. Isso não deve exigir alterações nas estratégias ou nas regras centrais. Da mesma forma, retirar um provedor não pode tornar outro conceitualmente obrigatório.

Uma particularidade externa que não possa ser representada pelos conceitos comuns não deve vazar como exceção para o Strategy Engine. Seu suporte exige uma extensão intencional do contrato neutro, justificada por uma necessidade real; até lá, ela permanece fora do MVP.

O formato concreto desse contrato, a forma de registrar adaptadores e o catálogo inicial de provedores permanecem decisões posteriores.

## 7. Estratégias de roteamento

A decisão possui duas fases:

1. **Elegibilidade:** aplicar restrições obrigatórias e excluir rotas incompatíveis.
2. **Comparação:** ordenar ou selecionar somente entre as rotas elegíveis.

Essa separação impede que um ganho econômico relaxe requisitos de capacidade, qualidade, disponibilidade ou preferências obrigatórias.

Para provar o valor central com a menor complexidade, o MVP aplica uma estratégia econômica simples e explícita a cada decisão, definida pela configuração. As estratégias específicas disponíveis e sua quantidade permanecem em aberto para documentação posterior. A estratégia aplicada compara o impacto econômico somente depois da elegibilidade e escolhe uma rota sem tratar custo como critério absoluto.

O algoritmo concreto de cada estratégia não é definido por esta arquitetura. Os documentos anteriores adiam essa escolha e exigem que a adoção de qualquer estratégia seja sustentada por critérios e evidências adequados. Diferentes estratégias poderão usar os mesmos fatos neutros e variar apenas na regra explícita de comparação, sem alterar o núcleo nem os adaptadores.

A estratégia aplicada recebe apenas fatos neutros e produz:

- identificação da estratégia aplicada;
- rota selecionada ou ausência de rota;
- alternativas elegíveis comparadas;
- critério determinante e regra de desempate utilizada;
- razão objetiva da decisão.

A quantidade de estratégias do MVP não é definida por esta arquitetura. Essa abertura não exige uma biblioteca de estratégias, um motor genérico de regras, plugins de seleção ou um classificador aprendido. Cada estratégia somente deve ser adotada quando uma necessidade real e evidências adequadas justificarem sua regra.

Toda estratégia adotada deverá:

- usar a mesma representação neutra de candidatos;
- respeitar restrições obrigatórias antes de comparar;
- avaliar provedores pelos mesmos critérios;
- não chamar provedores diretamente;
- produzir uma justificativa compreensível;
- ser validável no contexto em que será usada.

O critério econômico exato, pesos, limiares, critérios detalhados de qualidade e as regras de desempate aplicáveis permanecem em aberto para os requisitos e evidências correspondentes.

## 8. Custos

### Conhecimento de preços

Dados de preço ficam separados do Router, das estratégias e dos adaptadores. Para cada rota, o conjunto mínimo deve identificar, quando aplicável:

- provedor e modelo;
- unidade ou base de cobrança;
- valores relevantes;
- moeda;
- vigência, versão ou outra referência que permita saber qual preço foi usado;
- fonte ou responsabilidade pela manutenção do dado.

No MVP, esses dados podem ser fornecidos pela configuração. Não é necessário criar um serviço de atualização automática de preços.

### Estimativa e comparação

Antes da execução, o Cost Evaluation usa as características conhecidas da solicitação e os preços configurados para produzir uma estimativa. A estimativa deve carregar suas hipóteses e só pode ser comparada com outras quando os dados forem compatíveis.

Uma rota sem dados econômicos suficientes não pode participar silenciosamente de uma estratégia que dependa de custo. Ela deve ser marcada como não comparável e ficar inelegível para essa decisão. Se nenhuma alternativa comparável restar, o Maestro informa que não pode decidir economicamente.

Um limite econômico obrigatório que não possa ser avaliado torna a rota inelegível; ele nunca é ignorado silenciosamente. O MVP pode tratar limites por solicitação sem criar controle financeiro acumulado.

### Custo após a execução

Quando o provedor informar uso suficiente, o adaptador o normaliza e o Cost Evaluation calcula o custo com a mesma referência de preço. Esse valor é um custo calculado pelo Maestro, não uma fatura nem uma garantia de correspondência exata com a cobrança final do provedor.

Quando não houver informação suficiente, o custo permanece identificado como indisponível ou incerto; não deve ser inventado nem apresentado como exato.

O MVP não inclui faturamento, cobrança, créditos, contabilidade, conciliação financeira, previsão orçamentária ou um ledger de uso.

## 9. Explicabilidade da decisão

As informações necessárias para compreender a decisão de roteamento devem existir e estar disponíveis à aplicação. Quando aplicável, elas permitem identificar:

- modelo e provedor selecionados, além das condições relevantes da rota;
- estratégia utilizada;
- restrições e critérios obrigatórios considerados;
- motivo objetivo da escolha;
- informação econômica determinante, com estimativa, referência de preço, moeda e hipóteses relevantes;
- resultado da execução ou erro normalizado;
- uso normalizado e custo calculado após a execução, quando disponíveis;
- indicação explícita de qualquer dado ausente ou incerto.

Quando necessário para compreender ou validar a decisão, também podem ficar disponíveis detalhes comparativos, como alternativas consideradas, exclusões determinantes, estimativas por alternativa e referências às evidências aplicadas. Esses detalhes não incluem o conteúdo da resposta do modelo nem exigem telemetria adicional.

Essas informações devem permitir responder qual modelo foi usado, qual estratégia decidiu, por que a rota venceu e quais dados econômicos influenciaram a escolha.

A forma de organizar, serializar e disponibilizar essas informações, inclusive se ficam juntas ou separadas do resultado da execução, pertence ao contrato técnico a ser definido em [05-API.md](05-API.md). A arquitetura do MVP não exige banco de dados, retenção permanente, dashboards, tracing distribuído, pipeline de métricas ou uma plataforma de observabilidade.

## 10. Configuração

O MVP precisa conhecer apenas:

- provedores, modelos e rotas habilitados;
- associação entre rota e adaptador;
- capacidades, critérios de qualidade, referências às evidências disponíveis, limites e condições conhecidas usados na elegibilidade;
- dados de preço;
- estratégia selecionada e seus parâmetros indispensáveis;
- restrições obrigatórias e valores padrão;
- referências a credenciais;
- parâmetros operacionais essenciais para realizar a chamada, quando necessários.

Configuração obrigatória e restrições da solicitação se acumulam. A solicitação pode restringir o conjunto permitido, mas não habilitar uma rota desativada nem enfraquecer um limite obrigatório. Valores padrão são usados somente quando a solicitação não traz uma definição correspondente.

A configuração deve ser validada antes de participar de uma decisão. Erros precisam identificar o dado inválido sem expor segredos.

Credenciais não pertencem ao modelo de domínio, aos dados de preço, às estratégias, às informações da decisão nem às mensagens de erro. A configuração guarda apenas referências; o valor secreto é fornecido ao adaptador selecionado por um mecanismo seguro de execução.

Formato, armazenamento, precedência detalhada, recarga da configuração e mecanismo concreto de segredos permanecem abertos. O MVP não exige serviço de configuração, interface administrativa ou banco de dados.

## 11. Tratamento de falhas e limites

| Situação | Comportamento essencial |
| --- | --- |
| **Solicitação inválida** | Recusar antes de qualquer chamada externa e informar quais dados necessários estão ausentes ou inválidos. |
| **Configuração inválida** | Se o erro for global e indispensável, impedir o fluxo; se estiver restrito a uma rota, torná-la inelegível e declarar o motivo. Nunca adivinhar valores nem expor segredos. |
| **Nenhuma rota elegível** | Não chamar provedor; retornar erro compreensível com as restrições ou ausências que impediram a decisão. |
| **Provedor conhecido como indisponível antes da decisão** | Excluir sua rota da elegibilidade e registrar esse motivo. O MVP não exige monitoramento ativo de saúde. |
| **Erro, indisponibilidade ou timeout durante a chamada** | O adaptador normaliza o erro e mantém disponíveis as informações da decisão e da execução. O comportamento posterior depende de políticas de retry ou fallback ainda não definidas. |
| **Preço insuficiente para comparação** | Marcar a rota como não comparável e não a usar em uma decisão econômica. |
| **Uso insuficiente após uma resposta válida** | Devolver a resposta e identificar o custo posterior como indisponível ou incerto. |

O MVP não coordena múltiplos modelos como parte da execução normal de uma tarefa. Não há comparação de respostas durante a execução, consenso, votação ou pipelines multi-modelo. Políticas de retry ou fallback permanecem deliberadamente em aberto e não são definidas por esta arquitetura. Circuit breakers, filas e resiliência distribuída não pertencem ao MVP.

Em nenhuma falha o Maestro reduz silenciosamente requisitos de qualidade, capacidade, custo ou preferência para obter uma resposta.

## 12. Fronteiras arquiteturais

> O núcleo do Maestro não deve depender dos detalhes específicos de um provedor.

| Fronteira | Pertence | Não pertence |
| --- | --- | --- |
| **Núcleo / Router** | Coordenação do fluxo, aplicação de limites, elegibilidade, interação com a estratégia, execução da rota escolhida e composição do resultado. | Payloads externos, autenticação específica, preços embutidos ou favorecimento de provedor. |
| **Strategy Engine** | Comparação de alternativas neutras e produção de decisão justificável. | Chamadas externas, credenciais, tradução de formatos ou alteração silenciosa de restrições. |
| **Provider Registry** | Descrições configuradas de rotas, modelos, provedores, capacidades e condições conhecidas. | Execução, ranking e lógica de negócio da estratégia. |
| **Cost Evaluation** | Dados econômicos separados, estimativas comparáveis e custo calculado. | Billing, cobrança ou escolha final da rota. |
| **Validation** | Coerência da decisão e composição da explicação a partir dos fatos disponíveis. | Observabilidade completa, julgamento automático de qualidade ou benchmark como serviço. |
| **Adaptadores** | Detalhes de API, autenticação, tradução de solicitação, resposta, uso e erros. | Critérios econômicos, políticas de elegibilidade ou decisão de rota. |
| **Configuração** | Declaração de opções, limites, preços, estratégia e referências a segredos. | Execução de regras, código de integração ou armazenamento inseguro de credenciais. |
| **API única** | Entrada e saída comuns para a aplicação. | Acesso direto a provedores ou lógica específica de um deles. |

As dependências apontam para conceitos neutros do núcleo. Detalhes externos permanecem nos adaptadores, e dados variáveis permanecem na configuração ou nos catálogos correspondentes.

## 13. Fora do escopo do MVP

Não fazem parte desta arquitetura inicial:

- agentes, múltiplos agentes e frameworks de agentes;
- planejamento automático, memória e workflows;
- orquestração, fan-out, comparação, consenso, votação ou pipelines envolvendo múltiplos modelos;
- plataforma genérica de automações;
- marketplace e sistema de plugins avançados;
- execução distribuída, filas e coordenação entre nós;
- microserviços exigidos por antecipação;
- gateway corporativo amplo ou plataforma genérica de orquestração;
- subsistema próprio de multi-tenancy ou políticas empresariais complexas;
- dashboard completo;
- plataforma de observabilidade, monitoramento ou tracing;
- plataforma automática de benchmarks ou julgamento de qualidade;
- billing, faturamento ou infraestrutura financeira;
- armazenamento permanente obrigatório das informações de decisão;
- treinamento ou hospedagem de modelos;
- Docker, CI/CD ou outras melhorias de infraestrutura não autorizadas;
- escolha antecipada de linguagem, framework, banco de dados, protocolo ou provedor de infraestrutura.

O Maestro também não garante a rota universalmente mais barata, a maior qualidade, economia ou ausência de falhas. Casos de uso como SaaS, chatbot e produtos multi-tenant ilustram possíveis aplicações; eles não criam componentes adicionais no MVP. Restrições de um tenant podem chegar na solicitação, mas cadastro de tenants e gestão do ciclo de vida de suas políticas permanecem responsabilidade da aplicação.

## 14. Evolução futura

| Estágio | Alcance |
| --- | --- |
| **MVP** | Uma solicitação, uma decisão de rota, execução pela rota selecionada no fluxo normal, API comum, estratégia econômica simples aplicada a cada decisão, adaptadores de provedores, custo explícito e explicação da escolha. |
| **Versões futuras, após validação** | Inclusão incremental de adaptadores e amadurecimento de estratégias simples, critérios e evidências quando benchmarks relevantes demonstrarem necessidade e benefício. |
| **Ideia em avaliação** | Orquestração inteligente de múltiplos modelos, somente após o amadurecimento do roteamento econômico, necessidade real e valor verificável. |

Itens fora do escopo não formam automaticamente um roadmap. Em especial, agentes, memória, workflows, marketplace, execução distribuída e dashboard não são promessas futuras.

As fronteiras atuais permitem evolução sem antecipá-la: um novo provedor pode entrar por um adaptador, e uma nova estratégia pode usar os mesmos descritores neutros. Nenhuma dessas possibilidades exige componentes adicionais antes de existir uma necessidade comprovada.

## 15. Decisões arquiteturais principais

| Decisão | Razão |
| --- | --- |
| **Responsabilidades lógicas em uma arquitetura simples, sem distribuição obrigatória** | Prova o fluxo principal com menos complexidade e preserva execução local. |
| **A execução normal não coordena múltiplos modelos** | Mantém o MVP centrado em roteamento sem transformar a execução de uma tarefa em orquestração. Políticas de retry ou fallback permanecem abertas. |
| **API única com representação neutra** | Desacopla a aplicação dos formatos dos provedores sem definir prematuramente o contrato técnico. |
| **Router coordena; componentes especializados não controlam o fluxo completo** | Mantém responsabilidades claras e evita lógica de decisão espalhada. |
| **Provider Registry descreve rotas e adaptadores isolam integrações externas** | Permite substituir provedores sem acoplar o núcleo às suas APIs. |
| **Elegibilidade antecede comparação econômica** | Impede que custo viole capacidade, qualidade, disponibilidade ou restrições do usuário. |
| **Uma estratégia econômica simples e explicável é aplicada a cada decisão** | Demonstra a proposta central sem definir antecipadamente quais estratégias ou quantas estarão disponíveis no MVP. |
| **Preços separados da lógica e estimativa distinta de custo calculado** | Permite atualizar dados e comunicar incerteza sem criar billing. |
| **As informações de explicação ficam disponíveis à aplicação** | Garante transparência sem antecipar o contrato técnico da API nem exigir uma plataforma de observabilidade. |
| **Segredos ficam fora do domínio e chegam apenas ao adaptador selecionado** | Evita que credenciais contaminem decisão, configuração pública ou resposta. |
| **Falhas não relaxam restrições silenciosamente** | Preserva previsibilidade, controle do usuário e compreensão da execução sem fechar políticas de retry ou fallback. |
| **Extensão ocorre por fronteiras existentes, não por infraestrutura antecipada** | Mantém modularidade e evolução incremental sem overengineering. |

### Decisões deliberadamente em aberto

Permanecem para requisitos, evidências ou decisões tecnológicas posteriores:

- catálogo inicial de provedores, modelos e rotas;
- formato, protocolo, endpoints e contrato exato da API única;
- representação concreta de solicitações, respostas, erros e informações da decisão;
- metodologia, métricas e origem dos benchmarks de qualidade;
- critérios detalhados de elegibilidade, pesos, limiares e desempate;
- quantidade, definição específica e algoritmo das estratégias econômicas do MVP;
- método de estimar uso antes da execução;
- fonte, processo de atualização e representação concreta dos preços;
- forma de determinar disponibilidade sem criar monitoramento complexo;
- valores e mecanismo concreto de timeout;
- políticas de retry e fallback;
- formato, origem, precedência e recarga da configuração;
- mecanismo concreto de gestão de segredos;
- retenção ou persistência futura de decisões;
- linguagem, frameworks, banco de dados, protocolo interno, empacotamento e topologia de implantação.

Manter esses pontos abertos evita compromissos prematuros. Eles não impedem a compreensão do fluxo, das fronteiras nem do valor que a arquitetura do MVP precisa provar.

# O que é o Maestro Router

O Maestro Router é uma plataforma open source voltada ao roteamento econômico de modelos de inteligência artificial. Sua função é introduzir uma camada de decisão entre uma aplicação e os modelos que podem atender às suas solicitações.

O Maestro não cria, treina nem substitui modelos de IA. Ele decide qual rota utilizar para cada tarefa, de acordo com critérios explícitos. Uma rota representa uma escolha contextual que pode considerar o provedor, o modelo e as condições relevantes para a execução.

O projeto parte do princípio de que não existe uma escolha universalmente adequada para todas as tarefas. Capacidade, custo, qualidade e disponibilidade variam, assim como as restrições de cada usuário. Por isso, o Maestro busca tornar a seleção controlável, justificável e independente de preferências comerciais.

A identidade atual do produto está no roteamento econômico. A eventual orquestração inteligente de múltiplos modelos pertence a uma possibilidade futura e não representa uma capacidade atual nem um requisito do MVP.

# O problema

Aplicações que utilizam inteligência artificial frequentemente começam integradas a um único modelo ou provedor. Essa escolha pode ser suficiente no início, mas tende a criar dificuldades quando o volume de uso cresce, os custos mudam ou surgem requisitos diferentes dos originalmente previstos.

Os principais desafios são:

- dependência de um provedor, que reduz a liberdade de adaptação;
- aumento ou imprevisibilidade dos custos conforme o uso cresce;
- dificuldade para trocar de modelo sem afetar a aplicação;
- falta de transparência sobre qual opção foi utilizada e por quê;
- decisões complexas entre custo e qualidade;
- diferenças de capacidade e disponibilidade entre modelos;
- dificuldade para aplicar restrições distintas a tarefas ou usuários diferentes.

Escolher somente pela menor estimativa de custo pode comprometer requisitos de qualidade. Escolher somente pela maior capacidade disponível pode gerar desperdício. Fixar uma única opção simplifica a decisão inicial, mas pode tornar a aplicação menos adaptável.

O problema, portanto, não é apenas acessar modelos. É decidir de forma consistente quando e por que utilizar cada possibilidade, mantendo controle sobre custos, critérios e dependências.

# A solução

O Maestro Router introduz uma camada de decisão. Em vez de vincular toda solicitação a uma escolha fixa, a aplicação apresenta a tarefa e as restrições que devem orientar seu atendimento. O Maestro avalia essas informações e seleciona uma rota compatível com o contexto.

Uma rota pode considerar:

- custo aceitável;
- qualidade requerida;
- disponibilidade;
- capacidade necessária;
- preferências e restrições definidas pelo usuário.

O Maestro não procura declarar um modelo como o melhor de forma absoluta. Seu objetivo é escolher uma rota adequada aos critérios da execução. Duas solicitações semelhantes podem seguir rotas diferentes quando possuem restrições diferentes.

As decisões devem permanecer neutras em relação aos provedores. Relações comerciais, patrocínios ou preferências da equipe não podem determinar uma escolha. Estratégias somente devem ser adotadas ou alteradas quando houver evidências relevantes, como benchmarks adequados ao contexto avaliado.

## Diferença em relação a um proxy simples

Um proxy simples normalmente recebe uma solicitação e a encaminha para um destino previamente definido. O Maestro adiciona responsabilidade de decisão: considera restrições, aplica uma estratégia, seleciona uma rota e torna os motivos dessa escolha compreensíveis.

Essa diferença não significa adicionar complexidade sem necessidade. Quando não existe uma decisão relevante a ser tomada, um proxy ou uma integração direta pode ser a solução mais apropriada. O Maestro agrega valor quando escolher a rota é parte real do problema.

# Como funciona (alto nível)

O fluxo conceitual do Maestro Router é:

Aplicação  
↓  
Maestro Router  
↓  
Análise da restrições 
↓  
Escolha da estratégia configurada
↓  
Escolha da rota  
↓  
Execução  
↓  
Resposta

Nesse fluxo:

1. A aplicação apresenta uma tarefa e as restrições relevantes.
2. O Maestro analisa os critérios que devem orientar a decisão.
3. Uma estratégia determina como comparar as alternativas elegíveis.
4. Uma rota é escolhida de acordo com essa estratégia.
5. A tarefa segue para execução pelo modelo associado à rota.
6. A resposta retorna à aplicação, preservando a possibilidade de compreender a decisão tomada.

O fluxo descreve responsabilidades do produto, não sua organização interna. Detalhes técnicos pertencem a documentos específicos e devem ser definidos somente quando necessários.

# Componentes conceituais

Os componentes abaixo representam responsabilidades conceituais. Eles não definem uma arquitetura interna nem afirmam o estado de implementação de cada capacidade.

- **Router:** coordena o processo de decisão e encaminha a solicitação pela rota selecionada.
- **Strategy Engine:** aplica a estratégia escolhida para avaliar alternativas segundo critérios explícitos.
- **Provider Registry:** representa os provedores e modelos que podem ser considerados, junto às características necessárias para diferenciá-los.
- **Cost Evaluation:** considera o impacto econômico das alternativas e das restrições de custo informadas pelo usuário.
- **Validation:** permite analisar se uma estratégia e a rota selecionada podem ser justificadas por critérios claros, dados disponíveis e evidências relevantes.

Essas responsabilidades devem permanecer separáveis e compreensíveis. A forma concreta de realizá-las não é definida neste documento.

# Casos de uso

O Maestro Router pode ser relevante em produtos com tarefas variadas ou necessidade de controle sobre escolhas de modelos. Exemplos conceituais incluem:

- **Chatbot:** selecionar rotas diferentes conforme a complexidade da interação, os limites de custo e a qualidade necessária.
- **Assistente de programação:** considerar capacidades distintas para explicação, geração, revisão ou análise, sem assumir que todas as tarefas exigem a mesma opção.
- **Automação empresarial:** aplicar restrições específicas a processos com diferentes níveis de criticidade e orçamento.
- **Análise de documentos:** escolher rotas de acordo com volume, tipo de análise, capacidade requerida e critérios de qualidade.
- **Aplicações SaaS:** reduzir o acoplamento permanente a um único fornecedor e controlar o custo de diferentes funcionalidades.
- **Produtos multi-tenant:** respeitar limites, preferências e políticas distintas para cada contexto de uso.

Esses exemplos demonstram onde o roteamento pode gerar valor. Eles não constituem funcionalidades adicionais nem garantem adequação automática a todos os cenários.

# Quando utilizar

O Maestro tende a agregar valor quando:

- a aplicação precisa considerar mais de um modelo ou provedor;
- as tarefas apresentam requisitos diferentes de capacidade ou qualidade;
- o custo de uso é relevante e precisa ser controlado;
- existe necessidade de explicar por que uma rota foi escolhida;
- mudanças de disponibilidade não devem impor dependência permanente;
- diferentes usuários ou contextos possuem restrições próprias;
- estratégias de seleção precisam ser avaliadas por evidências;
- a liberdade de substituição entre opções faz parte dos requisitos do produto.

O público principal inclui equipes de desenvolvimento e organizações que tratam a escolha do modelo como uma decisão de produto, e não apenas como uma configuração fixa.

# Quando NÃO utilizar

Um projeto simples que utiliza apenas um modelo provavelmente não precisa do Maestro Router quando:

- a integração direta já atende ao caso de uso;
- não existe necessidade concreta de escolher entre rotas;
- o volume e o custo são baixos ou previsíveis;
- trocar de modelo ou provedor não é uma preocupação relevante;
- não há critérios diferentes entre tarefas ou usuários;
- o esforço de introduzir uma camada de decisão seria maior que o benefício esperado.

O Maestro também não deve ser adotado, no escopo atual, por projetos que dependam de agentes, planejamento automático, memória ou orquestração de múltiplos modelos. Essas capacidades não fazem parte do MVP.

Reconhecer esses limites é parte da honestidade técnica do projeto. O Maestro não deve ser apresentado como solução necessária para todo uso de inteligência artificial.

# Objetivos do MVP

O MVP tem escopo deliberadamente restrito. Seu objetivo é validar a proposta central antes de qualquer expansão.

O MVP contempla apenas:

- **roteamento econômico:** selecionar rotas segundo critérios econômicos explícitos;
- **abstração de provedores:** reduzir o acoplamento da aplicação a uma escolha permanente;
- **estratégias simples:** aplicar regras de seleção compreensíveis e limitadas;
- **transparência das decisões:** permitir identificar a rota escolhida e os fatores relevantes;
- **controle de custos:** considerar restrições de custo e tornar seu impacto compreensível;
- **API única:** oferecer uma interface de integração comum, sem definir neste documento seu formato ou contrato.

O MVP não inclui agentes, orquestração, memória ou workflows. O escopo acima descreve objetivos do MVP e não deve ser interpretado como afirmação de que todas essas capacidades já estão implementadas.

# Fora do escopo do MVP

Estão explicitamente fora do escopo do MVP:

- múltiplos agentes;
- planejamento automático;
- memória;
- workflows;
- orquestração de múltiplos modelos;
- marketplace;
- plugins avançados;
- execução distribuída;
- dashboard completo.

Esses itens são possibilidades que poderão ser avaliadas no futuro. Não são requisitos atuais, não estão prometidos e não devem orientar o MVP antes que exista necessidade real e evidência suficiente. A presença de um item nesta lista não significa que ele será desenvolvido.

# Filosofia de evolução

O Maestro Router evolui de forma incremental. Cada etapa deve produzir valor próprio, ter limites claros e ser validada antes da expansão seguinte.

1. **Primeiro, roteamento:** estabelecer a escolha econômica de rotas, a independência de provedores e a transparência das decisões.
2. **Depois, estratégias:** validar e amadurecer estratégias simples com benchmarks relevantes, ampliando-as somente quando os resultados justificarem a mudança.
3. **Somente no futuro, orquestração:** considerar a coordenação de múltiplos modelos caso o roteamento esteja maduro e existam necessidades comprovadas.

Essa sequência expressa uma ordem de prioridades, não uma promessa de funcionalidades futuras. O projeto não deve antecipar complexidade nem transformar possibilidades em requisitos atuais.

# Relação com outros documentos

Este documento complementa o [Manifesto do Maestro Router](00-MANIFESTO.md). O Manifesto define a identidade permanente, os valores e os princípios inegociáveis do projeto. Esta visão geral traduz essa identidade em uma explicação objetiva do problema, da solução, do público e dos limites atuais.

Em caso de conflito, os princípios estabelecidos no Manifesto prevalecem. Este documento não substitui nem redefine essa identidade.

# Decisões tomadas

- O Maestro Router é uma plataforma open source de roteamento econômico de modelos de IA.
- O produto escolhe uma rota contextual, não um modelo universalmente melhor.
- O Maestro não cria modelos de inteligência artificial.
- Restrições do usuário orientam a decisão de rota.
- Custo, qualidade, disponibilidade, capacidade e preferências podem participar da avaliação.
- Decisões devem ser transparentes, neutras entre provedores e sustentadas por evidências.
- Um proxy simples continua sendo adequado quando não há uma decisão de rota relevante.
- O MVP permanece limitado a roteamento econômico, abstração de provedores, estratégias simples, transparência, controle de custos e API única.
- Orquestração de múltiplos modelos não faz parte do MVP.
- A evolução será incremental e não criará compromissos antecipados com funcionalidades futuras.

# Decisões adiadas

As seguintes decisões foram propositalmente deixadas para documentos futuros:

- critérios detalhados de elegibilidade e comparação de rotas;
- metodologia exata dos benchmarks de custo e qualidade;
- catálogo inicial de provedores e modelos;
- formato e contrato da API única;
- organização interna das responsabilidades conceituais;
- estratégias específicas que serão incluídas no MVP;
- experiência de configuração e apresentação das decisões;
- critérios para avaliar possibilidades posteriores ao MVP.

Adiar essas decisões evita criar compromissos prematuros e mantém este documento no nível de visão geral.

# Próximos passos

O próximo documento é [02-PROPOSTA-DE-VALOR.md](02-PROPOSTA-DE-VALOR.md), que detalhará o valor oferecido pelo Maestro Router aos seus públicos sem alterar os limites estabelecidos nesta visão geral e no Manifesto.

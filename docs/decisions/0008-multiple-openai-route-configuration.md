# ADR 0008 — Configuração operacional de múltiplas rotas OpenAI

## Contexto

A composição OpenAI atual constrói uma única rota a partir das entradas aprovadas
pelas ADRs 0003, 0006 e 0007. Essa rota já pode carregar uma referência de preço
e uma previsão estática de uso, permitindo estimativa pré-execução e aplicação de
`max_estimated_cost`. Entretanto, uma única alternativa não demonstra a comparação
econômica que constitui o valor central do Maestro Router.

O núcleo, o contrato público e a decisão de roteamento já suportam múltiplas rotas,
estimativas por alternativa, a estratégia `lowest-estimated-cost`, desempate por
`route.id` e isolamento de falhas locais quando ainda existe um universo confiável.
Falta somente fechar a primeira configuração operacional que forneça mais de uma
rota executável ao bootstrap OpenAI sem alterar essas regras.

Esta ADR registra exclusivamente essa configuração para uma implementação futura.
A W18 é documental: não implementa parsing, validação, composição, variáveis
executáveis, testes nem qualquer outro comportamento de runtime.

## Decisão

### Mecanismo multirrota

Uma implementação futura poderá aceitar a variável opcional:

```text
MAESTRO_OPENAI_ROUTES_JSON
```

Seu valor será um único documento JSON fechado, mantido pelo operador, que contém
o conjunto de rotas OpenAI do snapshot. `OPENAI_API_KEY` continuará sendo uma
entrada obrigatória e separada. A credencial não será incorporada ao documento.

Quando `MAESTRO_OPENAI_ROUTES_JSON` estiver presente, inclusive como string vazia
ou formada somente por espaços, o bootstrap entrará no modo multirrota e validará
o documento inteiro antes de construir `AsyncOpenAI` ou a aplicação. Não haverá
fallback silencioso para o modo de rota única se o documento tiver sido fornecido
e for inválido.

O valor de nível superior será um objeto contendo exatamente o membro obrigatório
`routes`. `routes` será um array não vazio de objetos de rota. Um documento válido
poderá conter uma ou mais rotas; duas ou mais rotas válidas tornam efetiva a
comparação econômica, enquanto uma única rota válida conserva as regras atuais de
candidato único. A configuração não cria catálogo remoto, arquivo próprio, recarga
dinâmica nem formato geral definitivo para outros provedores.

Esta ADR não fornece documento de exemplo: qualquer valor de rota, modelo, preço
ou previsão pertence ao operador. A topologia normativa é `routes[]`, com os
quatro campos de rota definidos abaixo; as estruturas econômicas aninhadas são
as mesmas já aprovadas pelas ADRs 0006 e 0007.

### Documento fechado por rota

Cada membro de `routes` será um objeto fechado contendo exatamente:

- `route_id`;
- `model`;
- `price_reference`;
- `estimated_usage`.

Todos os quatro campos serão obrigatórios. Não haverá `provider`, `adapter_id`,
`enabled`, capacidades, critérios de qualidade, indisponibilidade, credencial ou
texto livre nesse primeiro formato. O provedor, o adaptador e o estado habilitado
serão fixados pela composição conforme esta ADR; as demais dimensões continuarão
com o comportamento mínimo da composição OpenAI atual.

`price_reference` repetirá exatamente a estrutura fechada, a gramática e as
declarações de completude aprovadas pela ADR 0006. `estimated_usage` repetirá
exatamente a estrutura fechada, as duas quantidades inteiras positivas e a
declaração `applicability_confirmed = true` aprovadas pela ADR 0007. Esses objetos
não repetirão rota, provedor ou modelo: a composição os vinculará ao objeto de
rota que os contém.

No modo multirrota, preço e previsão serão próprios e obrigatórios para cada rota.
Uma rota não herdará, compartilhará nem usará como padrão o preço ou a previsão
de outra. A ausência ou invalidade de qualquer um desses objetos tornará aquela
rota localmente inválida; não produzirá estimativa `unavailable`, preço zero ou
previsão implícita.

### Identidade e unicidade

`route_id` e `model` serão strings não brancas formadas por sequências Unicode bem
formadas; surrogate isolado será inválido. Seus valores serão opacos e comparados
de forma exata, sem trim, alteração de caixa, resolução de aliases ou normalização
Unicode implícita. O valor recebido será também o valor publicamente identificável
nos campos já aprovados por `docs/05-API.md`.

Dentro de um snapshot multirrota:

- cada `route_id` será único;
- cada `model` será único;
- cada `price_reference.id` será único.

A unicidade de `model` é exigida porque, nesta primeira composição, todas as rotas
usam o mesmo provedor, a mesma credencial, o mesmo cliente e o mesmo adaptador, sem
outra condição de execução capaz de distinguir duas rotas para a mesma identidade
de modelo. Duplicá-lo criaria alternativas operacionais semanticamente iguais com
fatos econômicos potencialmente divergentes.

Aliases ou nomes distintos que o provedor eventualmente trate como equivalentes
continuarão distintos para o Maestro. `model_identity_exact = true` permanece uma
declaração de responsabilidade do operador; o Maestro não consultará a OpenAI para
resolver identidade ou verificar preços.

As três unicidades serão avaliadas por igualdade exata sobre todas as identidades
estruturalmente válidas do documento, antes de excluir rotas por outras falhas
locais. Duplicidade torna o universo ambíguo e invalida a configuração inteira,
mesmo se os demais campos ou valores duplicados forem iguais. Uma identidade
ausente ou estruturalmente inválida não é convertida em valor para essa comparação.

### Validação e configuração incompleta

O documento será tratado como entrada não confiável, embora não seja uma
credencial. Aplicam-se, além das regras herdadas das ADRs 0006 e 0007:

- o valor de nível superior deverá ser um objeto JSON padrão;
- `routes` deverá existir, ser um array e conter ao menos um membro;
- campos ausentes, desconhecidos ou com tipo incorreto serão inválidos;
- nenhum valor será aparado, corrigido, convertido ou completado silenciosamente;
- nomes de membros JSON duplicados em qualquer objeto serão inválidos, mesmo se os
  valores forem iguais;
- `NaN`, infinito, números ou sintaxe fora do JSON padrão e interpretação
  permissiva equivalente não serão aceitos;
- a ordem dos membros dos objetos e a ordem informada no array não terão efeito na
  identidade, na validade, na prioridade ou no resultado econômico.

Serão erros globais: JSON malformado; membro duplicado ou estrutura inválida no
objeto superior; `routes` ausente, com tipo incorreto ou vazio; membro do array que
não seja objeto; combinação ambígua com o modo legado; `route_id` ausente,
duplicado no mesmo objeto, com tipo incorreto, branco ou repetido em outra entrada;
duplicidade exata de `model` ou `price_reference.id` entre identidades válidas; e
qualquer outra falha que impeça atribuir com segurança um erro a uma única rota.
Esses casos invalidarão a configuração inteira antes da inicialização.

Depois dessa validação global, uma falha restrita aos demais campos de uma rota,
inclusive campo ausente, desconhecido, duplicado ou inválido, poderá ser isolada
somente quando a entrada possuir `route_id` válido e único e sua exclusão preservar
um universo não ambíguo. A rota afetada não será registrada como executável nem
participará da avaliação econômica; as demais rotas válidas poderão compor a
aplicação. A distinção não cria fallback de preço ou previsão e não transforma
configuração inválida em estimativa `unavailable`.

O fato sanitizado da exclusão local será preservado entre os resultados de
validação do snapshot para que a decisão possa explicar `invalid_route` conforme
`docs/06-DECISAO-DE-ROTEAMENTO.md`. Esta ADR não cria novo campo público nem define
uma estrutura adicional de resposta.

Se nenhuma rota localmente válida restar, a configuração será estruturalmente
insuficiente e a inicialização falhará. Essa regra especializa, para o novo
documento multirrota, o fail-fast das ADRs 0006 e 0007 sem modificar o tratamento
das variáveis legadas de rota única. Ela também materializa o isolamento de rota
já exigido por `docs/04-CASOS-DE-USO.md`, `docs/05-API.md` e
`docs/06-DECISAO-DE-ROTEAMENTO.md`.

Nenhuma chamada de rede ocorrerá durante a validação. Mensagens, logs e exceções
de validação ou inicialização poderão identificar somente o nome seguro da
variável, o índice estrutural da entrada e categorias ou caminhos estáticos de
campos. Não reproduzirão `route_id`, JSON bruto, valores inválidos, modelos,
tarifas, fonte, condições, previsões ou credenciais.

### Snapshot, imutabilidade e ordem determinística

As entradas aplicáveis ao modo escolhido serão capturadas uma única vez durante a
composição; o documento multirrota será lido e validado somente a partir dessa
captura. As rotas localmente válidas serão materializadas em ordem crescente de
`route_id`, usando a mesma ordem de valores escalares Unicode definida em
`docs/06-DECISAO-DE-ROTEAMENTO.md`. A ordem original do array será descartada e
jamais constituirá prioridade ou desempate.

Cada rota do snapshot terá sua própria referência e sua própria estimativa já
derivada. O catálogo, as associações de adaptadores e os fatos econômicos usados
pela aplicação serão imutáveis depois da composição. Alteração posterior do
ambiente ou do objeto de configuração fornecido à fábrica não modificará uma
aplicação já criada. Atualizar rota, modelo, preço, previsão ou credencial exigirá
nova composição ou reinicialização e afetará apenas snapshots posteriores.

A credencial capturada será consumida somente para construir o cliente e não
integrará o snapshot neutro de rotas, associações e fatos econômicos.

O mesmo documento validado produzirá o mesmo conjunto ordenado de descritores;
a credencial não participa dessa identidade nem dessa ordenação. Com a mesma
solicitação e o mesmo snapshot, permanecem obrigatórios o resultado determinístico,
a comparação decimal exata e o desempate por menor `route.id` já aprovados. A
ordem de leitura, de declaração ou de iteração não poderá influenciar a escolha.

### Rotas, adaptador e cliente OpenAI

Cada rota válida será construída com:

- `provider = openai`;
- `adapter_id = openai-responses`;
- `enabled = true`;
- o `route_id` e o `model` declarados no próprio objeto;
- sua referência de preço e sua estimativa derivadas dos objetos aninhados;
- as mesmas ausências explícitas de capacidades, critérios de qualidade e
  indisponibilidade conhecida da composição OpenAI atual.

Depois de toda a validação, `OPENAI_API_KEY` será usada uma única vez para
construir um `AsyncOpenAI`. Um único `OpenAIResponsesAdapter`, injetado com esse
cliente, será registrado sob `openai-responses` e compartilhado por todas as rotas
do snapshot. O adaptador continuará recebendo o modelo exclusivamente da
`ExecutionRoute` selecionada e executará somente essa rota.

Preço, previsão, lista de rotas e credencial não serão entregues ao adaptador. O
núcleo continuará sem conhecer autenticação ou formatos OpenAI; adaptador e cliente
continuarão sem escolher, ordenar ou comparar rotas. A decisão não cria um cliente
por rota, não realiza chamadas concorrentes e não executa alternativas perdedoras.

### Compatibilidade com a composição de rota única

Na ausência de `MAESTRO_OPENAI_ROUTES_JSON`, a composição atual continuará usando,
sem alteração de significado ou validação:

- `MAESTRO_OPENAI_ROUTE_ID`;
- `MAESTRO_OPENAI_MODEL`;
- `MAESTRO_OPENAI_PRICE_REFERENCE_JSON`, quando presente;
- `MAESTRO_OPENAI_ESTIMATED_USAGE_JSON`, quando presente;
- `OPENAI_API_KEY`.

Quando `MAESTRO_OPENAI_ROUTES_JSON` estiver presente, as quatro entradas legadas
específicas de rota deverão estar ausentes. A mera presença simultânea de qualquer
uma delas, ainda que seu valor seja vazio ou inválido, será uma configuração global
ambígua e impedirá a inicialização; não haverá precedência, mescla ou sobrescrita
implícita. `OPENAI_API_KEY` será comum aos dois modos e continuará obrigatória.

Essa compatibilidade preserva aplicações e implantações atuais sem declarar as
variáveis legadas obsoletas e sem transformar a nova configuração em rota padrão.

### Sanitização e isolamento de credenciais

`OPENAI_API_KEY` continuará sendo a única entrada de credencial desta composição e
será aplicada igualmente a todas as rotas do snapshot. O valor será lido apenas no
ponto de composição e passado diretamente à construção do cliente. Não entrará no
JSON, em `Route`, `RouteCatalog`, referência de preço, estimativa, decisão, fatores,
respostas públicas, logs ou exceções.

O schema fechado não aceitará credencial, token, chave, header, endpoint, base URL,
identificador de organização ou projeto. Valores recebidos em campos desconhecidos
não serão reproduzidos. Esta primeira composição não suporta credenciais distintas
por rota, resolução de segredos, rotação automática nem armazenamento de segredos.

### Relação com `max_estimated_cost` e `lowest-estimated-cost`

Para cada rota válida, a estimativa será calculada a partir de sua previsão e de
sua referência usando a fórmula, a aritmética decimal exata, a moeda e as hipóteses
fixas já aprovadas pela ADR 0007. O mesmo preço da rota continuará sendo usado no
cálculo pós-execução quando o uso normalizado for suficiente, conforme a ADR 0005.

A configuração apenas fornece fatos ao núcleo e não altera o algoritmo:

- `max_estimated_cost` será aplicado a cada rota conforme
  `docs/06-DECISAO-DE-ROTEAMENTO.md`;
- uma estimativa comparável acima de ao menos um teto aplicável será uma violação
  conclusiva somente para aquela rota;
- moeda incompatível com teto tornará a avaliação daquela rota indeterminada, e
  os casos mistos conservarão a taxonomia e a precedência de erros existentes;
- sem teto, custo continuará indispensável somente quando restarem duas ou mais
  rotas elegíveis não economicamente;
- `lowest-estimated-cost` usará somente estimativas `available` com base econômica
  compatível, referentes à mesma solicitação e ao custo total estimado de uma
  execução completa sob as hipóteses declaradas;
- as estimativas comparadas deverão formar um conjunto não vazio em uma única
  moeda; o Maestro não escolherá um grupo de moeda, presumirá paridade nem fará
  conversão cambial;
- o menor valor decimal exato vencerá;
- empates continuarão resolvidos pelo menor `route.id` na ordem de valores
  escalares Unicode;
- somente quando não houver teto e restar exatamente uma rota elegível não
  economicamente aplicar-se-á a regra existente de candidato único, sem afirmar
  que o custo favoreceu a seleção;
- custo posterior não provocará nova decisão, retry, fallback ou segunda execução.

O fato de todas as primeiras alternativas usarem OpenAI não concede preferência ao
provedor e não comprova economia universal. A decisão compara apenas os modelos e
os fatos econômicos explicitamente configurados para o snapshot.

### Responsabilidade do operador

O operador será responsável por declarar, verificar e manter cada `route_id`, a
identidade exata e a disponibilidade operacional de cada modelo, a aplicabilidade,
origem, vigência e completude de cada referência de preço e a adequação de cada
previsão estática ao perfil de solicitações atendido. O Maestro validará estrutura,
coerência interna e declarações explícitas, mas não consultará a OpenAI para
confirmar modelos ou preços e não verificará automaticamente a precisão das
previsões.

A estimativa continuará sendo um cálculo exato sobre fatos declarados, não uma
garantia de uso ou gasto. O custo pós-execução continuará distinto de cobrança,
fatura ou conciliação do provedor.

### Relação com decisões anteriores

Esta ADR especializa a ADR 0003 somente para adicionar um modo operacional
multirrota e preserva integralmente seu modo de rota única. Ela reutiliza os
documentos econômicos das ADRs 0006 e 0007 por rota, tornando-os obrigatórios no
novo modo para viabilizar comparação real.

A decisão não modifica `docs/05-API.md`, `docs/06-DECISAO-DE-ROTEAMENTO.md`, a
estratégia `lowest-estimated-cost`, o contrato neutro de execução nem o adaptador
OpenAI. Ela fecha somente o mecanismo concreto de composição das primeiras
alternativas múltiplas do mesmo provedor.

Qualquer implementação posterior continuará dependendo de aprovação expressa do
Product Owner.

## Consequências

- O operador poderá declarar várias alternativas OpenAI em um único snapshot.
- Cada alternativa terá identidade, preço e previsão próprios e verificáveis.
- O núcleo existente poderá comparar estimativas derivadas dos fatos fornecidos
  pelo operador.
- Uma credencial e um cliente serão compartilhados por todas as rotas.
- A ordem declarada não criará preferência silenciosa.
- Falhas locais isoláveis não eliminarão rotas válidas; ambiguidades globais
  continuarão falhando cedo.
- O modo atual de rota única permanecerá compatível e sem mudança silenciosa.
- A exatidão dos modelos, preços, condições e previsões continuará sendo
  responsabilidade do operador.
- Nenhuma capacidade executável é entregue pela W18.

## Limites deliberados

A W18 não inclui implementação, parsing, novas variáveis executáveis, testes,
alteração da API pública ou mudança do algoritmo de roteamento. Também não inclui
segundo provedor, credencial por rota, modelo ou rota padrão, preço ou previsão
padrão, preços reais, tokenização, estimativa por solicitação, chamada externa para
estimar ou validar, tabela ou atualização automática de preços, aliases de modelo,
câmbio ou conversão de moeda.

Não inclui ainda retry, fallback, timeout novo, streaming, fan-out, execução
concorrente, comparação de respostas, cache, persistência, endpoint administrativo,
recarga dinâmica, arquivo `.env`, JSON em arquivo, YAML, TOML, banco de dados,
serviço remoto de configuração, gestão de segredos, organização ou projeto OpenAI,
base URL customizada, infraestrutura, Docker, CI/CD, observabilidade, monitoramento,
tracing ou dependências novas.

Esses limites não constituem roadmap nem promessa.

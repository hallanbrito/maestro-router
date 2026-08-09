# Decisão de Roteamento do MVP do Maestro Router

## 1. Propósito e fontes

Este documento fecha o comportamento interno mínimo necessário para que o MVP do Maestro Router produza, para uma solicitação, exatamente uma rota selecionada ou uma recusa determinística e explicável.

Suas fontes aprovadas são o [Manifesto](00-MANIFESTO.md), a [Visão Geral](01-VISAO-GERAL.md), a [Proposta de Valor](02-PROPOSTA-DE-VALOR.md), a [Arquitetura Conceitual](03-ARQUITETURA.md), os [Casos de Uso](04-CASOS-DE-USO.md) e a [API Pública](05-API.md). Este documento especializa decisões que esses documentos deixaram abertas; não altera seus contratos. Em caso de conflito, prevalece o Manifesto e, para a fronteira pública, permanece obrigatório o contrato de `05-API.md`.

As regras abaixo descrevem comportamento conceitual. Elas não escolhem linguagem, framework, banco de dados, ORM, formato de configuração ou infraestrutura e não afirmam que a implementação já exista.

## 2. Fronteira da decisão

A decisão de roteamento começa somente depois de:

- a solicitação ter passado pela validação pública definida em `05-API.md`;
- a configuração global indispensável ter sido considerada suficientemente válida.

A formação das restrições efetivas é a primeira etapa interna da decisão. Ela combina restrições obrigatórias, valores padrão aplicáveis e restrições da solicitação sem enfraquecimento.

A decisão termina com um destes resultados internos:

- uma seleção validada de exatamente uma rota;
- uma recusa validada por ausência de rota elegível;
- uma recusa validada por insuficiência econômica indispensável;
- uma decisão inválida, que impede a execução.

A execução externa começa somente após uma seleção válida. Tradução de payload, chamada ao provedor, retry, fallback, timeout durante a execução, normalização da resposta e cálculo de custo posterior não pertencem ao algoritmo de seleção deste documento.

A decisão não:

- chama provedores nem outro modelo para descobrir elegibilidade;
- avalia a qualidade da resposta antes ou depois da execução;
- coordena múltiplos modelos;
- relaxa restrições para obter uma resposta;
- cria política genérica, pesos, scores ou regras fornecidas pela solicitação;
- contém chain-of-thought, prompts internos, credenciais ou detalhes brutos de provedores.

## 3. Conflitos e ambiguidades identificados

Não foi encontrado conflito normativo material entre os documentos `00–05`. Há uma tensão aparente, mas conciliável: `03-ARQUITETURA.md` e `04-CASOS-DE-USO.md` exigem uma estratégia econômica simples, enquanto `05-API.md` admite decisões específicas nas quais custo não é indispensável. Este documento resolve a tensão definindo quando o resultado depende de custo e quando a existência de um único candidato torna a comparação desnecessária.

As seguintes decisões estavam deliberadamente abertas e precisavam ser fechadas:

| Ambiguidade anterior | Fechamento deste documento |
| --- | --- |
| Quantidade e algoritmo das estratégias | O MVP suporta uma única estratégia, `lowest-estimated-cost`. |
| Custo com apenas um candidato | Sem teto econômico, custo não é indispensável quando resta exatamente uma rota elegível. |
| Uso de estimativa `uncertain` | Ela não prova teto e não participa da comparação de menor custo do MVP. |
| Estimativa `unavailable` | Ela nunca equivale a zero e não participa de decisão que dependa de custo. |
| Moedas distintas | O MVP não converte nem compara moedas distintas. |
| Mistura de violação econômica conhecida e informação insuficiente | Se nenhuma rota comprovar conformidade e alguma permanecer indeterminada, prevalece `INSUFFICIENT_ECONOMIC_INFORMATION`; somente violações conclusivas produzem `NO_ELIGIBLE_ROUTE`. |
| Ordem dos filtros e motivo de exclusão | Há uma ordem fixa e cada rota conserva o primeiro motivo determinante de exclusão. |
| Desempate | Menor valor decimal exato e, em empate, menor `route.id` por ordem de valores escalares Unicode. |
| Estado de `strategy.applied` nas recusas | As recusas válidas deste MVP ocorrem antes da aplicação da estratégia e usam `false`. |
| Fatos dinâmicos e determinismo | Cada decisão usa um único snapshot coerente de configuração, disponibilidade conhecida e informação econômica. |

## 4. Vocabulário da decisão

| Termo | Definição |
| --- | --- |
| **Universo configurado** | Rotas descritas na configuração aplicável ao snapshot da decisão, antes dos filtros da solicitação. |
| **Candidato preliminar** | Rota do universo configurado ainda não excluída pelos filtros já processados. |
| **Elegível não economicamente** | Rota configurada, habilitada, localmente válida, permitida pelas allowlists, compatível com todas as capacidades e qualidades obrigatórias e sem indisponibilidade conhecida. |
| **Economicamente admissível** | Rota elegível não economicamente que comprovou todos os tetos aplicáveis, ou para a qual não existe teto econômico obrigatório. |
| **Economicamente indeterminada** | Rota que não possui informação suficiente ou moeda compatível para comprovar um teto aplicável, sem que já exista violação conclusiva. |
| **Comparável** | Rota cuja estimativa `available` pode participar da mesma base de comparação das demais rotas consideradas pela estratégia. |
| **Selecionável** | Rota entregue à estratégia como única opção admissível ou como integrante do conjunto comparável final. |
| **Selecionada** | A única rota devolvida pela estratégia e aprovada pela validação da decisão. |

### 4.1 Elegibilidade, comparação e seleção

**Elegibilidade** responde se uma rota pode ser admitida sob todas as restrições obrigatórias. Requisitos de capacidade, qualidade, disponibilidade, allowlist e teto econômico são gates: vantagem em outra dimensão não os compensa.

**Comparação** responde qual rota deve preceder as demais entre opções admissíveis e comparáveis. No MVP, ela considera somente a estimativa de custo anterior à execução e o desempate definido neste documento.

**Seleção** materializa uma única escolha a partir do resultado da estratégia. Ela não torna elegível uma rota excluída, não corrige falta de informação e não executa a rota.

## 5. Ordem obrigatória e snapshot da decisão

O fluxo preserva, sem intercalação, a ordem consolidada nos documentos aprovados:

1. validação da solicitação e da configuração indispensável;
2. formação das restrições efetivas;
3. elegibilidade não econômica;
4. avaliação econômica e aplicação de tetos;
5. preparação do conjunto selecionável;
6. aplicação da estratégia;
7. validação da decisão;
8. execução da única rota selecionada.

Nenhuma estimativa é usada para recuperar uma rota eliminada na etapa 3. Nenhuma chamada externa de execução acontece antes da conclusão da etapa 7, e filtros ou estratégia não chamam provedor nem outro modelo. A origem operacional de preços e disponibilidade permanece aberta, mas todas as entradas externas ou configuradas aplicáveis precisam estar congeladas no snapshot antes da avaliação.

### 5.1 Snapshot determinístico

Cada tentativa de decisão usa um snapshot conceitualmente único e coerente contendo somente as entradas estáveis necessárias:

- solicitação validada e restrições efetivas;
- estratégia efetiva;
- rotas configuradas e seus estados habilitados;
- resultado da validação local das rotas;
- capacidades, critérios de qualidade e referências de evidência aplicáveis;
- indisponibilidade conhecida no início da decisão;
- referências de preço, regras de cobrança, parâmetros de estimativa e demais fatos externos ou configurados aplicáveis à avaliação econômica.

O snapshot inicial não contém estimativas econômicas já produzidas. Estado, valor, moeda, hipóteses e razão da estimativa são resultados determinísticos derivados desse snapshot durante a etapa 4 e preservados na avaliação econômica da decisão.

Mudança de configuração, preço ou disponibilidade conhecida depois da captura do snapshot não altera retroativamente a decisão. Este requisito não exige persistência, relógio global, monitoramento ou identificador público de snapshot.

Com a mesma solicitação validada e o mesmo snapshot, a rota, o resultado da decisão, os critérios determinantes e a regra de desempate devem ser os mesmos. Ordem de leitura da configuração, ordem de iteração de coleções e preferência de provedor não participam do resultado.

O Cost Evaluation deve produzir o mesmo estado, valor, moeda, referência, hipóteses e razão quando receber a mesma solicitação normalizada, o mesmo descritor de rota, a mesma referência de preço e os mesmos parâmetros de estimativa. Relógio, aleatoriedade ou estado não registrado não podem alterar a estimativa. Quando não for possível oferecer essa estabilidade com precisão defensável, o estado deve permanecer deterministicamente `uncertain` ou `unavailable`.

## 6. Formação dos candidatos e sequência de filtros

Antes dos filtros, restrições da configuração e da solicitação são combinadas conforme `05-API.md`:

- requisitos obrigatórios de capacidade e qualidade são acumulados;
- allowlists obrigatórias são intersectadas;
- tetos econômicos se acumulam, e a rota precisa satisfazer todos;
- valores padrão suprem somente dimensões omitidas pela solicitação;
- a solicitação nunca habilita rota desabilitada nem substitui restrição obrigatória.

O universo configurado é a visão conceitual anterior aos filtros. O Provider Registry pode materializar diretamente apenas sua parcela habilitada, como admite `03-ARQUITETURA.md`; ainda assim, a decisão preserva como invariante que nenhuma rota desabilitada entrou no conjunto. As rotas efetivamente avaliadas são percorridas em ordem crescente de `route.id`, usando a ordenação definida na seção 8.4. A ordem não constitui prioridade; serve somente para estabilidade da avaliação e da explicação.

Cada rota atravessa os filtros abaixo na ordem indicada. Ao falhar, ela é excluída e recebe como motivo primário o primeiro fato determinante. O MVP não exige continuar avaliando filtros posteriores de uma rota já excluída.

| Ordem | Filtro | Regra de permanência | Motivo primário quando falha |
| ---: | --- | --- | --- |
| 1 | Habilitação | A rota está habilitada no snapshot. | `disabled_route` |
| 2 | Validade local | A rota possui descrição local suficientemente válida para elegibilidade, economia, estratégia e eventual execução. | `invalid_route` |
| 3 | Allowlist e preferências obrigatórias | O `route.id` pertence à interseção de todos os conjuntos obrigatórios aplicáveis. | `route_not_allowed` |
| 4 | Capacidade | A rota declara todas as capacidades efetivamente requeridas para a tarefa e seu contexto. | `incompatible_capability` |
| 5 | Qualidade | A configuração validada declara satisfeitos todos os critérios de qualidade efetivos. | `unsatisfied_quality` |
| 6 | Disponibilidade conhecida | A rota não está conhecida como indisponível no snapshot. | `known_unavailability` |

Os identificadores continuam opacos e usam igualdade exata, sem trim, alteração de caixa ou normalização Unicode implícita.

Os motivos internos possuem a seguinte projeção determinística para os enums públicos de `05-API.md`:

| Motivo ou fato interno | `decision.factors[].category` | Categoria de `applied_constraints` quando houver restrição correspondente |
| --- | --- | --- |
| `disabled_route` | `route` | `route`, fonte `configuration` |
| `invalid_route` | `configuration` | `route`, fonte `configuration` |
| `route_not_allowed` | `route` | `route`, preservando a fonte de cada allowlist |
| `incompatible_capability` | `capability` | `capability`, preservando a fonte do requisito |
| `unsatisfied_quality` | `quality` | `quality`, preservando a fonte do critério |
| `known_unavailability` | `availability` | `availability`, fonte `configuration` |
| teto violado, estimativa insuficiente ou não comparabilidade | `economics` | `economics`, preservando a fonte de cada teto |
| aplicação da regra da estratégia | `strategy` | Não cria restrição. |
| desempate efetivo | `tie_breaker` | Não cria restrição. |

`source` é `request` para a restrição recebida na solicitação e `configuration` para limite, estado ou requisito obrigatório configurado. Quando requisitos das duas fontes se acumulam, ambos são preservados separadamente. Preferência obrigatória configurada que não seja uma allowlist usa a categoria pública `preference`; a allowlist pública permanece na categoria `route`, conforme `05-API.md`.

### 6.1 Rota desabilitada

Uma rota desabilitada é excluída antes de qualquer avaliação econômica. Sua presença em `allowed_route_ids` ou em outra preferência não a habilita. Ela nunca pode ser selecionada.

### 6.2 Rota inválida

Uma falha isolável em uma rota exclui somente essa rota quando:

- a rota pode ser identificada de forma segura e unívoca;
- sua remoção não torna ambíguos os fatos das rotas restantes;
- as restrições globais, a estratégia e os demais dados indispensáveis continuam válidos.

Ausência ou duplicidade que impeça formar um universo unívoco, erro em restrição ou estratégia global, falha que não possa ser isolada com segurança ou conjunto de falhas que impeça uma conclusão confiável continua sendo `INVALID_CONFIGURATION`, antes da decisão. Dados econômicos bem formados, porém `uncertain` ou `unavailable`, não tornam a rota inválida por si sós.

Para fechar o limiar no MVP:

- se não existe rota habilitada e a configuração restante é válida, a configuração não é inválida por esse motivo; a decisão termina em `NO_ELIGIBLE_ROUTE`;
- se existem rotas habilitadas, mas nenhuma delas pode ser descrita como localmente válida devido a erros de rota, a configuração é estruturalmente insuficiente e produz `INVALID_CONFIGURATION`;
- se ao menos uma rota habilitada é localmente válida, falhas isoláveis nas demais rotas apenas as excluem, e a decisão continua com as válidas.

Este documento não redefine o formato nem o mecanismo do validador de configuração.

### 6.3 Capacidade incompatível

Toda capacidade efetivamente requerida deve estar declarada pela rota. Ausência de declaração equivale a requisito não satisfeito. A avaliação usa somente fatos configurados e características normalizadas já conhecidas da tarefa; não chama outro modelo e não trunca a entrada silenciosamente.

Uma rota incompatível é excluída ainda que sua estimativa seja a menor.

### 6.4 Qualidade não satisfeita

Qualidade é um filtro binário no MVP. Para cada critério requerido, a configuração validada deve declarar que a rota o satisfaz e manter as referências de evidência aplicáveis. Ausência, declaração negativa ou impossibilidade de sustentar essa declaração exclui a rota.

O algoritmo não cria score, peso, média, ranking de reputação nem compensação entre preço e qualidade.

### 6.5 Allowlist

A allowlist é sempre restritiva. A interseção efetiva pode ficar vazia mesmo quando cada lista de origem é não vazia. IDs inexistentes, inválidos, desabilitados ou indisponíveis não criam candidatos e não são corrigidos.

### 6.6 Indisponibilidade conhecida

Indisponibilidade conhecida no snapshot exclui a rota. Ausência de indisponibilidade conhecida permite que a rota continue, mas não constitui garantia de disponibilidade. Indisponibilidade descoberta durante a chamada pertence a `EXECUTION_UNAVAILABLE` e não reabre automaticamente a decisão, pois retry e fallback permanecem abertos.

## 7. Avaliação econômica

A avaliação econômica acontece somente para rotas elegíveis não economicamente. Para cada uma, o Maestro preserva o estado da estimativa, seu valor quando existente, moeda, referência de preço, hipóteses e razão de incerteza ou indisponibilidade conforme `05-API.md`.

### 7.1 Estados da estimativa

| Estado | Uso no MVP |
| --- | --- |
| `available` | Possui valor defensável. Pode comprovar teto na mesma moeda e pode participar da comparação. |
| `uncertain` | Possui valor aproximado com limitação material. Não comprova teto e não participa da comparação de menor custo. Pode acompanhar a seleção da única rota quando não houver teto. |
| `unavailable` | Não possui valor numérico defensável. Não comprova teto e não participa da comparação. Pode acompanhar a seleção da única rota quando não houver teto. |

Uma estimativa `uncertain` não é promovida a `available` porque seu valor parece conveniente. Uma estimativa `unavailable` nunca recebe valor `0`. Zero só é usado quando um custo realmente zero for defensável pela referência econômica aplicável.

Uma estimativa `available` somente é comparável quando se refere à mesma solicitação e representa, na mesma base semântica, o custo total estimado de uma execução completa pela rota sob as hipóteses declaradas. Cost Evaluation deve validar que escopo, unidades agregadas e hipóteses materiais permitem essa comparação. Se o valor for defensável isoladamente, mas sua base não for compatível com a base comum da decisão, a rota permanece economicamente não comparável e a razão fica explícita. Valor, moeda ou referência de preço estruturalmente malformados são problema de validade da configuração ou da rota, não estado `unavailable`.

### 7.2 Aplicação de tetos econômicos

Cada rota deve satisfazer todos os tetos obrigatórios efetivos. Tetos na mesma moeda equivalem, para a verificação, ao menor valor aplicável. O MVP não cria conversão para reconciliar tetos em moedas diferentes.

Para uma rota, a avaliação dos tetos possui três resultados:

| Resultado | Condição |
| --- | --- |
| **Comprovadamente admissível** | A estimativa é `available`, possui base compatível com o teto, usa a mesma moeda de todos os tetos aplicáveis e não excede nenhum deles. |
| **Violação conclusiva** | Uma estimativa `available`, em base e moeda comparáveis, excede ao menos um teto. Como os tetos são cumulativos, uma violação conhecida basta para excluir a rota. |
| **Indeterminada** | Não há violação conclusiva, mas estimativa `uncertain`, `unavailable`, base incompatível ou moeda distinta impede comprovar ao menos um teto. |

Depois de avaliar todas as rotas elegíveis não economicamente:

1. se ao menos uma rota comprovar conformidade, somente as rotas comprovadamente admissíveis seguem;
2. se nenhuma comprovar conformidade e ao menos uma estiver indeterminada, o resultado é `INSUFFICIENT_ECONOMIC_INFORMATION`;
3. se nenhuma comprovar conformidade e todas tiverem violação conclusiva, o resultado é `NO_ELIGIBLE_ROUTE`.

Essa precedência impede chamar de ausência de rota aquilo que os dados ainda não permitem concluir e também impede ignorar um teto obrigatório.

### 7.3 Quando custo é indispensável

Custo é indispensável para a decisão quando:

- existe ao menos um teto econômico obrigatório, qualquer que seja a quantidade de rotas; ou
- não existe teto, mas restam duas ou mais rotas elegíveis não economicamente e a estratégia precisa distingui-las.

Custo não é indispensável somente quando não existe teto econômico e resta exatamente uma rota elegível não economicamente. Nesse caso, a rota pode ser selecionada com estimativa `available`, `uncertain` ou `unavailable`; a explicação deve dizer que ela era a única rota elegível e não pode afirmar que custo a favoreceu.

Se nenhuma rota passa pela elegibilidade não econômica, a necessidade de custo não chega a ser avaliada.

### 7.4 Comparabilidade e moedas

Quando a comparação for necessária:

- somente estimativas `available` com base econômica compatível entram no conjunto comparável;
- todas devem usar a mesma moeda;
- valores são comparados como decimais exatos, sem ponto flutuante, arredondamento ou comparação textual;
- hipóteses e referências de preço permanecem associadas a cada estimativa;
- rotas `uncertain`, `unavailable` ou com base econômica incompatível ficam fora da comparação daquela decisão.

Se não restar nenhuma estimativa `available` com base compatível, o resultado é `INSUFFICIENT_ECONOMIC_INFORMATION`.

Se as estimativas `available` compatíveis restantes usarem mais de uma moeda, o resultado também é `INSUFFICIENT_ECONOMIC_INFORMATION`. O Maestro não escolhe arbitrariamente um grupo de moeda, não presume paridade e não converte valores. Com uma única rota e sem teto, moeda não precisa ser comparada.

Se restar pelo menos uma estimativa `available` com base compatível em uma única moeda, a estratégia compara esse conjunto. Rotas com informação incerta, indisponível ou de base incompatível não impedem a seleção quando já existe um conjunto comparável não vazio e unívoco em moeda, mas sua exclusão econômica deve permanecer explícita na decisão pública.

## 8. Estratégia suportada pelo MVP

### 8.1 Quantidade e estratégia padrão

O MVP suporta exatamente uma estratégia:

```text
lowest-estimated-cost
```

Ela é a estratégia inicial e padrão do MVP. Toda configuração válida deve resolver sua estratégia efetiva para esse identificador. Um identificador explicitamente diferente não recebe fallback silencioso e produz `INVALID_CONFIGURATION` neste MVP.

Uma única estratégia é suficiente para validar a proposta central: ela diferencia rotas admissíveis por custo estimado, é observável e não exige pesos, motor de regras, plugins ou preferências implícitas. Uma segunda estratégia não resolveria necessidade adicional aprovada para o MVP.

### 8.2 Pré-condições de aplicação

A estratégia somente é aplicada quando:

- existe exatamente uma rota economicamente admissível; ou
- existe um conjunto não vazio de rotas comparáveis em uma única moeda.

Recusas por filtros, teto ou insuficiência de comparabilidade são formadas antes da estratégia. Por isso, em toda recusa válida deste MVP, `decision.strategy.applied` é `false`. Em toda seleção produzida pelo algoritmo abaixo, é `true`.

Esse short-circuit é a especialização mínima do MVP: o Router forma a recusa quando não consegue entregar entrada selecionável à única estratégia. A capacidade conceitual mais ampla do Strategy Engine de indicar impossibilidade, descrita em `03-ARQUITETURA.md`, não é removida, mas não cria um segundo caminho de recusa neste MVP.

### 8.3 Algoritmo observável

1. Se houver exatamente uma rota admissível, selecione essa rota.
   - Sem teto, a seleção decorre de ela ser a única rota elegível; custo pode estar `available`, `uncertain` ou `unavailable`.
   - Com teto, ela já deve ter comprovado conformidade com estimativa `available` na moeda aplicável.
2. Se houver mais de uma rota admissível, considere somente o conjunto comparável preparado na seção 7.4.
3. Ordene as rotas comparáveis pelo valor numérico decimal exato da estimativa, em ordem crescente.
4. Se uma única rota possuir o menor valor, selecione-a.
5. Se duas ou mais rotas empatarem no menor valor, aplique a regra da seção 8.4 e selecione exatamente uma.
6. Produza o identificador da estratégia, o conjunto efetivamente comparado, o critério determinante, a estimativa da rota escolhida e a regra de desempate quando usada.

A estratégia não considera ordem de declaração, provedor, modelo, popularidade, reputação, qualidade acima do mínimo obrigatório nem custo calculado de execuções passadas.

Quando rotas `uncertain`, `unavailable` ou de base incompatível tiverem sido retiradas e restar um conjunto comparável, a razão deve afirmar “menor estimativa entre as rotas economicamente comparáveis”, ou significado equivalente. Ela não pode afirmar que a vencedora era a rota globalmente mais barata entre opções cujo custo não pôde ser comparado. Ao menos um fator `economics` deve identificar objetivamente as rotas retiradas, seus estados e as razões relevantes, admitido agrupamento determinístico por motivo.

### 8.4 Desempate determinístico

Valores decimais numericamente equivalentes empatam, ainda que tenham escalas textuais diferentes; por exemplo, `0.1`, `0.10` e `0.100` representam o mesmo valor para comparação.

Entre as rotas empatadas no menor custo, vence o menor `route.id` pela comparação lexicográfica ascendente das sequências de valores escalares Unicode, sem trim, mudança de caixa ou normalização. A configuração validada deve garantir IDs de rota únicos e formados por uma sequência Unicode bem formada; um surrogate isolado em ID configurado produz `INVALID_CONFIGURATION`.

Se o desempate for usado, a decisão deve incluir um fator público com categoria `tie_breaker` que informe essa regra e identifique o ID vencedor. A ordem da configuração nunca funciona como desempate.

## 9. Resultados e precedência

| Resultado | Condição necessária e suficiente no roteamento | Estratégia aplicada | Execução externa |
| --- | --- | --- | --- |
| **Seleção válida** | Existe rota selecionável; `lowest-estimated-cost` produz exatamente a rota determinada pela seção 8; a validação confirma todos os invariantes. | `true` | Permitida somente para a rota selecionada. |
| **`NO_ELIGIBLE_ROUTE`** | Depois da classificação de configuração da seção 6.2, nenhuma rota habilitada e localmente válida passa pelos demais filtros não econômicos; ou, havendo teto, todas as rotas que passaram possuem violação econômica conclusiva. | `false` | Proibida. |
| **`INSUFFICIENT_ECONOMIC_INFORMATION`** | Custo é indispensável e nenhuma rota comprova um teto quando ao menos uma permanece indeterminada; ou não existe estimativa `available` com base compatível para comparação; ou estimativas comparáveis usam moedas distintas. | `false` | Proibida. |
| **`INVALID_DECISION`** | Uma saída de seleção ou recusa viola a estrutura, os fatos, a estratégia, o desempate, a explicabilidade ou qualquer invariante deste documento. | A seleção inválida não é publicada. | Proibida. |

`INVALID_REQUEST` e `INVALID_CONFIGURATION` antecedem esta tabela e não podem ser mascarados como recusas de roteamento. Erros de execução somente existem depois de uma seleção válida.

### 9.1 Casos econômicos mistos

Para evitar ambiguidade:

- ao menos uma rota comprovadamente abaixo de todos os tetos permite continuar somente com as rotas que também comprovaram conformidade;
- nenhuma rota comprovada e ao menos uma rota indeterminada produz `INSUFFICIENT_ECONOMIC_INFORMATION`, mesmo que outras estejam comprovadamente acima do teto;
- somente quando todas as rotas restantes violarem de forma conclusiva ao menos um teto o resultado será `NO_ELIGIBLE_ROUTE`;
- sem teto e com várias rotas, uma ou mais estimativas `available` em base compatível e na mesma moeda permitem comparar essas rotas, mesmo que outras estejam `uncertain`, `unavailable` ou em base incompatível;
- sem teto e com várias estimativas `available` em moedas diferentes, nenhuma moeda recebe preferência e a decisão é economicamente insuficiente.

### 9.2 Condições de `INVALID_DECISION`

A validação produz `INVALID_DECISION`, no mínimo, se a saída:

- selecionar zero rotas ou mais de uma rota quando deveria haver seleção;
- selecionar rota fora do snapshot ou fora do conjunto selecionável;
- selecionar rota desabilitada, inválida, não permitida, incompatível, sem qualidade exigida ou conhecida como indisponível;
- selecionar rota que não comprovou um teto obrigatório;
- declarar menor custo diferente do mínimo decimal exato do conjunto comparado;
- aplicar desempate diferente do menor `route.id` definido na seção 8.4;
- usar estratégia diferente de `lowest-estimated-cost` ou marcar `applied = false` em uma seleção;
- omitir rota, estratégia, restrições exigidas, razão objetiva, fatores determinantes ou fator de desempate efetivamente usado;
- atribuir influência positiva a custo `uncertain` ou `unavailable` na seleção por candidato único;
- omitir a exclusão econômica determinante de rota `uncertain`, `unavailable` ou não comparável, ou alegar menor custo universal quando somente um subconjunto foi comparado;
- formar uma recusa incompatível com os fatos ou com a precedência da seção 9;
- depender de fato que não pertença ao snapshot da decisão;
- conter chain-of-thought, credencial, segredo ou detalhe bruto de provedor na representação da decisão.

O erro público segue `05-API.md`: inclui `issues` sanitizadas, não publica a seleção inválida como `decision`, não inclui `economics` e não chama provedor.

## 10. Invariantes

As seguintes regras nunca podem ser violadas:

1. Uma decisão válida seleciona exatamente uma rota.
2. A rota selecionada pertence ao universo configurado do snapshot, está habilitada e é localmente válida.
3. A rota selecionada satisfaz todas as restrições obrigatórias efetivas.
4. Uma rota incompatível nunca vence por ser mais barata.
5. A solicitação somente restringe; nunca habilita rota desabilitada nem enfraquece restrição obrigatória.
6. Elegibilidade não econômica sempre antecede avaliação econômica e estratégia.
7. Nenhum valor econômico ausente ou incerto é inventado, arredondado para decidir, convertido em zero ou apresentado como exato.
8. Teto econômico nunca é ignorado; sua conformidade exige estimativa `available` em base compatível e na mesma moeda.
9. Moedas diferentes nunca são comparadas ou convertidas pelo MVP.
10. A estratégia não chama provedores, não altera candidatos e não cria restrições.
11. Empate nunca é resolvido por ordem de configuração, ordem de iteração ou preferência de provedor.
12. A mesma solicitação e o mesmo snapshot produzem a mesma decisão.
13. Explicabilidade contém fatos, fatores, critérios e referências objetivos, nunca chain-of-thought.
14. Credenciais, segredos e detalhes externos brutos nunca pertencem à decisão.
15. Nenhuma execução externa ocorre após recusa ou decisão inválida.
16. Uma falha descoberta durante execução não altera retroativamente a rota que foi validamente selecionada.

## 11. Representação conceitual interna

Antes da resposta pública, o Router mantém uma representação conceitual suficiente para Validation verificar a decisão. Esta não é um schema de persistência nem um formato obrigatório de classe ou arquivo.

| Parte | Conteúdo mínimo |
| --- | --- |
| **Contexto da decisão** | Referência ao snapshot, solicitação normalizada e estratégia efetiva. |
| **Restrições efetivas** | Fonte, categoria e valor ou fato de cada restrição aplicável, distinguindo configuração e solicitação. |
| **Avaliação de candidatos** | Identidade neutra da rota, fase alcançada, estado incluído ou excluído e primeiro motivo determinante de exclusão. |
| **Avaliação econômica** | Estado da estimativa, valor quando defensável, moeda, referência de preço, hipóteses, razão de limitação, resultado diante dos tetos e comparabilidade. |
| **Base de comparação** | Quando houve comparação: IDs efetivamente comparados, base semântica, moeda comum, valores decimais exatos e ordem resultante. No candidato único sem comparação, registra somente `single_candidate`, sem inventar moeda, valor ou ordem econômica. |
| **Resultado da estratégia** | ID da estratégia, indicador de aplicação, rota única ou ausência, critério determinante e desempate usado. |
| **Explicação objetiva** | Restrições aplicadas, fatores, referências necessárias e resumo factual. |
| **Validação** | Resultado válido ou inválido, invariantes verificadas e inconsistências sanitizadas. |
| **Resultado interno final** | `selected`, `refused` com código correspondente, ou `invalid`; nunca estados simultâneos. |

As avaliações de candidatos são ordenadas por `route.id`. Restrições e fatores usam a ordem das fases deste documento; identificadores dentro da mesma fase usam a ordenação da seção 8.4. Essa ordem estabiliza a representação sem atribuir prioridade comercial.

Para explicação:

- toda restrição da solicitação deve aparecer em `applied_constraints`;
- restrição de configuração aparece quando excluiu candidato, comprovou ou impediu teto, ou é necessária para compreender a seleção;
- cada rota excluída mantém internamente um motivo primário; fatores públicos podem agrupar rotas com o mesmo motivo, desde que a recusa continue completa e objetiva;
- a seleção por menor custo informa valor, moeda e `price_reference` da rota escolhida e a existência do conjunto comparado;
- se alguma rota elegível foi retirada da comparação por estado `uncertain`, `unavailable` ou base incompatível, ao menos um fator público `economics` identifica as rotas afetadas, os estados e as razões determinantes;
- recusa por violação econômica conhecida informa estimativa, moeda e `price_reference`; recusa por incerteza ou indisponibilidade informa estado e razão e, quando houver valor aproximado defensável, também seu valor, moeda e referência;
- não comparabilidade de moedas informa as moedas e referências envolvidas sem calcular equivalência;
- um desempate efetivo sempre gera fator `tie_breaker`;
- textos descritivos podem variar, mas não podem mudar os fatos nem introduzir raciocínio oculto.

## 12. Relação com o objeto público `decision`

| Resultado interno | Projeção pública definida em `05-API.md` |
| --- | --- |
| Seleção validada | `decision.outcome = selected`; uma única `route`; `strategy.id = lowest-estimated-cost`; `strategy.applied = true`; restrições, razão e fatores; `economics` contém a estimativa registrada da rota, mesmo quando `uncertain` ou `unavailable` no caso de candidato único sem teto. |
| Recusa por elegibilidade | Erro `NO_ELIGIBLE_ROUTE`; `decision.outcome = refused`; sem `route` e sem `economics`; estratégia identificada com `applied = false`; `applied_constraints`, `reason` e `factors` obrigatórios apresentam os impedimentos determinantes. Quando um teto conhecido excluiu as rotas, os fatores incluem estimativa, moeda e `price_reference`. |
| Recusa econômica | Erro `INSUFFICIENT_ECONOMIC_INFORMATION`; `decision.outcome = refused`; sem `route` e sem `economics`; estratégia identificada com `applied = false`; `applied_constraints`, `reason` e `factors` obrigatórios declaram estados e razões e, quando existirem, valores, moedas e referências que impediram a decisão, sem fabricar dado. |
| Decisão inválida | Erro `INVALID_DECISION`; a seleção inválida não é projetada como `decision`; sem `economics`; `issues` identifica inconsistências sanitizadas. |

A representação interna pode conter avaliações de alternativas que não precisam ser publicadas integralmente. A projeção pública inclui somente fatos suficientes para compreender e validar a seleção ou recusa, preservando o schema fechado de `05-API.md`.

Em sucesso ou erro posterior à seleção, `economics.estimate` é exatamente a estimativa registrada antes da execução para a rota escolhida. Uso e custo calculado posteriores não participam da seleção e seguem exclusivamente as regras públicas de `05-API.md`.

## 13. Critérios mínimos de teste

Os testes posteriores da decisão devem cobrir, no mínimo:

| Cenário | Resultado esperado |
| --- | --- |
| Mesma solicitação e mesmo snapshot, com ordem de iteração diferente | Mesma rota, mesmos fatos determinantes e mesmo desempate. |
| Allowlist menciona rota desabilitada | A rota permanece excluída. |
| Universo configurado vazio ou todas as rotas desabilitadas, com configuração restante válida | `NO_ELIGIBLE_ROUTE`. |
| Rota localmente inválida e outras rotas válidas | Somente a rota inválida é excluída, desde que a falha seja isolável. |
| Existem rotas habilitadas, mas todas são localmente inválidas | `INVALID_CONFIGURATION` antes da decisão. |
| Rota inválida isolável e rotas válidas incompatíveis com a solicitação | `NO_ELIGIBLE_ROUTE`, com a falha local e as incompatibilidades preservadas como fatos, sem mascarar erro global. |
| Falha de configuração não isolável | `INVALID_CONFIGURATION` antes da decisão. |
| IDs configurados duplicados ou ID com sequência Unicode malformada | `INVALID_CONFIGURATION` antes da decisão. |
| Rota mais barata sem capacidade obrigatória | Exclusão por capacidade antes da economia. |
| Rota mais barata sem critério de qualidade obrigatório | Exclusão por qualidade antes da economia. |
| Interseção de allowlists vazia | `NO_ELIGIBLE_ROUTE`. |
| Última rota conhecida como indisponível | `NO_ELIGIBLE_ROUTE`, com fator de disponibilidade. |
| Disponibilidade apenas desconhecida | A rota não é excluída por disponibilidade; eventual falha pertence à execução. |
| Única rota, sem teto, estimativa `available` | Seleção por candidato único; custo não precisa ser alegado como determinante. |
| Única rota, sem teto, estimativa `uncertain` | Seleção válida; incerteza explícita e nenhuma alegação de vantagem econômica. |
| Única rota, sem teto, estimativa `unavailable` | Seleção válida; ausência explícita e nenhum valor inventado. |
| Única rota, com teto, estimativa `uncertain` ou `unavailable` | `INSUFFICIENT_ECONOMIC_INFORMATION`. |
| Única rota, com teto, estimativa `available` acima do limite | `NO_ELIGIBLE_ROUTE`. |
| Única rota, com teto, estimativa `available` dentro do limite | Seleção válida. |
| Várias rotas e nenhuma estimativa `available` | `INSUFFICIENT_ECONOMIC_INFORMATION`. |
| Várias rotas, uma estimativa `available` e demais `uncertain` ou `unavailable` | Seleção da única rota comparável, se não houver teto impeditivo. |
| Estimativas `available` em moedas diferentes | `INSUFFICIENT_ECONOMIC_INFORMATION`. |
| Estimativas `available` na mesma moeda, mas em bases semânticas incompatíveis | As incompatíveis não são comparadas; se não restar base comum não vazia, `INSUFFICIENT_ECONOMIC_INFORMATION`. |
| Tetos obrigatórios em moedas diferentes, sem conversão | `INSUFFICIENT_ECONOMIC_INFORMATION`, salvo se uma violação conclusiva já excluir cada rota. |
| Rotas acima do teto e rota economicamente indeterminada | `INSUFFICIENT_ECONOMIC_INFORMATION`. |
| Todas as rotas comprovadamente acima do teto | `NO_ELIGIBLE_ROUTE`. |
| Valores `0.1` e `0.10` | Empate numérico, resolvido por `route.id`. |
| Menor custo único | Seleção da rota de menor decimal exato. |
| Empate no menor custo | Seleção do menor `route.id` por valores escalares Unicode e fator `tie_breaker`. |
| Estratégia retorna rota fora do conjunto selecionável | `INVALID_DECISION`; nenhuma chamada externa. |
| Estratégia retorna rota que não é o mínimo ou erra o desempate | `INVALID_DECISION`; nenhuma chamada externa. |
| Seleção omite razão, fatores ou desempate usado | `INVALID_DECISION`; nenhuma chamada externa. |
| Recusa pública omite `applied_constraints`, `reason` ou fatos econômicos obrigatórios | `INVALID_DECISION`; nenhuma chamada externa. |
| Recusa, configuração inválida ou decisão inválida | Nenhum provedor é chamado. |
| Seleção válida | Somente o adaptador da rota selecionada pode ser acionado. |
| Dado externo potencialmente sensível | Deve ser sanitizado antes de formar a decisão. |
| Explicação entregue a Validation ainda contém segredo, payload bruto ou chain-of-thought | `INVALID_DECISION`; o conteúdo proibido nunca é exposto. |

## 14. Decisões fechadas por este documento

As decisões novas necessárias, antes abertas em `00–05`, são:

- o MVP possui uma única estratégia, `lowest-estimated-cost`, que também é a padrão;
- candidato único sem teto é selecionado sem tornar custo indispensável;
- custo é indispensável diante de qualquer teto ou quando duas ou mais rotas precisam ser distinguidas;
- `uncertain` e `unavailable` não participam da comparação de menor custo, mas podem acompanhar candidato único sem teto;
- somente estimativas `available` do mesmo snapshot, referentes a uma execução completa, em base semântica compatível e na mesma moeda são comparáveis;
- moedas diferentes não são comparadas, convertidas nem agrupadas com preferência implícita;
- filtros não econômicos possuem ordem fixa e guardam o primeiro motivo determinante de exclusão;
- tetos econômicos usam os resultados comprovadamente admissível, violação conclusiva e indeterminado;
- em resultado econômico misto sem rota comprovada, informação indeterminada prevalece sobre uma falsa conclusão de ausência de rota;
- comparação monetária usa decimal exato;
- empate usa menor `route.id` por ordem de valores escalares Unicode;
- toda seleção válida usa `strategy.applied = true`, e toda recusa válida deste MVP usa `false`;
- configuração e fatos variáveis são consumidos como um snapshot coerente da decisão;
- estimativas são determinísticas para os mesmos fatos e sua comparabilidade exige base semântica comum, além de moeda comum;
- somente indisponibilidade conhecida exclui; disponibilidade desconhecida não é convertida em garantia nem em impedimento;
- o limiar entre rota local inválida, configuração global inválida e ausência legítima de rota fica definido;
- as condições mínimas de `INVALID_DECISION`, a representação interna e sua projeção pública ficam definidas;
- ordem de configuração, preferência de provedor e dados de execuções passadas não influenciam a seleção.

## 15. Decisões deliberadamente abertas

Permanecem abertas porque não são necessárias para selecionar deterministicamente uma rota a partir dos fatos aprovados:

- catálogo inicial de provedores, modelos e rotas;
- vocabulário concreto de capacidades e critérios de qualidade;
- metodologia, métricas, limiares e processo de produção das evidências de qualidade;
- método concreto de estimar uso e custo antes da execução, preservados os estados e requisitos deste documento;
- origem, atualização e governança dos preços;
- forma concreta de determinar indisponibilidade conhecida;
- conversão cambial ou moeda-base em versões posteriores; nenhuma existe no MVP;
- estratégias adicionais, pesos ou preferências flexíveis depois do MVP e somente mediante necessidade e evidência;
- formato, origem, precedência operacional, recarga e armazenamento da configuração;
- mecanismo concreto de gestão de segredos;
- valores e mecanismo de timeout;
- retry, fallback e eventual nova decisão após falha de execução;
- persistência ou retenção de decisões;
- linguagem, framework, biblioteca HTTP, banco de dados, ORM, empacotamento, infraestrutura e implantação.

Essas aberturas não autorizam alterar o contrato público, enfraquecer invariantes nem introduzir comportamento não determinístico no MVP.

## 16. Validação contra os documentos aprovados

| Fonte | Compatibilidade preservada |
| --- | --- |
| `00-MANIFESTO.md` | Neutralidade, simplicidade, custo explícito, qualidade validável, transparência e controle do usuário. |
| `01-VISAO-GERAL.md` | Roteamento econômico contextual, estratégia simples, uma rota e ausência de orquestração no MVP. |
| `02-PROPOSTA-DE-VALOR.md` | Economia somente entre opções adequadas, sem promessa de menor custo universal ou qualidade presumida. |
| `03-ARQUITETURA.md` | Fronteiras dos componentes, ordem do fluxo, estimativa anterior distinta de custo posterior e execução somente depois da decisão válida. |
| `04-CASOS-DE-USO.md` | Preparação válida, execução sob restrições, recusa sem rota e explicação objetiva do impacto econômico. |
| `05-API.md` | Restrições públicas, estados econômicos, decisão selecionada ou recusada, taxonomia e precedência de erros, `strategy.applied`, fatores e ausência de chain-of-thought. |

O documento fecha somente a lógica interna indispensável à seleção do MVP e não adiciona código, testes executáveis, infraestrutura, observabilidade, persistência ou novos endpoints.

Implemente apenas o necessário. Não adicione Docker, CI/CD, monitoramento, documentação extensa, observabilidade ou outras melhorias de infraestrutura sem minha autorização.

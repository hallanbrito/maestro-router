# ADR 0007 — Previsão de uso fornecida pelo operador para estimativa pré-execução

## Contexto

O contrato público e a decisão de roteamento já distinguem a estimativa anterior
à execução do uso observado e do custo calculado posteriormente. A ADR 0005
definiu a política do cálculo pós-execução, e a ADR 0006 aprovou a configuração
operacional da referência de preço para a composição OpenAI. Mesmo com essa
referência, a composição publicada mantém `estimate.status = unavailable`, pois
a origem do primeiro uso estimado permaneceu deliberadamente aberta.

Esta ADR registra exclusivamente a primeira política operacional para essa
origem. Ela é uma decisão para implementação futura: a W16 não implementa
configuração, parsing, validação, cálculo nem qualquer comportamento executável.

## Decisão

### Natureza da primeira estimativa

A primeira estimativa pré-execução da composição OpenAI será baseada em uma
previsão estática de uso fornecida explicitamente pelo operador. Essa previsão
pertencerá ao snapshot da única rota OpenAI, será lida uma única vez durante a
composição e será aplicada igualmente a todas as solicitações atendidas pela
aplicação já construída.

A mesma previsão, portanto, será usada para todas as solicitações desse
snapshot, independentemente da tarefa e do contexto. Ela não será deduzida
automaticamente da tarefa ou do contexto, produzida por tokenizer, obtida por
consulta ao provedor nem derivada de execuções anteriores. A previsão não
constituirá garantia do uso real nem do custo calculado posteriormente.

### Mecanismo operacional futuro

Uma implementação futura poderá aceitar a variável opcional:

```text
MAESTRO_OPENAI_ESTIMATED_USAGE_JSON
```

Ela será adicional às configurações existentes e não substituirá:

- `OPENAI_API_KEY`;
- `MAESTRO_OPENAI_MODEL`;
- `MAESTRO_OPENAI_ROUTE_ID`;
- `MAESTRO_OPENAI_PRICE_REFERENCE_JSON`.

Na ausência da nova variável, o comportamento atual será preservado:

- `estimate.status = unavailable`;
- a razão continuará objetiva e sanitizada;
- uma referência de preço configurada ainda poderá sustentar somente o cálculo
  pós-execução;
- nenhuma estimativa será inventada.

A presença da variável significará que o operador deseja configurar
explicitamente uma previsão estática de uso.

### Documento JSON fechado

O valor deverá ser um objeto JSON fechado contendo exatamente:

```json
{
  "input_token": 300,
  "output_token": 500,
  "applicability_confirmed": true
}
```

Os três membros serão obrigatórios. Membros ausentes, desconhecidos ou
duplicados serão inválidos. `input_token` e `output_token` usarão os nomes das
unidades neutras do núcleo, e ambas as quantidades deverão ser inteiros JSON
positivos. Booleanos não serão aceitos como inteiros; números fracionários,
strings numéricas, valores negativos e zero serão inválidos.

`applicability_confirmed` deverá ser o booleano JSON literal `true`. Essa
declaração significará que, segundo o operador, a previsão é aplicável ao perfil
de solicitações destinado àquela composição. O Maestro validará a declaração e
a coerência estrutural, mas não verificará automaticamente sua precisão externa.

`NaN`, infinito e extensões permissivas fora do JSON padrão serão inválidos.
Valores não serão corrigidos, convertidos ou normalizados silenciosamente.

### Dependência da referência de preço

A previsão de uso somente poderá produzir uma estimativa monetária quando uma
referência de preço válida também estiver configurada por
`MAESTRO_OPENAI_PRICE_REFERENCE_JSON`.

Aplicam-se estas regras:

- previsão ausente e referência presente: a estimativa permanecerá
  `unavailable`, mas o custo pós-execução continuará podendo ficar `available`;
- previsão presente e referência ausente: a configuração será inválida e a
  inicialização será impedida;
- previsão presente e referência inválida: a configuração será inválida e a
  inicialização será impedida;
- previsão e referência válidas: uma implementação futura poderá construir uma
  estimativa `available`;
- não haverá fallback silencioso para estimativa indisponível quando a previsão
  tiver sido explicitamente fornecida de forma inválida ou incompleta.

A previsão não repetirá moeda, identificador da referência, provedor, modelo,
rota, tarifas, fonte ou condições. Esses fatos virão do mesmo `PriceReference`
já vinculado ao snapshot da rota.

### Cálculo futuro da estimativa

Quando ambas as configurações forem válidas, a estimativa será calculada
conceitualmente por:

```text
(input_token × tarifa de input_token ÷ base)
+
(output_token × tarifa de output_token ÷ base)
```

O cálculo usará as duas tarifas neutras já aprovadas e aritmética decimal exata,
sem ponto flutuante, aproximação ou arredondamento silencioso. A estimativa usará
a mesma moeda e o mesmo `price_reference` empregados pelo cálculo pós-execução.
A ordem das informações no JSON não influenciará o resultado.

Se a configuração explicitamente fornecida não puder produzir uma representação
compatível com o contrato público, a inicialização falhará. Esta ADR não define
assinatura Python, classe nem algoritmo de implementação definitivo.

### Estado econômico

A primeira política operacional produzirá somente:

- `available`, quando previsão e referência forem válidas e completas;
- `unavailable`, quando a previsão opcional estiver ausente.

Ela não produzirá `uncertain`. Esse estado continuará pertencendo ao domínio e
ao contrato público, mas ficará reservado para fontes futuras capazes de
fornecer um valor aproximado defensável com uma limitação material conhecida.

Uma configuração explicitamente presente e inválida não produzirá `uncertain`
nem `unavailable`: ela impedirá a inicialização. `available` significará que o
valor foi calculado exatamente a partir da previsão declarada explicitamente e
da referência configurada. Não significará que o Maestro conhece
antecipadamente o uso real.

### Hipóteses públicas e sanitização

A futura projeção pública continuará obedecendo exclusivamente a
`docs/05-API.md`. As hipóteses da estimativa serão geradas pelo Maestro com texto
fixo e sanitizado, indicando apenas que foram consideradas as quantidades
configuradas de `input_token` e `output_token`. Não será aceito texto livre do
operador para publicação como hipótese.

Nunca aparecerão em resposta pública, erro, log ou exceção de inicialização:

- credenciais;
- JSON bruto;
- tarifas individuais;
- fonte da referência;
- condições tarifárias;
- valores inválidos;
- detalhes externos brutos;
- conteúdo da tarefa ou do contexto.

As quantidades válidas da previsão poderão aparecer somente nas hipóteses
públicas aprovadas do objeto `estimate`, pois são fatos necessários para
compreender a estimativa. Ao fornecer a configuração, o operador aceita essa
exposição pública limitada. Erros de inicialização poderão identificar apenas o
nome seguro da variável ou um caminho ou categoria estática, sem reproduzir o
valor recebido.

### Snapshot e determinismo

A previsão será lida e validada uma única vez durante a composição. Depois da
criação da aplicação:

- alterações no ambiente não modificarão o snapshot;
- a mesma previsão permanecerá associada à rota;
- a mesma referência e previsão produzirão a mesma estimativa;
- uma atualização exigirá nova composição ou reinicialização;
- respostas anteriores não serão recalculadas.

### Relação com roteamento e teto econômico

Quando a estimativa estiver `available`, ela poderá participar das regras
econômicas existentes sem alterá-las. Na composição atual de uma única rota:

- `max_estimated_cost` poderá ser comprovado ou violado conforme as regras
  atuais;
- estimativa acima do teto produzirá a recusa já definida;
- moeda incompatível continuará economicamente insuficiente;
- estimativa válida não tornará o custo posterior uma garantia;
- não haverá nova estratégia;
- não haverá múltiplas rotas;
- não haverá comparação entre provedores;
- não haverá chamada externa para produzir a estimativa.

Esta ADR não anuncia que esse comportamento já está implementado.

### Neutralidade

O mecanismo inicial é específico do bootstrap OpenAI porque ele é a única
composição externa operacional existente. Ainda assim, unidades, referência e
estimativa continuarão neutras no núcleo. A OpenAI não se tornará provedora
padrão, e o formato não será declarado como configuração geral definitiva do
Maestro.

Outros provedores e múltiplas rotas exigirão decisões próprias. Não existe
preferência comercial ou econômica implícita.

### Relação com decisões existentes

Esta ADR especializa a ADR 0006 somente para definir a origem do primeiro uso
estimado. Ela não altera a política pós-execução da ADR 0005, não modifica
`docs/05-API.md` nem `docs/06-DECISAO-DE-ROTEAMENTO.md` e usa os estados,
unidades, moeda, referência, hipóteses e regras econômicas já aprovados.

A decisão fecha somente a origem operacional inicial da estimativa na
composição OpenAI. Qualquer implementação posterior exigirá nova aprovação
expressa do Product Owner.

## Consequências

- O operador ganhará controle explícito sobre uma previsão simples.
- A primeira política evitará tokenização automática e dependências novas.
- A estimativa poderá liberar o uso futuro de `max_estimated_cost` na composição
  OpenAI.
- O valor permanecerá fixo para todas as solicitações do snapshot.
- Tarefas com perfis de uso diferentes poderão ter estimativas pouco
  representativas.
- A precisão da previsão continuará sendo responsabilidade do operador.
- O custo calculado posterior permanecerá separado e poderá divergir.
- A ausência da nova variável preservará compatibilidade.
- Uma configuração explicitamente inválida falhará cedo.
- Nenhuma capacidade executável é entregue pela W16.

## Limites deliberados

A W16 não inclui implementação; alteração da API pública; estimativa enviada
pela solicitação; tokenização automática; contagem de caracteres, bytes ou
tokens; chamada externa para estimar; aprendizado com execuções anteriores;
preço real ou padrão; tabela ou atualização automática de preços; múltiplas
rotas; novo provedor; nova estratégia; mudança no cálculo pós-execução; garantia
de gasto; billing, cobrança ou conciliação; timeout, retry, fallback ou
streaming; persistência; endpoint administrativo; recarga dinâmica;
observabilidade, monitoramento ou tracing; Docker, CI/CD ou infraestrutura;
dependências novas; código ou testes.

Esses limites não constituem roadmap nem promessa.

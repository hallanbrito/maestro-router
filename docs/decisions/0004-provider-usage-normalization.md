# ADR 0004 — Normalização neutra de uso pós-execução

## Contexto

A fronteira neutra de execução e o primeiro adaptador OpenAI Responses já
existem. A composição operacional OpenAI explícita já pode executar uma rota
única. No estado atual, porém, mesmo uma execução bem-sucedida mantém `usage` e
`calculated_cost` publicamente como `unavailable`.

O contrato em `docs/05-API.md` já define a representação pública discriminada
de uso como `available`, `uncertain` ou `unavailable`. A
[documentação oficial da OpenAI](https://developers.openai.com/api/reference/resources/responses/methods/retrieve/)
informa contagens de tokens em `response.usage`, incluindo `input_tokens`,
`output_tokens`, `total_tokens` e detalhamentos adicionais. Essa documentação
descreve a resposta da provedora, mas não substitui os documentos normativos do
Maestro.

A normalização de uso ocorre somente depois da execução e não participa da
seleção da rota. Uso normalizado, estimativa anterior à execução e custo
calculado após a execução são conceitos diferentes.

## Decisão

Esta ADR registra uma decisão arquitetural para implementação futura; ela não
torna a normalização disponível nesta etapa.

1. A fronteira neutra de execução poderá transportar, além do conteúdo
   normalizado, uma representação neutra do uso observado na tentativa externa.
2. A representação de domínio não dependerá de classes, nomes de tipos ou
   objetos do SDK da OpenAI.
3. O adaptador traduzirá os campos externos para unidades neutras. O núcleo e a
   API não interpretarão diretamente o objeto bruto da provedora.
4. Na primeira implementação futura do adaptador OpenAI Responses,
   `response.usage.input_tokens` será normalizado como `input_token` e
   `response.usage.output_tokens` como `output_token`.
5. As quantidades serão inteiros não negativos informados pela provedora e serão
   projetadas publicamente como strings decimais exatas, nunca com ponto
   flutuante. Um zero realmente informado será preservado, sem inventar ausência
   ou consumo. A ordem será determinística: primeiro `input_token`, depois
   `output_token`.
6. O estado público futuro seguirá estas regras:
   - `available`: os dois contadores primários estão presentes e são inteiros
     não negativos;
   - `uncertain`: somente um dos contadores primários pode ser normalizado com
     segurança; os itens conhecidos são preservados e uma razão sanitizada
     explica a parcialidade;
   - `unavailable`: o objeto de uso está ausente ou nenhum dos dois contadores
     pode ser normalizado de forma defensável.
7. Ausência ou irregularidade de uso não transformará, por si só, conteúdo
   textual já validado em falha de execução. O resultado continuará disponível
   com o estado econômico correspondente.
8. A resposta externa bruta nunca será devolvida, serializada ou exposta pela
   API pública.
9. Nesta primeira decisão, `total_tokens`, contadores de cache, contadores de
   raciocínio e outros detalhamentos específicos da OpenAI não serão
   normalizados como itens públicos. Eles podem ser redundantes, sobrepostos ou
   relevantes para políticas de preço ainda não aprovadas. Sua exclusão não
   significa quantidade zero nem autoriza descartá-los silenciosamente em uma
   futura decisão de cálculo de custo.
10. `usage` permanece informação posterior à execução. Ele não altera a rota
    escolhida, não provoca uma segunda decisão, não aciona retry ou fallback,
    não substitui a estimativa registrada antes da execução e não comprova
    economia entre provedores.
11. `calculated_cost` continuará `unavailable` até que preço, referência
    econômica, método de cálculo e tratamento dos detalhamentos relevantes
    sejam aprovados separadamente.
12. A estimativa usada na seleção permanecerá exatamente a registrada antes da
    execução, sem recálculo retrospectivo.

## Segurança e neutralidade

Nenhum payload bruto, credencial, segredo, request ID externo ou mensagem
interna da provedora será publicado. Razões de uso `uncertain` ou `unavailable`
serão sanitizadas. Dados de uso não podem conter chain-of-thought nem conteúdo
de raciocínio.

O contrato neutro não importará o SDK da OpenAI. A primeira tradução concreta
para OpenAI não cria preferência comercial, econômica ou algorítmica. Futuros
adaptadores deverão produzir a mesma representação neutra sem fazer seus nomes
externos vazarem para o núcleo.

## Consequências

- A decisão prepara uma futura implementação de `usage` sem ainda torná-la
  disponível.
- O Maestro poderá distinguir uso completo, parcial e indisponível.
- A separação mantém aberta uma futura decisão sobre custo calculado.
- A ausência dos detalhamentos de cache e raciocínio limita qualquer cálculo
  financeiro até que exista uma política própria.
- Nenhuma comparação econômica nova passa a existir com esta ADR.

## Limites deliberados

Esta ADR não define nem implementa código de normalização, mudança no contrato
público de `docs/05-API.md`, preços ou tabelas de preço, estimativa
pré-execução, `calculated_cost`, referência ou governança de preços, cache
pricing, cobrança de reasoning tokens, múltiplas rotas, segundo provedor,
catálogo geral de provedores, timeout concreto, retry, fallback, streaming,
persistência, observabilidade, monitoramento, banco de dados, Docker, CI/CD,
deployment, dashboard ou qualquer capacidade futura não aprovada.

Esses limites não constituem roadmap ou promessa futura.

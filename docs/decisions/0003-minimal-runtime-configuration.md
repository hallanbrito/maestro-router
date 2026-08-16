# ADR 0003 — Configuração operacional mínima

## Contexto

O núcleo executável permanece neutro: `create_app()` conserva o comportamento
padrão atual, com catálogo e registro de adaptadores vazios, sem rota, provedora
ou modelo registrados automaticamente. Para permitir futuramente uma primeira
execução real, é necessária uma composição operacional explícita sem transferir
configuração ou credenciais para o núcleo ou para o adaptador.

Esta ADR registra somente a direção proposta. Qualquer implementação depende de
revisão e aprovação prévias do Product Owner.

## Decisão

A configuração operacional será um ponto de composição local, explícito,
opcional e separado do núcleo neutro. A implementação posterior seguirá a
direção de um módulo dedicado, conceitualmente `maestro_router.bootstrap`, com
uma fábrica ASGI de bootstrap OpenAI. Ela poderá ser iniciada explicitamente,
conceitualmente, por:

```shell
python -m uvicorn --factory --app-dir src maestro_router.bootstrap:create_openai_app_from_env
```

A composição será limitada a uma rota OpenAI Responses, um modelo informado
explicitamente, o `OpenAIResponsesAdapter`, execução local por processo e um
snapshot de configuração capturado uma vez na inicialização. Ela exigirá três
entradas não brancas, sem valores padrão silenciosos:

- `OPENAI_API_KEY`: segredo usado exclusivamente para construir o cliente
  assíncrono oficial;
- `MAESTRO_OPENAI_MODEL`: modelo enviado à Responses API;
- `MAESTRO_OPENAI_ROUTE_ID`: identificador público e opaco da rota.

Somente na composição, os identificadores internos serão fixos como provedor
`openai` e adaptador `openai-responses`. A rota será habilitada, sem capacidades
ou critérios de qualidade declarados, sem indisponibilidade conhecida, com o
modelo e o ID recebidos explicitamente e associada ao adaptador indicado.

Nenhum preço será embutido ou inventado. Enquanto preço e método de estimativa
não forem aprovados, a rota terá estimativa econômica `unavailable`, com razão
explícita e sanitizada. Assim, sem teto econômico, ela poderá ser selecionada
como candidato único; quando custo for indispensável, a decisão poderá resultar
em `INSUFFICIENT_ECONOMIC_INFORMATION`. Restrições de capacidade ou qualidade
não declaradas continuarão recusando a rota. Essa composição não demonstra
economia calculada nem comparação entre provedores.

## Validação e falhas

Todas as entradas serão validadas antes da construção da aplicação operacional.
Entrada ausente, vazia ou formada somente por espaços impedirá a inicialização,
antes de o processo atender solicitações. A falha identificará somente o nome
seguro da entrada inválida, sem incluir qualquer valor.

Essa falha operacional de inicialização não altera os envelopes HTTP aprovados
para aplicações construídas por `create_app()`. A implementação deverá permitir
testes controlados da validação e da composição sem consultar ou modificar o
ambiente real do processo e sem realizar chamadas de rede, sem que esta decisão
antecipe assinaturas Python.

## Segurança e neutralidade

`OPENAI_API_KEY` é a referência operacional concreta ao segredo nesta primeira
composição. Seu valor será lido somente no ponto de composição e entregue
diretamente à construção de `AsyncOpenAI`. Ele não entrará em `Route`,
`RouteCatalog`, contratos públicos, decisão, fatores, mensagens HTTP ou exemplos,
nem será registrado, serializado, devolvido, exibido em exceção ou preservado em
estrutura de domínio. O adaptador continuará recebendo por injeção um cliente já
construído e continuará sem ler ambiente, arquivos, credenciais ou configuração.

Esta primeira composição concreta existe porque o adaptador correspondente já
existe. Ela não é rota padrão do Maestro e não concede preferência econômica,
algorítmica ou comercial à OpenAI.

## Limites deliberados

Esta decisão não inclui arquivo `.env`, JSON, YAML ou TOML; argumentos de linha
de comando; banco de dados; serviço remoto de configuração; recarga dinâmica;
múltiplas rotas; endpoint administrativo; descoberta automática;
`OPENAI_BASE_URL`; endpoint customizado; nem nova dependência de configuração.

Ela também não implementa nem define modelo ou rota padrão, catálogo geral de
provedores, formato geral e definitivo de configuração, preço ou estimativa
real, `usage`, `calculated_cost`, timeout concreto, retry, fallback,
idempotência, streaming, armazenamento de segredos, persistência, Docker,
CI/CD, deployment, observabilidade ou monitoramento. Esses limites não formam
roadmap nem promessa futura.

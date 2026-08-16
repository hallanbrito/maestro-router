# ADR 0002 — Adaptador OpenAI Responses

## Decisão

A OpenAI Responses API é o primeiro adaptador externo concreto do Maestro
Router. Essa escolha prova a integração com um provedor real, mas não concede à
OpenAI prioridade comercial, algorítmica ou de configuração.

O adaptador implementa o contrato neutro assíncrono `ExecutionAdapter` e recebe
o cliente assíncrono oficial por injeção. Ele não lê variáveis de ambiente,
arquivos, credenciais, endpoints ou configuração operacional. O modelo enviado
vem exclusivamente de `ExecutionRoute.model`; identificadores de rota,
provedor e adaptador não se tornam instruções.

Cada execução realiza uma única chamada não streaming à Responses API, com o
retry automático do SDK neutralizado por `with_options(max_retries=0)`. O
adaptador não implementa retry, fallback, troca de rota ou nova decisão.

`task` e `context` são traduzidos deterministicamente para uma única mensagem
de usuário. Sem contexto, seu conteúdo contém somente `task`. Com contexto, a
mesma mensagem contém dois conteúdos `input_text`, primeiro `task` e depois
`context`. Dados da aplicação não são elevados aos papéis `system` ou
`developer`.

Somente uma resposta concluída com resultado textual válido é normalizada para
`TextExecutionResult`; texto vazio continua válido quando existir como saída
textual concluída. O objeto bruto do SDK nunca é devolvido. Timeout apenas é
traduzido quando reportado pelo cliente; esta decisão não define valor nem
política global de timeout.

Erros externos são convertidos para a taxonomia neutra existente. Nenhum
payload, corpo de erro, chave, endpoint interno, stack trace ou mensagem externa
alcança a resposta pública. `usage` e `calculated_cost` permanecem
`unavailable` nesta fatia.

## Limites deliberados

O adaptador não é registrado automaticamente no `create_app()` padrão. Nenhuma
rota, provedora, credencial ou modelo OpenAI é configurado por padrão. Os testes
automatizados usam clientes controlados e não realizam chamada real à OpenAI.

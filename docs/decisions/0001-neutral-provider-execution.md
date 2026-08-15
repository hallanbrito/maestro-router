# ADR 0001 — Execução neutra de provedores

## Decisão

O núcleo usa um contrato assíncrono neutro que entrega ao adaptador somente a
solicitação textual comum e a identidade neutra da rota. O adaptador devolve um
resultado textual normalizado ou um erro interno tipado de falha,
indisponibilidade ou timeout.

As associações entre identificadores e adaptadores são injetadas manualmente em
um `Mapping` em memória. Cada requisição captura um snapshot imutável das
associações aplicáveis e usa o mesmo snapshot na decisão e na execução.

Uma associação ausente ou inválida é uma falha local isolável: a rota afetada é
excluída antes dos demais filtros, enquanto rotas habilitadas e localmente
válidas continuam. Se nenhuma rota habilitada possuir associação válida, o
resultado é `INVALID_CONFIGURATION` antes da decisão.

O único adaptador concreto desta fatia é controlado e existe nos testes.

## Limites deliberados

Não há adaptador de provedor real, chamada de rede, gestão de segredos, timeout
concreto, retry ou fallback. Essas ausências são intencionais e não são
substituídas por descoberta automática, plugins, configuração persistente ou
container de dependências.

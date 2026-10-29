# 0013. Adaptador Google Gemini via Interactions API sem estado

- **Status:** Aprovada pelo Product Owner (Issue #28)
- **Data:** 2026-10-29
- **Autor:** Maestro Router Team
- **Decisores:** PO Hallan

## Contexto

O Maestro Router foi concebido para oferecer uma camada neutra de roteamento entre
múltiplos provedores de modelos de IA, sem conceder preferência comercial ou algorítmica
a nenhum provedor. Após o estabelecimento do adaptador OpenAI Responses (ADR 0002)
e da consolidação da camada administrativa local do Control Center (ADR 0012), a
Issue #28 determinou a implementação do segundo provedor externo concreto: a
Google Gemini Developer API utilizando a Interactions API em modo sem estado.

## Decisão

A Google Gemini Developer API via Interactions API sem estado é o segundo adaptador
externo concreto do Maestro Router. Essa escolha consolida o compromisso de
neutralidade entre provedores estabelecido no Manifesto e na ADR 0001, provando
a coexistência de múltiplos provedores no mesmo catálogo sem conceder privilégio
comercial, algorítmico ou de configuração a nenhum provedor.

### Fronteira e Injeção

O adaptador (`GoogleGeminiInteractionsAdapter`) implementa o protocolo neutro
assíncrono `ExecutionAdapter` e recebe o cliente assíncrono oficial (`google-genai`,
versão fixada `2.34.0`) por injeção externa. O cliente é construído fora do
núcleo e nenhuma regra central de roteamento ou decisão (`routing.py`) conhece
detalhes específicos do Google ou da OpenAI.

### Execução Textual sem Estado

Cada execução textual traduz deterministicamente `task` e `context` para o formato
de entrada textual da Interactions API:
- `task` como primeiro bloco de texto (`{"type": "text", "text": task}`);
- `context` (quando fornecido) como bloco subsequente (`{"type": "text", "text": context}`).

Toda chamada à Interactions API envia obrigatoriamente e explicitamente:
- `store=False`;
- `automatic_continuation=False` (desabilita a continuação automática padrão do SDK,
  garantindo uma única interação individual e prevenindo múltiplos hops com repreenchimento
  e reenvio de input acumulado).

O adaptador omite mandatoriamente:
- `previous_interaction_id`;
- `background=True`;
- tools e function calling;
- streaming;
- agentes ou memória conversacional multi-turn;
- continuação manual ou tokens de continuação.

### Normalização de Saída

Somente respostas com `status == "completed"` e conteúdo textual final defensável
são normalizadas para `TextExecutionResult`. Respostas bloqueadas, filtradas,
incompletas ou estruturalmente incompatíveis resultam em falha normalizada
(`ExecutionFailedError`). O payload bruto do SDK nunca é exposto à aplicação consumidora.

### Normalização de Uso (Usage)

O uso reportado pelo provedor é traduzido estritamente para as unidades neutras:
- `usage.total_input_tokens` → `input_token`;
- `usage.total_output_tokens` → `output_token`.

Quando o provedor retorna contagens completas, o estado é `available`. Quando apenas
uma contagem é retornada ou quando há indicação de incompletude, os estados
`uncertain` ou `unavailable` são atribuídos conforme os contratos normativos (ADR 0004).
Nenhum valor de uso ou token é inferido ou inventado na ausência de dados do provedor.

### Sanitização de Erros e Defensividade

Erros externos são traduzidos para a taxonomia neutra do Maestro:
- Erros de timeout (408 / deadlines) → `ExecutionTimeoutError`;
- Erros transitórios, indisponibilidade ou rate limit/quota (429, 503, 5xx) → `ExecutionUnavailableError`;
- Falhas de autenticação, permissão ou entrada inválida (400, 401, 403, 404) → `ExecutionFailedError`.

Nenhuma credencial (API key), corpo bruto de erro externo, stack trace ou mensagem
sensível do SDK é vazada na resposta ou nos logs operacionais.

### Camada Administrativa Local e Control Center

No Control Center (ADR 0012):
- **Ciclo de vida da credencial:** a Gemini API Key reside exclusivamente na memória
  volátil do processo backend. Nunca é gravada em disco, banco, arquivos,
  localStorage, sessionStorage ou fixtures. O backend nunca devolve o segredo ao navegador.
- **Verificação de credencial sem geração paga:** a validação da credencial é
  realizada exclusivamente por meio de operação oficial que lista modelos (`client.aio.models.list()`),
  sem invocar geração de texto ou incorrer em custos.
- **Descoberta oficial de modelos:** os modelos são descobertos dinamicamente via
  metadados oficiais da Developer API, filtrando modelos com capacidade textual compatível
  (`generateContent`) e excluindo modelos incompatíveis (embeddings, imagem, vídeo).
- **Dados econômicos e trilhas:** rotas Google não recebem preços automáticos nem
  previsão implícita de tokens. Todas as tarifas, fontes e estimativas exigem
  declaração consciente pelo operador humano. A trilha Free aceita apenas gratuidade
  explicitamente declarada (`rate = 0.00`).
- **Isolamento de snapshot:** execuções em andamento utilizam exclusivamente o catálogo
  e os adaptadores congelados no snapshot da requisição (PR #27), sem sofrer mutações
  concorrentes por alterações administrativas posteriores.

## Limites deliberados

O adaptador não implementa Vertex AI, OAuth corporativo, Antigravity, Deep Research,
streaming, retry automático, fallback entre rotas ou tabelas de preços embutidas.
Todos os testes automatizados utilizam clientes controlados e transporte simulado,
sem qualquer chamada real à rede externa do Google.

# FREE-LAB: fallback + cotas + três provedores (11/11/2026)

**Status:** experimental, não homologado. PR CH-2 para revisão do PO; não altera o contrato público `POST /v1/executions`, o roteador canônico nem o Control Center. Esta composição opcional cria `GET /lab/status` e `POST /lab/execute` num processo separado. Não fazer merge/release/deploy sem revisão.

## O que existe

- Groq: Chat Completions OpenAI-compatible, com `openai/gpt-oss-20b` e `openai/gpt-oss-120b`. O PO forneceu em 11/11/2026 os limites **por modelo** de 30 RPM, 1.000 RPD, 8.000 TPM e 200.000 TPD para os dois. São tetos locais, não saldo efetivo nem franquia garantida.
- Gemini: Interactions API sem estado, com `store=False`, `automatic_continuation=False`, sem ferramentas e com `generation_config.max_output_tokens`.
- Cerebras: Chat Completions OpenAI-compatible, modelo explicitamente configurado pelo operador. Oferece um plano gratuito segundo documentação pública; elegibilidade da conta precisa ser verificada.
- Fallback no máximo 3 **chamadas**; somente em HTTP 429 inequivocamente classificado pelo adaptador Groq/Cerebras. Esgotamento de cota local pula a rota. Falhas ambíguas (5xx, timeout, erro de rede, autenticação, conteúdo parcial ou saída inválida) encerram a tentativa, sem replay automático.
- Reserva concorrente em memória via `asyncio.Lock`, janelas deslizantes 60s e 24h; sem reembolso da reserva em falhas. Contador de tokens estimado por comprimento UTF-8 + 128 de margem + saída máxima de 512 tokens.
- Resposta traz rota e histórico de tentativas sanitizado, com `real_billing: unknown`. Nenhuma chave ou detalhe bruto de erro é devolvido.
- Inativo por padrão. Nunca troca para uma rota paga automaticamente.

**Limite de segurança:** os controles de quota **não garantem ausência de cobrança**. Não interrogam o saldo real do provedor, não detectam outros clientes do mesmo projeto, não rastreiam quotas agregadas cross-model/org, não garantem um limite universal de tokens para todos os tokenizadores e se perdem na reinicialização. Usar somente **1 worker** e instância local. Não representa a implementação normativa de evidências de gratuidade exigida pela ADR 0014; a aprovação dessa alteração exige avaliação adicional.

## Ativação local, após confirmar tier gratuito e permissões das contas

Instale as dependências do README do Maestro. Defina a chave **apenas no seu terminal**, nunca no Git.

```bash
export GROQ_API_KEY='(chave privada local)'
export MAESTRO_GROQ_FREE_CONFIRMED=yes
# Só ative depois de verificar sua modalidade real:
export MAESTRO_FREE_LAB_RISK_ACK=yes
export MAESTRO_FREE_LAB_LIVE=yes

python -m uvicorn --factory --app-dir src maestro_router.free_lab:create_free_lab_app --host 127.0.0.1 --port 8010 --workers 1
```

Teste em outro terminal:

```bash
curl -s http://127.0.0.1:8010/lab/status
curl -s -X POST http://127.0.0.1:8010/lab/execute \
  -H 'Content-Type: application/json' \
  -d '{"task":"Explique fallback em uma frase."}'
```

Para adicionar Gemini, somente depois de conferir no **seu** Google AI Studio o modelo elegível e quotas da conta/projeto:

```bash
export GEMINI_API_KEY='(chave privada local)'
export MAESTRO_GEMINI_MODEL='(modelo confirmado)'
export MAESTRO_GEMINI_RPM='(limite confirmado)'
export MAESTRO_GEMINI_RPD='(limite confirmado)'
export MAESTRO_GEMINI_TPM='(limite confirmado)'
export MAESTRO_GEMINI_TPD='(limite confirmado)'
export MAESTRO_GEMINI_FREE_CONFIRMED=yes
```

Para adicionar Cerebras, configurar analogamente `CEREBRAS_API_KEY`, `MAESTRO_CEREBRAS_MODEL`, `MAESTRO_CEREBRAS_RPM`, `MAESTRO_CEREBRAS_RPD`, `MAESTRO_CEREBRAS_TPM`, `MAESTRO_CEREBRAS_TPD` e `MAESTRO_CEREBRAS_FREE_CONFIRMED=yes`. Modelos e valores são intencionalmente obrigatórios e não inventados. Reinicie o processo após mudar o ambiente.

**Modo offline sem chamadas e sem risco:** não defina `MAESTRO_FREE_LAB_LIVE`; rode `PYTHONPATH=src pytest -q tests/test_free_fallback_lab.py`.

## Critérios de aceite e pendências

- Testes offline com fakes cobrindo 429, não repetição de falhas ambíguas, controle atômico de quota, allowlist Free e nenhum despacho sem autorização.
- Pendente: teste de integração real com credenciais e projetos confirmados, leitura de cabeçalhos oficiais de quotas, cota compartilhada de organização, reconciliação de uso reportado, reinício/persistência, revisão de compatibilidade do SDK e validação econômica `strict_no_additional_cost` da ADR 0014.
- **Sem autorização para merge, publicação, produção ou cobrar créditos.** Revisão independente e aceite do PO antes da integração canônica.

Fontes: https://console.groq.com/docs/rate-limits ; https://console.groq.com/docs/openai ; https://ai.google.dev/gemini-api/docs/pricing ; https://ai.google.dev/api/interactions-api-v1 ; https://inference-docs.cerebras.ai/support/pricing

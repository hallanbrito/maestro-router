# MAESTRO-0800 — laboratório offline Groq → Alibaba → Gemini

**Escopo:** extensão experimental da Draft PR #51; não integra o runtime canônico, não altera `POST /v1/executions`, não é homologação da trilha Free e não executa nenhum modelo durante os testes. Issue canônica: #61, dependências #56/#59/#60.

## Preparação local (NÃO ative o modo live neste teste)
A rota Alibaba existe **somente** quando cada item abaixo está presente no ambiente:

- `ALIBABA_API_KEY` (segredo local, nunca versionar)
- `MAESTRO_ALIBABA_WORKSPACE_ID` (apenas rótulo DNS, não URL)
- `MAESTRO_ALIBABA_MODEL` (modelo escolhido e confirmado no console)
- `MAESTRO_ALIBABA_FREE_EXPIRES_UTC` (AAAA-MM-DD, futuro, confirmado no console)
- `MAESTRO_ALIBABA_RPM`, `MAESTRO_ALIBABA_RPD`, `MAESTRO_ALIBABA_TPM`, `MAESTRO_ALIBABA_TPD` (limites locais conservadores)
- `MAESTRO_ALIBABA_FREE_CONFIRMED=yes`, `MAESTRO_ALIBABA_SCOPE_INTERNATIONAL_CONFIRMED=yes`, `MAESTRO_ALIBABA_FREE_QUOTA_ONLY_CONFIRMED=yes`

As flags representam declarações do operador, **não verificações automáticas**. Só a região Singapore e o escopo International recebem franquia gratuita para modelos elegíveis, sujeita a prazo e saldo próprios. No console, confirme o seletor *Free Quota Only* **ON por modelo** antes de considerar qualquer ensaio real; a configuração pode demorar a entrar em vigor. Sem prova verificável, manter live desativado.

A URL é construída de modo restrito: `https://<workspace>.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`. URLs arbitrárias são recusadas. Uma resposta 403/401, timeout, 5xx ou conteúdo incerto interrompe o ciclo sem replay automático. Apenas 429 explicitamente classificado por adaptador permite tentar outra rota. O limite de três despachos é conservador e o registro local de quotas **não é** saldo oficial, cobrança real nem reserva global.

## Comportamento da demonstração
Com flags válidas, a ordem experimental é Groq 20B → Alibaba → Gemini (até três despachos); Cerebras e Groq 120B ficam como alternativas posteriores quando elegíveis e a janela de tentativas permitir. A rota Alibaba é omitida se faltar flag, limite, workspace, modelo, data válida ou chave.

Comandos de validação offline:
```bash
PYTHONPATH=src python -m pytest -q tests/test_free_fallback_lab.py tests/test_free_lab_alibaba_offline.py
```

**Gates restantes:** revisão independente, CI, observação do saldo/Free Quota Only por conta e modelo, motor agregado de quotas (#59), adaptadores homologados (#56/#60), autorização específica do PO para smoke (#64). Não habilitar `MAESTRO_FREE_LAB_LIVE` nem `MAESTRO_FREE_LAB_RISK_ACK` sem novo gate.

Fontes: https://www.alibabacloud.com/help/en/model-studio/new-free-quota e https://www.alibabacloud.com/help/en/model-studio/base-url

# Maestro Router

**Roteamento econômico e explicável de modelos de inteligência artificial.**

O Maestro Router é um MVP open source em **Python 3.12 e FastAPI** que adiciona uma camada de decisão entre uma aplicação e os modelos de IA. Em vez de fixar um modelo para todas as solicitações, ele avalia **rotas previamente configuradas**, verifica quais atendem aos requisitos obrigatórios e **escolhe o menor custo estimado entre as rotas elegíveis e economicamente comparáveis**, explicando a decisão.

> **Estado do projeto:** MVP funcional para avaliação técnica, com testes automatizados. A pré-release `v0.1.0-rc.1` ainda não foi publicada. **Integração externa atual:** OpenAI (opcional); os outros provedores ainda não possuem adaptadores executáveis neste repositório.

## Por que existe?

Quem integra IA a um software precisa decidir **qual modelo usar, em quais condições e com qual custo previsto**. Essa escolha costuma ficar fixa na aplicação ou depender de regras pouco transparentes.

O Maestro separa a **decisão da execução**: primeiro verifica quais rotas configuradas atendem aos requisitos; depois compara estimativas econômicas compatíveis e escolhe uma rota segundo uma regra determinística. O resultado inclui informações para compreender a escolha.

### Exemplo: o menor custo que atende aos requisitos

Uma aplicação possui três rotas configuradas com estimativas comparáveis, todas em USD:

| Rota | Custo estimado | Atende aos requisitos? | Resultado |
| --- | ---: | :---: | --- |
| **A** | **US$ 0,003** | Sim | **Selecionada** |
| B | US$ 0,001 | Não | Excluída na elegibilidade |
| C | US$ 0,005 | Sim | Elegível, mas mais cara |

**Por que a rota A?** A rota B custa menos, mas não atende aos requisitos obrigatórios e é eliminada antes da comparação econômica. Entre as elegíveis A e C, o Maestro seleciona **A**, pois tem o menor custo estimado.

**Regra central: primeiro atender aos requisitos; depois comparar custos.** A avaliação utiliza capacidades, critérios e estimativas previamente declarados. O MVP não mede automaticamente a qualidade de uma resposta nem determina sozinho a complexidade da tarefa.

*Valores fictícios para ilustrar a regra de seleção, não preços reais de provedores ou economia comprovada.*

## Como funciona

```text
Aplicação
   ↓ tarefa, contexto e restrições
API do Maestro — POST /v1/executions
   ↓ validação e elegibilidade
Avaliação econômica das rotas admissíveis
   ↓ estratégia lowest-estimated-cost
Rota selecionada → adaptador → modelo configurado
   ↓
Resultado + explicação + dados econômicos disponíveis
```

A seleção considera **capacidades e critérios de qualidade declarados**, restrições de rotas, disponibilidade conhecida e limites econômicos. A estratégia atual desempata de modo determinístico. Não há uma classificação automática da complexidade semântica da tarefa.

## O que o MVP já entrega

- **API única:** validação rigorosa da operação `POST /v1/executions` e erros normalizados.
- **Roteamento controlável:** requisitos, rotas permitidas, indisponibilidade conhecida e configuração de habilitação.
- **Comparação econômica:** estimativa pré-execução quando o operador fornece informações suficientes; escolha da rota elegível de menor estimativa.
- **Execução desacoplada:** núcleo neutro de provedores, com adaptador OpenAI opcional e composição de uma ou múltiplas rotas OpenAI.
- **Explicabilidade:** informações sobre a seleção, uso normalizado e custo calculado após execução quando disponíveis.

**Limitações importantes:** não há preço ou modelo padrão, atualização automática de preços, adaptadores para outros provedores, retry ou fallback concretos. A comparação depende de preços e previsões fornecidos pelo operador; custo calculado não equivale à cobrança do provedor nem comprova economia real.

Veja o [estado técnico completo do MVP](docs/ESTADO-DO-MVP.md).

## Experimente localmente

**Requisito:** Python 3.12. No Linux ou macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Os testes automatizados usam clientes controlados e **não realizam chamadas externas**.

Para iniciar a API neutra:

```bash
python -m uvicorn --app-dir src maestro_router.api:app
```

O aplicativo padrão inicia **sem rotas ou adaptadores configurados**. Uma requisição válida recebe `NO_ELIGIBLE_ROUTE` — comportamento esperado, não uma demonstração de seleção entre modelos.

Para configurar uma execução real com OpenAI, inclusive o **modo multirrota**, ou seguir instruções para PowerShell, consulte o [guia de execução local](docs/GUIA-DE-EXECUCAO.md). Chamadas reais exigem credencial própria e podem gerar custos.

## Documentação e colaboração

| Quero entender... | Onde encontrar |
| --- | --- |
| Visão do produto e problema resolvido | [Visão geral](docs/01-VISAO-GERAL.md) |
| Como instalar, configurar e executar | [Guia de execução](docs/GUIA-DE-EXECUCAO.md) |
| Capacidades atuais e limitações | [Estado do MVP](docs/ESTADO-DO-MVP.md) |
| Formato da API, entradas, respostas e erros | [Contrato da API](docs/05-API.md) |
| Regras de decisão e desempate | [Decisão de roteamento](docs/06-DECISAO-DE-ROTEAMENTO.md) |
| Arquitetura e decisões técnicas | [Mapa de arquitetura](ARCHITECTURE.md) e [ADRs](docs/decisions/) |
| Processo colaborativo de engenharia | [Método C.H. de execução](docs/07-METODO-CH-EXECUCAO.md) |

Para navegar pelas fontes normativas, consulte [docs/INDEX.md](docs/INDEX.md). Agentes e contribuidores devem começar por [AGENTS.md](AGENTS.md) e [CONTRIBUTING.md](CONTRIBUTING.md). As [notas da pré-release candidata](docs/releases/v0.1.0-rc.1.md) descrevem seu escopo de avaliação; **não existe release publicada**.

Licença: [Apache 2.0](LICENSE).

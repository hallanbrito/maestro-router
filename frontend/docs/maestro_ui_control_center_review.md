# Maestro Router — Control Center (Homologação e Evidências Visuais)

Este documento integra o front-end do Maestro Router com os resultados das validações automatizadas e as capturas reais da interface gráfica em execução local.

---

## 1. Evidências Visuais Reais da Interface

As capturas abaixo foram geradas via navegador headless (Firefox) em ambiente local renderizando os componentes da interface conectada à API FastAPI nativa do Maestro Router:

### 1.1 Estado Inicial Desktop (`1280x850`)
- **Arquivo:** [`frontend/screenshots/01-estado-inicial-desktop.png`](../screenshots/01-estado-inicial-desktop.png)
- **Descrição:** Tela principal com formulário de envio limpo, menu de exemplos rápidos, painel sanfonado de restrições colapsado, atalho de teclado `Ctrl+Enter` visível e painel direito no estado vazio orientativo ("Pronto para Roteamento Neutro").
- **Comportamento:** O indicador superior exibe *"Pronto para execução"* sem disparar qualquer requisição automática de fundo (`fetch`) na carga da página.

### 1.2 Recusa Controlada: `NO_ELIGIBLE_ROUTE` (HTTP 422)
- **Arquivo:** [`frontend/screenshots/02-recusa-no-eligible-route.png`](../screenshots/02-recusa-no-eligible-route.png)
- **Descrição:** Resultado real obtido ao submeter uma solicitação para a API neutra padrão (`maestro_router.api:app`), cujo catálogo é deliberadamente vazio em memória.
- **Elementos Observáveis:**
  * Alerta de proteção ativa com código normativo `NO_ELIGIBLE_ROUTE`.
  * Orientações operacionais recomendadas explicando a neutralidade e o comando CLI para iniciar com o catálogo multirrota OpenAI (`create_openai_app_from_env`).
  * Cartão formal de **Decisão de Roteamento** com desfecho `ROTA RECUSADA` (`outcome: 'refused'`), estratégia `lowest-estimated-cost` (`applied: false`), razão objetiva e fator determinante categorizado (`[ROUTE] O catálogo não continha rotas configuradas.`).

### 1.3 Layout Mobile Responsivo (`412x1100`, largura < 840 px)
- **Arquivo:** [`frontend/screenshots/03-layout-mobile.png`](../screenshots/03-layout-mobile.png)
- **Descrição:** Comportamento responsivo em telas estreitas (largura <= 840 px).
- **Elementos Observáveis:**
  * Grid em coluna única vertical fluida.
  * Cabeçalho compacto com navegação horizontal deslizável sem barra de rolagem intrusiva.
  * Form actions e botões de toque com 100% de largura adaptativa.
  * Legibilidade e contraste mantidos integralmente.

---

## 2. Invariantes Técnicos e Contratos Normativos

| Invariante / Requisito | Status | Implementação |
| :--- | :---: | :--- |
| **Endpoint Único da API v1** | ✅ Aprovado | Conecta exclusivamente a `POST /v1/executions`. Nenhum endpoint inexistente (como `/health`, `/status` ou `/metrics`) é utilizado. |
| **Preservação do Contrato de Entrada** | ✅ Aprovado | `task`, `context`, identificadores de rota, critérios e moeda são transmitidos exatamente como digitados. O método `trim()` é restrito à verificação booleana de presença. |
| **Exposição de `required_quality_criteria`** | ✅ Aprovado | Campo acessível no painel expansível de restrições (`constraints`), permitindo filtrar rotas por critérios de qualidade configurados. |
| **Uniões Discriminadas Estritas** | ✅ Aprovado | `SelectedDecision` vs `RefusedDecision`; `Available`, `Uncertain` e `Unavailable` para estimativa, uso e custo; categorias fechadas sem escape `\| string`. |
| **Taxonomia Fechada de Erros** | ✅ Aprovado | Códigos contratuais estritos (400, 415, 422, 500, 502, 503, 504) com status numéricos literais; anomalias de protocolo desviadas para `protocol_error`. |
| **Valores Indisponíveis sem Falsos Zeros** | ✅ Aprovado | Quando a estimativa, uso ou custo são `unavailable`, a interface apresenta o traço `—` e a justificativa `reason`, nunca zero artificial. |
| **Decimais Monetários Preservados** | ✅ Aprovado | Grandezas numéricas trafegam e são manipuladas como strings para prevenir erros de precisão IEEE 754. |
| **Segurança e Operação Offline** | ✅ Aprovado | Zero armazenamento de segredos ou chaves no front-end; sem telemetria persistente ou cookies; fontes do sistema nativo para operação 100% desconectada da internet. |

---

## 3. Validações Automatizadas

- **Instalação Reproduzível:** `npm ci` aprovado com `engines` restrito a `^22.22.2 || ^24.15.0 || >=26.0.0`.
- **Suíte Front-end (Vitest):** 20 testes aprovados em 4.39s (100% de sucesso).
- **Tipagem e Compilação (`tsc && vite build`):** 1.941 módulos transformados em 666ms com zero erros.
- **Suíte Back-end (Pytest):** 625 testes aprovados em 5.75s (zero regressão).
- **Verificação de Diff Git (`git diff --check`):** Saída limpa.

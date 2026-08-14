# AGENTS.md — Maestro Router

## Identidade do projeto

- **Nome:** Maestro Router.
- **Estágio atual:** implementação incremental do MVP a partir da especificação normativa.
- **Objetivo:** oferecer uma camada open source que escolha uma rota de modelo de IA
  de forma econômica, neutra entre provedores, controlável e explicável.
- O repositório contém as primeiras fatias da implementação do produto.

Este arquivo é um mapa operacional. Ele não substitui a documentação normativa.
Use [docs/INDEX.md](docs/INDEX.md) para rotear o contexto da tarefa.

## Fontes de verdade

| Assunto | Arquivo que governa |
| --- | --- |
| Identidade, valores e princípios inegociáveis | [docs/00-MANIFESTO.md](docs/00-MANIFESTO.md) |
| Problema, solução, público e escopo do MVP | [docs/01-VISAO-GERAL.md](docs/01-VISAO-GERAL.md) |
| Valor, públicos e limites das promessas | [docs/02-PROPOSTA-DE-VALOR.md](docs/02-PROPOSTA-DE-VALOR.md) |
| Componentes, responsabilidades, fronteiras e fluxo | [docs/03-ARQUITETURA.md](docs/03-ARQUITETURA.md) |
| Comportamentos e casos de uso observáveis | [docs/04-CASOS-DE-USO.md](docs/04-CASOS-DE-USO.md) |
| Contrato técnico da API pública v1 | [docs/05-API.md](docs/05-API.md) |
| Algoritmo e invariantes da decisão de roteamento | [docs/06-DECISAO-DE-ROTEAMENTO.md](docs/06-DECISAO-DE-ROTEAMENTO.md) |
| Decisões arquiteturais adicionais | [docs/decisions/](docs/decisions/) |

Em caso de conflito, siga a precedência declarada nos próprios documentos.
O Manifesto prevalece como identidade permanente. Para a fronteira pública,
`docs/05-API.md` é obrigatório. A decisão de roteamento especializa esse contrato
sem poder alterá-lo.

## Antes de trabalhar

1. Leia este `AGENTS.md`.
2. Identifique em `docs/INDEX.md` quais documentos governam a tarefa.
3. Leia somente os documentos normativos necessários para a mudança.
4. Verifique `docs/decisions/` por decisões adicionais aplicáveis.
5. Se houver código, localize e analise apenas o código e os testes relevantes.
6. Distinga fatos documentados de suposições; declare qualquer suposição necessária.
7. Implemente a menor alteração capaz de atender à tarefa.

Não trate uma decisão deliberadamente aberta como autorização para inventá-la.
Se uma ambiguidade relevante de produto ou arquitetura puder mudar o resultado,
interrompa a decisão local e reporte a necessidade de decisão humana.

## Depois de trabalhar

1. Revise o próprio diff integralmente.
2. Execute os testes e validadores relacionados que já existirem.
3. Verifique compatibilidade com os contratos e invariantes aplicáveis.
4. Confirme que nenhuma decisão arquitetural foi alterada silenciosamente.
5. Confirme que nenhum documento normativo ou arquivo fora do escopo mudou por acidente.
6. Informe claramente:
   - arquivos alterados;
   - testes e validações realizados;
   - decisões tomadas e suposições usadas;
   - pontos que ainda exigem decisão humana.

## Guardrails

> Implemente apenas o necessário. Não adicione Docker, CI/CD, monitoramento, documentação extensa, observabilidade ou outras melhorias de infraestrutura sem autorização.

- Não implemente funcionalidades fora do MVP aprovado.
- Não antecipe abstrações sem uma necessidade real demonstrada.
- Não altere contratos aprovados silenciosamente.
- Não modifique decisões arquiteturais sem registrar a mudança adequada e informá-la.
- Não adicione dependências sem necessidade e justificativa explícitas.
- Não duplique documentação existente; prefira apontar para a fonte normativa.
- Prefira mudanças pequenas, reversíveis e verificáveis.
- Preserve neutralidade entre provedores e controle explícito do usuário.
- Não apresente possibilidades futuras como capacidades atuais ou compromissos de roadmap.
- Não confunda estimativa de custo, custo calculado e cobrança do provedor.
- Não exponha credenciais, segredos, payloads externos brutos ou raciocínio interno.
- Registre fatos documentados como fatos e suposições como suposições.
- Diante de ambiguidade relevante de produto ou arquitetura, solicite decisão humana.

## Escopo atual do repositório

- A documentação normativa está em `docs/`.
- `README.md` e `ARCHITECTURE.md` são apenas pontos de entrada; não são fontes normativas.
- `PRODUCT.md`, `ROADMAP.md`, `CONTRIBUTING.md` e `LICENSE` são placeholders vazios.
- Há código inicial do produto em `src/`, dependências declaradas e testes com pytest em `tests/`.
- Não existe estrutura persistente de planos. Tarefas pequenas não precisam dela;
  mudanças maiores só devem introduzi-la quando houver utilidade concreta.

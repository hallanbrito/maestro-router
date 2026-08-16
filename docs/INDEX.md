# Índice da documentação

Este índice é apenas um roteador de contexto. Os documentos vinculados são as
fontes normativas; este arquivo não resume nem redefine seu conteúdo.

| Documento | Assunto | Autoridade ou finalidade | Quando ler |
| --- | --- | --- | --- |
| [00-MANIFESTO.md](00-MANIFESTO.md) | Identidade e princípios | Fonte permanente dos valores e regras inegociáveis; prevalece em conflitos. | Em mudanças de escopo, princípios, posicionamento ou decisões com impacto amplo. |
| [01-VISAO-GERAL.md](01-VISAO-GERAL.md) | Produto e MVP | Governa problema, solução, público, objetivos e limites atuais. | Em tarefas que alterem comportamento, escopo ou definição do produto. |
| [02-PROPOSTA-DE-VALOR.md](02-PROPOSTA-DE-VALOR.md) | Valor e públicos | Governa benefícios defendidos, públicos e limites das promessas. | Em decisões de produto, posicionamento ou comunicação de valor. |
| [03-ARQUITETURA.md](03-ARQUITETURA.md) | Arquitetura conceitual | Governa componentes, responsabilidades, fronteiras, dependências e fluxo do MVP. | Ao alterar estrutura, componentes, integrações ou responsabilidades. |
| [04-CASOS-DE-USO.md](04-CASOS-DE-USO.md) | Casos de uso | Governa atores, fluxos observáveis, falhas e critérios de aceitação do MVP. | Ao implementar ou revisar comportamentos e cenários de usuário. |
| [05-API.md](05-API.md) | API pública v1 | Contrato técnico normativo da fronteira pública, schemas e erros. | Em qualquer mudança de endpoint, entrada, saída, validação ou teste de contrato. |
| [06-DECISAO-DE-ROTEAMENTO.md](06-DECISAO-DE-ROTEAMENTO.md) | Decisão de roteamento | Governa filtros, avaliação econômica, estratégia, desempate e invariantes internos. | Ao alterar seleção de rota, elegibilidade, custo, explicação ou determinismo. |
| [decisions/](decisions/) | Decisões adicionais | Decisões arquiteturais além dos documentos principais, incluindo execução, adaptação externa e composição operacional. | Verifique antes de decisões arquiteturais; há decisões registradas em `0001`, `0002` e `0003`. |
| [maps/](maps/) | Mapas do produto e do sistema | Navegação visual **não normativa**; não altera a autoridade dos documentos acima. | Para orientação rápida sobre o produto, o fluxo técnico e o estado atual. |

Em caso de conflito, aplique a precedência declarada nas próprias fontes. O
Manifesto prevalece; `05-API.md` governa a fronteira pública e
`06-DECISAO-DE-ROTEAMENTO.md` a especializa sem alterar seu contrato.

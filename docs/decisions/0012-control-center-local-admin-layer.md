# 0012. Camada administrativa local e experiência de primeiro uso do Control Center

- **Status:** Aprovada
- **Data:** 2026-10-22
- **Autor:** Maestro Router Team
- **Decisores:** PO Hallan e time de engenharia

## Contexto

O Maestro Router foi concebido sob princípios estritos de neutralidade entre provedores, explicabilidade e segurança defensiva. A API pública v1 (`docs/05-API.md`) expõe intencionalmente apenas `POST /v1/executions`, operando com um catálogo imutável configurado pelo operador via variáveis de ambiente (`bootstrap.py`).

Durante os primeiros testes do Maestro Control Center (commit `8087742`, PR #26), identificou-se que a experiência de primeiro uso para um engenheiro de software que nunca utilizou o Maestro apresentava barreiras significativas:
1. A interface não oferecia um percurso educativo sobre os conceitos centrais do produto (diferenças entre provedor, modelo, rota e trilha; regras de elegibilidade e custos).
2. Não era possível cadastrar, testar ou substituir chaves de provedores pela interface, exigindo manipulação manual de variáveis de ambiente.
3. Não havia mecanismo interativo para consultar o catálogo, habilitar/desabilitar rotas ou obter sugestões explicáveis (prévia de roteamento) antes de disparar uma execução.
4. O usuário preenchia qualquer tarefa e deparava-se imediatamente com a recusa protetiva `NO_ELIGIBLE_ROUTE`, sem caminhos visíveis de resolução.

## Decisão

1. **Camada Administrativa Local e Opcional (`/admin/*`):**
   - Cria-se uma composição operacional dedicada ao Control Center (`src/maestro_router/control_center.py`), separada do aplicativo neutro estrito de produção (`src/maestro_router/api.py`).
   - A aplicação neutra de produção permanece 100% inalterada e fiel a `docs/05-API.md`, expondo unicamente `POST /v1/executions`.
   - O Control Center monta `POST /v1/executions` utilizando os mesmos componentes de domínio e regras de elegibilidade do Maestro, complementado pelos endpoints administrativos locais protegidos.

2. **Segurança de Credenciais e Proteção de Sessão/CSRF:**
   - Credenciais de provedores (ex.: OpenAI API Key) cadastradas via frontend residem **exclusivamente na memória volátil** do processo backend. Nenhuma credencial é gravada em disco, logs, repositório, sessionStorage ou localStorage.
   - O backend nunca retorna o segredo para o frontend; apenas metadados seguros e o estado da credencial são trafegados.
   - Proteção de sessão dinâmica: na carga inicial, o frontend obtém um identificador de sessão e um token CSRF criptograficamente seguro via `GET /admin/session`. Requisições administrativas de mutação exigem o cabeçalho `X-Maestro-CSRF-Token` e validação de `Origin`/`Referer` restrito a loopback (`localhost`/`127.0.0.1`).
   - Nenhum segredo ou chave mestra é embutido no bundle estático do frontend.

3. **Ciclo de Vida da Credencial:**
   - O estado da credencial é categorizado rigorosamente em cinco situações distintas:
     - `Credencial cadastrada`: chave presente na memória, mas ainda não testada externamente.
     - `Credencial verificada`: chave validada com sucesso contra o provedor via chamada segura que não gera tokens pagos.
     - `Acesso recusado`: provedor retornou erro de autenticação ou permissão (HTTP 401/403).
     - `Sem saldo`: cota esgotada ou ausência de créditos no provedor (HTTP 429 com insuficiência de cota).
     - `Verificação indisponível`: falha de conectividade ou indisponibilidade do provedor externo.
   - Verificações externas são estritamente explícitas (acionadas pelo usuário) e utilizam métodos neutros e gratuitos (ex.: listagem de modelos via SDK), nunca gerando texto pago.

4. **Gerenciamento Operacional de Rotas e Isolamento em Voo:**
   - O Control Center mantém um catálogo reconfigurável em memória. Alterações em rotas ou credenciais realizam uma troca atômica do snapshot do `RouteCatalog` e do registro de adaptadores.
   - Execuções em andamento capturam o snapshot no instante do recebimento da requisição, garantindo que mutações na configuração administrativa não interfiram em tarefas em processamento.

5. **Trilhas de Roteamento (Free, Econômica e Inteligente):**
   - **Free:** restringe os candidatos estritamente a rotas cujo custo seja comprovadamente zero via referência de preço e condições documentadas. Custo desconhecido ou inexistente não autoriza inclusão na trilha Free. Se nenhuma rota gratuita estiver configurada, a recusa é informada com clareza.
   - **Econômica:** aplica a estratégia canônica `lowest-estimated-cost` do Maestro entre rotas elegíveis com dados comparáveis de estimativa.
   - **Inteligente:** avalia os requisitos da tarefa (capacidades exigidas, critérios de qualidade documentados) priorizando rotas que comprovem conformidade aos critérios de qualidade exigidos, aplicando em seguida o menor custo estimado entre as qualificadas.

6. **Sugestões Explicáveis (Prévia de Roteamento):**
   - Endpoint `POST /admin/preview` executa a decisão de elegibilidade e ranqueamento sobre o catálogo ativo sem acionar o provedor externo, com custo zero de tokens.
   - Retorna a rota recomendada, justificativa, fatores de decisão, exclusões fundamentadas e situação dos dados econômicos, permitindo aplicação direta ao formulário antes do envio.

7. **Modo Estudante e Preservação de Estado:**
   - A interface incorpora uma aba educativa "Aprender / Modo Estudante", com orientações passo a passo, glossário, explicações de recusa e links normativos.
   - O estado do formulário de execução é preservado na memória da aplicação React durante a navegação entre abas, evitando perda de trabalho e impedindo envios duplicados.

## Consequências

- **Positivas:**
  - Engenheiros de software podem compreender, configurar e testar o Maestro Router pelo navegador de ponta a ponta sem recorrer ao terminal ou arquivos de ambiente.
  - Segurança defensiva rigorosa preservada: credenciais efêmeras em memória, CSRF dinâmico, verificação sem custos e ausência de vazamentos.
  - Compatibilidade integral com os contratos normativos existentes (`docs/05-API.md`), mantendo o motor e a API pública inviolados.
- **Limitações Registradas:**
  - Chaves de API cadastradas pela interface não persistem após o encerramento do processo do servidor (requerem novo cadastro ao reiniciar).
  - Apenas o adaptador OpenAI está operacional no MVP atual; outros provedores são explicitamente apresentados como não implementados.

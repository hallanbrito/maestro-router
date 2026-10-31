# 0014. Política de produto para as três trilhas de roteamento

- **Status do registro:** Proposta documental em revisão (Issue #32; ainda não integrada à `master`).
- **Status da direção de produto:** Aprovada pelo Product Owner em 30/10/2026.
- **Data:** 2026-10-31
- **Decisor:** PO Hallan
- **Natureza:** Direção para evolução incremental; **não** representa implementação concluída.

## Contexto

O Maestro Router já implementa um núcleo neutro de seleção de rota, com a estratégia efetiva `lowest-estimated-cost`, elegibilidade e restrições descritas em `docs/06-DECISAO-DE-ROTEAMENTO.md`. A API pública v1 permanece limitada a `POST /v1/executions`, conforme `docs/05-API.md`.

A camada administrativa opcional do Control Center (ADR 0012) já apresenta as trilhas Free, Econômica e Inteligente, mas suas regras atuais **não** equivalem às garantias e capacidades desejadas nesta política. Em especial, a Free atual considera tarifa zero **declarada pelo operador**, sem comprovação de faturamento ou franquia real. A Econômica e a Inteligente atuais dependem de requisitos explícitos e da estratégia de menor estimativa de custo; não existe avaliação autônoma comprovada de qualidade/latência.

A ADR 0013 introduziu o adaptador Google Gemini Developer API via Interactions API sem estado, mas não incorporou prova automática de gratuidade, cota ou acesso por assinatura.

## Decisão de produto: responsabilidades comuns

1. O cliente escolhe uma **trilha** e informa credenciais, permissões e limites aplicáveis por provedor/conta/projeto. Não precisa selecionar manualmente um modelo para cada execução; o Maestro é responsável por **escolher a rota** sob critérios observáveis e restrições efetivas.
2. A comparação e a escolha permanecem **neutras entre provedores**, explicáveis e subordinadas à elegibilidade, às regras de segurança e às permissões do operador.
3. A existência de uma chave, assinatura, modelo listado ou tarifa publicada não comprova acesso gratuito à API. Tokens consumidos não equivalem necessariamente a cobrança; ausência de cobrança também não decorre automaticamente de uma assinatura do produto de chat.
4. As restrições nunca devem ser relaxadas silenciosamente. Informação insuficiente ou incompatível exige recusa ou outra decisão segura **antes da chamada**, jamais um fallback pago implícito.

### Trilha 0800 / Free

**Objetivo aprovado:** utilizar exclusivamente chamadas oficialmente permitidas que tenham evidência suficiente de **não gerar cobrança adicional** para a conta/projeto/credencial em uso. Isso pode incluir uma franquia de API gratuita ou acesso incluído em um plano **quando esse mecanismo específico estiver expressamente autorizado pelo provedor e tecnicamente verificável**.

- O Maestro deve distinguir tarifa nominal zero, franquia gratuita de API, acesso por assinatura oficialmente autorizado e crédito promocional. Nenhuma categoria implica automaticamente as outras.
- O controle futuro de quota deve considerar a **unidade real de limitação** definida pelo provedor (por exemplo, projeto e não simplesmente API key), janelas, esgotamento e eventuais limites compartilhados.
- Na ausência de prova suficiente de elegibilidade gratuita ou de quota disponível, **recusar sem enviar a execução**. Não usar saldo pago como reserva, não converter a tentativa em Econômica e não presumir que outra chave concede cota separada.
- A regra presente da ADR 0012, baseada em gratuidade declarada pelo operador, **não satisfaz ainda essa política mais forte**; requer evolução, testes e homologação próprios.

### Trilha Econômica

**Objetivo aprovado:** minimizar o **custo adicional autorizado**, que pode ser **zero**, entre alternativas elegíveis e comparáveis. Uma escolha que custa zero pode ser a mais econômica; não há obrigação de gastar tokens tarifados.

- Acesso a execução paga só pode ocorrer com autorização econômica e limites aplicáveis do operador.
- Quando houver múltiplos provedores/contas, as restrições pertencem à origem correta, sem duplicar ou inventar franquias.
- Estimativa anterior, custo calculado depois da execução e cobrança real pelo provedor são conceitos distintos. O Maestro não promete conhecer a fatura externa.
- A implementação efetiva atual limita-se à elegibilidade e à estratégia `lowest-estimated-cost` documentada, não a uma otimização global de cobrança/franquias.

### Trilha Inteligente

**Objetivo aprovado:** escolher uma rota que equilibre **qualidade demonstrável, latência e custo**, respeitando orçamento, requisitos e restrições. Uma rota mais cara só pode ser preferida quando o benefício alegado for defensável por evidências adequadas ao cenário.

- Não introduzir rankings, scores, pesos, benchmarks ou garantias universais sem dados e método verificáveis.
- Não inferir capacidade a partir de nomes comerciais, reputação ou popularidade do modelo.
- O nome atual da trilha na interface **não significa** que o equilíbrio automático entre qualidade, latência e custo já esteja implementado. No runtime atual aplicam-se os filtros declarados e `lowest-estimated-cost` sobre alternativas comparáveis.

## Fronteiras, segurança e compatibilidade

- A escolha da trilha pelo Control Center pertence à composição **administrativa local e opcional** da ADR 0012, não modifica o contrato público `POST /v1/executions` nem cria cabeçalhos, endpoints ou campos novos na API v1.
- Nenhuma das três trilhas concede ao Maestro autorização para registrar/compartilhar credenciais, contornar cobrança, usar endpoint não documentado, fazer retry/fallback pago, iniciar execução autônoma ou prometer compatibilidade de modelos.
- Fontes oficiais e limites observados são dados para validação, não contratos estáticos eternos. Políticas, preços e quotas variam; uma integração futura deve falhar de forma segura quando faltar evidência suficiente.
- OAuth, mecanismos específicos de franquia, verificação de saldo/quota, troca de credenciais, políticas de fallback, qualidade e latência **permanecem propostas futuras** sujeitas a estudo de viabilidade, permissões e aprovação independente do PO.
- Precedência documental preservada: Manifesto; API v1 para a fronteira pública; decisão de roteamento para a seleção canônica; ADRs especializam somente o escopo autorizado. Esta ADR não reescreve retrospectivamente as ADRs 0012 ou 0013.

## Alternativas e riscos reconhecidos

- **Equiparar `rate = 0` a gratuidade garantida:** rejeitado por confundir declaração local com cobrança real.
- **Tratar assinaturas de chat como autorização de API key:** rejeitado; sistemas de billing e meios de acesso podem ser separados.
- **Aceitar fallback pago silencioso na Free:** rejeitado por violar o controle do cliente.
- **Exigir gasto na Econômica:** rejeitado; custo adicional zero é permitido e desejável quando efetivamente disponível.
- **Inventar pontuação de qualidade e velocidade:** rejeitado até existir evidência validável.
- **Tratar múltiplas chaves do mesmo projeto como quotas independentes:** rejeitado sem comprovação explícita do limite definido pelo provedor.

## Evidências oficiais de referência (sujeitas a mudança)

- OpenAI — separação da cobrança ChatGPT/API: https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform
- OpenAI — Sign in with ChatGPT para OSS elegível, requisitos e consentimento: https://developers.openai.com/siwc/token-sharing-open-source
- Google Gemini API — preços Free/Paid e modelos elegíveis: https://ai.google.dev/gemini-api/docs/pricing
- Google Gemini API — rate limits, normalmente associados ao projeto: https://ai.google.dev/gemini-api/docs/rate-limits

Essas páginas **não atestam** que uma determinada credencial/conta específica esteja elegível para uma execução gratuita.

## Consequências e próximos gates

1. Este registro **não altera código**, dependências, UI, contratos, testes ou funcionalidades atualmente disponíveis.
2. Implementação das garantias da Free, otimização econômica com franquias e escolha inteligente justificável exigem **fatias futuras separadas** e testes offline/mocks antes de qualquer cobrança real.
3. A homologação do Control Center e a triagem dos BUG-UI-01 a BUG-UI-05 seguem na Issue #33, de forma independente desta ADR.
4. **Sem release e sem merge por efeito desta ADR.** Revisão técnica independente e aceite explícito do PO são exigidos para integração à `master`; a publicação de release continua condicionada à homologação das três trilhas pela interface gráfica.

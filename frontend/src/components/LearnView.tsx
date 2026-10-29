import React from 'react';
import {
  BookOpen,
  Compass,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  ExternalLink,
  Layers,
  Sparkles,
  Scale,
} from 'lucide-react';
import { ActiveTab } from './Header';

interface LearnViewProps {
  onNavigateTab: (tab: ActiveTab) => void;
  onLoadExampleAndExecute: () => void;
}

export const LearnView: React.FC<LearnViewProps> = ({
  onNavigateTab,
  onLoadExampleAndExecute,
}) => {
  return (
    <div className="info-view-container">
      {/* Hero Educativo */}
      <div className="info-hero">
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
          <span className="badge badge-purple" style={{ padding: '0.35rem 0.75rem', fontSize: '0.85rem' }}>
            <BookOpen size={14} style={{ marginRight: '0.25rem' }} /> Modo Estudante / Onboarding
          </span>
        </div>
        <h2 className="info-hero-title">O que é o Maestro Router?</h2>
        <p className="info-hero-desc">
          O <strong>Maestro Router</strong> é uma camada open source que escolhe uma rota de modelo de IA
          de forma <strong>econômica</strong>, <strong>neutra entre provedores</strong>, <strong>controlável</strong> e{' '}
          <strong>explicável</strong>. Ele opera antes de qualquer chamada externa, garantindo que
          critérios de elegibilidade técnica precedam decisões de custo.
        </p>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginTop: '1.25rem' }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onNavigateTab('execution')}
          >
            Começar Agora
            <ArrowRight size={16} />
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onNavigateTab('providers')}
          >
            <Layers size={16} />
            Configurar Provedores
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onLoadExampleAndExecute}
          >
            <Sparkles size={16} />
            Experimentar Exemplo
          </button>
        </div>
      </div>

      {/* Fluxo de Entradas, Decisão e Saída */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 className="card-title" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Compass size={20} color="var(--color-primary)" />
          O que o Maestro Recebe, Decide e Devolve
        </h3>

        <div className="info-grid">
          <div style={{ padding: '1rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
              1. O que ele recebe
            </h4>
            <ul style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', paddingLeft: '1.2rem', lineHeight: 1.6 }}>
              <li><strong>task:</strong> instrução textual obrigatória a ser executada.</li>
              <li><strong>context:</strong> contexto auxiliar opcional (documentos, código, histórico).</li>
              <li><strong>constraints:</strong> restrições opcionais do chamador (capacidades necessárias, critérios de qualidade, allowlist de rotas e teto de custo máximo).</li>
            </ul>
          </div>

          <div style={{ padding: '1rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
              2. O que ele decide
            </h4>
            <ul style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', paddingLeft: '1.2rem', lineHeight: 1.6 }}>
              <li><strong>Elegibilidade Não-Econômica:</strong> filtra rotas que atendam aos requisitos técnicos (capacidade, qualidade, allowlist, disponibilidade).</li>
              <li><strong>Avaliação Econômica:</strong> compara estimativas prévias apenas entre candidatos com preços comprovados e comparáveis.</li>
              <li><strong>Seleção Determinística:</strong> seleciona a rota vencedora segundo a estratégia configurada (ex.: menor custo estimado).</li>
            </ul>
          </div>

          <div style={{ padding: '1rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
              3. O que ele devolve
            </h4>
            <ul style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', paddingLeft: '1.2rem', lineHeight: 1.6 }}>
              <li><strong>result:</strong> conteúdo gerado pelo modelo selecionado.</li>
              <li><strong>decision:</strong> rota e modelo selecionados, estratégia aplicada e justificativa completa com fatores auditáveis.</li>
              <li><strong>economics:</strong> estimativa prévia, uso observado normalizado e custo exato calculado após a execução.</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Conceitos Fundamentais */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 className="card-title" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Scale size={20} color="var(--color-primary)" />
          Diferenças Essenciais: Provedor, Modelo, Rota e Trilha
        </h3>

        <div className="info-grid">
          <div style={{ borderLeft: '3px solid var(--color-primary)', paddingLeft: '1rem' }}>
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>Provedor</h4>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.25rem 0' }}>
              A entidade de infraestrutura externa que processa a requisição (ex.: OpenAI, Google Gemini). No MVP atual,
              o adaptador oficial operacional é o OpenAI Responses.
            </p>
          </div>

          <div style={{ borderLeft: '3px solid var(--color-success)', paddingLeft: '1rem' }}>
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>Modelo</h4>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.25rem 0' }}>
              A rede neural específica com seus pesos e treinamento (ex.: <code>gpt-4o</code>, <code>gpt-4o-mini</code>).
            </p>
          </div>

          <div style={{ borderLeft: '3px solid var(--color-warning)', paddingLeft: '1rem' }}>
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>Rota</h4>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.25rem 0' }}>
              A unidade operacional do Maestro. Uma rota vincula um modelo a um identificador, com políticas de
              preço de referência, previsão de uso, capacidades atestadas e critérios de qualidade documentados.
            </p>
          </div>

          <div style={{ borderLeft: '3px solid var(--color-danger)', paddingLeft: '1rem' }}>
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>Trilha</h4>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.25rem 0' }}>
              A política de decisão orientada ao usuário: <strong>Free</strong> (somente tarifas zero declaradas pelo operador; não confirma faturamento na conta do provedor),
              <strong> Econômica</strong> (menor custo estimado entre rotas comparáveis) ou <strong>Inteligente</strong> (aplica critérios de qualidade e requisitos explicitamente informados com evidências auditáveis, sem inferência de scores ou rankings universais).
            </p>
          </div>
        </div>
      </div>

      {/* Primeiro Uso Guiado Passo a Passo */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 className="card-title" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <CheckCircle2 size={20} color="var(--color-success)" />
          Roteiro de Primeiro Uso Guiado
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
            <span style={{ background: 'var(--color-primary)', color: 'white', borderRadius: '50%', width: '24px', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, flexShrink: 0 }}>
              1
            </span>
            <div>
              <strong style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>Cadastre sua chave de API do provedor</strong>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.25rem 0' }}>
                Acesse a aba <strong>Provedores & Rotas</strong> e informe sua OpenAI API Key. A chave permanece exclusivamente na memória volátil do backend e é limpa ao desligar o servidor.
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
            <span style={{ background: 'var(--color-primary)', color: 'white', borderRadius: '50%', width: '24px', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, flexShrink: 0 }}>
              2
            </span>
            <div>
              <strong style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>Verifique a credencial de forma segura</strong>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.25rem 0' }}>
                Clique em <strong>Verificar Credencial</strong>. O sistema realiza uma consulta gratuita de modelos, confirmando permissão e saldo sem gerar texto ou cobrança de tokens.
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
            <span style={{ background: 'var(--color-primary)', color: 'white', borderRadius: '50%', width: '24px', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, flexShrink: 0 }}>
              3
            </span>
            <div>
              <strong style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>Confira as rotas ativas</strong>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.25rem 0' }}>
                Verifique que pelo menos uma rota (ex.: <code>route-openai-gpt4o-mini</code>) está habilitada com referência de preço ativa.
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
            <span style={{ background: 'var(--color-primary)', color: 'white', borderRadius: '50%', width: '24px', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, flexShrink: 0 }}>
              4
            </span>
            <div>
              <strong style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>Solicite uma sugestão explicável antes de enviar</strong>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.25rem 0' }}>
                Na tela de <strong>Execução</strong>, escolha a trilha e clique em <strong>Sugerir modelos/rotas</strong>. O Maestro analisa a elegibilidade e os custos sem acionar o modelo, mostrando os fatores que justificam a recomendação.
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
            <span style={{ background: 'var(--color-primary)', color: 'white', borderRadius: '50%', width: '24px', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, flexShrink: 0 }}>
              5
            </span>
            <div>
              <strong style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>Execute sua tarefa e analise os dados econômicos</strong>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.25rem 0' }}>
                Envie a solicitação com <code>Ctrl + Enter</code>. Acompanhe a decisão, os tokens consumidos e o custo exato pós-execução auditado.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Interpretação de Seleção, Recusa e Falha */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 className="card-title" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <AlertCircle size={20} color="var(--color-warning)" />
          Como Interpretar Respostas: Seleção, Recusa e Falha
        </h3>

        <div className="info-grid">
          <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
            <span className="badge badge-green" style={{ marginBottom: '0.5rem' }}>HTTP 200 • Seleção Concluída</span>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: 0 }}>
              Uma rota elegível foi selecionada e o provedor concluiu a geração. Retorna texto gerado, uso em tokens e custo calculado.
            </p>
          </div>

          <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
            <span className="badge badge-purple" style={{ marginBottom: '0.5rem' }}>HTTP 422 • Recusa Controlada</span>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: 0 }}>
              O motor avaliou as rotas e recusou a execução de forma protetiva. Exemplos: <code>NO_ELIGIBLE_ROUTE</code> (nenhuma rota atende às restrições ou catálogo vazio) ou <code>INSUFFICIENT_ECONOMIC_INFORMATION</code> (preços incompletos impedem comparação justa). Nenhum provedor é chamado.
            </p>
          </div>

          <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
            <span className="badge badge-red" style={{ marginBottom: '0.5rem' }}>HTTP 502/503/504 • Falha Externa</span>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: 0 }}>
              A seleção foi concluída com sucesso, mas o provedor externo falhou (502), estava indisponível (503) ou excedeu o timeout (504). O Maestro protege o chamador traduzindo o erro de forma neutra.
            </p>
          </div>
        </div>
      </div>

      {/* Glossário em Português */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 className="card-title" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <HelpCircle size={20} color="var(--color-primary)" />
          Glossário Rápido do Maestro
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
          <div>
            <strong style={{ fontSize: '0.85rem', color: 'var(--color-primary)' }}>Elegibilidade Não-Econômica</strong>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0.2rem 0' }}>
              Filtro prévio obrigatório que avalia se a rota suporta as capacidades e critérios exigidos antes de considerar preços.
            </p>
          </div>

          <div>
            <strong style={{ fontSize: '0.85rem', color: 'var(--color-primary)' }}>Fator de Decisão</strong>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0.2rem 0' }}>
              Evidência auditável registrada pelo roteador explicando por que uma rota foi selecionada ou excluída.
            </p>
          </div>

          <div>
            <strong style={{ fontSize: '0.85rem', color: 'var(--color-primary)' }}>Referência de Preço</strong>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0.2rem 0' }}>
              Estrutura auditável de taxas por unidade (ex.: USD por 1M de tokens) e condições aplicáveis de faturamento.
            </p>
          </div>

          <div>
            <strong style={{ fontSize: '0.85rem', color: 'var(--color-primary)' }}>Teto de Custo Estimado</strong>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0.2rem 0' }}>
              Valor monetário máximo fixado pelo chamador. Qualquer rota cuja estimativa prévia exceda o teto é excluída.
            </p>
          </div>

          <div>
            <strong style={{ fontSize: '0.85rem', color: 'var(--color-primary)' }}>Uso Normalizado</strong>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0.2rem 0' }}>
              Medição neutra de recursos observados (tokens de entrada e saída), padronizada independentemente do formato do provedor.
            </p>
          </div>

          <div>
            <strong style={{ fontSize: '0.85rem', color: 'var(--color-primary)' }}>Custo Calculado</strong>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0.2rem 0' }}>
              Cálculo aritmético exato pós-execução combinando o uso normalizado com a referência de preço da rota.
            </p>
          </div>
        </div>
      </div>

      {/* Links Normativos */}
      <div className="card">
        <h3 className="card-title" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <ExternalLink size={20} color="var(--color-primary)" />
          Documentação Normativa e Código-Fonte
        </h3>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          O Maestro Router é governado por documentos normativos estritos versionados no repositório:
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
          <a
            href="https://github.com/hallanbrito/maestro-router/blob/master/README.md"
            target="_blank"
            rel="noopener noreferrer"
            className="code-snippet"
            style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
          >
            <span>README.md (Guia Rápido)</span>
            <ExternalLink size={14} />
          </a>

          <a
            href="https://github.com/hallanbrito/maestro-router/blob/master/docs/00-MANIFESTO.md"
            target="_blank"
            rel="noopener noreferrer"
            className="code-snippet"
            style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
          >
            <span>docs/00-MANIFESTO.md</span>
            <ExternalLink size={14} />
          </a>

          <a
            href="https://github.com/hallanbrito/maestro-router/blob/master/docs/05-API.md"
            target="_blank"
            rel="noopener noreferrer"
            className="code-snippet"
            style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
          >
            <span>docs/05-API.md (Contrato Público)</span>
            <ExternalLink size={14} />
          </a>

          <a
            href="https://github.com/hallanbrito/maestro-router/blob/master/docs/06-DECISAO-DE-ROTEAMENTO.md"
            target="_blank"
            rel="noopener noreferrer"
            className="code-snippet"
            style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
          >
            <span>docs/06-DECISAO-DE-ROTEAMENTO.md</span>
            <ExternalLink size={14} />
          </a>
        </div>
      </div>
    </div>
  );
};

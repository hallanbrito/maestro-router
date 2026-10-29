import React from 'react';
import { ArrowRight, ShieldAlert, Terminal, Layers, HelpCircle } from 'lucide-react';
import { ExecutionErrorResponse } from '../types';
import { DecisionCard } from './DecisionCard';

interface RefusalCardProps {
  errorResponse: ExecutionErrorResponse;
  onNavigateToProviders?: () => void;
  onNavigateToLearn?: () => void;
}

export const RefusalCard: React.FC<RefusalCardProps> = ({
  errorResponse,
  onNavigateToProviders,
  onNavigateToLearn,
}) => {
  const { error, decision } = errorResponse;
  const isNoEligibleRoute = error.code === 'NO_ELIGIBLE_ROUTE';
  const isInsufficientEconomics = error.code === 'INSUFFICIENT_ECONOMIC_INFORMATION';

  // Confirmed human-readable explanation
  let headlineMessage = 'O Maestro Router avaliou a solicitação e recusou o encaminhamento antes de acionar qualquer modelo externo.';
  if (isNoEligibleRoute) {
    if (decision?.factors?.some((f) => f.description.includes('catálogo') || f.description.includes('0 rotas'))) {
      headlineMessage = 'Falta configurar uma rota de IA. O servidor respondeu, mas não há rotas configuradas para executar sua tarefa.';
    } else {
      headlineMessage = 'Nenhuma rota atendeu aos requisitos exigidos pela tarefa (capacidades, critérios ou rotas permitidas).';
    }
  } else if (isInsufficientEconomics) {
    headlineMessage = 'Informações econômicas insuficientes para comparação de custos. As rotas candidatas necessitam de tabelas de preços auditáveis.';
  }

  return (
    <div style={{ marginTop: '1.5rem' }}>
      <div className="alert-card warning" role="alert">
        <div className="alert-header">
          <ShieldAlert size={24} color="var(--color-warning)" />
          <div>
            <h3 className="alert-title">
              {isNoEligibleRoute && 'Recusa Controlada: Nenhuma Rota Elegível (NO_ELIGIBLE_ROUTE)'}
              {isInsufficientEconomics && 'Recusa Econômica: Informação Insuficiente (INSUFFICIENT_ECONOMIC_INFORMATION)'}
              {!isNoEligibleRoute && !isInsufficientEconomics && `Recusa da Operação: ${error.code}`}
            </h3>
            <span className="badge badge-warning" style={{ marginTop: '0.25rem' }}>
              Proteção do Roteador Ativa
            </span>
          </div>
        </div>

        <p className="alert-message">
          <strong>{headlineMessage}</strong>
          {error.message && error.message !== headlineMessage && ` ${error.message}`}
        </p>

        {/* Recomendações e Próximos Passos */}
        <div className="recommendation-box">
          <h4 className="recommendation-title">
            <ArrowRight size={14} />
            Próximas Ações Recomendadas
          </h4>

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginTop: '0.5rem', marginBottom: '1rem' }}>
            {onNavigateToProviders && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={onNavigateToProviders}
                style={{ fontSize: '0.85rem', padding: '0.4rem 0.8rem' }}
              >
                <Layers size={15} />
                Configurar Provedores & Rotas
              </button>
            )}

            {onNavigateToLearn && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onNavigateToLearn}
                style={{ fontSize: '0.85rem', padding: '0.4rem 0.8rem' }}
              >
                <HelpCircle size={15} />
                Entender Regras de Elegibilidade
              </button>
            )}
          </div>

          <details style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            <summary style={{ cursor: 'pointer', fontWeight: 600, color: 'var(--text-primary)' }}>
              Ver detalhes técnicos e linha de comando
            </summary>
            <div style={{ marginTop: '0.5rem' }}>
              <p style={{ margin: '0 0 0.5rem 0' }}>
                Código do erro normativo: <code>{error.code}</code> (HTTP 422 Unprocessable Content).
              </p>
              {isNoEligibleRoute && (
                <ul style={{ paddingLeft: '1.25rem', marginBottom: '0.5rem', lineHeight: 1.6 }}>
                  <li>
                    <strong>Catálogo em Memória:</strong> Se nenhuma rota estiver habilitada com credencial válida, o roteador recusa de forma defensiva para evitar cobranças não autorizadas.
                  </li>
                  <li>
                    <strong>Restrições Aplicadas:</strong> Caso tenha informado capacidades ou allowlist, certifique-se de que correspondem às rotas configuradas.
                  </li>
                </ul>
              )}
              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                <Terminal size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
                Inicialização via terminal (modo operacional):
              </span>
              <pre className="code-snippet">
python -m uvicorn --app-dir src maestro_router.control_center:app --port 8000
              </pre>
            </div>
          </details>
        </div>
      </div>

      {/* Exibição da Decisão formal enviada pela API */}
      {decision && <DecisionCard decision={decision} />}
    </div>
  );
};

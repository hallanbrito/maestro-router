import React from 'react';
import { ArrowRight, ShieldAlert, Terminal } from 'lucide-react';
import { ExecutionErrorResponse } from '../types';
import { DecisionCard } from './DecisionCard';

interface RefusalCardProps {
  errorResponse: ExecutionErrorResponse;
}

export const RefusalCard: React.FC<RefusalCardProps> = ({ errorResponse }) => {
  const { error, decision } = errorResponse;
  const isNoEligibleRoute = error.code === 'NO_ELIGIBLE_ROUTE';
  const isInsufficientEconomics = error.code === 'INSUFFICIENT_ECONOMIC_INFORMATION';

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
          {error.message ||
            'O Maestro Router avaliou a solicitação e recusou o encaminhamento antes de acionar qualquer modelo externo.'}
        </p>

        {/* Recomendações e Próximos Passos */}
        <div className="recommendation-box">
          <h4 className="recommendation-title">
            <ArrowRight size={14} />
            Próximas Ações Recomendadas
          </h4>

          {isNoEligibleRoute && (
            <div className="recommendation-text">
              <p style={{ marginBottom: '0.5rem' }}>
                O Maestro Router opera com <strong>neutralidade estrita</strong>. Esta recusa ocorre normalmente por um dos seguintes motivos:
              </p>
              <ul style={{ paddingLeft: '1.25rem', marginBottom: '0.75rem', lineHeight: 1.6 }}>
                <li>
                  <strong>Aplicativo Neutro Padrão:</strong> Se você iniciou com{' '}
                  <code style={{ color: 'var(--color-primary)' }}>maestro_router.api:app</code>,
                  o catálogo em memória é deliberadamente vazio (0 rotas), comprovando que o roteador não inventa rotas.
                </li>
                <li>
                  <strong>Restrições Estritas:</strong> Verifique se capacidades exigidas (
                  <code>required_capabilities</code>), critérios de qualidade ou teto de custo (
                  <code>max_estimated_cost</code>) eliminaram as rotas existentes.
                </li>
              </ul>

              <div style={{ marginTop: '0.75rem' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                  <Terminal size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
                  Para rodar com rotas operacionais configuradas:
                </span>
                <pre className="code-snippet">
python -m uvicorn --factory --app-dir src maestro_router.bootstrap:create_openai_app_from_env
                </pre>
              </div>
            </div>
          )}

          {isInsufficientEconomics && (
            <div className="recommendation-text">
              <p>
                Havia rotas candidatas, mas a estratégia selecionada exige avaliação de custos e nenhuma rota possuía referência de preço ou método de estimativa comparável.
              </p>
              <p style={{ marginTop: '0.5rem' }}>
                <strong>Ação:</strong> Forneça uma tabela de referência de preços auditável através de{' '}
                <code>MAESTRO_OPENAI_PRICE_REFERENCE_JSON</code> ou nas rotas em{' '}
                <code>MAESTRO_OPENAI_ROUTES_JSON</code>.
              </p>
            </div>
          )}

          {!isNoEligibleRoute && !isInsufficientEconomics && (
            <div className="recommendation-text">
              <p>
                Verifique os parâmetros enviados na solicitação e o estado das rotas no ambiente de execução.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Exibição da Decisão formal enviada pela API */}
      {decision && <DecisionCard decision={decision} />}
    </div>
  );
};

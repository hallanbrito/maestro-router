import React from 'react';
import { CheckCircle2, XCircle, Sliders, Info, Cpu } from 'lucide-react';
import { Decision } from '../types';

interface DecisionCardProps {
  decision: Decision;
}

export const DecisionCard: React.FC<DecisionCardProps> = ({ decision }) => {
  const isSelected = decision.outcome === 'selected';

  return (
    <div className="card" style={{ marginTop: '1.25rem' }}>
      <div className="card-header">
        <h3 className="card-title">
          <Sliders size={18} color="var(--color-primary)" />
          Decisão de Roteamento
        </h3>
        <span className={`badge ${isSelected ? 'badge-success' : 'badge-warning'}`}>
          {isSelected ? (
            <>
              <CheckCircle2 size={12} />
              Rota Selecionada
            </>
          ) : (
            <>
              <XCircle size={12} />
              Rota Recusada
            </>
          )}
        </span>
      </div>

      {decision.outcome === 'selected' && (
        <div className="route-pill" aria-label="Detalhes da rota selecionada">
          <div className="route-item">
            <span className="route-item-label">ID da Rota</span>
            <span className="route-item-val">{decision.route.id}</span>
          </div>
          <div className="route-item">
            <span className="route-item-label">Provedor</span>
            <span className="route-item-val">{decision.route.provider}</span>
          </div>
          <div className="route-item">
            <span className="route-item-label">Modelo</span>
            <span className="route-item-val">{decision.route.model}</span>
          </div>
          <div className="route-item">
            <span className="route-item-label">Estratégia</span>
            <span className="route-item-val" style={{ color: 'var(--color-purple)' }}>
              {decision.strategy.id}
            </span>
          </div>
        </div>
      )}

      <div style={{ marginBottom: '1rem' }}>
        <span
          style={{
            fontSize: '0.75rem',
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            display: 'block',
            marginBottom: '0.25rem',
          }}
        >
          Razão da Decisão
        </span>
        <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
          {decision.reason}
        </p>
      </div>

      {decision.factors && decision.factors.length > 0 && (
        <div style={{ marginBottom: '1rem' }}>
          <span
            style={{
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem',
              marginBottom: '0.4rem',
            }}
          >
            <Info size={12} />
            Fatos Determinantes ({decision.factors.length})
          </span>
          <div className="factors-list">
            {decision.factors.map((factor, index) => (
              <div key={index} className="factor-item">
                <span className="factor-category">{factor.category}</span>
                <span style={{ flex: 1 }}>{factor.description}</span>
                {factor.references && factor.references.length > 0 && (
                  <span
                    className="code-font"
                    style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}
                    title={`Referências: ${factor.references.join(', ')}`}
                  >
                    [{factor.references.join(', ')}]
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {decision.applied_constraints && decision.applied_constraints.length > 0 && (
        <div>
          <span
            style={{
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem',
              marginBottom: '0.4rem',
            }}
          >
            <Cpu size={12} />
            Restrições Efetivas Aplicadas ({decision.applied_constraints.length})
          </span>
          <div className="factors-list">
            {decision.applied_constraints.map((constraint, index) => (
              <div key={index} className="factor-item">
                <span className="badge badge-neutral" style={{ fontSize: '0.65rem' }}>
                  {constraint.source} / {constraint.category}
                </span>
                <span style={{ flex: 1 }}>{constraint.description}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

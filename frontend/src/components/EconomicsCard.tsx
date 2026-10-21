import React from 'react';
import { DollarSign, Clock, Hash, Check, HelpCircle, AlertTriangle } from 'lucide-react';
import { ExecutionEconomics, EconomicStatus } from '../types';

interface EconomicsCardProps {
  economics: ExecutionEconomics;
}

const renderStatusBadge = (status: EconomicStatus) => {
  switch (status) {
    case 'available':
      return (
        <span className="badge badge-success" title="Valor defensável e apurado">
          <Check size={10} /> Disponível
        </span>
      );
    case 'uncertain':
      return (
        <span className="badge badge-warning" title="Valor aproximado ou parcial com hipóteses">
          <AlertTriangle size={10} /> Incerto
        </span>
      );
    case 'unavailable':
      return (
        <span className="badge badge-neutral" title="Valor não apurável com os dados atuais">
          <HelpCircle size={10} /> Indisponível
        </span>
      );
    default:
      return null;
  }
};

export const EconomicsCard: React.FC<EconomicsCardProps> = ({ economics }) => {
  const { estimate, usage, calculated_cost } = economics;

  return (
    <div className="card" style={{ marginTop: '1.25rem' }}>
      <div className="card-header">
        <h3 className="card-title">
          <DollarSign size={18} color="var(--color-success)" />
          Observabilidade Econômica & Uso
        </h3>
        <span className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>
          Auditável
        </span>
      </div>

      <div className="economics-grid">
        {/* Estimativa Pré-Execução */}
        <div className="metric-box">
          <div className="metric-label">
            <span>
              <Clock size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
              Estimativa Prévia
            </span>
            {renderStatusBadge(estimate.status)}
          </div>
          <div className="metric-value">
            {estimate.status !== 'unavailable' && estimate.amount
              ? `${estimate.amount} ${estimate.currency || 'USD'}`
              : '—'}
          </div>
          {estimate.price_reference && (
            <div className="metric-sub" title="Referência de Preço">
              Ref: {estimate.price_reference}
            </div>
          )}
          {estimate.reason && (
            <div style={{ fontSize: '0.75rem', color: 'var(--color-warning)', marginTop: 4 }}>
              {estimate.reason}
            </div>
          )}
          {estimate.assumptions && estimate.assumptions.length > 0 && (
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Hipóteses: {estimate.assumptions.join('; ')}
            </div>
          )}
        </div>

        {/* Custo Calculado Pós-Execução */}
        <div className="metric-box">
          <div className="metric-label">
            <span>
              <DollarSign size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
              Custo Calculado
            </span>
            {renderStatusBadge(calculated_cost.status)}
          </div>
          <div className="metric-value" style={{ color: 'var(--color-success)' }}>
            {calculated_cost.status !== 'unavailable' && calculated_cost.amount
              ? `${calculated_cost.amount} ${calculated_cost.currency || 'USD'}`
              : '—'}
          </div>
          {calculated_cost.price_reference && (
            <div className="metric-sub" title="Referência de Preço Calculada">
              Ref: {calculated_cost.price_reference}
            </div>
          )}
          {calculated_cost.reason && (
            <div style={{ fontSize: '0.75rem', color: 'var(--color-warning)', marginTop: 4 }}>
              {calculated_cost.reason}
            </div>
          )}
          {calculated_cost.assumptions && calculated_cost.assumptions.length > 0 && (
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Hipóteses: {calculated_cost.assumptions.join('; ')}
            </div>
          )}
        </div>

        {/* Uso Registrado */}
        <div className="metric-box">
          <div className="metric-label">
            <span>
              <Hash size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
              Uso Normalizado
            </span>
            {renderStatusBadge(usage.status)}
          </div>
          {usage.items && usage.items.length > 0 ? (
            <div style={{ marginTop: '0.35rem' }}>
              {usage.items.map((item, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '0.85rem',
                    fontFamily: 'var(--font-mono)',
                    padding: '2px 0',
                  }}
                >
                  <span style={{ color: 'var(--text-secondary)' }}>{item.unit}:</span>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{item.quantity}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="metric-value">—</div>
          )}
          {usage.reason && (
            <div style={{ fontSize: '0.75rem', color: 'var(--color-warning)', marginTop: 4 }}>
              {usage.reason}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

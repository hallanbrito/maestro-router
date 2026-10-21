import React from 'react';
import { DollarSign, Clock, Hash, Check, HelpCircle, AlertTriangle } from 'lucide-react';
import { ExecutionEconomics } from '../types';

interface EconomicsCardProps {
  economics: ExecutionEconomics;
}

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
            {estimate.status === 'available' && (
              <span className="badge badge-success" title="Valor defensável e apurado">
                <Check size={10} /> Disponível
              </span>
            )}
            {estimate.status === 'uncertain' && (
              <span className="badge badge-warning" title="Valor aproximado com hipóteses">
                <AlertTriangle size={10} /> Incerto
              </span>
            )}
            {estimate.status === 'unavailable' && (
              <span className="badge badge-neutral" title="Valor não apurável com os dados atuais">
                <HelpCircle size={10} /> Indisponível
              </span>
            )}
          </div>
          <div className="metric-value">
            {estimate.status !== 'unavailable'
              ? `${estimate.amount} ${estimate.currency}`
              : '—'}
          </div>
          {estimate.status !== 'unavailable' && (
            <div className="metric-sub" title="Referência de Preço">
              Ref: {estimate.price_reference}
            </div>
          )}
          {estimate.status !== 'available' && (
            <div style={{ fontSize: '0.75rem', color: 'var(--color-warning)', marginTop: 4 }}>
              {estimate.reason}
            </div>
          )}
          {estimate.status !== 'unavailable' && estimate.assumptions.length > 0 && (
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Hipóteses: {estimate.assumptions.join('; ')}
            </div>
          )}
        </div>

        {/* Custo Calculado pelo Maestro Pós-Execução */}
        <div className="metric-box">
          <div className="metric-label">
            <span>
              <DollarSign size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
              Custo Calculado pelo Maestro
            </span>
            {calculated_cost.status === 'available' && (
              <span className="badge badge-success" title="Valor defensável e apurado">
                <Check size={10} /> Disponível
              </span>
            )}
            {calculated_cost.status === 'uncertain' && (
              <span className="badge badge-warning" title="Valor aproximado com hipóteses">
                <AlertTriangle size={10} /> Incerto
              </span>
            )}
            {calculated_cost.status === 'unavailable' && (
              <span className="badge badge-neutral" title="Valor não apurável com os dados atuais">
                <HelpCircle size={10} /> Indisponível
              </span>
            )}
          </div>
          <div className="metric-value" style={{ color: 'var(--color-success)' }}>
            {calculated_cost.status !== 'unavailable'
              ? `${calculated_cost.amount} ${calculated_cost.currency}`
              : '—'}
          </div>
          {calculated_cost.status !== 'unavailable' && (
            <div className="metric-sub" title="Referência de Preço Calculada">
              Ref: {calculated_cost.price_reference}
            </div>
          )}
          {calculated_cost.status !== 'available' && (
            <div style={{ fontSize: '0.75rem', color: 'var(--color-warning)', marginTop: 4 }}>
              {calculated_cost.reason}
            </div>
          )}
          {calculated_cost.status !== 'unavailable' && calculated_cost.assumptions.length > 0 && (
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
            {usage.status === 'available' && (
              <span className="badge badge-success" title="Uso apurado">
                <Check size={10} /> Disponível
              </span>
            )}
            {usage.status === 'uncertain' && (
              <span className="badge badge-warning" title="Uso aproximado ou parcial">
                <AlertTriangle size={10} /> Incerto
              </span>
            )}
            {usage.status === 'unavailable' && (
              <span className="badge badge-neutral" title="Uso indisponível">
                <HelpCircle size={10} /> Indisponível
              </span>
            )}
          </div>
          {usage.status !== 'unavailable' ? (
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
          {usage.status !== 'available' && (
            <div style={{ fontSize: '0.75rem', color: 'var(--color-warning)', marginTop: 4 }}>
              {usage.reason}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

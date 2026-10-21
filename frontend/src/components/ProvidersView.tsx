import React from 'react';
import { ShieldCheck, Terminal, Server, KeyRound } from 'lucide-react';

export const ProvidersView: React.FC = () => {
  return (
    <div className="info-view-container">
      <div className="info-hero">
        <h2 className="info-hero-title">Gerenciamento Operacional de Rotas & Provedores</h2>
        <p className="info-hero-desc">
          O Maestro Router opera sob estrita neutralidade entre provedores e modelo de segurança defensiva.
          O catálogo de rotas é imutável em tempo de execução e configurado pelo operador via variáveis de ambiente seguras.
        </p>
      </div>

      <div className="alert-card info">
        <div className="alert-header">
          <ShieldCheck size={22} color="var(--color-primary)" />
          <div>
            <h3 className="alert-title">Arquitetura de Segurança de Credenciais</h3>
            <p className="alert-message" style={{ margin: 0 }}>
              Por decisão arquitetural normativa (ADR 0001, ADR 0003 e docs/05-API.md), o front-end
              <strong> nunca armazena, solicita nem transmite chaves de API</strong> de provedores externos.
              Todas as credenciais residem exclusivamente no ambiente operacional do backend.
            </p>
          </div>
        </div>
      </div>

      <div className="info-grid">
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">
              <Server size={18} color="var(--color-primary)" />
              Modo Multirrota
            </h3>
            <span className="badge badge-purple">Recomendado</span>
          </div>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Permite registrar múltiplos modelos e provedores com atributos granulares: capacidades declaradas,
            critérios de qualidade validados, referências auditáveis de preço e previsão de uso.
          </p>
          <div style={{ marginTop: '1rem' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
              Variável de Ambiente:
            </span>
            <pre className="code-snippet">MAESTRO_OPENAI_ROUTES_JSON</pre>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">
              <Terminal size={18} color="var(--color-success)" />
              Modo Neutro em Memória
            </h3>
            <span className="badge badge-neutral">Ambiente Padrão</span>
          </div>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Iniciado sem rotas externas cadastradas. Ideal para testar a recusa segura e controlada
            (<code>NO_ELIGIBLE_ROUTE</code>), garantindo que nenhuma requisição não autorizada atinja serviços externos.
          </p>
          <div style={{ marginTop: '1rem' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
              Comando de Inicialização:
            </span>
            <pre className="code-snippet">python -m uvicorn --app-dir src maestro_router.api:app</pre>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: '1.5rem' }}>
        <div className="card-header">
          <h3 className="card-title">
            <KeyRound size={18} color="var(--color-warning)" />
            Exemplo Estruturado de Rota Neutra (ADR 0008)
          </h3>
          <span className="badge badge-neutral">JSON Operacional</span>
        </div>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
          Estrutura utilizada pelo operador para disponibilizar rotas elegíveis ao motor de decisão:
        </p>
        <pre className="code-snippet" style={{ maxHeight: '280px', overflowY: 'auto' }}>
{`{
  "routes": [
    {
      "route_id": "route-openai-gpt4o",
      "model": "gpt-4o",
      "enabled": true,
      "known_unavailable": false,
      "capabilities": ["text_generation", "summarization", "coding"],
      "price_reference": {
        "id": "pricing-openai-2026-08",
        "currency": "USD",
        "version": "1.0",
        "source": "https://openai.com/api/pricing/",
        "rates": [
          {"unit": "input_token", "rate": "0.000005", "base": "1"},
          {"unit": "output_token", "rate": "0.000015", "base": "1"}
        ],
        "conditions": [],
        "context_complete": true,
        "units_exhaustive": true,
        "no_double_counting": true,
        "model_identity_exact": true
      },
      "estimated_usage": {
        "input_token": 300,
        "output_token": 150,
        "applicability_confirmed": true
      }
    }
  ]
}`}
        </pre>
      </div>
    </div>
  );
};

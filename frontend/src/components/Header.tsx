import React from 'react';
import { Layers, Play, DollarSign, Compass, BookOpen } from 'lucide-react';

export type ActiveTab = 'execution' | 'providers' | 'learn' | 'reports';
export type ConnectionState = 'idle' | 'connected' | 'disconnected';

interface HeaderProps {
  activeTab: ActiveTab;
  onSelectTab: (tab: ActiveTab) => void;
  connectionState: ConnectionState;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  onSelectTab,
  connectionState,
}) => {
  return (
    <header className="app-header" role="banner">
      <div className="header-inner">
        <div className="brand-section">
          <div className="brand-logo" aria-hidden="true">
            <Compass size={22} />
          </div>
          <div>
            <h1 className="brand-title">
              Maestro Router
              <span className="brand-badge">Control Center MVP</span>
            </h1>
          </div>
        </div>

        <nav className="header-nav" aria-label="Navegação principal">
          <button
            type="button"
            className={`nav-button ${activeTab === 'execution' ? 'active' : ''}`}
            onClick={() => onSelectTab('execution')}
            aria-current={activeTab === 'execution' ? 'page' : undefined}
          >
            <Play size={16} aria-hidden="true" />
            <span>Execução</span>
          </button>

          <button
            type="button"
            className={`nav-button ${activeTab === 'providers' ? 'active' : ''}`}
            onClick={() => onSelectTab('providers')}
            aria-current={activeTab === 'providers' ? 'page' : undefined}
          >
            <Layers size={16} aria-hidden="true" />
            <span>Provedores & Rotas</span>
          </button>

          <button
            type="button"
            className={`nav-button ${activeTab === 'learn' ? 'active' : ''}`}
            onClick={() => onSelectTab('learn')}
            aria-current={activeTab === 'learn' ? 'page' : undefined}
          >
            <BookOpen size={16} aria-hidden="true" />
            <span>Aprender</span>
          </button>

          <button
            type="button"
            className={`nav-button ${activeTab === 'reports' ? 'active' : ''}`}
            onClick={() => onSelectTab('reports')}
            aria-current={activeTab === 'reports' ? 'page' : undefined}
          >
            <DollarSign size={16} aria-hidden="true" />
            <span>Métricas & Economia</span>
          </button>
        </nav>

        {/* Indicador de conexão orientado a eventos reais (sem endpoint falso nem POST automático) */}
        <div className="header-status">
          <div
            className={`status-dot ${
              connectionState === 'connected'
                ? 'online'
                : connectionState === 'disconnected'
                ? 'offline'
                : 'checking'
            }`}
            aria-hidden="true"
          />
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            {connectionState === 'idle' && 'Pronto para execução'}
            {connectionState === 'connected' && 'API Respondendo'}
            {connectionState === 'disconnected' && 'API Inacessível'}
          </span>
        </div>
      </div>
    </header>
  );
};

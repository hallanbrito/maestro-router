import React, { useState } from 'react';
import { Header, ActiveTab, ConnectionState } from './components/Header';
import { ExecutionView } from './components/ExecutionView';
import { ProvidersView } from './components/ProvidersView';
import { ReportsView } from './components/ReportsView';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('execution');
  // O estado de conexão inicia como 'idle' e reflete exclusivamente execuções reais,
  // sem chamadas de fundo, endpoints inventados ou POST automático na carga da página.
  const [connectionState, setConnectionState] = useState<ConnectionState>('idle');

  return (
    <div className="app-container">
      <Header
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        connectionState={connectionState}
      />

      <main className="main-content" role="main">
        {activeTab === 'execution' && (
          <ExecutionView
            onExecutionResult={(outcome) => {
              if (outcome === 'network_error') {
                setConnectionState('disconnected');
              } else {
                setConnectionState('connected');
              }
            }}
          />
        )}
        {activeTab === 'providers' && <ProvidersView />}
        {activeTab === 'reports' && <ReportsView />}
      </main>

      <footer className="app-footer" role="contentinfo">
        <p>
          Maestro Router MVP Control Center • Licença Apache 2.0 • Conformidade com{' '}
          <code>docs/05-API.md</code>
        </p>
      </footer>
    </div>
  );
};

export default App;

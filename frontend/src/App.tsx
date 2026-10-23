import React, { useState, useEffect } from 'react';
import { Header, ActiveTab, ConnectionState } from './components/Header';
import { ExecutionView, PRESET_EXAMPLES } from './components/ExecutionView';
import { ProvidersView } from './components/ProvidersView';
import { LearnView } from './components/LearnView';
import { ReportsView } from './components/ReportsView';
import {
  ExecutionApiResponse,
  ProviderInfo,
  RouteConfig,
  RoutingPreview,
  TrackType,
} from './types';
import { fetchAdminConfig } from './services/api';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('execution');
  const [connectionState, setConnectionState] = useState<ConnectionState>('idle');

  // Preserved Form & Execution State in memory (without sensitive localStorage persistence)
  const [task, setTask] = useState('');
  const [context, setContext] = useState('');
  const [track, setTrack] = useState<TrackType>('economica');
  const [showConstraints, setShowConstraints] = useState(false);
  const [capabilitiesInput, setCapabilitiesInput] = useState('');
  const [criteriaInput, setCriteriaInput] = useState('');
  const [allowedRoutesInput, setAllowedRoutesInput] = useState('');
  const [maxCostAmount, setMaxCostAmount] = useState('');
  const [maxCostCurrency, setMaxCostCurrency] = useState('USD');
  const [apiResponse, setApiResponse] = useState<ExecutionApiResponse | null>(null);
  const [routingPreview, setRoutingPreview] = useState<RoutingPreview | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Operational Config Info
  const [configInfo, setConfigInfo] = useState<{
    providers: ProviderInfo[];
    routes: RouteConfig[];
  }>({
    providers: [],
    routes: [],
  });

  const refreshConfig = async () => {
    try {
      const data = await fetchAdminConfig();
      setConfigInfo({
        providers: data.providers,
        routes: data.routes,
      });
    } catch {
      // Offline or initial load
    }
  };

  useEffect(() => {
    refreshConfig();
  }, [activeTab]);

  const handleLoadExampleAndExecute = () => {
    const firstExample = PRESET_EXAMPLES[0];
    setTask(firstExample.request.task);
    setContext(firstExample.request.context || '');
    setShowConstraints(false);
    setCapabilitiesInput('');
    setCriteriaInput('');
    setAllowedRoutesInput('');
    setMaxCostAmount('');
    setActiveTab('execution');
  };

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
            task={task}
            setTask={setTask}
            context={context}
            setContext={setContext}
            track={track}
            setTrack={setTrack}
            showConstraints={showConstraints}
            setShowConstraints={setShowConstraints}
            capabilitiesInput={capabilitiesInput}
            setCapabilitiesInput={setCapabilitiesInput}
            criteriaInput={criteriaInput}
            setCriteriaInput={setCriteriaInput}
            allowedRoutesInput={allowedRoutesInput}
            setAllowedRoutesInput={setAllowedRoutesInput}
            maxCostAmount={maxCostAmount}
            setMaxCostAmount={setMaxCostAmount}
            maxCostCurrency={maxCostCurrency}
            setMaxCostCurrency={setMaxCostCurrency}
            apiResponse={apiResponse}
            setApiResponse={setApiResponse}
            routingPreview={routingPreview}
            setRoutingPreview={setRoutingPreview}
            isLoading={isLoading}
            setIsLoading={setIsLoading}
            onNavigateTab={setActiveTab}
            configInfo={configInfo}
            onExecutionResult={(outcome) => {
              if (outcome === 'network_error') {
                setConnectionState('disconnected');
              } else {
                setConnectionState('connected');
              }
            }}
          />
        )}
        {activeTab === 'providers' && (
          <ProvidersView onConfigUpdated={refreshConfig} />
        )}
        {activeTab === 'learn' && (
          <LearnView
            onNavigateTab={setActiveTab}
            onLoadExampleAndExecute={handleLoadExampleAndExecute}
          />
        )}
        {activeTab === 'reports' && <ReportsView />}
      </main>

      <footer className="app-footer" role="contentinfo">
        <p>
          Maestro Router Control Center • Licença Apache 2.0 • Conformidade com{' '}
          <code>docs/05-API.md</code> e ADR 0012
        </p>
      </footer>
    </div>
  );
};

export default App;

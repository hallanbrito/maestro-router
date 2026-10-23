import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  Server,
  KeyRound,
  CheckCircle2,
  AlertCircle,
  XCircle,
  RefreshCw,
  Plus,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Info,
  Terminal,
  Edit2,
} from 'lucide-react';
import {
  ProviderInfo,
  RouteConfig,
  CredentialStatus,
} from '../types';
import {
  fetchAdminConfig,
  saveCredential,
  removeCredential,
  verifyCredential,
  saveRoute,
  toggleRoute,
  deleteRoute,
} from '../services/api';

interface ProvidersViewProps {
  onConfigUpdated?: () => void;
}

export const ProvidersView: React.FC<ProvidersViewProps> = ({ onConfigUpdated }) => {
  const [loading, setLoading] = useState(false);
  const [config, setConfig] = useState<{
    providers: ProviderInfo[];
    routes: RouteConfig[];
    models: string[];
  }>({
    providers: [],
    routes: [],
    models: [],
  });

  // Credential input state
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [credentialMessage, setCredentialMessage] = useState<{
    type: 'success' | 'error' | 'info';
    text: string;
  } | null>(null);

  // Route Form State
  const [showRouteModal, setShowRouteModal] = useState(false);
  const [isEditingRoute, setIsEditingRoute] = useState(false);
  const [routeModel, setRouteModel] = useState('gpt-4o-mini');
  const [customModel, setCustomModel] = useState('');
  const [newRouteId, setNewRouteId] = useState('route-openai-gpt4o-mini');
  const [routeCapabilities, setRouteCapabilities] = useState('text_generation');
  const [routeQualityCriteria, setRouteQualityCriteria] = useState('');
  const [routeEvidenceReferences, setRouteEvidenceReferences] = useState('');

  // Economic Configuration State
  const [configureEconomics, setConfigureEconomics] = useState(false);
  const [routeCurrency, setRouteCurrency] = useState('USD');
  const [routeInputRate, setRouteInputRate] = useState('');
  const [routeOutputRate, setRouteOutputRate] = useState('');
  const [routeEstimatedInput, setRouteEstimatedInput] = useState('1500');
  const [routeEstimatedOutput, setRouteEstimatedOutput] = useState('500');
  const [economicError, setEconomicError] = useState<string | null>(null);

  const loadConfig = async () => {
    try {
      setLoading(true);
      const data = await fetchAdminConfig();
      setConfig(data);
      if (onConfigUpdated) onConfigUpdated();
    } catch (_err) {
      // Backend may be offline or initializing
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  const openaiProvider = config.providers.find((p) => p.id === 'openai');
  const credentialStatus = openaiProvider?.credential.status || 'not_registered';

  const handleSaveCredential = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKeyInput.trim()) return;

    try {
      setLoading(true);
      setCredentialMessage(null);
      const res = await saveCredential('openai', apiKeyInput.trim());
      // Clear secret from React state immediately
      setApiKeyInput('');
      setCredentialMessage({
        type: 'success',
        text: res.message || 'Credencial cadastrada na memória do servidor.',
      });
      await loadConfig();
    } catch (err: any) {
      setCredentialMessage({
        type: 'error',
        text: err.message || 'Falha ao cadastrar credencial.',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveCredential = async () => {
    if (!window.confirm('Tem certeza de que deseja remover a credencial de memória do servidor?')) {
      return;
    }
    try {
      setLoading(true);
      setCredentialMessage(null);
      const res = await removeCredential('openai');
      setCredentialMessage({
        type: 'info',
        text: res.message || 'Credencial removida com sucesso.',
      });
      await loadConfig();
    } catch (err: any) {
      setCredentialMessage({
        type: 'error',
        text: err.message || 'Falha ao remover credencial.',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyCredential = async () => {
    try {
      setLoading(true);
      setCredentialMessage(null);
      const res = await verifyCredential('openai');
      const isSuccess = res.status === 'verified';
      setCredentialMessage({
        type: isSuccess ? 'success' : 'error',
        text: res.message,
      });
      await loadConfig();
    } catch (err: any) {
      setCredentialMessage({
        type: 'error',
        text: err.message || 'Falha ao acionar verificação.',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleToggleRoute = async (routeId: string) => {
    try {
      setLoading(true);
      await toggleRoute(routeId);
      await loadConfig();
    } catch (err: any) {
      alert(err.message || 'Falha ao alternar estado da rota.');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteRoute = async (routeId: string) => {
    if (!window.confirm(`Tem certeza de que deseja excluir a rota "${routeId}"?`)) return;
    try {
      setLoading(true);
      await deleteRoute(routeId);
      await loadConfig();
    } catch (err: any) {
      alert(err.message || 'Falha ao excluir rota.');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenAddRoute = () => {
    setIsEditingRoute(false);
    setNewRouteId(`route-openai-${Date.now().toString().slice(-4)}`);
    setRouteModel(config.models[0] || 'gpt-4o-mini');
    setCustomModel('');
    setRouteCapabilities('text_generation');
    setRouteQualityCriteria('');
    setRouteEvidenceReferences('');
    setConfigureEconomics(false);
    setRouteCurrency('USD');
    setRouteInputRate('');
    setRouteOutputRate('');
    setRouteEstimatedInput('1500');
    setRouteEstimatedOutput('500');
    setEconomicError(null);
    setShowRouteModal(true);
  };

  const handleOpenEditRoute = (route: RouteConfig) => {
    setIsEditingRoute(true);
    setNewRouteId(route.route_id);
    if (config.models.includes(route.model)) {
      setRouteModel(route.model);
      setCustomModel('');
    } else {
      setRouteModel('custom');
      setCustomModel(route.model);
    }
    setRouteCapabilities(route.capabilities.join(', '));
    setRouteQualityCriteria(route.quality_criteria.join(', '));
    setRouteEvidenceReferences('referencia-auditada-operador');

    if (route.price_reference && route.price_reference.rates) {
      setConfigureEconomics(true);
      setRouteCurrency(route.price_reference.currency || 'USD');
      const inRate = route.price_reference.rates.find((r) => r.unit === 'input_token')?.rate || '0.00';
      const outRate = route.price_reference.rates.find((r) => r.unit === 'output_token')?.rate || '0.00';
      setRouteInputRate(inRate);
      setRouteOutputRate(outRate);
      setRouteEstimatedInput(String(route.estimated_usage?.input_token || 1500));
      setRouteEstimatedOutput(String(route.estimated_usage?.output_token || 500));
    } else {
      setConfigureEconomics(false);
      setRouteCurrency('USD');
      setRouteInputRate('');
      setRouteOutputRate('');
      setRouteEstimatedInput('1500');
      setRouteEstimatedOutput('500');
    }
    setEconomicError(null);
    setShowRouteModal(true);
  };

  const handleSetZeroRates = () => {
    setConfigureEconomics(true);
    setRouteInputRate('0.00');
    setRouteOutputRate('0.00');
    setRouteEstimatedInput('1000');
    setRouteEstimatedOutput('500');
    setEconomicError(null);
  };

  const handleSaveRouteForm = async (e: React.FormEvent) => {
    e.preventDefault();
    const finalModel = customModel.trim() ? customModel.trim() : routeModel;
    if (!newRouteId.trim() || !finalModel) {
      alert('Identificador da rota e modelo são obrigatórios.');
      return;
    }

    const caps = routeCapabilities
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const criteriaList = routeQualityCriteria
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const evidenceRefs = routeEvidenceReferences
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    if (criteriaList.length > 0 && evidenceRefs.length === 0) {
      alert(
        'Para declarar critérios de qualidade, é obrigatório fornecer ao menos uma referência de evidência documentada pelo operador.'
      );
      return;
    }

    const qcs = criteriaList.map((c) => ({
      criterion: c,
      evidence_references: evidenceRefs,
    }));

    let priceRefObj: any = null;
    let estUsageObj: any = null;

    if (configureEconomics) {
      const inRate = routeInputRate.trim();
      const outRate = routeOutputRate.trim();
      const inTokens = parseInt(routeEstimatedInput.trim(), 10);
      const outTokens = parseInt(routeEstimatedOutput.trim(), 10);

      if (
        !inRate ||
        !outRate ||
        isNaN(Number(inRate)) ||
        isNaN(Number(outRate)) ||
        Number(inRate) < 0 ||
        Number(outRate) < 0
      ) {
        setEconomicError(
          'Tarifas de entrada e saída devem ser valores numéricos decimais não negativos (ex: 0.1500 ou 0.00).'
        );
        return;
      }
      if (isNaN(inTokens) || isNaN(outTokens) || inTokens <= 0 || outTokens <= 0) {
        setEconomicError('Previsão de tokens de entrada e saída deve conter números inteiros positivos.');
        return;
      }

      priceRefObj = {
        id: `pricing-openai-${finalModel}-${newRouteId.trim()}`,
        currency: routeCurrency,
        version: '2026-10',
        source: 'Configurado pelo operador via Control Center',
        rates: [
          { unit: 'input_token', rate: inRate, base: 1000000 },
          { unit: 'output_token', rate: outRate, base: 1000000 },
        ],
        conditions: ['configurado via control center'],
        context_complete: true,
        units_exhaustive: true,
        no_double_counting: true,
        model_identity_exact: true,
      };

      estUsageObj = {
        input_token: inTokens,
        output_token: outTokens,
        applicability_confirmed: true,
      };
    }

    try {
      setLoading(true);
      await saveRoute({
        route_id: newRouteId.trim(),
        provider: 'openai',
        model: finalModel,
        enabled: isEditingRoute
          ? (config.routes.find((r) => r.route_id === newRouteId.trim())?.enabled ?? true)
          : true,
        capabilities: caps,
        quality_criteria: qcs as any,
        price_reference: priceRefObj,
        estimated_usage: estUsageObj,
      });
      setShowRouteModal(false);
      await loadConfig();
    } catch (err: any) {
      alert(err.message || 'Falha ao salvar rota.');
    } finally {
      setLoading(false);
    }
  };

  const renderStatusBadge = (status: CredentialStatus) => {
    switch (status) {
      case 'verified':
        return (
          <span className="badge badge-green" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
            <CheckCircle2 size={13} /> Credencial Verificada
          </span>
        );
      case 'registered':
        return (
          <span className="badge badge-blue" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
            <Info size={13} /> Credencial Cadastrada (Não Verificada)
          </span>
        );
      case 'access_denied':
        return (
          <span className="badge badge-red" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
            <XCircle size={13} /> Acesso Recusado (401/403)
          </span>
        );
      case 'insufficient_quota':
        return (
          <span className="badge badge-orange" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
            <AlertCircle size={13} /> Sem Saldo / Cota Excedida
          </span>
        );
      case 'verification_unavailable':
        return (
          <span className="badge badge-neutral" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
            <AlertCircle size={13} /> Verificação Indisponível
          </span>
        );
      default:
        return (
          <span className="badge badge-neutral">Não Cadastrada</span>
        );
    }
  };

  return (
    <div className="info-view-container">
      {/* Hero Operacional */}
      <div className="info-hero">
        <h2 className="info-hero-title">Gerenciamento Operacional de Provedores & Rotas</h2>
        <p className="info-hero-desc">
          Configure sua credencial de acesso, habilite ou cadastre rotas operacionais e gerencie a
          composição de modelos que alimentará as decisões do Maestro Router.
        </p>
      </div>

      {/* Aviso de Provedores Implementados */}
      <div className="card" style={{ marginBottom: '1.5rem', borderLeft: '4px solid var(--color-primary)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
              Provedores Integrados no MVP: OpenAI
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.25rem 0 0 0' }}>
              Atualmente, apenas o adaptador <strong>OpenAI Responses</strong> está implementado no motor. Outros provedores (Google Gemini, Anthropic, etc.) serão adicionados em versões futuras.
            </p>
          </div>
          <span className="badge badge-purple">OpenAI Operacional</span>
        </div>
      </div>

      {/* Seção 1: Cadastro e Verificação de Credencial */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header" style={{ marginBottom: '1rem' }}>
          <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <KeyRound size={20} color="var(--color-primary)" />
            Credencial do Provedor (OpenAI)
          </h3>
          {renderStatusBadge(credentialStatus)}
        </div>

        <div className="alert-card info" style={{ marginBottom: '1rem' }}>
          <div className="alert-header">
            <ShieldCheck size={20} color="var(--color-primary)" />
            <div>
              <p className="alert-message" style={{ margin: 0, fontSize: '0.85rem' }}>
                <strong>Válida até o servidor ser encerrado:</strong> por segurança defensiva (ADR 0012),
                a chave reside <em>exclusivamente na memória volátil do backend</em>. Não é gravada em disco,
                localStorage, logs ou sessionStorage. O servidor nunca devolve o segredo para o navegador.
              </p>
            </div>
          </div>
        </div>

        {credentialMessage && (
          <div
            className={`alert-card ${credentialMessage.type === 'error' ? 'danger' : 'info'}`}
            style={{ marginBottom: '1rem' }}
          >
            <p className="alert-message" style={{ margin: 0, fontSize: '0.85rem' }}>
              {credentialMessage.text}
            </p>
          </div>
        )}

        <form onSubmit={handleSaveCredential} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <div>
            <label htmlFor="apiKeyInput" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem', color: 'var(--text-primary)' }}>
              OpenAI API Key (sk-...)
            </label>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <input
                id="apiKeyInput"
                type="password"
                className="input-field"
                placeholder={
                  openaiProvider?.credential.registered
                    ? 'Chave cadastrada na memória (digite para substituir)'
                    : 'Cole sua OpenAI API Key aqui'
                }
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                autoComplete="off"
                style={{ flex: 1, minWidth: '240px' }}
              />
              <button
                type="submit"
                className="btn btn-primary"
                disabled={loading || !apiKeyInput.trim()}
              >
                Salvar Chave
              </button>
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem', display: 'block' }}>
              O campo de senha é limpo imediatamente após o envio.
            </span>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleVerifyCredential}
              disabled={loading || !openaiProvider?.credential.registered}
            >
              <RefreshCw size={15} className={loading ? 'spin' : ''} />
              Verificar Credencial (Sem Custos)
            </button>

            {openaiProvider?.credential.registered && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleRemoveCredential}
                disabled={loading}
                style={{ color: 'var(--color-danger)' }}
              >
                <Trash2 size={15} />
                Remover Chave da Memória
              </button>
            )}
          </div>
        </form>

        {/* Modelos Descobertos */}
        {config.models && config.models.length > 0 && (
          <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '0.35rem' }}>
              Modelos Reconhecidos / Disponíveis no Provedor:
            </span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
              {config.models.map((m) => (
                <span
                  key={m}
                  className="badge badge-neutral"
                  style={{ fontSize: '0.75rem', cursor: 'pointer' }}
                  onClick={() => {
                    setRouteModel(m);
                    setNewRouteId(`route-openai-${m.replace(/[^a-zA-Z0-9]/g, '-')}`);
                    setShowRouteModal(true);
                  }}
                  title="Clique para criar uma rota com este modelo"
                >
                  {m}
                </span>
              ))}
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem', display: 'block' }}>
              * Nota explicativa: "Modelo listado" indica que o provedor oferece o modelo. Para ser utilizado em execuções, o modelo deve estar configurado em uma <strong>rota</strong> abaixo.
            </span>
          </div>
        )}
      </div>

      {/* Seção 2: Rotas Operacionais */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header" style={{ marginBottom: '1rem' }}>
          <div>
            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Server size={20} color="var(--color-primary)" />
              Rotas Operacionais Configuradas
            </h3>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Rotas ativas disponíveis para seleção pelo motor de decisão do Maestro.
            </span>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleOpenAddRoute}
            style={{ fontSize: '0.85rem' }}
          >
            <Plus size={15} />
            Nova Rota
          </button>
        </div>

        {config.routes.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
            <AlertCircle size={32} style={{ margin: '0 auto 0.5rem auto', opacity: 0.5 }} />
            <p style={{ margin: 0, fontWeight: 500 }}>Nenhuma rota configurada.</p>
            <p style={{ fontSize: '0.85rem', margin: '0.25rem 0' }}>
              Cadastre ao menos uma rota para permitir a execução de tarefas.
            </p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {config.routes.map((route) => {
              const isReady = route.status === 'ready';
              return (
                <div
                  key={route.route_id}
                  style={{
                    padding: '1rem',
                    background: 'var(--bg-secondary)',
                    borderRadius: 'var(--radius-md)',
                    border: `1px solid ${isReady ? 'var(--border-color)' : 'var(--color-warning)'}`,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <strong style={{ fontSize: '0.95rem', color: 'var(--text-primary)' }}>
                          {route.route_id}
                        </strong>
                        <span className="badge badge-purple">{route.model}</span>
                        {route.enabled ? (
                          <span className="badge badge-green">Habilitada</span>
                        ) : (
                          <span className="badge badge-neutral">Desabilitada</span>
                        )}
                        {route.known_unavailable && (
                          <span className="badge badge-red">Indisponível</span>
                        )}
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                        Provedor: <strong>{route.provider}</strong> • Capacidades:{' '}
                        {route.capabilities.join(', ') || 'Nenhuma'} • Critérios:{' '}
                        {route.quality_criteria.join(', ') || 'Nenhum'}
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                        {route.price_reference && route.price_reference.rates ? (
                          <span>
                            Tarifas: <strong>{route.price_reference.currency}</strong> (In:{' '}
                            {route.price_reference.rates.find((r) => r.unit === 'input_token')?.rate || '0.00'} / Out:{' '}
                            {route.price_reference.rates.find((r) => r.unit === 'output_token')?.rate || '0.00'}) • Previsão:{' '}
                            {route.estimated_usage?.input_token ?? 0} in / {route.estimated_usage?.output_token ?? 0} out
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>
                            Dados econômicos: Não configurados (economicamente indisponível)
                          </span>
                        )}
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ padding: '0.35rem 0.65rem', fontSize: '0.8rem' }}
                        onClick={() => handleOpenEditRoute(route)}
                        title="Editar Rota e Dados Econômicos"
                        data-testid={`edit-route-${route.route_id}`}
                      >
                        <Edit2 size={14} />
                        Editar
                      </button>

                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ padding: '0.35rem 0.65rem', fontSize: '0.8rem' }}
                        onClick={() => handleToggleRoute(route.route_id)}
                        title={route.enabled ? 'Desabilitar Rota' : 'Habilitar Rota'}
                      >
                        {route.enabled ? (
                          <>
                            <ToggleRight size={16} color="var(--color-success)" />
                            Desabilitar
                          </>
                        ) : (
                          <>
                            <ToggleLeft size={16} color="var(--text-muted)" />
                            Habilitar
                          </>
                        )}
                      </button>

                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ padding: '0.35rem 0.65rem', color: 'var(--color-danger)' }}
                        onClick={() => handleDeleteRoute(route.route_id)}
                        title="Excluir Rota"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>

                  {/* Bloqueadores / Impedimentos */}
                  {route.blockers && route.blockers.length > 0 && (
                    <div
                      style={{
                        marginTop: '0.75rem',
                        padding: '0.5rem 0.75rem',
                        background: 'rgba(234, 179, 8, 0.1)',
                        borderRadius: 'var(--radius-sm)',
                        borderLeft: '3px solid var(--color-warning)',
                      }}
                    >
                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-warning)', display: 'block' }}>
                        Requisitos que impedem o uso desta rota:
                      </span>
                      <ul style={{ margin: '0.25rem 0 0 0', paddingLeft: '1.2rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                        {route.blockers.map((b, idx) => (
                          <li key={idx}>{b}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Modal / Formulário de Criação de Rota */}
      {showRouteModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
        >
          <div
            className="card"
            style={{
              maxWidth: '540px',
              width: '100%',
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            <div className="card-header" style={{ marginBottom: '1rem' }}>
              <h3 className="card-title">
                {isEditingRoute ? `Editar Rota: ${newRouteId}` : 'Cadastrar / Configurar Rota'}
              </h3>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ padding: '0.25rem 0.5rem' }}
                onClick={() => setShowRouteModal(false)}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveRouteForm} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                  Identificador da Rota (route_id)
                </label>
                <input
                  type="text"
                  className="input-field"
                  value={newRouteId}
                  onChange={(e) => setNewRouteId(e.target.value)}
                  placeholder="ex: route-openai-gpt4o-mini"
                  disabled={isEditingRoute}
                  required
                />
                {isEditingRoute && (
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    O identificador é imutável durante a edição.
                  </span>
                )}
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                  Modelo
                </label>
                <select
                  className="input-field"
                  value={routeModel}
                  onChange={(e) => setRouteModel(e.target.value)}
                  style={{ marginBottom: '0.35rem' }}
                >
                  {config.models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                  <option value="custom">Outro modelo (digitar manualmente)...</option>
                </select>

                {routeModel === 'custom' && (
                  <input
                    type="text"
                    className="input-field"
                    value={customModel}
                    onChange={(e) => setCustomModel(e.target.value)}
                    placeholder="Digite o identificador do modelo (ex.: gpt-4-turbo)"
                    required
                  />
                )}
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                  Capacidades Declaradas (separadas por vírgula)
                </label>
                <input
                  type="text"
                  className="input-field"
                  value={routeCapabilities}
                  onChange={(e) => setRouteCapabilities(e.target.value)}
                  placeholder="text_generation, summarization, code_analysis"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                  Critérios de Qualidade (opcional, separados por vírgula)
                </label>
                <input
                  type="text"
                  className="input-field"
                  value={routeQualityCriteria}
                  onChange={(e) => setRouteQualityCriteria(e.target.value)}
                  placeholder="ex: summary_faithfulness_accepted"
                />
              </div>

              {routeQualityCriteria.trim().length > 0 && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                    Referências de Evidência da Qualidade (obrigatório se houver critério)
                  </label>
                  <input
                    type="text"
                    className="input-field"
                    value={routeEvidenceReferences}
                    onChange={(e) => setRouteEvidenceReferences(e.target.value)}
                    placeholder="ex: avaliacao-equipe-2026, benchmark-auditado-v1"
                    required
                  />
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    O Maestro proíbe declarações de qualidade sem referências de evidências auditáveis fornecidas pelo operador.
                  </span>
                </div>
              )}

              <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', margin: 0, fontWeight: 600, fontSize: '0.85rem' }}>
                    <input
                      type="checkbox"
                      checked={configureEconomics}
                      onChange={(e) => setConfigureEconomics(e.target.checked)}
                      data-testid="toggle-economics-config"
                    />
                    Configurar Referência Econômica e Previsão de Uso
                  </label>
                  {configureEconomics && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleSetZeroRates}
                      style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}
                      title="Preenche tarifas zero para qualificar na trilha Free"
                      data-testid="btn-set-zero-rates"
                    >
                      Definir Tarifas Zero (Free)
                    </button>
                  )}
                </div>

                {configureEconomics ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', marginTop: '0.5rem' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                      <div>
                        <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.2rem' }}>
                          Moeda
                        </label>
                        <select
                          className="input-field"
                          value={routeCurrency}
                          onChange={(e) => setRouteCurrency(e.target.value)}
                          style={{ fontSize: '0.8rem', padding: '0.35rem 0.5rem' }}
                        >
                          <option value="USD">USD</option>
                          <option value="BRL">BRL</option>
                          <option value="EUR">EUR</option>
                        </select>
                      </div>
                      <div>
                        <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '1.2rem' }}>
                          Base: 1.000.000 tokens
                        </span>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                      <div>
                        <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.2rem' }}>
                          Tarifa Entrada (por 1M tokens)
                        </label>
                        <input
                          type="text"
                          className="input-field"
                          value={routeInputRate}
                          onChange={(e) => {
                            setRouteInputRate(e.target.value);
                            setEconomicError(null);
                          }}
                          placeholder="ex: 0.1500 ou 0.00"
                          style={{ fontSize: '0.8rem', padding: '0.35rem 0.5rem' }}
                          data-testid="route-input-rate"
                        />
                      </div>
                      <div>
                        <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.2rem' }}>
                          Tarifa Saída (por 1M tokens)
                        </label>
                        <input
                          type="text"
                          className="input-field"
                          value={routeOutputRate}
                          onChange={(e) => {
                            setRouteOutputRate(e.target.value);
                            setEconomicError(null);
                          }}
                          placeholder="ex: 0.6000 ou 0.00"
                          style={{ fontSize: '0.8rem', padding: '0.35rem 0.5rem' }}
                          data-testid="route-output-rate"
                        />
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                      <div>
                        <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.2rem' }}>
                          Previsão Tokens Entrada
                        </label>
                        <input
                          type="number"
                          className="input-field"
                          value={routeEstimatedInput}
                          onChange={(e) => {
                            setRouteEstimatedInput(e.target.value);
                            setEconomicError(null);
                          }}
                          placeholder="ex: 1500"
                          style={{ fontSize: '0.8rem', padding: '0.35rem 0.5rem' }}
                          data-testid="route-estimated-input"
                        />
                      </div>
                      <div>
                        <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.2rem' }}>
                          Previsão Tokens Saída
                        </label>
                        <input
                          type="number"
                          className="input-field"
                          value={routeEstimatedOutput}
                          onChange={(e) => {
                            setRouteEstimatedOutput(e.target.value);
                            setEconomicError(null);
                          }}
                          placeholder="ex: 500"
                          style={{ fontSize: '0.8rem', padding: '0.35rem 0.5rem' }}
                          data-testid="route-estimated-output"
                        />
                      </div>
                    </div>

                    {economicError && (
                      <span
                        style={{ color: 'var(--color-danger)', fontSize: '0.75rem', display: 'block', marginTop: '0.25rem', fontWeight: 500 }}
                        data-testid="route-economic-error"
                      >
                        {economicError}
                      </span>
                    )}
                  </div>
                ) : (
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: 0 }}>
                    Novas rotas cadastradas (incluindo gpt-4o-mini) não possuem tarifas nem previsão de tokens pré-preenchidas automaticamente. Dados econômicos ausentes permanecem explicitamente indisponíveis até que sejam configurados pelo operador.
                  </p>
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowRouteModal(false)}
                >
                  Cancelar
                </button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {isEditingRoute ? 'Salvar Alterações' : 'Salvar Rota'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Seção 3: Avançado (Variáveis de Ambiente / JSON) */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Terminal size={18} color="var(--text-muted)" />
            Avançado: Configuração Headless / Variáveis de Ambiente
          </h3>
          <span className="badge badge-neutral">Operador</span>
        </div>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
          Para execuções em servidores de produção sem navegador, o Maestro pode ser iniciado via variáveis de ambiente normativas:
        </p>
        <pre className="code-snippet">
{`# Exemplo de inicialização headless
export OPENAI_API_KEY="sk-..."
export MAESTRO_OPENAI_ROUTES_JSON='{"routes":[{"route_id":"route-gpt4o-mini","model":"gpt-4o-mini","enabled":true,"price_reference":{...},"estimated_usage":{...}}]}'
python -m uvicorn --app-dir src maestro_router.bootstrap:app`}
        </pre>
      </div>
    </div>
  );
};

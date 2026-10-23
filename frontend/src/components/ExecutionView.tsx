import React, { useState, useEffect } from 'react';
import {
  Send,
  RotateCcw,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  AlertOctagon,
  AlertCircle,
  WifiOff,
  Terminal,
  FileText,
  SlidersHorizontal,
  HelpCircle,
  DollarSign,
  Scale,
  Layers,
  BookOpen,
  Info,
  Compass,
} from 'lucide-react';
import {
  ExecutionApiResponse,
  ExecutionRequest,
  ProviderInfo,
  RouteConfig,
  RoutingPreview,
  TrackType,
} from '../types';
import { executeAdminTask, fetchRoutingPreview } from '../services/api';
import { DecisionCard } from './DecisionCard';
import { EconomicsCard } from './EconomicsCard';
import { RefusalCard } from './RefusalCard';
import { ActiveTab } from './Header';

export interface PresetExample {
  title: string;
  request: ExecutionRequest;
}

/** Exemplos normativos reprodutíveis baseados na documentação e casos de uso do MVP. */
export const PRESET_EXAMPLES: PresetExample[] = [
  {
    title: '1. Resumo Conciso (Fluxo Geral)',
    request: {
      task: 'Resuma o contexto a seguir em no máximo duas frases objetivas.',
      context:
        'O Maestro Router é uma camada open source que escolhe uma rota de modelo de IA de forma econômica, neutra entre provedores, controlável e explicável. A elegibilidade não-econômica sempre precede a avaliação de preços.',
    },
  },
  {
    title: '2. Restrição de Capacidades Neutras',
    request: {
      task: 'Analise o texto e extraia os três pontos principais.',
      context: 'Arquitetura modular orientada a contratos estritos e explicabilidade transparente.',
      constraints: {
        required_capabilities: ['text_generation', 'summarization'],
      },
    },
  },
  {
    title: '3. Critério de Qualidade Obrigatório',
    request: {
      task: 'Elabore uma síntese técnica dos invariantes de roteamento.',
      context: 'A decisão de roteamento do Maestro separa elegibilidade não econômica de avaliação de custos.',
      constraints: {
        required_quality_criteria: ['summary_faithfulness_accepted'],
      },
    },
  },
  {
    title: '4. Teto de Custo Estimado (0.0100 USD)',
    request: {
      task: 'Explique a importância da neutralidade de provedores em roteamento de IA.',
      constraints: {
        max_estimated_cost: {
          amount: '0.0100',
          currency: 'USD',
        },
      },
    },
  },
  {
    title: '5. Allowlist Restritiva de Rota',
    request: {
      task: 'Gere um exemplo de cabeçalho HTTP em JSON.',
      constraints: {
        allowed_route_ids: ['route-openai-gpt4o-mini', 'route-fast-local'],
      },
    },
  },
];

interface ExecutionViewProps {
  /** Notifica o componente pai sobre o resultado da requisição para atualizar o status da conexão. */
  onExecutionResult?: (
    outcome:
      | 'success'
      | 'refusal'
      | 'client_error'
      | 'execution_error'
      | 'server_error'
      | 'protocol_error'
      | 'network_error'
  ) => void;
  onNavigateTab?: (tab: ActiveTab) => void;
  // Controlled props with uncontrolled fallback for state preservation
  task?: string;
  setTask?: (val: string) => void;
  context?: string;
  setContext?: (val: string) => void;
  track?: TrackType;
  setTrack?: (val: TrackType) => void;
  showConstraints?: boolean;
  setShowConstraints?: (val: boolean) => void;
  capabilitiesInput?: string;
  setCapabilitiesInput?: (val: string) => void;
  criteriaInput?: string;
  setCriteriaInput?: (val: string) => void;
  allowedRoutesInput?: string;
  setAllowedRoutesInput?: (val: string) => void;
  maxCostAmount?: string;
  setMaxCostAmount?: (val: string) => void;
  maxCostCurrency?: string;
  setMaxCostCurrency?: (val: string) => void;
  apiResponse?: ExecutionApiResponse | null;
  setApiResponse?: (val: ExecutionApiResponse | null) => void;
  routingPreview?: RoutingPreview | null;
  setRoutingPreview?: (val: RoutingPreview | null) => void;
  configInfo?: {
    providers: ProviderInfo[];
    routes: RouteConfig[];
  };
}

export const ExecutionView: React.FC<ExecutionViewProps> = ({
  onExecutionResult,
  onNavigateTab,
  task: controlledTask,
  setTask: setControlledTask,
  context: controlledContext,
  setContext: setControlledContext,
  track: controlledTrack,
  setTrack: setControlledTrack,
  showConstraints: controlledShowConstraints,
  setShowConstraints: setControlledShowConstraints,
  capabilitiesInput: controlledCaps,
  setCapabilitiesInput: setControlledCaps,
  criteriaInput: controlledCriteria,
  setCriteriaInput: setControlledCriteria,
  allowedRoutesInput: controlledRoutes,
  setAllowedRoutesInput: setControlledRoutes,
  maxCostAmount: controlledMaxCostAmount,
  setMaxCostAmount: setControlledMaxCostAmount,
  maxCostCurrency: controlledMaxCostCurrency,
  setMaxCostCurrency: setControlledMaxCostCurrency,
  apiResponse: controlledApiResponse,
  setApiResponse: setControlledApiResponse,
  routingPreview: controlledRoutingPreview,
  setRoutingPreview: setControlledRoutingPreview,
  configInfo,
}) => {
  // Internal fallback states if props are not supplied (e.g. in standalone tests)
  const [internalTask, setInternalTask] = useState('');
  const [internalContext, setInternalContext] = useState('');
  const [internalTrack, setInternalTrack] = useState<TrackType>('economica');
  const [internalShowConstraints, setInternalShowConstraints] = useState(false);
  const [internalCaps, setInternalCaps] = useState('');
  const [internalCriteria, setInternalCriteria] = useState('');
  const [internalRoutes, setInternalRoutes] = useState('');
  const [internalMaxCostAmount, setInternalMaxCostAmount] = useState('');
  const [internalMaxCostCurrency, setInternalMaxCostCurrency] = useState('USD');
  const [internalApiResponse, setInternalApiResponse] = useState<ExecutionApiResponse | null>(null);
  const [internalRoutingPreview, setInternalRoutingPreview] = useState<RoutingPreview | null>(null);

  const task = controlledTask !== undefined ? controlledTask : internalTask;
  const setTask = setControlledTask || setInternalTask;

  const context = controlledContext !== undefined ? controlledContext : internalContext;
  const setContext = setControlledContext || setInternalContext;

  const track = controlledTrack !== undefined ? controlledTrack : internalTrack;
  const setTrack = setControlledTrack || setInternalTrack;

  const showConstraints = controlledShowConstraints !== undefined ? controlledShowConstraints : internalShowConstraints;
  const setShowConstraints = setControlledShowConstraints || setInternalShowConstraints;

  const capabilitiesInput = controlledCaps !== undefined ? controlledCaps : internalCaps;
  const setCapabilitiesInput = setControlledCaps || setInternalCaps;

  const criteriaInput = controlledCriteria !== undefined ? controlledCriteria : internalCriteria;
  const setCriteriaInput = setControlledCriteria || setInternalCriteria;

  const allowedRoutesInput = controlledRoutes !== undefined ? controlledRoutes : internalRoutes;
  const setAllowedRoutesInput = setControlledRoutes || setInternalRoutes;

  const maxCostAmount = controlledMaxCostAmount !== undefined ? controlledMaxCostAmount : internalMaxCostAmount;
  const setMaxCostAmount = setControlledMaxCostAmount || setInternalMaxCostAmount;

  const maxCostCurrency = controlledMaxCostCurrency !== undefined ? controlledMaxCostCurrency : internalMaxCostCurrency;
  const setMaxCostCurrency = setControlledMaxCostCurrency || setInternalMaxCostCurrency;

  const apiResponse = controlledApiResponse !== undefined ? controlledApiResponse : internalApiResponse;
  const setApiResponse = setControlledApiResponse || setInternalApiResponse;

  const routingPreview = controlledRoutingPreview !== undefined ? controlledRoutingPreview : internalRoutingPreview;
  const setRoutingPreview = setControlledRoutingPreview || setInternalRoutingPreview;

  const [isLoading, setIsLoading] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [activeTooltip, setActiveTooltip] = useState<string | null>(null);

  // Manipulador de atalho de teclado: Ctrl + Enter / Cmd + Enter
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (!isLoading && task.trim().length > 0) {
          handleSubmit();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [task, context, capabilitiesInput, criteriaInput, allowedRoutesInput, maxCostAmount, maxCostCurrency, isLoading]);

  const loadPreset = (preset: PresetExample) => {
    setTask(preset.request.task);
    setContext(preset.request.context || '');

    if (preset.request.constraints) {
      setShowConstraints(true);
      setCapabilitiesInput(
        preset.request.constraints.required_capabilities?.join(',') || ''
      );
      setCriteriaInput(
        preset.request.constraints.required_quality_criteria?.join(',') || ''
      );
      setAllowedRoutesInput(
        preset.request.constraints.allowed_route_ids?.join(',') || ''
      );
      if (preset.request.constraints.max_estimated_cost) {
        setMaxCostAmount(preset.request.constraints.max_estimated_cost.amount);
        setMaxCostCurrency(preset.request.constraints.max_estimated_cost.currency);
      } else {
        setMaxCostAmount('');
      }
    } else {
      setShowConstraints(false);
      setCapabilitiesInput('');
      setCriteriaInput('');
      setAllowedRoutesInput('');
      setMaxCostAmount('');
    }
  };

  const handleClear = () => {
    setTask('');
    setContext('');
    setCapabilitiesInput('');
    setCriteriaInput('');
    setAllowedRoutesInput('');
    setMaxCostAmount('');
    setMaxCostCurrency('USD');
    setApiResponse(null);
    setRoutingPreview(null);
  };

  const handleFetchPreview = async () => {
    if (!task.trim()) {
      alert('Por favor, informe uma tarefa antes de solicitar sugestão de rota.');
      return;
    }

    try {
      setIsPreviewLoading(true);
      const parseListWithoutTrimming = (val: string) =>
        val.split(',').filter((s) => s.length > 0);

      const caps = parseListWithoutTrimming(capabilitiesInput);
      const criteria = parseListWithoutTrimming(criteriaInput);
      const routes = parseListWithoutTrimming(allowedRoutesInput);

      const constraintsPayload: Record<string, unknown> = {};
      if (caps.length > 0) constraintsPayload.required_capabilities = caps;
      if (criteria.length > 0) constraintsPayload.required_quality_criteria = criteria;
      if (routes.length > 0) constraintsPayload.allowed_route_ids = routes;
      if (maxCostAmount.length > 0) {
        constraintsPayload.max_estimated_cost = {
          amount: maxCostAmount,
          currency: maxCostCurrency,
        };
      }

      const preview = await fetchRoutingPreview({
        task,
        context: context.trim() ? context : undefined,
        track,
        constraints: Object.keys(constraintsPayload).length > 0 ? constraintsPayload : undefined,
      });
      setRoutingPreview(preview);
    } catch (err: any) {
      alert(err.message || 'Falha ao obter sugestão de roteamento.');
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleApplyPreview = () => {
    if (routingPreview?.recommended_route) {
      const rec = routingPreview.recommended_route;
      setShowConstraints(true);
      setAllowedRoutesInput(rec.route_id);
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    if (!task.trim() || isLoading) {
      return;
    }

    setIsLoading(true);
    setApiResponse(null);

    const parseListWithoutTrimming = (val: string) =>
      val.split(',').filter((s) => s.length > 0);

    const caps = parseListWithoutTrimming(capabilitiesInput);
    const criteria = parseListWithoutTrimming(criteriaInput);
    const routes = parseListWithoutTrimming(allowedRoutesInput);

    const requestPayload: ExecutionRequest = {
      task: task,
    };

    if (context.trim().length > 0) {
      requestPayload.context = context;
    }

    const hasConstraints =
      caps.length > 0 ||
      criteria.length > 0 ||
      routes.length > 0 ||
      maxCostAmount.length > 0;

    if (hasConstraints) {
      requestPayload.constraints = {};
      if (caps.length > 0) requestPayload.constraints.required_capabilities = caps;
      if (criteria.length > 0) requestPayload.constraints.required_quality_criteria = criteria;
      if (routes.length > 0) requestPayload.constraints.allowed_route_ids = routes;
      if (maxCostAmount.length > 0) {
        requestPayload.constraints.max_estimated_cost = {
          amount: maxCostAmount,
          currency: maxCostCurrency,
        };
      }
    }

    const response = await executeAdminTask(requestPayload, track);
    setApiResponse(response);
    setIsLoading(false);

    if (onExecutionResult) {
      onExecutionResult(response.kind);
    }
  };

  const handleCopyResult = () => {
    if (apiResponse && apiResponse.kind === 'success') {
      navigator.clipboard.writeText(apiResponse.data.result.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Safe status indicators for OpenAI
  const openaiProvider = configInfo?.providers.find((p) => p.id === 'openai');
  const isKeyRegistered = openaiProvider?.credential.registered;
  const isKeyVerified = openaiProvider?.credential.status === 'verified';
  const activeRoutesCount = configInfo?.routes.filter((r) => r.enabled).length ?? 1;

  return (
    <div className="execution-view">
      {/* Onboarding & Apresentação Rápida */}
      <div className="card" style={{ marginBottom: '1.25rem', background: 'linear-gradient(135deg, var(--bg-surface) 0%, var(--bg-secondary) 100%)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Compass size={20} color="var(--color-primary)" />
              Solicitação de Execução
            </h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.25rem 0 0.75rem 0', maxWidth: '650px' }}>
              Pronto para Roteamento Neutro. O Maestro analisa requisitos técnicos e referências auditáveis de preço antes de enviar sua tarefa ao provedor de IA.
            </p>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {onNavigateTab && (
              <>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ fontSize: '0.8rem', padding: '0.35rem 0.65rem' }}
                  onClick={() => onNavigateTab('learn')}
                >
                  <BookOpen size={14} />
                  Modo Estudante
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ fontSize: '0.8rem', padding: '0.35rem 0.65rem' }}
                  onClick={() => onNavigateTab('providers')}
                >
                  <Layers size={14} />
                  Provedores & Rotas
                </button>
              </>
            )}
          </div>
        </div>

        {/* Resumo de Configuração Ativa */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', paddingTop: '0.75rem', borderTop: '1px solid var(--border-color)', fontSize: '0.8rem' }}>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Provedor: </span>
            <strong style={{ color: 'var(--text-primary)' }}>OpenAI</strong>{' '}
            {isKeyVerified ? (
              <span className="badge badge-green" style={{ fontSize: '0.7rem' }}>Chave Verificada</span>
            ) : isKeyRegistered ? (
              <span className="badge badge-blue" style={{ fontSize: '0.7rem' }}>Chave em Memória</span>
            ) : (
              <span className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>Chave não cadastrada</span>
            )}
          </div>

          <div>
            <span style={{ color: 'var(--text-muted)' }}>Rotas Habilitadas: </span>
            <strong style={{ color: 'var(--text-primary)' }}>{activeRoutesCount}</strong>
          </div>

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--color-warning)' }}>
            <Info size={13} />
            <span style={{ fontSize: '0.75rem' }}>
              Execuções reais acionam chamadas à OpenAI sujeitas à tarifação da sua conta.
            </span>
          </div>
        </div>
      </div>

      {/* Preset Examples */}
      <div className="presets-container" style={{ marginBottom: '1.25rem' }}>
        <span className="presets-label">Exemplos Rápidos:</span>
        <div className="presets-scroll">
          {PRESET_EXAMPLES.map((preset, index) => (
            <button
              key={index}
              type="button"
              className="preset-pill"
              onClick={() => loadPreset(preset)}
              title={preset.request.task}
            >
              <Sparkles size={12} className="preset-icon" />
              <span>{preset.title}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Main Execution Form */}
      <form onSubmit={handleSubmit} className="execution-form">
        {/* Seletor de Trilha de Roteamento (Section 6) */}
        <div className="card" style={{ marginBottom: '1rem', padding: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                Trilha de Roteamento
              </label>
              <span
                style={{ cursor: 'pointer', color: 'var(--text-muted)' }}
                onClick={() => setActiveTooltip(activeTooltip === 'track' ? null : 'track')}
                title="Ajuda sobre trilhas"
              >
                <HelpCircle size={14} />
              </span>
            </div>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleFetchPreview}
              disabled={isPreviewLoading || !task.trim()}
              style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem', borderColor: 'var(--color-primary)' }}
            >
              <Sparkles size={14} color="var(--color-primary)" className={isPreviewLoading ? 'spin' : ''} />
              Sugerir modelos/rotas (Custo Zero)
            </button>
          </div>

          {activeTooltip === 'track' && (
            <div className="alert-card info" style={{ marginBottom: '0.75rem', fontSize: '0.8rem' }}>
              <p style={{ margin: 0 }}>
                <strong>Trilha:</strong> determina a política que o Maestro aplicará para selecionar a rota.
                A trilha <em>Free</em> exige tarifas zero declaradas pelo operador e estimativa calculada igual a zero; não confirma faturamento na conta do provedor. A trilha <em>Econômica</em> busca o menor custo estimado entre as rotas aptas comparáveis. A trilha <em>Inteligente</em> aplica critérios de qualidade e requisitos técnicos explicitamente declarados com evidências auditáveis.
              </p>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.5rem' }}>
            <div
              onClick={() => setTrack('free')}
              style={{
                padding: '0.65rem 0.85rem',
                borderRadius: 'var(--radius-sm)',
                border: `2px solid ${track === 'free' ? 'var(--color-primary)' : 'var(--border-color)'}`,
                background: track === 'free' ? 'rgba(99, 102, 241, 0.08)' : 'var(--bg-secondary)',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <Sparkles size={15} color="var(--color-primary)" />
                <strong style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>Free</strong>
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginTop: '0.2rem' }}>
                Somente candidatos com tarifas zero declaradas pelo operador.
              </span>
            </div>

            <div
              onClick={() => setTrack('economica')}
              style={{
                padding: '0.65rem 0.85rem',
                borderRadius: 'var(--radius-sm)',
                border: `2px solid ${track === 'economica' ? 'var(--color-primary)' : 'var(--border-color)'}`,
                background: track === 'economica' ? 'rgba(99, 102, 241, 0.08)' : 'var(--bg-secondary)',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <DollarSign size={15} color="var(--color-success)" />
                <strong style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>Econômica</strong>
                <span className="badge badge-purple" style={{ fontSize: '0.65rem' }}>Padrão</span>
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginTop: '0.2rem' }}>
                Menor custo estimado entre rotas elegíveis comparáveis.
              </span>
            </div>

            <div
              onClick={() => setTrack('inteligente')}
              style={{
                padding: '0.65rem 0.85rem',
                borderRadius: 'var(--radius-sm)',
                border: `2px solid ${track === 'inteligente' ? 'var(--color-primary)' : 'var(--border-color)'}`,
                background: track === 'inteligente' ? 'rgba(99, 102, 241, 0.08)' : 'var(--bg-secondary)',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <Scale size={15} color="var(--color-warning)" />
                <strong style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>Inteligente</strong>
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginTop: '0.2rem' }}>
                Aplica critérios de qualidade e requisitos explícitos.
              </span>
            </div>
          </div>

          {track === 'free' && (
            <div
              className="alert-card warning"
              style={{ marginTop: '0.75rem', fontSize: '0.8rem' }}
              data-testid="free-track-disclaimer"
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
                <AlertCircle size={16} color="var(--color-warning)" style={{ flexShrink: 0, marginTop: '2px' }} />
                <div>
                  <strong>Aviso sobre a Trilha Free (Gratuidade declarada pelo operador):</strong>{' '}
                  A trilha Free valida apenas se as tarifas cadastradas localmente pelo operador são iguais a zero e se a estimativa calculada é zero.
                  Ela não confirma se a sua conta ou cota no provedor realmente possuem isenção de faturamento; cabe ao operador validar as condições e políticas comerciais do provedor.
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Card de Sugestão / Prévia Explicável (Section 7) */}
        {routingPreview && (
          <div
            className="card"
            style={{
              marginBottom: '1rem',
              borderLeft: '4px solid var(--color-primary)',
              background: 'var(--bg-secondary)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <span className="badge badge-purple" style={{ marginBottom: '0.25rem' }}>
                  Sugestão Explicável • Prévia Sem Custo de Tokens
                </span>
                <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                  {routingPreview.recommended_route
                    ? `Rota Recomendada: ${routingPreview.recommended_route.route_id} (${routingPreview.recommended_route.model})`
                    : 'Nenhuma Recomendação Confiável na Trilha Selecionada'}
                </h4>
              </div>

              {routingPreview.recommended_route && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleApplyPreview}
                  style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem' }}
                >
                  <Check size={14} />
                  Aplicar Sugestão ao Formulário
                </button>
              )}
            </div>

            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.5rem 0' }}>
              {routingPreview.explanation}
            </p>

            {routingPreview.recommended_route && (
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                <span>{routingPreview.economic_data_status}</span>
                {routingPreview.billing_warning && (
                  <span style={{ color: 'var(--color-warning)' }}>
                    * Possibilidade de cobrança no provedor ao executar
                  </span>
                )}
              </div>
            )}

            {/* Exclusões Explicadas */}
            {routingPreview.exclusions && routingPreview.exclusions.length > 0 && (
              <details style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                <summary style={{ cursor: 'pointer', fontWeight: 600 }}>
                  Ver {routingPreview.exclusions.length} exclusão(ões) analisada(s)
                </summary>
                <ul style={{ paddingLeft: '1.25rem', marginTop: '0.25rem' }}>
                  {routingPreview.exclusions.map((exc, idx) => (
                    <li key={idx}>{exc.description || `${exc.route_id}: ${exc.reason}`}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}

        {/* Campo Tarefa (task) */}
        <div className="form-group">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <label htmlFor="task-input" className="form-label">
              Tarefa Principal (<code>task</code>) <span className="required-star">*</span>
            </label>
            <span
              style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
              onClick={() => setActiveTooltip(activeTooltip === 'task' ? null : 'task')}
            >
              <HelpCircle size={13} /> Ajuda
            </span>
          </div>

          {activeTooltip === 'task' && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
              Instrução obrigatória que define o objetivo da execução para o modelo.
            </span>
          )}

          <textarea
            id="task-input"
            className="input-textarea task-area"
            placeholder="Ex: Resuma o texto a seguir em duas frases objetivas..."
            value={task}
            onChange={(e) => setTask(e.target.value)}
            rows={3}
            required
            aria-required="true"
          />
        </div>

        {/* Campo Contexto (context) */}
        <div className="form-group">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <label htmlFor="context-input" className="form-label">
              Contexto Adicional (<code>context</code>) <span className="optional-tag">(opcional)</span>
            </label>
            <span
              style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
              onClick={() => setActiveTooltip(activeTooltip === 'context' ? null : 'context')}
            >
              <HelpCircle size={13} /> Ajuda
            </span>
          </div>

          {activeTooltip === 'context' && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
              Texto auxiliar opcional (documento, código ou histórico) fornecido como contexto para a tarefa.
            </span>
          )}

          <textarea
            id="context-input"
            className="input-textarea"
            placeholder="Insira dados, trechos de código ou texto complementar aqui..."
            value={context}
            onChange={(e) => setContext(e.target.value)}
            rows={2}
          />
        </div>

        {/* Accordion de Restrições Técnicas */}
        <div className="constraints-section">
          <button
            type="button"
            className="constraints-toggle"
            onClick={() => setShowConstraints(!showConstraints)}
            aria-expanded={showConstraints}
            aria-controls="constraints-fields"
          >
            <div className="constraints-toggle-left">
              <SlidersHorizontal size={16} />
              <span>Restrições da Solicitação (Opcional)</span>
            </div>
            {showConstraints ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>

          {showConstraints && (
            <div id="constraints-fields" className="constraints-fields">
              <div className="constraints-grid">
                <div>
                  <label htmlFor="caps-input" className="form-label-sub">
                    Capacidades Exigidas (<code>required_capabilities</code>)
                  </label>
                  <input
                    id="caps-input"
                    type="text"
                    className="input-text-sub"
                    placeholder="text_generation, summarization"
                    value={capabilitiesInput}
                    onChange={(e) => setCapabilitiesInput(e.target.value)}
                  />
                  <span className="field-hint">Valores separados por vírgula.</span>
                </div>

                <div>
                  <label htmlFor="criteria-input" className="form-label-sub">
                    Critérios de Qualidade Obrigatórios (<code>required_quality_criteria</code>)
                  </label>
                  <input
                    id="criteria-input"
                    type="text"
                    className="input-text-sub"
                    placeholder="summary_faithfulness_accepted"
                    value={criteriaInput}
                    onChange={(e) => setCriteriaInput(e.target.value)}
                  />
                  <span className="field-hint">Critérios técnicos validados.</span>
                </div>

                <div>
                  <label htmlFor="routes-input" className="form-label-sub">
                    Rotas Permitidas (<code>allowed_route_ids</code>)
                  </label>
                  <input
                    id="routes-input"
                    type="text"
                    className="input-text-sub"
                    placeholder="route-openai-gpt4o-mini"
                    value={allowedRoutesInput}
                    onChange={(e) => setAllowedRoutesInput(e.target.value)}
                  />
                  <span className="field-hint">Allowlist estrita de rotas.</span>
                </div>

                <div>
                  <label htmlFor="cost-amount-input" className="form-label-sub">
                    Teto de Custo Estimado (<code>max_estimated_cost</code>)
                  </label>
                  <div className="cost-input-group">
                    <input
                      id="cost-amount-input"
                      type="text"
                      className="input-text-sub"
                      placeholder="0.0100"
                      value={maxCostAmount}
                      onChange={(e) => setMaxCostAmount(e.target.value)}
                    />
                    <select
                      className="select-sub"
                      value={maxCostCurrency}
                      onChange={(e) => setMaxCostCurrency(e.target.value)}
                    >
                      <option value="USD">USD</option>
                      <option value="BRL">BRL</option>
                      <option value="EUR">EUR</option>
                    </select>
                  </div>
                  <span className="field-hint">Exato: 4 casas decimais.</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Ações do Formulário */}
        <div className="form-actions">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={isLoading || task.trim().length === 0}
            title="Enviar solicitação (Ctrl + Enter)"
          >
            {isLoading ? (
              <>
                <div className="btn-spinner" aria-hidden="true" />
                <span>Processando...</span>
              </>
            ) : (
              <>
                <Send size={16} />
                <span>Executar Rota</span>
                <kbd className="keyboard-shortcut">Ctrl+Enter</kbd>
              </>
            )}
          </button>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleClear}
            disabled={isLoading}
          >
            <RotateCcw size={16} />
            <span>Limpar Formulário</span>
          </button>
        </div>
      </form>

      {/* Resultados e Recusas */}
      <div className="results-container" aria-live="polite">
        {isLoading && (
          <div className="card loading-card">
            <div className="loading-content">
              <div className="loading-spinner" />
              <div className="loading-text">
                <h3>Avaliando Elegibilidade e Roteando...</h3>
                <p>O Maestro Router está aplicando as regras não-econômicas e econômicas da trilha {track}.</p>
              </div>
            </div>
          </div>
        )}

        {!isLoading && apiResponse && (
          <div className="response-section">
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.5rem' }}>
              Escopo da Visualização: <strong>Resultado da última execução nesta sessão</strong>. A resposta reflete a chamada realizada e não constitui garantia de disponibilidade contínua.
            </span>

            {/* Sucesso HTTP 200 */}
            {apiResponse.kind === 'success' && (
              <div className="success-container">
                <div className="card result-card">
                  <div className="result-header">
                    <div className="result-header-left">
                      <FileText size={20} color="var(--color-success)" />
                      <h3 className="result-title">Conteúdo Gerado pelo Modelo</h3>
                    </div>
                    <button
                      type="button"
                      className="copy-button"
                      onClick={handleCopyResult}
                      aria-label="Copiar resultado"
                    >
                      {copied ? (
                        <>
                          <Check size={14} color="var(--color-success)" />
                          <span style={{ color: 'var(--color-success)' }}>Copiado!</span>
                        </>
                      ) : (
                        <>
                          <Copy size={14} />
                          <span>Copiar</span>
                        </>
                      )}
                    </button>
                  </div>
                  <div className="result-content">
                    <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                      {apiResponse.data.result.content}
                    </p>
                  </div>
                </div>

                {apiResponse.data.decision && (
                  <DecisionCard decision={apiResponse.data.decision} />
                )}

                {apiResponse.data.economics && (
                  <EconomicsCard economics={apiResponse.data.economics} />
                )}
              </div>
            )}

            {/* Recusa HTTP 422 */}
            {apiResponse.kind === 'refusal' && (
              <RefusalCard
                errorResponse={apiResponse.error}
                onNavigateToProviders={() => onNavigateTab && onNavigateTab('providers')}
                onNavigateToLearn={() => onNavigateTab && onNavigateTab('learn')}
              />
            )}

            {/* Erro de Validação da Requisição (400 ou 415) */}
            {apiResponse.kind === 'client_error' && (
              <div className="alert-card danger" role="alert">
                <div className="alert-header">
                  <AlertOctagon size={24} color="var(--color-danger)" />
                  <div>
                    <h3 className="alert-title">
                      Erro de Validação da Solicitação (HTTP {apiResponse.status})
                    </h3>
                    <span className="badge badge-danger">
                      Código: {apiResponse.error.error.code}
                    </span>
                  </div>
                </div>
                <p className="alert-message">{apiResponse.error.error.message}</p>
                {apiResponse.error.error.issues && (
                  <ul className="error-issues-list">
                    {apiResponse.error.error.issues.map((issue, idx) => (
                      <li key={idx}>{issue.message}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* Falha de Execução do Provedor (502, 503, 504) */}
            {apiResponse.kind === 'execution_error' && (
              <div className="alert-card danger" role="alert">
                <div className="alert-header">
                  <AlertOctagon size={24} color="var(--color-danger)" />
                  <div>
                    <h3 className="alert-title">
                      Falha na Execução do Provedor (HTTP {apiResponse.status})
                    </h3>
                    <span className="badge badge-danger">
                      Código: {apiResponse.error.error.code}
                    </span>
                  </div>
                </div>
                <p className="alert-message">{apiResponse.error.error.message}</p>
                <div className="recommendation-box">
                  <h4 className="recommendation-title">Comportamento do Motor</h4>
                  <p className="recommendation-text">
                    O Maestro Router selecionou a rota com sucesso, mas o provedor externo falhou ou demorou além do limite tolerável. O erro foi traduzido sem vazar dados confidenciais externos.
                  </p>
                </div>
                {apiResponse.error.decision && (
                  <DecisionCard decision={apiResponse.error.decision} />
                )}
              </div>
            )}

            {/* Erro Interno (500) */}
            {apiResponse.kind === 'server_error' && (
              <div className="alert-card danger" role="alert">
                <div className="alert-header">
                  <AlertOctagon size={24} color="var(--color-danger)" />
                  <div>
                    <h3 className="alert-title">Erro Interno do Servidor (HTTP 500)</h3>
                    <span className="badge badge-danger">
                      Código: {apiResponse.error.error.code}
                    </span>
                  </div>
                </div>
                <p className="alert-message">{apiResponse.error.error.message}</p>
              </div>
            )}

            {/* Falha de Conexão de Rede (status 0) */}
            {apiResponse.kind === 'network_error' && (
              <div className="alert-card danger" role="alert">
                <div className="alert-header">
                  <WifiOff size={24} color="var(--color-danger)" />
                  <div>
                    <h3 className="alert-title">Falha de Conectividade com a API</h3>
                    <span className="badge badge-danger">Servidor Inacessível</span>
                  </div>
                </div>
                <p className="alert-message">{apiResponse.message}</p>
                {apiResponse.details && (
                  <div className="network-instructions">
                    <span className="network-instructions-label">
                      <Terminal size={12} style={{ display: 'inline', marginRight: 4 }} />
                      Como iniciar o backend:
                    </span>
                    <pre className="code-snippet">
python -m uvicorn --app-dir src maestro_router.control_center:app --port 8000
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* Erro de Protocolo Inesperado */}
            {apiResponse.kind === 'protocol_error' && (
              <div className="alert-card danger" role="alert">
                <div className="alert-header">
                  <AlertOctagon size={24} color="var(--color-danger)" />
                  <div>
                    <h3 className="alert-title">Erro de Protocolo HTTP ({apiResponse.status})</h3>
                    <span className="badge badge-danger">
                      {apiResponse.error.code}
                    </span>
                  </div>
                </div>
                <p className="alert-message">{apiResponse.error.message}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

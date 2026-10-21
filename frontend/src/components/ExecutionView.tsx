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
  WifiOff,
  Terminal,
  FileText,
  SlidersHorizontal,
} from 'lucide-react';
import { ExecutionApiResponse, ExecutionRequest } from '../types';
import { executeTask } from '../services/api';
import { DecisionCard } from './DecisionCard';
import { EconomicsCard } from './EconomicsCard';
import { RefusalCard } from './RefusalCard';

interface PresetExample {
  title: string;
  request: ExecutionRequest;
}

/** Exemplos normativos reprodutíveis baseados na documentação e casos de uso do MVP. */
const PRESET_EXAMPLES: PresetExample[] = [
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
    title: '3. Teto de Custo Estimado (0.010 USD)',
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
    title: '4. Allowlist Restritiva de Rota',
    request: {
      task: 'Gere um exemplo de cabeçalho HTTP em JSON.',
      constraints: {
        allowed_route_ids: ['route-primary-openai', 'route-fast-local'],
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
      | 'network_error'
  ) => void;
}

export const ExecutionView: React.FC<ExecutionViewProps> = ({ onExecutionResult }) => {
  const [task, setTask] = useState('');
  const [context, setContext] = useState('');
  const [showConstraints, setShowConstraints] = useState(false);
  const [capabilitiesInput, setCapabilitiesInput] = useState('');
  const [criteriaInput, setCriteriaInput] = useState('');
  const [allowedRoutesInput, setAllowedRoutesInput] = useState('');
  const [maxCostAmount, setMaxCostAmount] = useState('');
  const [maxCostCurrency, setMaxCostCurrency] = useState('USD');

  const [isLoading, setIsLoading] = useState(false);
  const [apiResponse, setApiResponse] = useState<ExecutionApiResponse | null>(null);
  const [copied, setCopied] = useState(false);

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
        preset.request.constraints.required_capabilities?.join(', ') || ''
      );
      setCriteriaInput(
        preset.request.constraints.required_quality_criteria?.join(', ') || ''
      );
      setAllowedRoutesInput(
        preset.request.constraints.allowed_route_ids?.join(', ') || ''
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
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    if (!task.trim()) {
      return;
    }

    setIsLoading(true);
    setApiResponse(null);

    const parseList = (val: string) =>
      val
        .split(',')
        .map((s) => s.trim())
        .filter((s) => s.length > 0);

    const caps = parseList(capabilitiesInput);
    const criteria = parseList(criteriaInput);
    const routes = parseList(allowedRoutesInput);

    const requestPayload: ExecutionRequest = {
      task: task.trim(),
    };

    if (context.trim()) {
      requestPayload.context = context.trim();
    }

    const hasConstraints =
      caps.length > 0 ||
      criteria.length > 0 ||
      routes.length > 0 ||
      Boolean(maxCostAmount.trim());

    if (hasConstraints) {
      requestPayload.constraints = {};
      if (caps.length > 0) requestPayload.constraints.required_capabilities = caps;
      if (criteria.length > 0) requestPayload.constraints.required_quality_criteria = criteria;
      if (routes.length > 0) requestPayload.constraints.allowed_route_ids = routes;
      if (maxCostAmount.trim()) {
        requestPayload.constraints.max_estimated_cost = {
          amount: maxCostAmount.trim(),
          currency: maxCostCurrency.trim() || 'USD',
        };
      }
    }

    const response = await executeTask(requestPayload);
    setApiResponse(response);
    setIsLoading(false);

    if (onExecutionResult) {
      onExecutionResult(response.kind);
    }
  };

  const handleCopyContent = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="execution-grid">
      {/* Coluna da Esquerda: Formulário de Entrada */}
      <section aria-labelledby="form-title">
        <div className="card">
          <div className="card-header">
            <h2 id="form-title" className="card-title">
              <Sparkles size={18} color="var(--color-primary)" />
              Solicitação de Execução
            </h2>

            <div className="examples-bar" style={{ margin: 0 }}>
              <select
                aria-label="Carregar exemplo rápido"
                className="example-select"
                onChange={(e) => {
                  const idx = parseInt(e.target.value, 10);
                  if (!isNaN(idx) && PRESET_EXAMPLES[idx]) {
                    loadPreset(PRESET_EXAMPLES[idx]);
                  }
                }}
                defaultValue=""
              >
                <option value="" disabled>
                  Carregar exemplo...
                </option>
                {PRESET_EXAMPLES.map((ex, i) => (
                  <option key={i} value={i}>
                    {ex.title}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="task-input" className="form-label">
                Tarefa (<span className="code-font">task</span>)
                <span className="required" title="Campo obrigatório">*</span>
              </label>
              <textarea
                id="task-input"
                className="form-textarea"
                rows={3}
                placeholder="Ex.: Resuma o texto em duas frases..."
                value={task}
                onChange={(e) => setTask(e.target.value)}
                required
                aria-required="true"
              />
              <div className="form-help">
                Instrução principal para o modelo. Não contém dados de autenticação.
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="context-input" className="form-label">
                Contexto Adicional (<span className="code-font">context</span>)
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: 6 }}>
                  (Opcional)
                </span>
              </label>
              <textarea
                id="context-input"
                className="form-textarea"
                rows={4}
                placeholder="Ex.: Cole aqui documentos, trechos de código ou texto complementar..."
                value={context}
                onChange={(e) => setContext(e.target.value)}
              />
              <div className="form-help">
                Se omitido, nenhum contexto complementar será presumido pelo Maestro.
              </div>
            </div>

            {/* Painel Expansível de Restrições */}
            <button
              type="button"
              className="accordion-toggle"
              onClick={() => setShowConstraints(!showConstraints)}
              aria-expanded={showConstraints}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <SlidersHorizontal size={16} />
                Restrições da Solicitação (<span className="code-font">constraints</span>)
              </span>
              {showConstraints ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>

            {showConstraints && (
              <div className="accordion-body">
                <div className="form-group">
                  <label htmlFor="caps-input" className="form-label" style={{ fontSize: '0.8rem' }}>
                    Capacidades Obrigatórias
                  </label>
                  <input
                    id="caps-input"
                    type="text"
                    className="form-input code-font"
                    placeholder="text_generation, summarization"
                    value={capabilitiesInput}
                    onChange={(e) => setCapabilitiesInput(e.target.value)}
                  />
                  <div className="form-help">Separadas por vírgula.</div>
                </div>

                <div className="form-group">
                  <label htmlFor="routes-input" className="form-label" style={{ fontSize: '0.8rem' }}>
                    Rotas Permitidas (Allowlist)
                  </label>
                  <input
                    id="routes-input"
                    type="text"
                    className="form-input code-font"
                    placeholder="route-primary, route-openai-mini"
                    value={allowedRoutesInput}
                    onChange={(e) => setAllowedRoutesInput(e.target.value)}
                  />
                  <div className="form-help">
                    Intersectadas com as rotas habilitadas da configuração.
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '0.75rem' }}>
                  <div className="form-group">
                    <label htmlFor="cost-amt-input" className="form-label" style={{ fontSize: '0.8rem' }}>
                      Teto de Custo Máximo
                    </label>
                    <input
                      id="cost-amt-input"
                      type="text"
                      className="form-input code-font"
                      placeholder="0.0100"
                      value={maxCostAmount}
                      onChange={(e) => setMaxCostAmount(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="cost-curr-input" className="form-label" style={{ fontSize: '0.8rem' }}>
                      Moeda
                    </label>
                    <input
                      id="cost-curr-input"
                      type="text"
                      className="form-input code-font"
                      maxLength={3}
                      placeholder="USD"
                      value={maxCostCurrency}
                      onChange={(e) => setMaxCostCurrency(e.target.value.toUpperCase())}
                    />
                  </div>
                </div>
              </div>
            )}

            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={isLoading || task.trim().length === 0}
                aria-busy={isLoading}
              >
                {isLoading ? (
                  <>
                    <div className="spinner" aria-hidden="true" />
                    <span>Roteando & Executando...</span>
                  </>
                ) : (
                  <>
                    <Send size={16} aria-hidden="true" />
                    <span>Executar Rota</span>
                  </>
                )}
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleClear}
                disabled={isLoading}
              >
                <RotateCcw size={16} aria-hidden="true" />
                <span>Limpar</span>
              </button>

              <span
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-muted)',
                  marginLeft: 'auto',
                }}
              >
                Atalho: <kbd style={{ padding: '2px 4px', background: 'var(--bg-tertiary)', borderRadius: 4 }}>Ctrl+Enter</kbd>
              </span>
            </div>
          </form>
        </div>
      </section>

      {/* Coluna da Direita: Painel de Resultados & Observabilidade */}
      <section aria-labelledby="results-title" aria-live="polite">
        <h2 id="results-title" className="visually-hidden" style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden' }}>
          Resultado da Execução
        </h2>

        {/* Estado Vazio */}
        {!isLoading && !apiResponse && (
          <div className="empty-state">
            <div className="empty-icon">
              <FileText size={28} />
            </div>
            <h3 className="empty-title">Pronto para Roteamento Neutro</h3>
            <p className="empty-description">
              Envie uma tarefa e parâmetros opcionais para que o Maestro avalie as rotas elegíveis,
              calcule estimativas prévias e execute a melhor opção de forma transparente e auditável.
            </p>
          </div>
        )}

        {/* Estado de Carregamento */}
        {isLoading && (
          <div className="loading-card">
            <div className="loading-pulse" />
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Avaliando Critérios de Rota...
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
              Verificando elegibilidade não-econômica, estimativas monetárias e selecionando a rota ideal.
            </p>
          </div>
        )}

        {/* Sucesso (200 OK) */}
        {!isLoading && apiResponse && apiResponse.kind === 'success' && (
          <div>
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">
                  <Check size={18} color="var(--color-success)" />
                  Resultado da Execução
                </h3>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <span className="badge badge-success">HTTP 200 OK</span>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleCopyContent(apiResponse.data.result.content)}
                    title="Copiar resultado textual"
                  >
                    {copied ? <Check size={12} color="var(--color-success)" /> : <Copy size={12} />}
                    <span>{copied ? 'Copiado!' : 'Copiar'}</span>
                  </button>
                </div>
              </div>

              <div className="result-box">
                <div className="result-content">{apiResponse.data.result.content}</div>
              </div>
            </div>

            {/* Decisão do Roteador */}
            <DecisionCard decision={apiResponse.data.decision} />

            {/* Métricas Econômicas */}
            <EconomicsCard economics={apiResponse.data.economics} />
          </div>
        )}

        {/* Recusa (422 NO_ELIGIBLE_ROUTE ou INSUFFICIENT_ECONOMIC_INFORMATION) */}
        {!isLoading && apiResponse && apiResponse.kind === 'refusal' && (
          <RefusalCard errorResponse={apiResponse.error} />
        )}

        {/* Erro de Validação de Solicitação (400 Bad Request / 415 Unsupported Media Type) */}
        {!isLoading && apiResponse && apiResponse.kind === 'client_error' && (
          <div className="alert-card danger" role="alert">
            <div className="alert-header">
              <AlertOctagon size={24} color="var(--color-danger)" />
              <div>
                <h3 className="alert-title">
                  Erro de Solicitação ({apiResponse.error.error.code} - HTTP {apiResponse.status})
                </h3>
                <p className="alert-message" style={{ margin: 0 }}>
                  {apiResponse.error.error.message}
                </p>
              </div>
            </div>

            {apiResponse.error.error.issues && apiResponse.error.error.issues.length > 0 && (
              <div style={{ marginTop: '1rem' }}>
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Inconsistências apontadas pelo validador:
                </span>
                <ul style={{ paddingLeft: '1.25rem', marginTop: '0.5rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  {apiResponse.error.error.issues.map((issue, idx) => (
                    <li key={idx}>
                      {issue.path && <strong className="code-font">{issue.path}: </strong>}
                      {issue.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Erros de Execução Pós-Seleção (502 Bad Gateway / 503 Service Unavailable / 504 Gateway Timeout) */}
        {!isLoading && apiResponse && apiResponse.kind === 'execution_error' && (
          <div>
            <div className="alert-card danger" role="alert">
              <div className="alert-header">
                <AlertOctagon size={24} color="var(--color-danger)" />
                <div>
                  <h3 className="alert-title">
                    Falha na Execução do Provedor ({apiResponse.error.error.code} - HTTP {apiResponse.status})
                  </h3>
                  <p className="alert-message" style={{ margin: 0 }}>
                    {apiResponse.error.error.message}
                  </p>
                </div>
              </div>
            </div>

            {/* Em erros pós-seleção, a decisão e as estimativas econômicas acompanham o erro */}
            {apiResponse.error.decision && (
              <DecisionCard decision={apiResponse.error.decision} />
            )}
            {apiResponse.error.economics && (
              <EconomicsCard economics={apiResponse.error.economics} />
            )}
          </div>
        )}

        {/* Erro de Servidor Interno (500 INVALID_CONFIGURATION ou INVALID_DECISION) */}
        {!isLoading && apiResponse && apiResponse.kind === 'server_error' && (
          <div className="alert-card danger" role="alert">
            <div className="alert-header">
              <AlertOctagon size={24} color="var(--color-danger)" />
              <div>
                <h3 className="alert-title">
                  Falha do Servidor ({apiResponse.error.error.code} - HTTP {apiResponse.status})
                </h3>
                <p className="alert-message" style={{ margin: 0 }}>
                  {apiResponse.error.error.message}
                </p>
              </div>
            </div>
            {apiResponse.error.decision && (
              <DecisionCard decision={apiResponse.error.decision} />
            )}
          </div>
        )}

        {/* Erro de Conexão / Rede */}
        {!isLoading && apiResponse && apiResponse.kind === 'network_error' && (
          <div className="alert-card danger" role="alert">
            <div className="alert-header">
              <WifiOff size={24} color="var(--color-danger)" />
              <div>
                <h3 className="alert-title">Conexão Indisponível com o Maestro Router</h3>
                <p className="alert-message">{apiResponse.message}</p>
              </div>
            </div>

            <div className="recommendation-box">
              <h4 className="recommendation-title">
                <Terminal size={14} />
                Como Iniciar a API Localmente:
              </h4>
              <p className="recommendation-text">
                O backend do Maestro deve estar em execução no endereço <code>http://127.0.0.1:8000</code>.
                Execute no terminal:
              </p>
              <pre className="code-snippet">
python -m uvicorn --app-dir src maestro_router.api:app
              </pre>
            </div>
          </div>
        )}
      </section>
    </div>
  );
};

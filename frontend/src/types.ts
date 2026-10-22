/**
 * Contratos técnicos da API pública v1 do Maestro Router (docs/05-API.md).
 * Tipos rigorosamente alinhados à especificação normativa do MVP:
 *
 * 1. Uniões discriminadas estritas para decisões (SelectedDecision vs RefusedDecision).
 * 2. Uniões discriminadas estritas para economia e uso (available, uncertain, unavailable).
 * 3. Categorias estritamente fechadas para restrições e fatores (sem escape "| string").
 * 4. Taxonomia de erros fechada aos 8 códigos da API v1; erros de protocolo/cliente separados.
 * 5. Status HTTP contratuais representados por literais estritos (sem fallback "| number").
 * 6. Preservação mandatória de grandezas decimais como strings exatas.
 */

export interface MaxEstimatedCost {
  /** Valor monetário formatado estritamente como string decimal não negativa (ex: "0.0100"). */
  amount: string;
  /** Código de moeda ISO com exatamente 3 letras maiúsculas (ex: "USD"). */
  currency: string;
}

export interface RequestConstraints {
  /** Capacidades neutras exigidas da rota (ex: ["text_generation", "summarization"]). */
  required_capabilities?: string[];
  /** Critérios de qualidade aceitos na configuração (ex: ["summary_faithfulness_accepted"]). */
  required_quality_criteria?: string[];
  /** Identificadores de rota permitidos (allowlist estrita). */
  allowed_route_ids?: string[];
  /** Teto de custo estimado pré-execução. */
  max_estimated_cost?: MaxEstimatedCost;
}

export interface ExecutionRequest {
  /** Instrução textual principal da execução (obrigatória). */
  task: string;
  /** Material textual complementar (opcional; ausência significa nenhum contexto adicional). */
  context?: string;
  /** Restrições operacionais da solicitação (opcional). */
  constraints?: RequestConstraints;
}

export interface ExecutionResult {
  /** Conteúdo textual normalizado gerado pela rota executada. */
  content: string;
}

export interface SelectedRoute {
  /** Identificador neutro e único da rota na configuração. */
  id: string;
  /** Identificador neutro do provedor associado. */
  provider: string;
  /** Identificador neutro do modelo associado. */
  model: string;
}

export type ConstraintSource = 'request' | 'configuration';

export type ConstraintCategory =
  | 'route'
  | 'capability'
  | 'quality'
  | 'availability'
  | 'preference'
  | 'economics';

export interface AppliedConstraint {
  source: ConstraintSource;
  category: ConstraintCategory;
  description: string;
}

export type FactorCategory =
  | 'route'
  | 'capability'
  | 'quality'
  | 'availability'
  | 'preference'
  | 'economics'
  | 'configuration'
  | 'strategy'
  | 'tie_breaker';

export interface DecisionFactor {
  category: FactorCategory;
  description: string;
  references?: string[];
}

/** Decisão válida com rota selecionada (docs/05-API.md seção 7.2). */
export interface SelectedDecision {
  outcome: 'selected';
  route: SelectedRoute;
  strategy: {
    id: string;
    applied: true;
  };
  applied_constraints: AppliedConstraint[];
  reason: string;
  factors: DecisionFactor[];
}

/** Decisão de recusa válida antes da execução (docs/05-API.md seção 9.2). */
export interface RefusedDecision {
  outcome: 'refused';
  route?: never;
  strategy: {
    id: string;
    applied: false;
  };
  applied_constraints: AppliedConstraint[];
  reason: string;
  factors: DecisionFactor[];
}

export type Decision = SelectedDecision | RefusedDecision;

/* ==========================================================================
   Observabilidade Econômica (docs/05-API.md seção 8.1)
   ========================================================================== */

export interface AvailableEconomicEstimate {
  status: 'available';
  amount: string;
  currency: string;
  price_reference: string;
  assumptions: string[];
  reason?: never;
}

export interface UncertainEconomicEstimate {
  status: 'uncertain';
  amount: string;
  currency: string;
  price_reference: string;
  assumptions: string[];
  reason: string;
}

export interface UnavailableEconomicEstimate {
  status: 'unavailable';
  reason: string;
  amount?: never;
  currency?: never;
  price_reference?: never;
  assumptions?: never;
}

export type EconomicEstimate =
  | AvailableEconomicEstimate
  | UncertainEconomicEstimate
  | UnavailableEconomicEstimate;

export interface AvailableCalculatedCost {
  status: 'available';
  amount: string;
  currency: string;
  price_reference: string;
  assumptions: string[];
  reason?: never;
}

export interface UncertainCalculatedCost {
  status: 'uncertain';
  amount: string;
  currency: string;
  price_reference: string;
  assumptions: string[];
  reason: string;
}

export interface UnavailableCalculatedCost {
  status: 'unavailable';
  reason: string;
  amount?: never;
  currency?: never;
  price_reference?: never;
  assumptions?: never;
}

export type CalculatedCost =
  | AvailableCalculatedCost
  | UncertainCalculatedCost
  | UnavailableCalculatedCost;

/* ==========================================================================
   Uso Normalizado (docs/05-API.md seção 8.2)
   ========================================================================== */

export interface UsageItem {
  unit: string;
  quantity: string;
}

export interface AvailableUsage {
  status: 'available';
  items: UsageItem[];
  reason?: never;
}

export interface UncertainUsage {
  status: 'uncertain';
  items: UsageItem[];
  reason: string;
}

export interface UnavailableUsage {
  status: 'unavailable';
  reason: string;
  items?: never;
}

export type Usage = AvailableUsage | UncertainUsage | UnavailableUsage;

export interface ExecutionEconomics {
  estimate: EconomicEstimate;
  usage: Usage;
  calculated_cost: CalculatedCost;
}

export interface ExecutionSuccessResponse {
  result: ExecutionResult;
  decision: SelectedDecision;
  economics: ExecutionEconomics;
}

export interface ErrorIssue {
  path?: string;
  message: string;
}

/** Códigos semânticos estáveis enumerados na API pública v1 (docs/05-API.md seção 9.3). */
export type ApiErrorCode =
  | 'INVALID_REQUEST'
  | 'INVALID_CONFIGURATION'
  | 'NO_ELIGIBLE_ROUTE'
  | 'INSUFFICIENT_ECONOMIC_INFORMATION'
  | 'INVALID_DECISION'
  | 'EXECUTION_FAILED'
  | 'EXECUTION_UNAVAILABLE'
  | 'EXECUTION_TIMEOUT';

export interface ApiErrorPayload {
  code: ApiErrorCode;
  message: string;
  issues?: ErrorIssue[];
}

export interface ExecutionErrorResponse {
  error: ApiErrorPayload;
  decision?: Decision;
  economics?: ExecutionEconomics;
}

/** Erros internos de protocolo ou respostas anômalas fora do contrato v1. */
export type ProtocolErrorCode = 'INVALID_SERVER_RESPONSE' | 'UNEXPECTED_HTTP_STATUS';

export interface ProtocolErrorPayload {
  code: ProtocolErrorCode;
  message: string;
}

/**
 * Respostas categorizadas com fidelidade aos status HTTP do contrato:
 * - Sucesso: 200
 * - Recusa: 422
 * - Erro de cliente: 400 | 415
 * - Falha de execução pós-seleção: 502 | 503 | 504
 * - Erro interno do servidor: 500
 * - Erro de protocolo/inesperado: status genérico
 * - Falha de rede: status 0
 */
export type ExecutionApiResponse =
  | { kind: 'success'; status: 200; data: ExecutionSuccessResponse }
  | { kind: 'refusal'; status: 422; error: ExecutionErrorResponse }
  | { kind: 'client_error'; status: 400 | 415; error: ExecutionErrorResponse }
  | { kind: 'execution_error'; status: 502 | 503 | 504; error: ExecutionErrorResponse }
  | { kind: 'server_error'; status: 500; error: ExecutionErrorResponse }
  | { kind: 'protocol_error'; status: number; error: ProtocolErrorPayload }
  | { kind: 'network_error'; status: 0; message: string; details?: string };

// --- Tipos Operacionais da Camada Administrativa Local do Control Center (ADR 0012) ---

export type TrackType = 'free' | 'economica' | 'inteligente';

export type CredentialStatus =
  | 'not_registered'
  | 'registered'
  | 'verified'
  | 'access_denied'
  | 'insufficient_quota'
  | 'verification_unavailable';

export interface ProviderCredential {
  registered: boolean;
  status: CredentialStatus;
  verified_at: string | null;
  message: string | null;
}

export interface ProviderInfo {
  id: string;
  name: string;
  implemented: boolean;
  credential: ProviderCredential;
}

export interface RouteConfig {
  route_id: string;
  provider: string;
  model: string;
  enabled: boolean;
  known_unavailable: boolean;
  capabilities: string[];
  quality_criteria: string[];
  price_reference?: {
    id: string;
    currency: string;
    rates?: Array<{ unit: string; rate: string; base: number }>;
  };
  estimated_usage?: {
    input_token: number;
    output_token: number;
    applicability_confirmed?: boolean;
  };
  status: 'ready' | 'blocked';
  blockers: string[];
}

export interface RoutingPreview {
  track: TrackType;
  policy_description: string;
  recommended_route: {
    route_id: string;
    provider: string;
    model: string;
    estimate: {
      amount: string | null;
      currency: string | null;
      status: string;
    };
    price_reference: {
      id: string;
      currency: string;
    } | null;
    justification: string;
  } | null;
  candidate_evaluations: Array<{
    route_id: string;
    status: string;
    reason: string;
  }>;
  factors: Array<{
    category: string;
    description: string;
  }>;
  exclusions: Array<{
    route_id: string;
    reason: string;
    description?: string;
  }>;
  economic_data_status: string;
  billing_warning: boolean;
  explanation: string;
  refusal_code?: string;
}


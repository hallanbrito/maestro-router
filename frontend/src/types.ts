/**
 * Contratos técnicos da API pública v1 do Maestro Router (docs/05-API.md).
 * Tipos estritamente alinhados à especificação normativa do MVP.
 *
 * Preserva números decimais monetários e de uso como strings exatas,
 * evitando imprecisão de ponto flutuante e conversões cambiais silenciosas.
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
  /** Critérios de qualidade previamente aceitos na configuração. */
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
  /** Identificador neutro e único da rota. */
  id: string;
  /** Identificador neutro do provedor da rota. */
  provider: string;
  /** Identificador neutro do modelo associado. */
  model: string;
}

export interface StrategyInfo {
  /** Identificador da estratégia aplicada. */
  id: string;
  /** Indica se a estratégia chegou a ser efetivamente executada. */
  applied: boolean;
}

export interface AppliedConstraint {
  /** Origem da restrição: 'request' ou 'configuration'. */
  source: 'request' | 'configuration' | string;
  /** Categoria da restrição. */
  category: 'route' | 'capability' | 'quality' | 'availability' | 'preference' | 'economics' | string;
  /** Descrição factual da restrição aplicada. */
  description: string;
}

export interface DecisionFactor {
  /** Categoria do fator determinante. */
  category:
    | 'route'
    | 'capability'
    | 'quality'
    | 'availability'
    | 'preference'
    | 'economics'
    | 'configuration'
    | 'strategy'
    | 'tie_breaker'
    | string;
  /** Descrição factual que justifica a escolha ou recusa. */
  description: string;
  /** Referências auditáveis associadas ao fator. */
  references?: string[];
}

export interface Decision {
  /** Resultado do roteamento: selecionada ou recusada. */
  outcome: 'selected' | 'refused';
  /** Rota selecionada (presente exclusivamente quando outcome === 'selected'). */
  route?: SelectedRoute;
  /** Estratégia configurada. */
  strategy: StrategyInfo;
  /** Restrições efetivas determinantes para a decisão. */
  applied_constraints: AppliedConstraint[];
  /** Razão objetiva e sintetizada da decisão. */
  reason: string;
  /** Fatos determinantes sem raciocínio interno ou dados secretos. */
  factors: DecisionFactor[];
}

export type EconomicStatus = 'available' | 'uncertain' | 'unavailable';

export interface EconomicEstimate {
  /** Estado de disponibilidade da estimativa. */
  status: EconomicStatus;
  /** Valor monetário estimado pré-execução preservado como string decimal. */
  amount?: string;
  /** Moeda da estimativa (3 letras maiúsculas). */
  currency?: string;
  /** Identificador neutro da tabela de preços auditável. */
  price_reference?: string;
  /** Hipóteses declaradas na estimativa. */
  assumptions?: string[];
  /** Justificativa quando status for uncertain ou unavailable. */
  reason?: string;
}

export interface UsageItem {
  /** Unidade neutra de consumo (ex: "input_token", "output_token"). */
  unit: string;
  /** Quantidade consumida preservada como string decimal. */
  quantity: string;
}

export interface Usage {
  /** Estado de disponibilidade dos dados de uso. */
  status: EconomicStatus;
  /** Itens normalizados de consumo após resposta do provedor. */
  items?: UsageItem[];
  /** Justificativa quando uso for uncertain ou unavailable. */
  reason?: string;
}

export interface CalculatedCost {
  /** Estado de disponibilidade do custo apurado. */
  status: EconomicStatus;
  /** Valor monetário final calculado preservado como string decimal. */
  amount?: string;
  /** Moeda do cálculo (3 letras maiúsculas). */
  currency?: string;
  /** Referência de preços auditável utilizada no cálculo. */
  price_reference?: string;
  /** Hipóteses consideradas no cálculo. */
  assumptions?: string[];
  /** Justificativa quando custo calculado for uncertain ou unavailable. */
  reason?: string;
}

export interface ExecutionEconomics {
  /** Estimativa antes da execução. */
  estimate: EconomicEstimate;
  /** Uso registrado após o acionamento do provedor. */
  usage: Usage;
  /** Custo auditável calculado pós-execução. */
  calculated_cost: CalculatedCost;
}

export interface ExecutionSuccessResponse {
  /** Resultado textual normalizado. */
  result: ExecutionResult;
  /** Decisão formal de seleção do roteador. */
  decision: Decision;
  /** Dados econômicos completos. */
  economics: ExecutionEconomics;
}

export interface ErrorIssue {
  /** Caminho do membro JSON em formato JSON Pointer (ex: "/task"). */
  path?: string;
  /** Mensagem sanitizada sobre a inconsistência. */
  message: string;
}

export interface ApiErrorPayload {
  /** Código taxonômico estável do erro (docs/05-API.md seção 9.3). */
  code:
    | 'INVALID_REQUEST'
    | 'INVALID_CONFIGURATION'
    | 'NO_ELIGIBLE_ROUTE'
    | 'INSUFFICIENT_ECONOMIC_INFORMATION'
    | 'INVALID_DECISION'
    | 'EXECUTION_FAILED'
    | 'EXECUTION_UNAVAILABLE'
    | 'EXECUTION_TIMEOUT'
    | string;
  /** Resumo compreensível do erro. */
  message: string;
  /** Lista de inconsistências detalhadas quando aplicável. */
  issues?: ErrorIssue[];
}

export interface ExecutionErrorResponse {
  /** Detalhes do erro retornado pela API. */
  error: ApiErrorPayload;
  /** Decisão formal presente em recusas (422) e falhas de execução pós-seleção (502, 503, 504). */
  decision?: Decision;
  /** Informações econômicas presentes em erros após seleção válida. */
  economics?: ExecutionEconomics;
}

/** Representação discriminada das respostas da API do Maestro. */
export type ExecutionApiResponse =
  | { kind: 'success'; status: 200; data: ExecutionSuccessResponse }
  | { kind: 'refusal'; status: 422; error: ExecutionErrorResponse }
  | { kind: 'client_error'; status: 400 | 415 | number; error: ExecutionErrorResponse }
  | { kind: 'execution_error'; status: 502 | 503 | 504; error: ExecutionErrorResponse }
  | { kind: 'server_error'; status: 500 | number; error: ExecutionErrorResponse }
  | { kind: 'network_error'; status: 0; message: string; details?: string };

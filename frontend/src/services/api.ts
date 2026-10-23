/**
 * Cliente HTTP para a fronteira pública da API v1 do Maestro Router.
 *
 * Em conformidade estrita com docs/05-API.md:
 * - Comunica-se exclusivamente com POST /v1/executions (único endpoint público).
 * - Não inventa endpoints inexistentes de saúde, status, catálogo ou métricas.
 * - Não executa POST automático, polling ou repetições autônomas de execução.
 * - Preserva valores textuais e numéricos exatamente como informados:
 *   * trim() é utilizado exclusivamente para verificar a presença de texto não-branco.
 *   * task e context são transmitidos integralmente com quaisquer espaços significativos.
 *   * Identificadores de rota, capacidades e critérios preservam seus caracteres originais.
 *   * amount e currency em max_estimated_cost não sofrem conversão ou correção de caixa implícita.
 * - Mapeia com fidelidade os status HTTP literais do contrato (200, 400, 415, 422, 500, 502, 503, 504).
 * - Desvia anomalias ou respostas não-JSON para a categoria protocol_error.
 */

import {
  ExecutionApiResponse,
  ExecutionErrorResponse,
  ExecutionRequest,
  ExecutionSuccessResponse,
} from '../types';

/** Endpoint público versionado fixado pelo contrato v1. */
export const API_ENDPOINT = '/v1/executions';

/**
 * Constrói o corpo da solicitação preservando espaços significativos e a gramática do contrato.
 */
function buildExecutionBody(request: ExecutionRequest): Record<string, unknown> {
  const bodyPayload: Record<string, unknown> = {
    task: request.task,
  };

  if (request.context !== undefined && request.context.trim().length > 0) {
    bodyPayload.context = request.context;
  }

  if (request.constraints) {
    const constraintsPayload: Record<string, unknown> = {};

    if (
      request.constraints.required_capabilities &&
      request.constraints.required_capabilities.length > 0
    ) {
      constraintsPayload.required_capabilities =
        request.constraints.required_capabilities;
    }

    if (
      request.constraints.required_quality_criteria &&
      request.constraints.required_quality_criteria.length > 0
    ) {
      constraintsPayload.required_quality_criteria =
        request.constraints.required_quality_criteria;
    }

    if (
      request.constraints.allowed_route_ids &&
      request.constraints.allowed_route_ids.length > 0
    ) {
      constraintsPayload.allowed_route_ids =
        request.constraints.allowed_route_ids;
    }

    if (
      request.constraints.max_estimated_cost &&
      request.constraints.max_estimated_cost.amount !== undefined &&
      request.constraints.max_estimated_cost.currency !== undefined
    ) {
      constraintsPayload.max_estimated_cost = {
        amount: request.constraints.max_estimated_cost.amount,
        currency: request.constraints.max_estimated_cost.currency,
      };
    }

    if (Object.keys(constraintsPayload).length > 0) {
      bodyPayload.constraints = constraintsPayload;
    }
  }

  return bodyPayload;
}

/**
 * Mapeia as respostas HTTP conforme a taxonomia rigorosa de status e tipos da API pública v1.
 */
async function mapExecutionResponse(response: Response): Promise<ExecutionApiResponse> {
  let responseData: unknown = null;
  try {
    responseData = await response.json();
  } catch {
    return {
      kind: 'protocol_error',
      status: response.status,
      error: {
        code: 'INVALID_SERVER_RESPONSE',
        message: `O servidor retornou status HTTP ${response.status} com corpo incompatível com JSON.`,
      },
    };
  }

  // 200 OK: Execução concluída com resultado válido
  if (response.status === 200) {
    return {
      kind: 'success',
      status: 200,
      data: responseData as ExecutionSuccessResponse,
    };
  }

  const errorResponse = responseData as ExecutionErrorResponse;

  // 422 Unprocessable Content: Recusa do roteamento (NO_ELIGIBLE_ROUTE ou INSUFFICIENT_ECONOMIC_INFORMATION)
  if (response.status === 422) {
    return {
      kind: 'refusal',
      status: 422,
      error: errorResponse,
    };
  }

  // 400 Bad Request / 415 Unsupported Media Type: Erro de validação da solicitação
  if (response.status === 400 || response.status === 415) {
    return {
      kind: 'client_error',
      status: response.status,
      error: errorResponse,
    };
  }

  // 502 Bad Gateway / 503 Service Unavailable / 504 Gateway Timeout: Falha no acionamento do provedor pós-seleção
  if (
    response.status === 502 ||
    response.status === 503 ||
    response.status === 504
  ) {
    return {
      kind: 'execution_error',
      status: response.status,
      error: errorResponse,
    };
  }

  // 500 Internal Server Error (INVALID_CONFIGURATION ou INVALID_DECISION)
  if (response.status === 500) {
    return {
      kind: 'server_error',
      status: 500,
      error: errorResponse,
    };
  }

  // Qualquer outro status HTTP inesperado fora do contrato público v1
  return {
    kind: 'protocol_error',
    status: response.status,
    error: {
      code: 'UNEXPECTED_HTTP_STATUS',
      message: `O servidor retornou status HTTP inesperado: ${response.status}.`,
    },
  };
}

/**
 * Envia uma solicitação síncrona de execução à API pública v1 (docs/05-API.md).
 *
 * Comunica-se exclusivamente com POST /v1/executions sem interpretar cabeçalhos ou trilhas.
 */
export async function executeTask(
  request: ExecutionRequest
): Promise<ExecutionApiResponse> {
  const bodyPayload = buildExecutionBody(request);

  try {
    const response = await fetch(API_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(bodyPayload),
    });

    return await mapExecutionResponse(response);
  } catch (_err: unknown) {
    return {
      kind: 'network_error',
      status: 0,
      message:
        'Não foi possível estabelecer conexão com o Maestro Router em http://127.0.0.1:8000.',
      details:
        'Certifique-se de que o backend FastAPI esteja em execução. Exemplo: "python -m uvicorn --app-dir src maestro_router.control_center:app".',
    };
  }
}

/**
 * Envia uma solicitação de execução operacional governada pela trilha selecionada no Control Center.
 *
 * Aciona o endpoint administrativo local POST /admin/executions (ADR 0012) com autenticação CSRF.
 */
export async function executeAdminTask(
  request: ExecutionRequest,
  track: TrackType
): Promise<ExecutionApiResponse> {
  const bodyPayload = buildExecutionBody(request);
  const token = await getAdminCsrfToken();

  try {
    const response = await fetch('/admin/executions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Maestro-CSRF-Token': token,
      },
      body: JSON.stringify({
        ...bodyPayload,
        track,
      }),
    });

    return await mapExecutionResponse(response);
  } catch (_err: unknown) {
    return {
      kind: 'network_error',
      status: 0,
      message:
        'Não foi possível estabelecer conexão com o Maestro Router em http://127.0.0.1:8000.',
      details:
        'Certifique-se de que o backend FastAPI esteja em execução. Exemplo: "python -m uvicorn --app-dir src maestro_router.control_center:app".',
    };
  }
}

// ==============================================================================
// Serviços Administrativos Locais do Control Center (ADR 0012)
// ==============================================================================

import {
  ProviderInfo,
  RouteConfig,
  RoutingPreview,
  TrackType,
} from '../types';

let cachedCsrfToken: string | null = null;

export function resetAdminCsrfTokenForTesting(): void {
  cachedCsrfToken = null;
}

/**
 * Obtém ou reutiliza o token CSRF dinâmico gerado pelo backend administrativo em memória.
 */
export async function getAdminCsrfToken(): Promise<string> {
  if (cachedCsrfToken) {
    return cachedCsrfToken;
  }
  const res = await fetch('/admin/session', { method: 'GET' });
  if (!res.ok) {
    throw new Error(`Falha no handshake de sessão administrativa: HTTP ${res.status}`);
  }
  const data = await res.json();
  cachedCsrfToken = data.csrf_token;
  return data.csrf_token;
}

/**
 * Consulta o estado seguro da configuração operacional (provedores, credenciais e rotas).
 */
export async function fetchAdminConfig(): Promise<{
  providers: ProviderInfo[];
  routes: RouteConfig[];
  models: string[];
}> {
  const res = await fetch('/admin/config', { method: 'GET' });
  if (!res.ok) {
    throw new Error(`Falha ao consultar configuração administrativa: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Cadastra ou substitui uma chave de API na memória volátil do backend.
 */
export async function saveCredential(
  provider: string,
  apiKey: string
): Promise<{ provider: string; status: string; message: string }> {
  const token = await getAdminCsrfToken();
  const res = await fetch('/admin/credentials', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Maestro-CSRF-Token': token,
    },
    body: JSON.stringify({ provider, api_key: apiKey }),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(
      errorBody.detail?.message || `Erro ao salvar credencial: HTTP ${res.status}`
    );
  }
  return await res.json();
}

/**
 * Remove a credencial de um provedor da memória volátil do servidor.
 */
export async function removeCredential(
  provider: string
): Promise<{ provider: string; status: string; message: string }> {
  const token = await getAdminCsrfToken();
  const res = await fetch(`/admin/credentials?provider=${encodeURIComponent(provider)}`, {
    method: 'DELETE',
    headers: {
      'X-Maestro-CSRF-Token': token,
    },
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(
      errorBody.detail?.message || `Erro ao remover credencial: HTTP ${res.status}`
    );
  }
  return await res.json();
}

/**
 * Aciona a verificação explícita da credencial via listagem neutra de modelos (zero geração paga).
 */
export async function verifyCredential(
  provider: string
): Promise<{
  provider: string;
  status: string;
  models?: string[];
  message: string;
}> {
  const token = await getAdminCsrfToken();
  const res = await fetch('/admin/credentials/verify', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Maestro-CSRF-Token': token,
    },
    body: JSON.stringify({ provider }),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(
      errorBody.detail?.message || `Erro ao verificar credencial: HTTP ${res.status}`
    );
  }
  return await res.json();
}

/**
 * Consulta a lista de modelos suportados / verificados.
 */
export async function fetchModels(): Promise<{
  provider: string;
  models: string[];
  verified: boolean;
}> {
  const res = await fetch('/admin/models', { method: 'GET' });
  if (!res.ok) {
    throw new Error(`Falha ao obter lista de modelos: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Salva ou atualiza uma rota na configuração ativa em memória.
 */
export async function saveRoute(
  route: Partial<RouteConfig>
): Promise<{ status: string; route: RouteConfig }> {
  const token = await getAdminCsrfToken();
  const res = await fetch('/admin/routes', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Maestro-CSRF-Token': token,
    },
    body: JSON.stringify(route),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(
      errorBody.detail?.message || `Erro ao salvar rota: HTTP ${res.status}`
    );
  }
  return await res.json();
}

/**
 * Alterna habilitação (enable/disable) de uma rota.
 */
export async function toggleRoute(
  routeId: string
): Promise<{ route_id: string; enabled: boolean }> {
  const token = await getAdminCsrfToken();
  const res = await fetch(`/admin/routes/${encodeURIComponent(routeId)}/toggle`, {
    method: 'PATCH',
    headers: {
      'X-Maestro-CSRF-Token': token,
    },
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(
      errorBody.detail?.message || `Erro ao alternar rota: HTTP ${res.status}`
    );
  }
  return await res.json();
}

/**
 * Remove uma rota da configuração ativa.
 */
export async function deleteRoute(
  routeId: string
): Promise<{ status: string; route_id: string }> {
  const token = await getAdminCsrfToken();
  const res = await fetch(`/admin/routes/${encodeURIComponent(routeId)}`, {
    method: 'DELETE',
    headers: {
      'X-Maestro-CSRF-Token': token,
    },
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(
      errorBody.detail?.message || `Erro ao excluir rota: HTTP ${res.status}`
    );
  }
  return await res.json();
}

/**
 * Solicita uma sugestão e prévia explicável de roteamento com custo zero.
 */
export async function fetchRoutingPreview(params: {
  task: string;
  context?: string;
  track: TrackType;
  constraints?: Record<string, unknown>;
}): Promise<RoutingPreview> {
  const res = await fetch('/admin/preview', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(
      errorBody.detail?.message || `Erro ao obter sugestão: HTTP ${res.status}`
    );
  }
  return await res.json();
}


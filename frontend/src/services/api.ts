/**
 * Cliente HTTP para a fronteira pública da API v1 do Maestro Router.
 *
 * Em conformidade estrita com docs/05-API.md:
 * - Comunica-se exclusivamente com POST /v1/executions (único endpoint público).
 * - Não inventa endpoints inexistentes de saúde, status, catálogo ou métricas.
 * - Não executa POST automático, polling ou repetições autônomas de execução.
 * - Preserva valores numéricos decimais como strings para prevenir perda de precisão.
 * - Mapeia com fidelidade a taxonomia de erros: 400, 415, 422, 500, 502, 503 e 504.
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
 * Envia uma solicitação síncrona de execução ao Maestro Router.
 *
 * Esta função só é acionada por comando explícito do usuário (botão ou atalho),
 * nunca em segundo plano ou de forma recorrente.
 */
export async function executeTask(
  request: ExecutionRequest
): Promise<ExecutionApiResponse> {
  // Construção estrita do payload (sem campos nulos ou membros vazios indevidos)
  const bodyPayload: Record<string, unknown> = {
    task: request.task,
  };

  // O campo context só é enviado se contiver caracteres válidos
  if (request.context && request.context.trim().length > 0) {
    bodyPayload.context = request.context;
  }

  // Composição opcional de restrições respeitando a gramática fechada do contrato
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
      request.constraints.max_estimated_cost.amount &&
      request.constraints.max_estimated_cost.currency
    ) {
      constraintsPayload.max_estimated_cost = {
        amount: request.constraints.max_estimated_cost.amount,
        currency: request.constraints.max_estimated_cost.currency.toUpperCase(),
      };
    }

    if (Object.keys(constraintsPayload).length > 0) {
      bodyPayload.constraints = constraintsPayload;
    }
  }

  try {
    const response = await fetch(API_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(bodyPayload),
    });

    let responseData: unknown = null;
    try {
      responseData = await response.json();
    } catch {
      return {
        kind: 'server_error',
        status: response.status,
        error: {
          error: {
            code: 'INVALID_SERVER_RESPONSE',
            message: `O servidor retornou status HTTP ${response.status} com corpo incompatível com JSON.`,
          },
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
    return {
      kind: 'server_error',
      status: response.status,
      error: errorResponse,
    };
  } catch (_err: unknown) {
    // Falha de rede ou servidor FastAPI inacessível
    return {
      kind: 'network_error',
      status: 0,
      message:
        'Não foi possível estabelecer conexão com o Maestro Router em http://127.0.0.1:8000.',
      details:
        'Certifique-se de que o backend FastAPI esteja em execução. Exemplo: "python -m uvicorn --app-dir src maestro_router.api:app".',
    };
  }
}

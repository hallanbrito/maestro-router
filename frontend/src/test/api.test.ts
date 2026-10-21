import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { executeTask } from '../services/api';

describe('executeTask service', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends simple task correctly formatted with string decimals', async () => {
    const mockSuccessResponse = {
      result: { content: 'Resposta de teste normalizada.' },
      decision: {
        outcome: 'selected',
        route: { id: 'route-test', provider: 'test', model: 'm1' },
        strategy: { id: 'lowest-estimated-cost', applied: true },
        applied_constraints: [],
        reason: 'Menor custo.',
        factors: [{ category: 'economics', description: 'Custo mais baixo.' }],
      },
      economics: {
        estimate: { status: 'available', amount: '0.001000', currency: 'USD' },
        usage: { status: 'available', items: [{ unit: 'input_token', quantity: '10' }] },
        calculated_cost: { status: 'available', amount: '0.000100', currency: 'USD' },
      },
    };

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 200,
      json: async () => mockSuccessResponse,
    } as unknown as Response);

    const result = await executeTask({ task: 'Diga olá' });

    expect(fetchSpy).toHaveBeenCalledWith('/v1/executions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task: 'Diga olá' }),
    });

    expect(result.kind).toBe('success');
    if (result.kind === 'success') {
      expect(result.data.result.content).toBe('Resposta de teste normalizada.');
      expect(result.data.decision.route?.id).toBe('route-test');
      expect(result.data.economics.estimate.amount).toBe('0.001000');
    }
  });

  it('omits context when empty and formats constraints strictly without floating numbers', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 200,
      json: async () => ({}),
    } as unknown as Response);

    await executeTask({
      task: 'Analise os dados',
      context: '   ', // whitespace only -> must be omitted
      constraints: {
        required_capabilities: ['text_generation'],
        max_estimated_cost: {
          amount: '0.0200',
          currency: 'usd',
        },
      },
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const callBody = JSON.parse(fetchSpy.mock.calls[0][1]?.body as string);
    expect(callBody.task).toBe('Analise os dados');
    expect(callBody.context).toBeUndefined();
    expect(callBody.constraints).toEqual({
      required_capabilities: ['text_generation'],
      max_estimated_cost: {
        amount: '0.0200',
        currency: 'USD',
      },
    });
  });

  it('handles 422 refusal (NO_ELIGIBLE_ROUTE)', async () => {
    const mockRefusalResponse = {
      error: {
        code: 'NO_ELIGIBLE_ROUTE',
        message: 'Nenhuma rota configurada é elegível para a solicitação.',
      },
      decision: {
        outcome: 'refused',
        strategy: { id: 'lowest-estimated-cost', applied: false },
        applied_constraints: [],
        reason: 'Nenhuma rota habilitada satisfaz as restrições aplicáveis.',
        factors: [{ category: 'route', description: 'Catálogo de rotas está vazio.' }],
      },
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 422,
      json: async () => mockRefusalResponse,
    } as unknown as Response);

    const result = await executeTask({ task: 'Qualquer tarefa' });

    expect(result.kind).toBe('refusal');
    if (result.kind === 'refusal') {
      expect(result.status).toBe(422);
      expect(result.error.error.code).toBe('NO_ELIGIBLE_ROUTE');
      expect(result.error.decision?.outcome).toBe('refused');
    }
  });

  it('handles 400 client validation error (INVALID_REQUEST)', async () => {
    const mockClientError = {
      error: {
        code: 'INVALID_REQUEST',
        message: 'A solicitação é inválida.',
        issues: [{ path: '/task', message: 'O campo deve ser uma string com ao menos um caractere não branco.' }],
      },
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 400,
      json: async () => mockClientError,
    } as unknown as Response);

    const result = await executeTask({ task: '' });

    expect(result.kind).toBe('client_error');
    if (result.kind === 'client_error') {
      expect(result.status).toBe(400);
      expect(result.error.error.code).toBe('INVALID_REQUEST');
      expect(result.error.error.issues).toHaveLength(1);
    }
  });

  it('handles 502/503/504 execution errors with decision and economics', async () => {
    const mockExecError = {
      error: {
        code: 'EXECUTION_UNAVAILABLE',
        message: 'A rota selecionada está temporariamente indisponível.',
      },
      decision: {
        outcome: 'selected',
        route: { id: 'route-test', provider: 'test', model: 'm1' },
        strategy: { id: 'lowest-estimated-cost', applied: true },
        applied_constraints: [],
        reason: 'Rota selecionada.',
        factors: [],
      },
      economics: {
        estimate: { status: 'available', amount: '0.0050', currency: 'USD' },
        usage: { status: 'unavailable', reason: 'Falha antes do retorno de métricas.' },
        calculated_cost: { status: 'unavailable', reason: 'Uso indisponível.' },
      },
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 503,
      json: async () => mockExecError,
    } as unknown as Response);

    const result = await executeTask({ task: 'Tarefa com falha de provedor' });

    expect(result.kind).toBe('execution_error');
    if (result.kind === 'execution_error') {
      expect(result.status).toBe(503);
      expect(result.error.error.code).toBe('EXECUTION_UNAVAILABLE');
      expect(result.error.decision?.outcome).toBe('selected');
      expect(result.error.economics?.estimate.status).toBe('available');
    }
  });

  it('handles network failure gracefully without raising uncaught exception', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Failed to fetch'));

    const result = await executeTask({ task: 'Tarefa teste' });

    expect(result.kind).toBe('network_error');
    if (result.kind === 'network_error') {
      expect(result.status).toBe(0);
      expect(result.message).toContain('Não foi possível estabelecer conexão com o Maestro Router');
      expect(result.details).toContain('python -m uvicorn');
    }
  });
});

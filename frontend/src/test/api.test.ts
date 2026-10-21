import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { executeTask } from '../services/api';
import {
  ExecutionSuccessResponse,
  SelectedDecision,
  RefusedDecision,
  AvailableEconomicEstimate,
  AvailableUsage,
  AvailableCalculatedCost,
  UnavailableEconomicEstimate,
  UnavailableUsage,
  UnavailableCalculatedCost,
} from '../types';

describe('executeTask service', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('preserva task e context com espaços significativos sem trim truncador', async () => {
    const rawTask = '   Tarefa com múltiplos   espaços no início e fim   ';
    const rawContext = '   Contexto com \n quebras e espaços preservados   ';

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 200,
      json: async () => ({}),
    } as unknown as Response);

    await executeTask({
      task: rawTask,
      context: rawContext,
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const callBody = JSON.parse(fetchSpy.mock.calls[0][1]?.body as string);
    // Preservação estrita dos caracteres originais (Point 1)
    expect(callBody.task).toBe(rawTask);
    expect(callBody.context).toBe(rawContext);
  });

  it('omite context somente quando for ausente ou contiver unicamente espaços em branco', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 200,
      json: async () => ({}),
    } as unknown as Response);

    await executeTask({
      task: 'Tarefa válida',
      context: '   \n  \t  ',
    });

    const callBody = JSON.parse(fetchSpy.mock.calls[0][1]?.body as string);
    expect(callBody.task).toBe('Tarefa válida');
    expect(callBody.context).toBeUndefined();
  });

  it('preserva identificadores de rota, capacidades, critérios e moeda sem alterações ou trim silencioso', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 200,
      json: async () => ({}),
    } as unknown as Response);

    await executeTask({
      task: 'Gere código de teste',
      constraints: {
        required_capabilities: [' text_generation ', 'summarization'],
        required_quality_criteria: ['summary_faithfulness_accepted'],
        allowed_route_ids: [' route-with-space '],
        max_estimated_cost: {
          amount: '0.0200',
          currency: 'usd', // Não deve ser corrigido para maiúsculo silenciosamente
        },
      },
    });

    const callBody = JSON.parse(fetchSpy.mock.calls[0][1]?.body as string);
    expect(callBody.constraints.required_capabilities).toEqual([
      ' text_generation ',
      'summarization',
    ]);
    expect(callBody.constraints.required_quality_criteria).toEqual([
      'summary_faithfulness_accepted',
    ]);
    expect(callBody.constraints.allowed_route_ids).toEqual([
      ' route-with-space ',
    ]);
    expect(callBody.constraints.max_estimated_cost).toEqual({
      amount: '0.0200',
      currency: 'usd',
    });
  });

  it('processa resposta de sucesso 200 OK com fixtures obedecendo aos contratos estritos', async () => {
    const decision: SelectedDecision = {
      outcome: 'selected',
      route: { id: 'route-text-a', provider: 'openai', model: 'gpt-4o' },
      strategy: { id: 'lowest-estimated-cost', applied: true },
      applied_constraints: [
        {
          source: 'request',
          category: 'capability',
          description: 'Requer text_generation.',
        },
      ],
      reason: 'Rota selecionada por menor custo estimado.',
      factors: [
        {
          category: 'economics',
          description: 'Estimativa prévia de 0.001000 USD.',
          references: ['pricing-text-a-2026-08'],
        },
      ],
    };

    const estimate: AvailableEconomicEstimate = {
      status: 'available',
      amount: '0.001000',
      currency: 'USD',
      price_reference: 'pricing-text-a-2026-08',
      assumptions: ['Volume de saída estimado com base na média histórica.'],
    };

    const usage: AvailableUsage = {
      status: 'available',
      items: [
        { unit: 'input_token', quantity: '120' },
        { unit: 'output_token', quantity: '45' },
      ],
    };

    const cost: AvailableCalculatedCost = {
      status: 'available',
      amount: '0.000350',
      currency: 'USD',
      price_reference: 'pricing-text-a-2026-08',
      assumptions: [],
    };

    const mockResponse: ExecutionSuccessResponse = {
      result: { content: 'Resultado normalizado da execução.' },
      decision,
      economics: {
        estimate,
        usage,
        calculated_cost: cost,
      },
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 200,
      json: async () => mockResponse,
    } as unknown as Response);

    const result = await executeTask({ task: 'Execute a tarefa' });

    expect(result.kind).toBe('success');
    if (result.kind === 'success') {
      expect(result.data.result.content).toBe('Resultado normalizado da execução.');
      expect(result.data.decision.outcome).toBe('selected');
      expect(result.data.decision.strategy.applied).toBe(true);
      expect(result.data.economics.estimate.status).toBe('available');
      expect(result.data.economics.estimate.amount).toBe('0.001000');
    }
  });

  it('mapeia erro de mídia HTTP 415 (INVALID_REQUEST)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 415,
      json: async () => ({
        error: {
          code: 'INVALID_REQUEST',
          message: 'O Content-Type deve ser application/json com charset UTF-8.',
          issues: [{ message: 'Media type não suportado.' }],
        },
      }),
    } as unknown as Response);

    const result = await executeTask({ task: 'Tarefa com mídia inválida' });

    expect(result.kind).toBe('client_error');
    if (result.kind === 'client_error') {
      expect(result.status).toBe(415);
      expect(result.error.error.code).toBe('INVALID_REQUEST');
    }
  });

  it('mapeia erro de cliente HTTP 400 (INVALID_REQUEST com issues)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 400,
      json: async () => ({
        error: {
          code: 'INVALID_REQUEST',
          message: 'A solicitação é inválida.',
          issues: [
            {
              path: '/constraints/max_estimated_cost/currency',
              message: 'Moeda deve seguir ^[A-Z]{3}$.',
            },
          ],
        },
      }),
    } as unknown as Response);

    const result = await executeTask({ task: 'Tarefa com moeda inválida' });

    expect(result.kind).toBe('client_error');
    if (result.kind === 'client_error') {
      expect(result.status).toBe(400);
      expect(result.error.error.issues?.[0].path).toBe(
        '/constraints/max_estimated_cost/currency'
      );
    }
  });

  it('mapeia ambos os códigos HTTP 422: NO_ELIGIBLE_ROUTE e INSUFFICIENT_ECONOMIC_INFORMATION', async () => {
    const refusedDecision: RefusedDecision = {
      outcome: 'refused',
      strategy: { id: 'lowest-estimated-cost', applied: false },
      applied_constraints: [],
      reason: 'Todas as rotas foram excluídas antes da comparação econômica.',
      factors: [
        {
          category: 'route',
          description: 'O catálogo não continha rotas configuradas.',
        },
      ],
    };

    // 1. Teste de NO_ELIGIBLE_ROUTE
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 422,
      json: async () => ({
        error: {
          code: 'NO_ELIGIBLE_ROUTE',
          message: 'Nenhuma rota configurada é elegível.',
        },
        decision: refusedDecision,
      }),
    } as unknown as Response);

    const res1 = await executeTask({ task: 'Sem rotas' });
    expect(res1.kind).toBe('refusal');
    if (res1.kind === 'refusal') {
      expect(res1.error.error.code).toBe('NO_ELIGIBLE_ROUTE');
      expect(res1.error.decision?.outcome).toBe('refused');
      expect(res1.error.decision?.strategy.applied).toBe(false);
    }

    // 2. Teste de INSUFFICIENT_ECONOMIC_INFORMATION
    const insufficientDecision: RefusedDecision = {
      outcome: 'refused',
      strategy: { id: 'lowest-estimated-cost', applied: false },
      applied_constraints: [],
      reason: 'Nenhuma alternativa pôde ser avaliada economicamente.',
      factors: [
        {
          category: 'economics',
          description: 'Preço indispensável não disponível para comparação.',
        },
      ],
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 422,
      json: async () => ({
        error: {
          code: 'INSUFFICIENT_ECONOMIC_INFORMATION',
          message: 'Informação econômica insuficiente.',
        },
        decision: insufficientDecision,
      }),
    } as unknown as Response);

    const res2 = await executeTask({ task: 'Sem preço' });
    expect(res2.kind).toBe('refusal');
    if (res2.kind === 'refusal') {
      expect(res2.error.error.code).toBe('INSUFFICIENT_ECONOMIC_INFORMATION');
    }
  });

  it('mapeia erro de servidor HTTP 500 (INVALID_CONFIGURATION)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      status: 500,
      json: async () => ({
        error: {
          code: 'INVALID_CONFIGURATION',
          message: 'Configuração global indispensável inválida.',
          issues: [{ message: 'Arquivo de configuração corrompido.' }],
        },
      }),
    } as unknown as Response);

    const result = await executeTask({ task: 'Execução com falha de config' });

    expect(result.kind).toBe('server_error');
    if (result.kind === 'server_error') {
      expect(result.status).toBe(500);
      expect(result.error.error.code).toBe('INVALID_CONFIGURATION');
    }
  });

  describe('erros de execução pós-seleção parametrizados (502, 503, 504)', () => {
    const errorCodes = [
      { status: 502, code: 'EXECUTION_FAILED' },
      { status: 503, code: 'EXECUTION_UNAVAILABLE' },
      { status: 504, code: 'EXECUTION_TIMEOUT' },
    ] as const;

    errorCodes.forEach(({ status, code }) => {
      it(`mapeia status HTTP ${status} com código ${code} preservando decisão e economia`, async () => {
        const decision: SelectedDecision = {
          outcome: 'selected',
          route: { id: 'route-timeout', provider: 'openai', model: 'gpt-4o' },
          strategy: { id: 'lowest-estimated-cost', applied: true },
          applied_constraints: [],
          reason: 'Rota selecionada antes da tentativa externa.',
          factors: [],
        };

        const unavailableEstimate: UnavailableEconomicEstimate = {
          status: 'unavailable',
          reason: 'Estimativa indisponível.',
        };

        const unavailableUsage: UnavailableUsage = {
          status: 'unavailable',
          reason: 'Uso não registrado devido à falha de execução.',
        };

        const unavailableCost: UnavailableCalculatedCost = {
          status: 'unavailable',
          reason: 'Custo indisponível.',
        };

        vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
          status,
          json: async () => ({
            error: {
              code,
              message: `Falha na integração: status ${status}.`,
            },
            decision,
            economics: {
              estimate: unavailableEstimate,
              usage: unavailableUsage,
              calculated_cost: unavailableCost,
            },
          }),
        } as unknown as Response);

        const result = await executeTask({ task: `Testando erro ${status}` });

        expect(result.kind).toBe('execution_error');
        if (result.kind === 'execution_error') {
          expect(result.status).toBe(status);
          expect(result.error.error.code).toBe(code);
          expect(result.error.decision?.outcome).toBe('selected');
          expect(result.error.economics?.usage.status).toBe('unavailable');
          expect(result.error.economics?.usage.reason).toBe(
            'Uso não registrado devido à falha de execução.'
          );
        }
      });
    });
  });

  it('trata falha de rede sem propagar exceção não capturada', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(
      new Error('Failed to fetch')
    );

    const result = await executeTask({ task: 'Tarefa com falha de conexão' });

    expect(result.kind).toBe('network_error');
    if (result.kind === 'network_error') {
      expect(result.status).toBe(0);
      expect(result.message).toContain(
        'Não foi possível estabelecer conexão com o Maestro Router'
      );
      expect(result.details).toContain('python -m uvicorn');
    }
  });
});

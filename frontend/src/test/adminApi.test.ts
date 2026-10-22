import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  getAdminCsrfToken,
  resetAdminCsrfTokenForTesting,
  fetchAdminConfig,
  saveCredential,
  removeCredential,
  verifyCredential,
  fetchModels,
  saveRoute,
  toggleRoute,
  deleteRoute,
  fetchRoutingPreview,
} from '../services/api';

describe('Admin API client methods', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    resetAdminCsrfTokenForTesting();
  });

  it('realiza handshake e obtém token CSRF', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ csrf_token: 'csrf-token-12345' }),
    } as Response);

    const token = await getAdminCsrfToken();
    expect(token).toBe('csrf-token-12345');
  });

  it('salva credencial enviando cabeçalho X-Maestro-CSRF-Token', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ csrf_token: 'csrf-active-token' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          provider: 'openai',
          status: 'registered',
          message: 'Cadastrada',
        }),
      } as Response);

    const res = await saveCredential('openai', 'sk-my-secret-key');
    expect(res.status).toBe('registered');

    expect(fetchSpy).toHaveBeenLastCalledWith(
      '/admin/credentials',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-Maestro-CSRF-Token': 'csrf-active-token',
        }),
        body: JSON.stringify({ provider: 'openai', api_key: 'sk-my-secret-key' }),
      })
    );
  });

  it('solicita verificação neutra de credenciais', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ csrf_token: 'csrf-active-token' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          provider: 'openai',
          status: 'verified',
          models: ['gpt-4o'],
          message: 'Verificada com sucesso',
        }),
      } as Response);

    const res = await verifyCredential('openai');
    expect(res.status).toBe('verified');
    expect(res.models).toContain('gpt-4o');
  });

  it('executa preview de roteamento via POST /admin/preview', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        track: 'economica',
        policy_description: 'Menor custo',
        recommended_route: {
          route_id: 'route-test',
          provider: 'openai',
          model: 'gpt-4o-mini',
          estimate: { amount: '0.000100', currency: 'USD', status: 'available' },
          price_reference: null,
          justification: 'Menor custo estimado',
        },
        candidate_evaluations: [],
        factors: [],
        exclusions: [],
        economic_data_status: 'OK',
        billing_warning: false,
        explanation: 'Recomendação gerada com sucesso.',
      }),
    } as Response);

    const preview = await fetchRoutingPreview({
      task: 'Resuma o texto',
      track: 'economica',
    });

    expect(preview.recommended_route?.route_id).toBe('route-test');
    expect(preview.track).toBe('economica');
  });

  it('gerencia rotas e credenciais complementares', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ providers: [], routes: [], models: [] }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ csrf_token: 'tok' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ provider: 'openai', status: 'not_registered', message: 'ok' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ provider: 'openai', models: ['m1'], verified: true }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ status: 'success', route: { route_id: 'r1' } }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ route_id: 'r1', enabled: false }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ status: 'deleted', route_id: 'r1' }),
      } as Response);

    const cfg = await fetchAdminConfig();
    expect(cfg.providers).toEqual([]);

    const delCred = await removeCredential('openai');
    expect(delCred.status).toBe('not_registered');

    const modelsRes = await fetchModels();
    expect(modelsRes.models).toContain('m1');

    const routeRes = await saveRoute({ route_id: 'r1' });
    expect(routeRes.status).toBe('success');

    const toggleRes = await toggleRoute('r1');
    expect(toggleRes.enabled).toBe(false);

    const delRouteRes = await deleteRoute('r1');
    expect(delRouteRes.status).toBe('deleted');
  });
});

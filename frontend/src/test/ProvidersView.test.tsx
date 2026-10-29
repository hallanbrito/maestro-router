import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ProvidersView } from '../components/ProvidersView';
import * as apiService from '../services/api';

describe('ProvidersView component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('exibe estado seguro da credencial e aviso de provedores implementados', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValueOnce({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22T15:00:00Z',
            message: 'Credencial verificada com sucesso.',
          },
        },
      ],
      routes: [
        {
          route_id: 'route-openai-gpt4o-mini',
          provider: 'openai',
          model: 'gpt-4o-mini',
          enabled: true,
          known_unavailable: false,
          capabilities: ['text_generation'],
          quality_criteria: ['summary_faithfulness_accepted'],
          status: 'ready',
          blockers: [],
        },
      ],
      models: ['gpt-4o', 'gpt-4o-mini'],
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByText(/Provedores Integrados no MVP: OpenAI/i)).toBeInTheDocument();
      expect(screen.getByText(/Credencial Verificada/i)).toBeInTheDocument();
      expect(screen.getByText('route-openai-gpt4o-mini')).toBeInTheDocument();
      expect(screen.getAllByText('gpt-4o-mini').length).toBeGreaterThan(0);
    });
  });

  it('salva a credencial em memória e limpa o campo de senha imediatamente', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: false,
            status: 'not_registered',
            verified_at: null,
            message: null,
          },
        },
      ],
      routes: [],
      models: [],
    });

    const saveSpy = vi.spyOn(apiService, 'saveCredential').mockResolvedValueOnce({
      provider: 'openai',
      status: 'registered',
      message: 'Credencial cadastrada na memória do servidor.',
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByText('Não Cadastrada')).toBeInTheDocument();
    });

    const input = screen.getByLabelText(/OpenAI API Key/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'sk-test-secret-key-123' } });
    expect(input.value).toBe('sk-test-secret-key-123');

    const saveBtn = screen.getByRole('button', { name: /Salvar Chave/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(saveSpy).toHaveBeenCalledWith('openai', 'sk-test-secret-key-123');
      // Campo deve ser limpo imediatamente após envio
      expect(input.value).toBe('');
      expect(
        screen.getByText(/Credencial cadastrada na memória do servidor/i)
      ).toBeInTheDocument();
    });
  });

  it('aciona a verificação neutra de credencial sem gerar texto pago', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'registered',
            verified_at: null,
            message: null,
          },
        },
      ],
      routes: [],
      models: [],
    });

    const verifySpy = vi.spyOn(apiService, 'verifyCredential').mockResolvedValueOnce({
      provider: 'openai',
      status: 'verified',
      models: ['gpt-4o', 'gpt-4o-mini'],
      message: 'Credencial verificada com sucesso.',
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Verificar Credencial/i })
      ).toBeInTheDocument();
    });

    const verifyBtn = screen.getByRole('button', { name: /Verificar Credencial/i });
    fireEvent.click(verifyBtn);

    await waitFor(() => {
      expect(verifySpy).toHaveBeenCalledWith('openai');
      expect(screen.getByText('Credencial verificada com sucesso.')).toBeInTheDocument();
    });
  });

  it('alterna o estado da rota ao clicar no botão de habilitação', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22',
            message: null,
          },
        },
      ],
      routes: [
        {
          route_id: 'route-test-toggle',
          provider: 'openai',
          model: 'gpt-4o',
          enabled: true,
          known_unavailable: false,
          capabilities: [],
          quality_criteria: [],
          status: 'ready',
          blockers: [],
        },
      ],
      models: ['gpt-4o'],
    });

    const toggleSpy = vi.spyOn(apiService, 'toggleRoute').mockResolvedValueOnce({
      route_id: 'route-test-toggle',
      enabled: false,
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByText('route-test-toggle')).toBeInTheDocument();
    });

    const toggleBtn = screen.getByRole('button', { name: /Desabilitar/i });
    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(toggleSpy).toHaveBeenCalledWith('route-test-toggle');
    });
  });

  it('exibe aviso no modal informando que novas rotas não possuem dados econômicos preenchidos automaticamente', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22',
            message: null,
          },
        },
      ],
      routes: [],
      models: ['gpt-4o-mini'],
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nova Rota/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Nova Rota/i }));

    expect(
      screen.getByText(/Novas rotas cadastradas \(incluindo gpt-4o-mini\) não possuem tarifas nem previsão de tokens pré-preenchidas automaticamente/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Dados econômicos ausentes permanecem explicitamente indisponíveis até que sejam configurados pelo operador\./i)
    ).toBeInTheDocument();
  });

  it('permite editar uma rota existente, configurar tarifas econômicas e salvar no backend', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22',
            message: null,
          },
        },
      ],
      routes: [
        {
          route_id: 'route-openai-test',
          provider: 'openai',
          model: 'gpt-4o-mini',
          enabled: true,
          known_unavailable: false,
          capabilities: ['text_generation'],
          quality_criteria: [],
          status: 'ready',
          blockers: [],
        },
      ],
      models: ['gpt-4o-mini'],
    });

    const saveSpy = vi.spyOn(apiService, 'saveRoute').mockResolvedValueOnce({
      status: 'saved',
      route: {
        route_id: 'route-openai-test',
        provider: 'openai',
        model: 'gpt-4o-mini',
        enabled: true,
        known_unavailable: false,
        capabilities: ['text_generation'],
        quality_criteria: [],
        status: 'ready',
        blockers: [],
      },
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByTestId('edit-route-route-openai-test')).toBeInTheDocument();
    });

    // Clica no botão Editar da rota
    fireEvent.click(screen.getByTestId('edit-route-route-openai-test'));

    expect(screen.getByText(/Editar Rota: route-openai-test/i)).toBeInTheDocument();

    // Habilita a configuração econômica
    const toggleEconomics = screen.getByTestId('toggle-economics-config');
    fireEvent.click(toggleEconomics);

    // Preenche tarifas e estimativas de uso
    const inputRate = screen.getByTestId('route-input-rate');
    const outputRate = screen.getByTestId('route-output-rate');
    const estInput = screen.getByTestId('route-estimated-input');
    const estOutput = screen.getByTestId('route-estimated-output');
    const priceSource = screen.getByTestId('route-price-source');

    fireEvent.change(inputRate, { target: { value: '0.1500' } });
    fireEvent.change(outputRate, { target: { value: '0.6000' } });
    fireEvent.change(estInput, { target: { value: '2000' } });
    fireEvent.change(estOutput, { target: { value: '800' } });
    fireEvent.change(priceSource, { target: { value: 'https://openai.com/api/pricing' } });

    // Confirma conscientemente as declarações do operador (B1 / ADR 0006 e ADR 0007)
    fireEvent.click(screen.getByTestId('decl-rates-complete'));
    fireEvent.click(screen.getByTestId('decl-model-exact'));
    fireEvent.click(screen.getByTestId('decl-usage-applicable'));

    // Salva o formulário
    const saveBtn = screen.getByRole('button', { name: /Salvar Alterações/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(saveSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          route_id: 'route-openai-test',
          provider: 'openai',
          model: 'gpt-4o-mini',
          price_reference: expect.objectContaining({
            currency: 'USD',
            rates: [
              { unit: 'input_token', rate: '0.1500', base: 1000000 },
              { unit: 'output_token', rate: '0.6000', base: 1000000 },
            ],
          }),
          estimated_usage: {
            input_token: 2000,
            output_token: 800,
            applicability_confirmed: true,
          },
        })
      );
    });
  });

  it('permite definir tarifas zero via atalho no modal para qualificar na trilha Free', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22',
            message: null,
          },
        },
      ],
      routes: [],
      models: ['gpt-4o-mini'],
    });

    const saveSpy = vi.spyOn(apiService, 'saveRoute').mockResolvedValueOnce({
      status: 'saved',
      route: {
        route_id: 'route-free-test',
        provider: 'openai',
        model: 'gpt-4o-mini',
        enabled: true,
        known_unavailable: false,
        capabilities: ['text_generation'],
        quality_criteria: [],
        status: 'ready',
        blockers: [],
      },
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nova Rota/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Nova Rota/i }));

    // Habilita seção econômica
    const toggleEconomics = screen.getByTestId('toggle-economics-config');
    fireEvent.click(toggleEconomics);

    // Clica no atalho de tarifas zero
    const zeroRatesBtn = screen.getByTestId('btn-set-zero-rates');
    fireEvent.click(zeroRatesBtn);

    const inputRate = screen.getByTestId('route-input-rate') as HTMLInputElement;
    const outputRate = screen.getByTestId('route-output-rate') as HTMLInputElement;

    expect(inputRate.value).toBe('0.00');
    expect(outputRate.value).toBe('0.00');

    // Confirma que o atalho NÃO preenche fonte nem marca declarações automaticamente (R1)
    expect((screen.getByTestId('route-price-source') as HTMLInputElement).value).toBe('');
    expect((screen.getByTestId('decl-rates-complete') as HTMLInputElement).checked).toBe(false);
    expect((screen.getByTestId('decl-model-exact') as HTMLInputElement).checked).toBe(false);
    expect((screen.getByTestId('decl-usage-applicable') as HTMLInputElement).checked).toBe(false);

    // Operador preenche conscientemente a fonte, estimativas e confirma as declarações
    fireEvent.change(screen.getByTestId('route-price-source'), {
      target: { value: 'https://openai.com/api/pricing-free-tier' },
    });
    fireEvent.change(screen.getByTestId('route-estimated-input'), {
      target: { value: '1000' },
    });
    fireEvent.change(screen.getByTestId('route-estimated-output'), {
      target: { value: '500' },
    });
    fireEvent.click(screen.getByTestId('decl-rates-complete'));
    fireEvent.click(screen.getByTestId('decl-model-exact'));
    fireEvent.click(screen.getByTestId('decl-usage-applicable'));

    // Submete a rota com tarifas zero
    const saveBtn = screen.getByRole('button', { name: /Salvar Rota/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(saveSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          price_reference: expect.objectContaining({
            rates: [
              { unit: 'input_token', rate: '0.00', base: 1000000 },
              { unit: 'output_token', rate: '0.00', base: 1000000 },
            ],
            source: 'https://openai.com/api/pricing-free-tier',
            context_complete: true,
            model_identity_exact: true,
          }),
          estimated_usage: {
            input_token: 1000,
            output_token: 500,
            applicability_confirmed: true,
          },
        })
      );
    });
  });

  it('atalho de tarifas zero não contorna as declarações obrigatórias nem permite salvar sem fonte e confirmações (R1)', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22',
            message: null,
          },
        },
      ],
      routes: [],
      models: ['gpt-4o-mini'],
    });

    const saveSpy = vi.spyOn(apiService, 'saveRoute');

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nova Rota/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Nova Rota/i }));

    const toggleEconomics = screen.getByTestId('toggle-economics-config');
    fireEvent.click(toggleEconomics);

    const zeroRatesBtn = screen.getByTestId('btn-set-zero-rates');
    fireEvent.click(zeroRatesBtn);

    // Tenta salvar imediatamente sem preencher estimativas, fonte nem declarações
    const saveBtn = screen.getByRole('button', { name: /Salvar Rota/i });
    fireEvent.click(saveBtn);

    expect(
      screen.getByText(/Previsão de tokens de entrada e saída deve conter números inteiros positivos/i)
    ).toBeInTheDocument();
    expect(saveSpy).not.toHaveBeenCalled();
  });

  it('ao trocar o modelo de uma rota, desmarca a confirmação de identidade exata do modelo anterior (R1)', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22',
            message: null,
          },
        },
      ],
      routes: [
        {
          route_id: 'route-model-change-test',
          provider: 'openai',
          model: 'gpt-4o-mini',
          enabled: true,
          known_unavailable: false,
          capabilities: ['text_generation'],
          quality_criteria: [],
          price_reference: {
            id: 'pricing-1',
            currency: 'USD',
            version: '2026-10',
            source: 'https://openai.com/api/pricing',
            rates: [{ unit: 'input_token', rate: '0.1500', base: 1000000 }],
            context_complete: true,
            model_identity_exact: true,
          },
          estimated_usage: {
            input_token: 1000,
            output_token: 500,
            applicability_confirmed: true,
          },
          status: 'ready',
          blockers: [],
        },
      ],
      models: ['gpt-4o-mini', 'gpt-4o'],
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByTestId('edit-route-route-model-change-test')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('edit-route-route-model-change-test'));

    const checkboxModelExact = screen.getByTestId('decl-model-exact') as HTMLInputElement;
    expect(checkboxModelExact.checked).toBe(true);

    // Troca o modelo no select
    const selectModel = screen.getByTestId('route-model-select');
    fireEvent.change(selectModel, { target: { value: 'gpt-4o' } });

    // A confirmação de identidade exata do modelo DEVE ser desmarcada automaticamente (R1)
    expect(checkboxModelExact.checked).toBe(false);
  });

  it('rejeita tarifas inválidas com mensagem de erro no modal sem enviar para o backend', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22',
            message: null,
          },
        },
      ],
      routes: [],
      models: ['gpt-4o-mini'],
    });

    const saveSpy = vi.spyOn(apiService, 'saveRoute');

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nova Rota/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Nova Rota/i }));

    const toggleEconomics = screen.getByTestId('toggle-economics-config');
    fireEvent.click(toggleEconomics);

    const inputRate = screen.getByTestId('route-input-rate');
    fireEvent.change(inputRate, { target: { value: 'abc' } });

    const saveBtn = screen.getByRole('button', { name: /Salvar Rota/i });
    fireEvent.click(saveBtn);

    expect(
      screen.getByText(/Tarifas de entrada e saída devem ser valores numéricos decimais não negativos/i)
    ).toBeInTheDocument();
    expect(saveSpy).not.toHaveBeenCalled();
  });

  it('exige preenchimento de fonte e declarações conscientes do operador para salvar dados econômicos', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22',
            message: null,
          },
        },
      ],
      routes: [],
      models: ['gpt-4o-mini'],
    });

    const saveSpy = vi.spyOn(apiService, 'saveRoute');

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nova Rota/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Nova Rota/i }));

    const toggleEconomics = screen.getByTestId('toggle-economics-config');
    fireEvent.click(toggleEconomics);

    const inputRate = screen.getByTestId('route-input-rate');
    const outputRate = screen.getByTestId('route-output-rate');
    const estInput = screen.getByTestId('route-estimated-input');
    const estOutput = screen.getByTestId('route-estimated-output');

    fireEvent.change(inputRate, { target: { value: '0.1500' } });
    fireEvent.change(outputRate, { target: { value: '0.6000' } });
    fireEvent.change(estInput, { target: { value: '1500' } });
    fireEvent.change(estOutput, { target: { value: '500' } });

    // Tenta salvar sem preencher fonte
    const saveBtn = screen.getByRole('button', { name: /Salvar Rota/i });
    fireEvent.click(saveBtn);

    expect(
      screen.getByText(/A fonte das tarifas \(ex: documentação de preços do provedor\) é obrigatória/i)
    ).toBeInTheDocument();
    expect(saveSpy).not.toHaveBeenCalled();

    // Preenche fonte mas não confirma declarações
    const priceSource = screen.getByTestId('route-price-source');
    fireEvent.change(priceSource, { target: { value: 'https://openai.com/api/pricing' } });
    fireEvent.click(saveBtn);

    expect(
      screen.getByText(/É obrigatório que o operador confirme conscientemente todas as declarações/i)
    ).toBeInTheDocument();
    expect(saveSpy).not.toHaveBeenCalled();
  });

  it('preserva evidências documentadas e dados de qualidade ao editar uma rota (B2)', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22',
            message: null,
          },
        },
      ],
      routes: [
        {
          route_id: 'route-evidence-test',
          provider: 'openai',
          model: 'gpt-4o-mini',
          enabled: true,
          known_unavailable: false,
          capabilities: ['text_generation'],
          quality_criteria: [
            {
              criterion: 'fast_response',
              evidence_references: ['benchmarks/latency-q3.json#p95', 'docs/slo.md#fast'],
            },
          ],
          status: 'ready',
          blockers: [],
        },
      ],
      models: ['gpt-4o-mini'],
    });

    const saveSpy = vi.spyOn(apiService, 'saveRoute').mockResolvedValueOnce({
      status: 'saved',
      route: {
        route_id: 'route-evidence-test',
        provider: 'openai',
        model: 'gpt-4o-mini',
        enabled: true,
        known_unavailable: false,
        capabilities: ['text_generation'],
        quality_criteria: [],
        status: 'ready',
        blockers: [],
      },
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByTestId('edit-route-route-evidence-test')).toBeInTheDocument();
    });

    // Clica no botão Editar da rota
    fireEvent.click(screen.getByTestId('edit-route-route-evidence-test'));

    expect(screen.getByText(/Editar Rota: route-evidence-test/i)).toBeInTheDocument();

    // Salva o formulário diretamente
    const saveBtn = screen.getByRole('button', { name: /Salvar Alterações/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(saveSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          route_id: 'route-evidence-test',
          quality_criteria: [
            {
              criterion: 'fast_response',
              evidence_references: ['benchmarks/latency-q3.json#p95', 'docs/slo.md#fast'],
            },
          ],
        })
      );
    });
  });

  it('preserva a associação individual entre múltiplos critérios e evidências sem achatamento em lista única (R2)', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22',
            message: null,
          },
        },
      ],
      routes: [
        {
          route_id: 'route-multi-evidence-test',
          provider: 'openai',
          model: 'gpt-4o-mini',
          enabled: true,
          known_unavailable: false,
          capabilities: ['text_generation'],
          quality_criteria: [
            {
              criterion: 'fast_response',
              evidence_references: ['benchmarks/latency-q3.json#p95'],
            },
            {
              criterion: 'strict_instruction_following',
              evidence_references: ['eval-accuracy-v2.json'],
            },
          ],
          status: 'ready',
          blockers: [],
        },
      ],
      models: ['gpt-4o-mini'],
    });

    const saveSpy = vi.spyOn(apiService, 'saveRoute').mockResolvedValueOnce({
      status: 'saved',
      route: {
        route_id: 'route-multi-evidence-test',
        provider: 'openai',
        model: 'gpt-4o-mini',
        enabled: true,
        known_unavailable: false,
        capabilities: ['text_generation'],
        quality_criteria: [],
        status: 'ready',
        blockers: [],
      },
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByTestId('edit-route-route-multi-evidence-test')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('edit-route-route-multi-evidence-test'));

    // Verifica que cada critério está no seu próprio input sem achatamento
    expect((screen.getByTestId('criterion-name-0') as HTMLInputElement).value).toBe('fast_response');
    expect((screen.getByTestId('criterion-evidence-0') as HTMLInputElement).value).toBe('benchmarks/latency-q3.json#p95');
    expect((screen.getByTestId('criterion-name-1') as HTMLInputElement).value).toBe('strict_instruction_following');
    expect((screen.getByTestId('criterion-evidence-1') as HTMLInputElement).value).toBe('eval-accuracy-v2.json');

    const saveBtn = screen.getByRole('button', { name: /Salvar Alterações/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(saveSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          route_id: 'route-multi-evidence-test',
          quality_criteria: [
            {
              criterion: 'fast_response',
              evidence_references: ['benchmarks/latency-q3.json#p95'],
            },
            {
              criterion: 'strict_instruction_following',
              evidence_references: ['eval-accuracy-v2.json'],
            },
          ],
        })
      );
    });
  });

  it('permite alternar para Google Gemini, cadastrar chave na memória e verificar sem custos', async () => {
    let googleRegistered = false;
    vi.spyOn(apiService, 'fetchAdminConfig').mockImplementation(async () => ({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-22T15:00:00Z',
            message: 'Credencial verificada com sucesso.',
          },
        },
        {
          id: 'google',
          name: 'Google',
          implemented: true,
          credential: {
            registered: googleRegistered,
            status: googleRegistered ? 'registered' : 'not_registered',
            verified_at: null,
            message: null,
          },
        },
      ],
      routes: [],
      models: ['gpt-4o'],
      models_by_provider: {
        openai: ['gpt-4o'],
        google: ['gemini-2.5-flash', 'gemini-2.5-pro'],
      },
    }));

    const saveSpy = vi.spyOn(apiService, 'saveCredential').mockImplementation(async () => {
      googleRegistered = true;
      return {
        provider: 'google',
        status: 'registered',
        message: 'Credencial Google cadastrada na memória do servidor.',
      };
    });

    const verifySpy = vi.spyOn(apiService, 'verifyCredential').mockResolvedValueOnce({
      provider: 'google',
      status: 'verified',
      models: ['gemini-2.5-flash', 'gemini-2.5-pro'],
      message: 'Credencial Google verificada com sucesso.',
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-provider-google')).toBeInTheDocument();
    });

    // Alterna para Google Gemini
    fireEvent.click(screen.getByTestId('tab-provider-google'));

    expect(screen.getByText(/Credencial do Provedor \(Google Gemini\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Gemini API Key \(AIza\.\.\.\)/i)).toBeInTheDocument();

    const input = screen.getByTestId('credential-api-key-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'AIzaSyFakeKeyForTest123' } });
    expect(input.value).toBe('AIzaSyFakeKeyForTest123');

    fireEvent.click(screen.getByTestId('btn-save-credential'));

    await waitFor(() => {
      expect(saveSpy).toHaveBeenCalledWith('google', 'AIzaSyFakeKeyForTest123');
      expect(input.value).toBe('');
      expect(screen.getByTestId('btn-verify-credential')).not.toBeDisabled();
    });

    fireEvent.click(screen.getByTestId('btn-verify-credential'));

    await waitFor(() => {
      expect(verifySpy).toHaveBeenCalledWith('google');
    });
  });

  it('permite criar rota Google Gemini com provider "google" e dados econômicos conscientes', async () => {
    vi.spyOn(apiService, 'fetchAdminConfig').mockResolvedValue({
      providers: [
        {
          id: 'google',
          name: 'Google',
          implemented: true,
          credential: {
            registered: true,
            status: 'verified',
            verified_at: '2026-10-29T10:00:00Z',
            message: 'OK',
          },
        },
      ],
      routes: [],
      models: ['gemini-2.5-flash'],
      models_by_provider: {
        openai: ['gpt-4o'],
        google: ['gemini-2.5-flash', 'gemini-2.5-pro'],
      },
    });

    const saveSpy = vi.spyOn(apiService, 'saveRoute').mockResolvedValueOnce({
      status: 'saved',
      route: {
        route_id: 'route-google-gemini-flash',
        provider: 'google',
        model: 'gemini-2.5-flash',
        enabled: true,
        known_unavailable: false,
        capabilities: ['text_generation'],
        quality_criteria: [],
        status: 'ready',
        blockers: [],
      },
    });

    render(<ProvidersView />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nova Rota/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Nova Rota/i }));

    // Seleciona provedor Google Gemini no modal
    const providerSelect = screen.getByTestId('route-provider-select');
    fireEvent.change(providerSelect, { target: { value: 'google' } });

    // Modelo gemini-2.5-flash deve estar selecionável
    const modelSelect = screen.getByTestId('route-model-select');
    fireEvent.change(modelSelect, { target: { value: 'gemini-2.5-flash' } });

    // Configura economia consciente
    fireEvent.click(screen.getByTestId('toggle-economics-config'));
    fireEvent.change(screen.getByTestId('route-input-rate'), { target: { value: '0.075' } });
    fireEvent.change(screen.getByTestId('route-output-rate'), { target: { value: '0.30' } });
    fireEvent.change(screen.getByTestId('route-estimated-input'), { target: { value: '2000' } });
    fireEvent.change(screen.getByTestId('route-estimated-output'), { target: { value: '500' } });
    fireEvent.change(screen.getByTestId('route-price-source'), { target: { value: 'https://ai.google.dev/pricing' } });

    fireEvent.click(screen.getByTestId('decl-rates-complete'));
    fireEvent.click(screen.getByTestId('decl-model-exact'));
    fireEvent.click(screen.getByTestId('decl-usage-applicable'));

    fireEvent.click(screen.getByRole('button', { name: /Salvar Rota/i }));

    await waitFor(() => {
      expect(saveSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'google',
          model: 'gemini-2.5-flash',
          price_reference: expect.objectContaining({
            currency: 'USD',
            source: 'https://ai.google.dev/pricing',
            rates: [
              { unit: 'input_token', rate: '0.075', base: 1000000 },
              { unit: 'output_token', rate: '0.30', base: 1000000 },
            ],
          }),
        })
      );
    });
  });
});

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

    fireEvent.change(inputRate, { target: { value: '0.1500' } });
    fireEvent.change(outputRate, { target: { value: '0.6000' } });
    fireEvent.change(estInput, { target: { value: '2000' } });
    fireEvent.change(estOutput, { target: { value: '800' } });

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
          }),
        })
      );
    });
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
});

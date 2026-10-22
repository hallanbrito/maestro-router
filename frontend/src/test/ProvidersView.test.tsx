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
});

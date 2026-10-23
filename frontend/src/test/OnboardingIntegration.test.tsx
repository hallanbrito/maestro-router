import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import App from '../App';
import * as apiService from '../services/api';

describe('Onboarding and State Preservation Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
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
          route_id: 'route-openai-gpt4o-mini',
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
  });

  it('preserva os dados do formulário de execução ao navegar entre abas', async () => {
    render(<App />);

    // 1. Digita uma tarefa e contexto na aba de execução
    const taskInput = screen.getByLabelText(/Tarefa/i) as HTMLTextAreaElement;
    fireEvent.change(taskInput, {
      target: { value: 'Minha tarefa técnica que não deve ser perdida ao navegar' },
    });
    expect(taskInput.value).toBe('Minha tarefa técnica que não deve ser perdida ao navegar');

    const contextInput = screen.getByLabelText(/Contexto Adicional/i) as HTMLTextAreaElement;
    fireEvent.change(contextInput, {
      target: { value: 'Contexto preservado em memória' },
    });

    // 2. Navega para a aba "Aprender"
    const learnTabBtn = screen.getByRole('button', { name: /Aprender/i });
    fireEvent.click(learnTabBtn);

    // Confirma que a tela de aprendizado está visível
    expect(screen.getByText(/O que é o Maestro Router\?/i)).toBeInTheDocument();

    // 3. Navega para a aba "Provedores & Rotas"
    const providersTabBtn = screen.getByRole('button', { name: /Provedores & Rotas/i });
    fireEvent.click(providersTabBtn);

    // Confirma que a tela de provedores está visível
    expect(screen.getByText(/Gerenciamento Operacional de Provedores & Rotas/i)).toBeInTheDocument();

    // 4. Retorna para a aba de Execução
    const executionTabBtn = screen.getByRole('button', { name: /Execução/i });
    fireEvent.click(executionTabBtn);

    // 5. Verifica se os valores foram preservados fielmente
    const returnedTaskInput = screen.getByLabelText(/Tarefa/i) as HTMLTextAreaElement;
    expect(returnedTaskInput.value).toBe(
      'Minha tarefa técnica que não deve ser perdida ao navegar'
    );

    const returnedContextInput = screen.getByLabelText(/Contexto Adicional/i) as HTMLTextAreaElement;
    expect(returnedContextInput.value).toBe('Contexto preservado em memória');
  });

  it('solicita sugestão explicável de roteamento e permite aplicá-la ao formulário', async () => {
    const previewSpy = vi.spyOn(apiService, 'fetchRoutingPreview').mockResolvedValueOnce({
      track: 'economica',
      policy_description: 'Trilha Econômica: menor custo estimado.',
      recommended_route: {
        route_id: 'route-openai-gpt4o-mini',
        provider: 'openai',
        model: 'gpt-4o-mini',
        estimate: {
          amount: '0.000225',
          currency: 'USD',
          status: 'available',
        },
        price_reference: {
          id: 'pricing-openai-gpt-4o-mini-2026',
          currency: 'USD',
        },
        justification: 'route-openai-gpt4o-mini foi selecionada por menor custo estimado.',
      },
      candidate_evaluations: [
        {
          route_id: 'route-openai-gpt4o-mini',
          status: 'selected',
          reason: 'Menor custo',
        },
      ],
      factors: [
        {
          category: 'route',
          description: 'Única rota elegível com referência ativa',
        },
      ],
      exclusions: [],
      economic_data_status: 'Estimativa disponível: 0.000225 USD',
      billing_warning: true,
      explanation: 'Recomendação baseada em menor custo estimado.',
    });

    render(<App />);

    const taskInput = screen.getByLabelText(/Tarefa/i);
    fireEvent.change(taskInput, { target: { value: 'Resuma este relatório financeiro.' } });

    // Clica no botão "Sugerir modelos/rotas"
    const suggestBtn = screen.getByRole('button', { name: /Sugerir modelos\/rotas/i });
    fireEvent.click(suggestBtn);

    await waitFor(() => {
      expect(previewSpy).toHaveBeenCalledWith({
        task: 'Resuma este relatório financeiro.',
        track: 'economica',
      });
      expect(
        screen.getByText(/Rota Recomendada: route-openai-gpt4o-mini \(gpt-4o-mini\)/i)
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: /Aplicar Sugestão ao Formulário/i })
      ).toBeInTheDocument();
    });

    // Clica em "Aplicar Sugestão ao Formulário"
    const applyBtn = screen.getByRole('button', { name: /Aplicar Sugestão ao Formulário/i });
    fireEvent.click(applyBtn);

    // O campo de rotas permitidas deve ter sido preenchido
    const routesInput = screen.getByLabelText(/Rotas Permitidas/i) as HTMLInputElement;
    expect(routesInput.value).toBe('route-openai-gpt4o-mini');
  });

  it('preserva o estado de execução pendente ao navegar entre abas e impede envio duplicado', async () => {
    let resolveExecution!: (val: any) => void;
    const executionPromise = new Promise((resolve) => {
      resolveExecution = resolve;
    });

    const executeSpy = vi.spyOn(apiService, 'executeAdminTask').mockImplementation(
      () => executionPromise as any
    );

    render(<App />);

    const taskInput = screen.getByLabelText(/Tarefa/i);
    fireEvent.change(taskInput, { target: { value: 'Tarefa concorrente' } });

    const submitBtn = screen.getByRole('button', { name: /Executar Rota/i });
    fireEvent.click(submitBtn);

    // Deve entrar em estado de processamento
    await waitFor(() => {
      expect(screen.getByText(/Processando\.\.\./i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Processando\.\.\./i })).toBeDisabled();
    });

    expect(executeSpy).toHaveBeenCalledTimes(1);

    // Navega para a aba "Aprender" enquanto a execução ainda está pendente
    const learnTabBtn = screen.getByRole('button', { name: /Aprender/i });
    fireEvent.click(learnTabBtn);
    expect(screen.getByText(/O que é o Maestro Router\?/i)).toBeInTheDocument();

    // Retorna para a aba de Execução
    const executionTabBtn = screen.getByRole('button', { name: /Execução/i });
    fireEvent.click(executionTabBtn);

    // O botão ainda deve estar em estado "Processando..." e desabilitado
    const processingBtn = screen.getByRole('button', { name: /Processando\.\.\./i });
    expect(processingBtn).toBeInTheDocument();
    expect(processingBtn).toBeDisabled();

    // Clicar no botão desabilitado não deve disparar nova execução
    fireEvent.click(processingBtn);
    expect(executeSpy).toHaveBeenCalledTimes(1);

    // Conclui a execução pendente
    resolveExecution({
      kind: 'success',
      status: 200,
      data: {
        result: { content: 'Sucesso retornado.' },
        decision: {
          outcome: 'selected',
          route: { id: 'route-openai-gpt4o-mini', provider: 'openai', model: 'gpt-4o-mini' },
          strategy: { id: 'lowest-estimated-cost', applied: true },
          applied_constraints: [],
          reason: 'Rota selecionada.',
          factors: [],
        },
        economics: {
          estimate: { status: 'available', amount: '0.000100', currency: 'USD', price_reference: 'ref', assumptions: [] },
          usage: { status: 'available', items: [] },
          calculated_cost: { status: 'available', amount: '0.000100', currency: 'USD', price_reference: 'ref', assumptions: [] },
        },
      },
    });

    // Aguarda retorno ao estado normal
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Executar Rota/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Executar Rota/i })).not.toBeDisabled();
      expect(screen.getByText('Sucesso retornado.')).toBeInTheDocument();
    });
  });
});

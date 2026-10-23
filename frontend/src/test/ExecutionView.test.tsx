import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ExecutionView } from '../components/ExecutionView';
import * as apiService from '../services/api';

describe('ExecutionView component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('não realiza fetch automático na montagem inicial da tela', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    render(<ExecutionView />);

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.getByText('Solicitação de Execução')).toBeInTheDocument();
    expect(screen.getByText(/Pronto para Roteamento Neutro/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Executar Rota/i })
    ).toBeInTheDocument();
  });

  it('permite preenchimento de task, context e required_quality_criteria preservando valores', async () => {
    const mockExecute = vi.spyOn(apiService, 'executeAdminTask').mockResolvedValueOnce({
      kind: 'success',
      status: 200,
      data: {
        result: { content: 'Texto gerado pelo Maestro Router.' },
        decision: {
          outcome: 'selected',
          route: { id: 'route-test-1', provider: 'openai', model: 'gpt-4o' },
          strategy: { id: 'lowest-estimated-cost', applied: true },
          applied_constraints: [],
          reason: 'Rota selecionada por menor custo estimado.',
          factors: [{ category: 'economics', description: 'Custo estimado $0.000200' }],
        },
        economics: {
          estimate: {
            status: 'available',
            amount: '0.000200',
            currency: 'USD',
            price_reference: 'ref-1',
            assumptions: [],
          },
          usage: {
            status: 'available',
            items: [{ unit: 'input_token', quantity: '50' }],
          },
          calculated_cost: {
            status: 'available',
            amount: '0.000150',
            currency: 'USD',
            price_reference: 'ref-1',
            assumptions: [],
          },
        },
      },
    });

    render(<ExecutionView />);

    // Digita tarefa com espaços preservados
    const taskInput = screen.getByLabelText(/Tarefa/i);
    fireEvent.change(taskInput, {
      target: { value: '  Instrução técnica com espaços  ' },
    });

    // Digita contexto
    const contextInput = screen.getByLabelText(/Contexto Adicional/i);
    fireEvent.change(contextInput, {
      target: { value: 'Contexto relevante.' },
    });

    // Expande restrições
    const toggleConstraintsBtn = screen.getByRole('button', {
      name: /Restrições da Solicitação/i,
    });
    fireEvent.click(toggleConstraintsBtn);

    // Preenche critério de qualidade exposto (Point 2)
    const criteriaInput = screen.getByLabelText(
      /Critérios de Qualidade Obrigatórios/i
    );
    fireEvent.change(criteriaInput, {
      target: { value: 'summary_faithfulness_accepted' },
    });

    const submitBtn = screen.getByRole('button', { name: /Executar Rota/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalledWith(
        {
          task: '  Instrução técnica com espaços  ',
          context: 'Contexto relevante.',
          constraints: {
            required_quality_criteria: ['summary_faithfulness_accepted'],
          },
        },
        'economica'
      );
      expect(
        screen.getByText('Texto gerado pelo Maestro Router.')
      ).toBeInTheDocument();
      expect(screen.getByText('route-test-1')).toBeInTheDocument();
      expect(screen.getByText('gpt-4o')).toBeInTheDocument();
    });
  });

  it('exibe RefusalCard com orientações quando a API retorna NO_ELIGIBLE_ROUTE (422)', async () => {
    vi.spyOn(apiService, 'executeAdminTask').mockResolvedValueOnce({
      kind: 'refusal',
      status: 422,
      error: {
        error: {
          code: 'NO_ELIGIBLE_ROUTE',
          message:
            'Nenhuma rota configurada, habilitada e válida satisfaz as restrições aplicáveis.',
        },
        decision: {
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
        },
      },
    });

    render(<ExecutionView />);

    const taskInput = screen.getByLabelText(/Tarefa/i);
    fireEvent.change(taskInput, {
      target: { value: 'Qualquer tarefa para testar recusa' },
    });

    const submitBtn = screen.getByRole('button', { name: /Executar Rota/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/Recusa Controlada: Nenhuma Rota Elegível/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Próximas Ações Recomendadas/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/O catálogo não continha rotas configuradas/i)
      ).toBeInTheDocument();
    });
  });
  it('não preenche respostas nem altera status por parâmetros de consulta sem interação do usuário', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const onExecutionResultMock = vi.fn();

    window.history.pushState({}, '', '/?demo=refusal&test=1');

    try {
      render(<ExecutionView onExecutionResult={onExecutionResultMock} />);

      expect(fetchSpy).not.toHaveBeenCalled();
      expect(onExecutionResultMock).not.toHaveBeenCalled();
      expect(
        screen.queryByText(/Recusa Controlada: Nenhuma Rota Elegível/i)
      ).not.toBeInTheDocument();
      expect(
        screen.queryByText(/Demonstração de recusa de rota/i)
      ).not.toBeInTheDocument();
      expect(
        screen.getByText(/Pronto para Roteamento Neutro/i)
      ).toBeInTheDocument();
    } finally {
      window.history.pushState({}, '', '/');
    }
  });

  it('exibe aviso e terminologia de gratuidade declarada pelo operador ao selecionar a trilha Free', async () => {
    const mockExecute = vi.spyOn(apiService, 'executeAdminTask').mockResolvedValueOnce({
      kind: 'success',
      status: 200,
      data: {
        result: { content: 'Executado com rota gratuita' },
        decision: {
          outcome: 'selected',
          route: { id: 'route-free', provider: 'openai', model: 'mock-free' },
          strategy: { id: 'lowest-estimated-cost', applied: true },
          applied_constraints: [],
          reason: 'Rota gratuita selecionada.',
          factors: [],
        },
        economics: {
          estimate: { status: 'available', amount: '0.000000', currency: 'USD', price_reference: 'free', assumptions: [] },
          usage: { status: 'available', items: [] },
          calculated_cost: { status: 'available', amount: '0.000000', currency: 'USD', price_reference: 'free', assumptions: [] },
        },
      },
    });

    render(<ExecutionView />);

    // Verifica que a descrição inicial da trilha Free usa a nova terminologia honesta
    expect(
      screen.getByText(/Somente candidatos com tarifas zero declaradas pelo operador\./i)
    ).toBeInTheDocument();

    // Seleciona a trilha Free
    const freeCard = screen.getByText('Free').closest('div')!;
    fireEvent.click(freeCard);

    // O aviso explícito sobre faturamento deve surgir
    expect(
      screen.getByTestId('free-track-disclaimer')
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Aviso sobre a Trilha Free \(Gratuidade declarada pelo operador\):/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Ela não confirma se a sua conta ou cota no provedor realmente possuem isenção de faturamento/i)
    ).toBeInTheDocument();

    // Digita tarefa e executa na trilha Free
    const taskInput = screen.getByLabelText(/Tarefa/i);
    fireEvent.change(taskInput, { target: { value: 'Tarefa sob trilha Free' } });

    const submitBtn = screen.getByRole('button', { name: /Executar Rota/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalledWith(
        expect.objectContaining({ task: 'Tarefa sob trilha Free' }),
        'free'
      );
    });
  });

  it('apresenta erro de validação junto ao campo de teto de custo sem quebrar a tela quando o valor for inválido', async () => {
    render(<ExecutionView />);

    // Expande a seção de restrições
    const toggleConstraintsBtn = screen.getByRole('button', {
      name: /Restrições da Solicitação/i,
    });
    fireEvent.click(toggleConstraintsBtn);

    const costInput = screen.getByLabelText(/Teto de Custo Estimado/i);
    // Digita valor inválido
    fireEvent.change(costInput, { target: { value: 'abc' } });

    // O erro deve ser renderizado inline junto ao campo
    const errorEl = screen.getByTestId('cost-limit-error');
    expect(errorEl).toBeInTheDocument();
    expect(errorEl.textContent).toContain('O teto de custo deve ser um valor decimal não negativo válido');
  });

  it('trata resposta de erro com envelope detail sem gerar TypeError', async () => {
    vi.spyOn(apiService, 'executeAdminTask').mockResolvedValueOnce({
      kind: 'client_error',
      status: 400,
      error: {
        error: {
          code: 'INVALID_REQUEST',
          message: 'Parâmetro inválido',
          issues: [
            {
              path: '/constraints/max_estimated_cost/amount',
              message: 'O valor deve ser decimal no formato 0.0000',
            },
          ],
        },
      },
    });

    render(<ExecutionView />);

    // Expande restrições
    const toggleConstraintsBtn = screen.getByRole('button', {
      name: /Restrições da Solicitação/i,
    });
    fireEvent.click(toggleConstraintsBtn);

    const taskInput = screen.getByLabelText(/Tarefa/i);
    fireEvent.change(taskInput, { target: { value: 'Tarefa com teto inválido' } });

    const submitBtn = screen.getByRole('button', { name: /Executar Rota/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      const errorEl = screen.getByTestId('cost-limit-error');
      expect(errorEl).toBeInTheDocument();
      expect(errorEl.textContent).toContain('O valor deve ser decimal no formato 0.0000');
    });
  });

  it('sempre encerra o estado de carregamento via finally mesmo quando a sessão ou requisição falhar', async () => {
    vi.spyOn(apiService, 'executeAdminTask').mockRejectedValueOnce(
      new Error('Falha no handshake CSRF')
    );

    render(<ExecutionView />);

    const taskInput = screen.getByLabelText(/Tarefa/i);
    fireEvent.change(taskInput, { target: { value: 'Tarefa para teste de falha' } });

    const submitBtn = screen.getByRole('button', { name: /Executar Rota/i });
    fireEvent.click(submitBtn);

    // O botão deve voltar a ficar ativo após a falha, sem ficar preso em "Processando..."
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Executar Rota/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Executar Rota/i })).not.toBeDisabled();
      expect(screen.getByText(/Falha no handshake CSRF/i)).toBeInTheDocument();
    });
  });
});

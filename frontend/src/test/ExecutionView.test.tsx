import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ExecutionView } from '../components/ExecutionView';
import * as apiService from '../services/api';

describe('ExecutionView component', () => {
  it('renders initial form and empty state', () => {
    render(<ExecutionView />);

    expect(screen.getByText('Solicitação de Execução')).toBeInTheDocument();
    expect(screen.getByText(/Pronto para Roteamento Neutro/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Executar Rota/i })).toBeInTheDocument();
  });

  it('allows filling task and submitting', async () => {
    const mockExecute = vi.spyOn(apiService, 'executeTask').mockResolvedValueOnce({
      kind: 'success',
      status: 200,
      data: {
        result: { content: 'Resultado gerado com sucesso pelo Maestro Router.' },
        decision: {
          outcome: 'selected',
          route: { id: 'route-test-1', provider: 'openai', model: 'gpt-4o-mini' },
          strategy: { id: 'lowest-estimated-cost', applied: true },
          applied_constraints: [],
          reason: 'Rota com menor custo estimado.',
          factors: [{ category: 'economics', description: 'Custo estimado $0.0002' }],
        },
        economics: {
          estimate: { status: 'available', amount: '0.000200', currency: 'USD', price_reference: 'ref-1' },
          usage: { status: 'available', items: [{ unit: 'input_token', quantity: '50' }] },
          calculated_cost: { status: 'available', amount: '0.000150', currency: 'USD' },
        },
      },
    });

    render(<ExecutionView />);

    const taskInput = screen.getByLabelText(/Tarefa/i);
    fireEvent.change(taskInput, { target: { value: 'Escreva um haicai sobre código' } });

    const submitBtn = screen.getByRole('button', { name: /Executar Rota/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalledWith({
        task: 'Escreva um haicai sobre código',
      });
      expect(screen.getByText('Resultado gerado com sucesso pelo Maestro Router.')).toBeInTheDocument();
      expect(screen.getByText('route-test-1')).toBeInTheDocument();
      expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument();
    });
  });

  it('displays RefusalCard when NO_ELIGIBLE_ROUTE is returned', async () => {
    vi.spyOn(apiService, 'executeTask').mockResolvedValueOnce({
      kind: 'refusal',
      status: 422,
      error: {
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
      },
    });

    render(<ExecutionView />);

    const taskInput = screen.getByLabelText(/Tarefa/i);
    fireEvent.change(taskInput, { target: { value: 'Qualquer tarefa para testar recusa' } });

    const submitBtn = screen.getByRole('button', { name: /Executar Rota/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/Recusa Controlada: Nenhuma Rota Elegível/i)).toBeInTheDocument();
      expect(screen.getByText(/Próximas Ações Recomendadas/i)).toBeInTheDocument();
      expect(screen.getByText(/Catálogo de rotas está vazio/i)).toBeInTheDocument();
    });
  });
});

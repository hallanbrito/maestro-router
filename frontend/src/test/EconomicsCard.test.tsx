import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { EconomicsCard } from '../components/EconomicsCard';
import { ExecutionEconomics } from '../types';

describe('EconomicsCard component', () => {
  it('exibe traço "—" e a justificativa reason quando os estados forem unavailable (sem falsos zeros)', () => {
    const economics: ExecutionEconomics = {
      estimate: {
        status: 'unavailable',
        reason: 'Não há preço aprovado para esta rota.',
      },
      usage: {
        status: 'unavailable',
        reason: 'O provedor não retornou métricas de uso.',
      },
      calculated_cost: {
        status: 'unavailable',
        reason: 'Custo não pôde ser calculado devido à ausência de uso.',
      },
    };

    render(<EconomicsCard economics={economics} />);

    // Deve renderizar os traços "—" ao invés de "0" ou "0.00"
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(3);

    // Deve renderizar as justificativas obrigatórias do estado unavailable
    expect(
      screen.getByText('Não há preço aprovado para esta rota.')
    ).toBeInTheDocument();
    expect(
      screen.getByText('O provedor não retornou métricas de uso.')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Custo não pôde ser calculado devido à ausência de uso.')
    ).toBeInTheDocument();

    // Garante que nenhum custo zero foi inventado
    expect(screen.queryByText(/0\.00/)).not.toBeInTheDocument();
  });

  it('exibe valores numéricos e justificativa quando o estado for uncertain', () => {
    const economics: ExecutionEconomics = {
      estimate: {
        status: 'uncertain',
        amount: '0.002500',
        currency: 'USD',
        price_reference: 'pricing-q3-2026',
        assumptions: ['Volume de saída estimado com base na média'],
        reason: 'Volume de saída não pode ser determinado com precisão.',
      },
      usage: {
        status: 'uncertain',
        items: [{ unit: 'input_token', quantity: '150' }],
        reason: 'Métricas parciais do provedor.',
      },
      calculated_cost: {
        status: 'uncertain',
        amount: '0.000450',
        currency: 'USD',
        price_reference: 'pricing-q3-2026',
        assumptions: ['Base de cálculo parcial'],
        reason: 'Custo aproximado.',
      },
    };

    render(<EconomicsCard economics={economics} />);

    expect(screen.getByText('0.002500 USD')).toBeInTheDocument();
    expect(
      screen.getByText('Volume de saída não pode ser determinado com precisão.')
    ).toBeInTheDocument();
    expect(screen.getByText('0.000450 USD')).toBeInTheDocument();
    expect(screen.getByText('Métricas parciais do provedor.')).toBeInTheDocument();
  });

  it('exibe valores apurados sem campo reason quando o estado for available', () => {
    const economics: ExecutionEconomics = {
      estimate: {
        status: 'available',
        amount: '0.001200',
        currency: 'USD',
        price_reference: 'pricing-audit-2026',
        assumptions: [],
      },
      usage: {
        status: 'available',
        items: [
          { unit: 'input_token', quantity: '200' },
          { unit: 'output_token', quantity: '50' },
        ],
      },
      calculated_cost: {
        status: 'available',
        amount: '0.000300',
        currency: 'USD',
        price_reference: 'pricing-audit-2026',
        assumptions: [],
      },
    };

    render(<EconomicsCard economics={economics} />);

    expect(screen.getByText('0.001200 USD')).toBeInTheDocument();
    expect(screen.getByText('0.000300 USD')).toBeInTheDocument();
    expect(screen.getByText('input_token:')).toBeInTheDocument();
    expect(screen.getByText('200')).toBeInTheDocument();
    expect(screen.getByText('output_token:')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
  });
});

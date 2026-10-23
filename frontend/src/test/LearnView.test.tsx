import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { LearnView } from '../components/LearnView';

describe('LearnView component', () => {
  it('renderiza os conceitos fundamentais e o que o Maestro recebe, decide e devolve', () => {
    const onNavigateTab = vi.fn();
    const onLoadExampleAndExecute = vi.fn();

    render(
      <LearnView
        onNavigateTab={onNavigateTab}
        onLoadExampleAndExecute={onLoadExampleAndExecute}
      />
    );

    // O que é o Maestro
    expect(screen.getByText(/O que é o Maestro Router\?/i)).toBeInTheDocument();
    expect(screen.getByText(/O que o Maestro Recebe, Decide e Devolve/i)).toBeInTheDocument();

    // Diferenças entre Provedor, Modelo, Rota e Trilha
    expect(screen.getByText('Provedor')).toBeInTheDocument();
    expect(screen.getByText('Modelo')).toBeInTheDocument();
    expect(screen.getByText('Rota')).toBeInTheDocument();
    expect(screen.getByText('Trilha')).toBeInTheDocument();

    // Glossário em Português
    expect(screen.getByText(/Glossário Rápido do Maestro/i)).toBeInTheDocument();
    expect(screen.getByText('Elegibilidade Não-Econômica')).toBeInTheDocument();
    expect(screen.getByText('Fator de Decisão')).toBeInTheDocument();
    expect(screen.getByText('Referência de Preço')).toBeInTheDocument();

    // Links normativos
    expect(screen.getByText(/docs\/05-API\.md/i)).toBeInTheDocument();
    expect(screen.getByText(/docs\/00-MANIFESTO\.md/i)).toBeInTheDocument();
  });

  it('permite navegação para Execução, Provedores e carregamento de exemplo', () => {
    const onNavigateTab = vi.fn();
    const onLoadExampleAndExecute = vi.fn();

    render(
      <LearnView
        onNavigateTab={onNavigateTab}
        onLoadExampleAndExecute={onLoadExampleAndExecute}
      />
    );

    const startBtn = screen.getByRole('button', { name: /Começar Agora/i });
    fireEvent.click(startBtn);
    expect(onNavigateTab).toHaveBeenCalledWith('execution');

    const providersBtn = screen.getByRole('button', { name: /Configurar Provedores/i });
    fireEvent.click(providersBtn);
    expect(onNavigateTab).toHaveBeenCalledWith('providers');

    const exampleBtn = screen.getByRole('button', { name: /Experimentar Exemplo/i });
    fireEvent.click(exampleBtn);
    expect(onLoadExampleAndExecute).toHaveBeenCalled();
  });
});

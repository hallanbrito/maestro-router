import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { Header } from '../components/Header';

describe('Header component', () => {
  it('renderiza o estado inicial idle como "Pronto para execução"', () => {
    render(
      <Header
        activeTab="execution"
        onSelectTab={vi.fn()}
        connectionState="idle"
      />
    );

    expect(screen.getByText('Pronto para execução')).toBeInTheDocument();
  });

  it('renderiza "API Respondendo" e ponto online quando conectado com sucesso', () => {
    render(
      <Header
        activeTab="execution"
        onSelectTab={vi.fn()}
        connectionState="connected"
      />
    );

    expect(screen.getByText('API Respondendo')).toBeInTheDocument();
  });

  it('distingue conexão HTTP de erro na execução externa sem classificar HTTP 503 como sucesso (BUG-UI-04)', () => {
    const { container } = render(
      <Header
        activeTab="execution"
        onSelectTab={vi.fn()}
        connectionState="execution_error"
      />
    );

    // Não exibe o falso sucesso "API Respondendo"
    expect(screen.queryByText('API Respondendo')).not.toBeInTheDocument();

    // Exibe status fidedigno que confirma conexão HTTP porém aponta falha de execução externa
    expect(
      screen.getByText('API Conectada • Falha na Execução Externa')
    ).toBeInTheDocument();

    // O ponto de status deve adotar classe warning, e não online
    const dot = container.querySelector('.status-dot');
    expect(dot).toHaveClass('warning');
    expect(dot).not.toHaveClass('online');
  });

  it('renderiza "API Conectada • Erro Interno do Servidor (500)" e ponto server-error sem falsa desconexão (A01)', () => {
    const { container } = render(
      <Header
        activeTab="execution"
        onSelectTab={vi.fn()}
        connectionState="server_error"
      />
    );

    expect(screen.getByText('API Conectada • Erro Interno do Servidor (500)')).toBeInTheDocument();
    expect(screen.queryByText('API Inacessível')).not.toBeInTheDocument();
    const dot = container.querySelector('.status-dot');
    expect(dot).toHaveClass('server-error');
    expect(dot).not.toHaveClass('offline');
  });

  it('preserva categoria de erro de protocolo com mensagem própria e ponto protocol-error (A02)', () => {
    const { container } = render(
      <Header
        activeTab="execution"
        onSelectTab={vi.fn()}
        connectionState="protocol_error"
      />
    );

    expect(screen.getByText('API Conectada • Resposta Inesperada')).toBeInTheDocument();
    expect(screen.queryByText(/Erro Interno/i)).not.toBeInTheDocument();
    expect(screen.queryByText('API Inacessível')).not.toBeInTheDocument();
    const dot = container.querySelector('.status-dot');
    expect(dot).toHaveClass('protocol-error');
    expect(dot).not.toHaveClass('server-error');
    expect(dot).not.toHaveClass('offline');
  });

  it('renderiza "API Inacessível" e ponto offline quando desconectado', () => {
    const { container } = render(
      <Header
        activeTab="execution"
        onSelectTab={vi.fn()}
        connectionState="disconnected"
      />
    );

    expect(screen.getByText('API Inacessível')).toBeInTheDocument();
    const dot = container.querySelector('.status-dot');
    expect(dot).toHaveClass('offline');
  });

  it('permite alternar abas ao clicar nos botões de navegação', () => {
    const onSelectTabMock = vi.fn();
    render(
      <Header
        activeTab="execution"
        onSelectTab={onSelectTabMock}
        connectionState="idle"
      />
    );

    const providersBtn = screen.getByRole('button', { name: /Provedores & Rotas/i });
    fireEvent.click(providersBtn);
    expect(onSelectTabMock).toHaveBeenCalledWith('providers');
  });
});

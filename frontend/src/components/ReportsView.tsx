import React from 'react';
import { DollarSign, Clock, Hash, CheckCircle2, FileSpreadsheet } from 'lucide-react';

export const ReportsView: React.FC = () => {
  return (
    <div className="info-view-container">
      <div className="info-hero">
        <h2 className="info-hero-title">Modelo Econômico & Métricas do Maestro Router</h2>
        <p className="info-hero-desc">
          O Maestro trata custos como parte fundamental da decisão algorítmica, separando de forma estrita
          a estimativa prévia do custo real calculado pós-execução.
        </p>
      </div>

      <div className="alert-card info">
        <div className="alert-header">
          <FileSpreadsheet size={22} color="var(--color-primary)" />
          <div>
            <h3 className="alert-title">Transparência sem Persistência Falsa</h3>
            <p className="alert-message" style={{ margin: 0 }}>
              Conforme a seção 4.3 de <code>docs/05-API.md</code>, a API pública v1 não armazena histórico
              em banco de dados e não expõe endpoints de telemetria pública. Todas as métricas econômicas
              acompanham a própria resposta da requisição síncrona.
            </p>
          </div>
        </div>
      </div>

      <div className="info-grid">
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">
              <Clock size={18} color="var(--color-primary)" />
              1. Estimativa Pré-Execução
            </h3>
            <span className="badge badge-neutral">Antes da Chamada</span>
          </div>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Calculada antes de qualquer acionamento externo. É confrontada com o teto de custo da solicitação
            (<code>max_estimated_cost</code>) e com as restrições operacionais. Se incerta ou indisponível,
            a rota pode ser desclassificada caso custo seja indispensável na estratégia.
          </p>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">
              <Hash size={18} color="var(--color-purple)" />
              2. Uso Normalizado
            </h3>
            <span className="badge badge-purple">Pós-Execução</span>
          </div>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Quantidades neutras registradas após a resposta do provedor (como <code>input_token</code> e{' '}
            <code>output_token</code>). Não expõe nomes de campos proprietários de APIs externas.
          </p>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">
              <DollarSign size={18} color="var(--color-success)" />
              3. Custo Calculado
            </h3>
            <span className="badge badge-success">Auditável</span>
          </div>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Multiplicação do uso normalizado pelas taxas da referência de preços auditável (
            <code>price_reference</code>). Diferencia custo calculado de fatura ou cobrança final do provedor.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginTop: '1.5rem' }}>
        <h3 className="card-title" style={{ marginBottom: '0.75rem' }}>
          <CheckCircle2 size={18} color="var(--color-success)" />
          Garantias Inegociáveis do Maestro Router
        </h3>
        <ul style={{ paddingLeft: '1.25rem', fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          <li>
            <strong>Elegibilidade antes do preço:</strong> Um modelo mais barato nunca é escolhido se não atender às capacidades e critérios exigidos pela tarefa.
          </li>
          <li>
            <strong>Sem conversão cambial oculta:</strong> Moedas diferentes não são convertidas implicitamente para evitar flutuações e erros de precisão.
          </li>
          <li>
            <strong>Explicabilidade compulsória:</strong> Toda seleção ou recusa traz os fatores determinantes estruturados na chave <code>decision.factors</code>.
          </li>
        </ul>
      </div>
    </div>
  );
};

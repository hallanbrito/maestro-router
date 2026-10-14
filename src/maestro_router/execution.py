"""Contratos neutros e desacoplados para execução de rotas no Maestro Router.

Papel Arquitetural:
    Este módulo define a fronteira neutra entre o núcleo de roteamento do Maestro
    e os adaptadores de provedores externos (como o adaptador OpenAI suportado no
    MVP). A menção a "Port" ou "Arquitetura Hexagonal" possui finalidade didática
    para ilustrar o desacoplamento por contratos neutros, não constituindo nova
    decisão arquitetural ou taxonomia normativa do projeto. O núcleo opera
    exclusivamente com as abstrações deste módulo e desconhece protocolos HTTP,
    SDKs proprietários, cabeçalhos ou formatos externos.

Fluxo da Requisição:
    1. A aplicação cliente envia uma tarefa textual através da API pública.
    2. O núcleo de roteamento valida restrições e seleciona exatamente uma
       rota candidata (:class:`ExecutionRoute`).
    3. O núcleo despacha a requisição (:class:`TextExecutionRequest`) e a rota
       para o adaptador registrado (:class:`ExecutionAdapter`).
    4. O adaptador traduz a solicitação para a API do provedor e converte a
       resposta bruta em um resultado neutro (:class:`TextExecutionResult`),
       incluindo o uso observado e normalizado (:class:`NormalizedUsage`).
    5. O resultado é devolvido ao núcleo para validação, explicabilidade e
       eventual cálculo de custo pelo Maestro em :mod:`maestro_router.economics`.

Invariantes e Confiabilidade:
    - Imutabilidade: Objetos de transferência de dados são dataclasses congeladas
      (`frozen=True`) com `slots=True`, prevenindo mutações acidentais e efeitos
      colaterais durante o ciclo de vida do snapshot.
    - Normalização Conservadora de Uso: Estados de uso (:class:`NormalizedUsage`)
      são discriminados de forma explícita (`available`, `uncertain` ou
      `unavailable`). Métricas ausentes ou parciais não são mascaradas como
      consumo zero, resguardando a explicabilidade da execução e do custo calculado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


def _require_non_blank(value: str, field_name: str) -> None:
    """Valida defensivamente se uma string não é nula, não vazia e não apenas espaços.

    Args:
        value: O valor textual a ser validado.
        field_name: O nome descritivo do campo para a mensagem de erro.

    Raises:
        ValueError: Se o valor não for uma string ou contiver somente espaços.
    """

    # Rejeita tipos não string e sequências compostas exclusivamente por espaços.
    # Em identificadores e campos de domínio, strings em branco causam falhas
    # silenciosas ou estados ambíguos em etapas posteriores do pipeline.
    if not isinstance(value, str) or not any(
        not character.isspace() for character in value
    ):
        raise ValueError(f"{field_name} must be a non-blank string.")


@dataclass(frozen=True, slots=True)
class TextExecutionRequest:
    """Solicitação textual mínima enviada do núcleo de roteamento ao adaptador.

    Encapsula o conteúdo que o provedor externo deve processar, desacoplando
    estruturas de requisição HTTP ou parâmetros proprietários de SDKs.
    """

    task: str
    context: str | None = None

    def __post_init__(self) -> None:
        """Assegura as invariantes da solicitação preservando a imutabilidade."""

        # A tarefa é a unidade central de trabalho e deve ser obrigatória e legível.
        _require_non_blank(self.task, "task")
        # O contexto é opcional; porém, quando fornecido, não pode ser vazio ou em branco.
        if self.context is not None:
            _require_non_blank(self.context, "context")


@dataclass(frozen=True, slots=True)
class ExecutionRoute:
    """Identidade neutra e explícita da rota selecionada para execução.

    Informa ao adaptador qual provedor e modelo devem ser acionados na execução,
    referenciando o identificador estável gerado na fase de decisão.
    """

    id: str
    provider: str
    model: str

    def __post_init__(self) -> None:
        """Exige que todos os componentes de identidade da rota sejam explícitos."""

        # Identificadores de rota, provedor e modelo são pré-requisitos para despacho
        # correto e auditoria; nenhum deles pode ser omitido ou deixado em branco.
        _require_non_blank(self.id, "route id")
        _require_non_blank(self.provider, "provider")
        _require_non_blank(self.model, "model")


# Estados possíveis do uso normalizado:
# - ``available``: uso observado completo retornado pelo provedor.
# - ``uncertain``: uso observado parcial ou incompleto, acompanhado de justificativa.
# - ``unavailable``: uso ausente ou não normalizável, acompanhado de justificativa.
# Esta distinção semântica impede que ausência de dados seja confundida com consumo zero.
UsageStatus = Literal["available", "uncertain", "unavailable"]


@dataclass(frozen=True, slots=True)
class NormalizedUsageItem:
    """Quantidade de uso observada em uma unidade tarifável neutra.

    Representa uma medição reportada pelo provedor (ex.: tokens de entrada),
    isolando terminologias proprietárias como contadores brutos do SDK.
    """

    unit: str
    quantity: int

    def __post_init__(self) -> None:
        """Garante uma unidade não vazia e uma quantidade inteira não negativa."""

        _require_non_blank(self.unit, "usage unit")
        # Validação estrita de tipo: em Python, bool é subclasse de int (isinstance(True, int) é True).
        # Usamos `type(self.quantity) is not int` para rejeitar booleanos e floats.
        # Quantidades de uso não podem ser negativas no domínio de medição.
        if type(self.quantity) is not int or self.quantity < 0:
            raise ValueError("usage quantity must be a non-negative integer.")


@dataclass(frozen=True, slots=True)
class NormalizedUsage:
    """Uso observado normalizado de forma independente do formato do provedor.

    Implementa uma estrutura discriminada conservadora (ADR 0004):
    - ``available``: exige itens e não permite justificativa (reason).
    - ``uncertain``: exige itens parciais e exige uma justificativa sanitizada.
    - ``unavailable``: não permite itens e exige uma justificativa sanitizada.

    Essa separação estrita evita que métricas faltantes sejam tratadas como
    consumo nulo, resguardando a integridade do custo calculado pelo Maestro.
    """

    status: UsageStatus
    items: tuple[NormalizedUsageItem, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        """Aplica as invariantes de consistência associadas a cada estado de uso."""

        if self.status not in ("available", "uncertain", "unavailable"):
            raise ValueError("usage status is invalid.")
        # Coleção imutável obrigatória: tuplas garantem ausência de mutação pós-criação.
        if not isinstance(self.items, tuple) or any(
            not isinstance(item, NormalizedUsageItem) for item in self.items
        ):
            raise ValueError("usage items must be normalized usage items.")
        # Unicidade de unidades: previne contagens conflitantes ou duplas para a mesma métrica.
        units = tuple(item.unit for item in self.items)
        if len(set(units)) != len(units):
            raise ValueError("usage units must be unique.")
        # Se o uso é conhecido (total ou parcial), é obrigatório apresentar ao menos uma métrica.
        if self.status in ("available", "uncertain") and not self.items:
            raise ValueError("known usage must contain at least one item.")
        # Estado available: dados completos não admitem justificativa de exceção ou incerteza.
        if self.status == "available":
            if self.reason is not None:
                raise ValueError("available usage must not contain a reason.")
            return
        # Estados uncertain e unavailable: a explicabilidade exige uma justificativa clara.
        if self.reason is None:
            raise ValueError("non-available usage must contain a reason.")
        _require_non_blank(self.reason, "usage reason")
        # Estado unavailable: proíbe itens para evitar confusão entre uso parcial e ausente.
        if self.status == "unavailable" and self.items:
            raise ValueError("unavailable usage must not contain items.")


# Mensagem estável e padronizada para respostas públicas quando um adaptador
# não consegue extrair dados de uso normalizáveis da resposta do provedor.
USAGE_UNAVAILABLE_REASON = "A execução não forneceu uso normalizável."


# Instância sentinela padrão que representa uso ausente com motivo sanitizado.
# Utilizada como valor default fail-safe no resultado de execução.
USAGE_NOT_PROVIDED = NormalizedUsage(
    status="unavailable",
    reason=USAGE_UNAVAILABLE_REASON,
)


@dataclass(frozen=True, slots=True)
class TextExecutionResult:
    """Resultado neutro de execução retornado pelo adaptador ao núcleo.

    Agrupa o conteúdo textual gerado pelo modelo, o uso observado e normalizado
    e a identidade do modelo efetivamente observado durante a chamada externa.
    """

    content: str
    usage: NormalizedUsage = USAGE_NOT_PROVIDED
    observed_model: str | None = None

    def __post_init__(self) -> None:
        """Garante que nenhum adaptador retorne um resultado neutro corrompido."""

        if not isinstance(self.content, str):
            raise ValueError("content must be a string.")
        if not isinstance(self.usage, NormalizedUsage):
            raise ValueError("usage must be normalized usage.")
        if self.observed_model is not None:
            _require_non_blank(self.observed_model, "observed model")
            # Validação Unicode: caracteres no intervalo de surrogates (0xD800 a 0xDFFF)
            # são inválidos em UTF-8 e quebram a serialização JSON da API pública.
            if any(
                0xD800 <= ord(character) <= 0xDFFF
                for character in self.observed_model
            ):
                raise ValueError(
                    "observed model must be a well-formed Unicode scalar sequence."
                )


class ExecutionFailedError(RuntimeError):
    """Exceção base neutra para falhas ocorridas durante a execução no provedor."""


class ExecutionUnavailableError(ExecutionFailedError):
    """Indica que a rota selecionada ou o provedor estava indisponível no momento da execução."""


class ExecutionTimeoutError(ExecutionFailedError):
    """Indica que a chamada ao provedor ultrapassou o tempo limite configurado."""


class ExecutionAdapter(Protocol):
    """Contrato estrutural (Protocol) para adaptadores de execução de provedores.

    Separação por Contrato:
        O núcleo do Maestro estabelece o protocolo necessário para execução, e
        adaptadores concretos (como :class:`~maestro_router.adapters.openai.OpenAIResponsesAdapter`)
        o implementam sem que o núcleo dependa de bibliotecas ou SDKs proprietários.
        A referência a inversão de dependência ou portas possui caráter didático.
    """

    async def execute(
        self, request: TextExecutionRequest, route: ExecutionRoute
    ) -> TextExecutionResult:
        """Executa exatamente a rota selecionada e devolve o resultado normalizado.

        Args:
            request: Solicitação textual comum contendo tarefa e contexto opcional.
            route: Identificação neutra da rota (provedor, modelo e id da rota).

        Returns:
            TextExecutionResult contendo o texto gerado, o uso e o modelo observado.

        Raises:
            ExecutionUnavailableError: Se o provedor ou endpoint estiver indisponível.
            ExecutionTimeoutError: Se o tempo limite da requisição expirar.
            ExecutionFailedError: Para outras falhas operacionais na chamada externa.
        """

        ...

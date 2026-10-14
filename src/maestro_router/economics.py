"""Cálculos econômicos exatos, neutros e determinísticos do Maestro Router.

Papel Arquitetural:
    Este módulo constitui o núcleo de avaliação econômica (Cost Evaluation)
    do Maestro Router. Ele atua em dois momentos do ciclo de vida da requisição:
    1. Estimativa pré-execução (:func:`calculate_pre_execution_amount`): calcula o
       valor monetário a partir de uma previsão de consumo configurada pelo operador,
       permitindo verificar conformidade com tetos de gastos (`max_estimated_cost`).
    2. Custo pós-execução (:func:`calculate_post_execution_cost`): apura o custo
       calculado pelo Maestro a partir do uso observado e normalizado
       (:class:`~maestro_router.execution.NormalizedUsage`) e da referência de
       preço vinculada ao snapshot da rota executada.

Separação entre Uso Observado, Estimativa e Custo Calculado:
    O Maestro mantém distinção estrita entre a estimativa anterior à execução,
    o uso observado e normalizado e o custo calculado pelo Maestro após a execução.
    O custo pós-execução é um custo calculado pelo Maestro; ele não é custo real,
    não constitui fato econômico observado e não representa fatura, cobrança ou
    conciliação de provedor. As tarifas e referências de preço chegam exclusivamente
    por configuração imutável fornecida pelo operador (:class:`PriceReference`),
    sem buscas automáticas na web, tabelas embutidas no código-fonte ou conciliação
    com faturas de provedores.

Aritmética Decimal Exata vs. Ponto Flutuante (IEEE 754):
    Para prevenir imprecisões de representação e arredondamentos cumulativos
    inerentes ao ponto flutuante binário (`float`, ex.: `0.1 + 0.2 != 0.3`), o
    Maestro adota aritmética decimal exata. Este módulo utiliza a classe
    :class:`decimal.Decimal` sob contexto estrito (:func:`decimal.localcontext`),
    calculando analiticamente a precisão necessária (:func:`_required_precision`)
    e ativando armadilhas (:attr:`decimal.Context.traps`) para :class:`decimal.Inexact`
    e :class:`decimal.Rounded`. Se uma operação aritmética não puder ser resolvida
    sem arredondamento na política aprovada, ela falha deliberadamente em vez de
    arredondar silenciosamente.

Bases de Potência de Dez:
    Tarifas de modelos de linguagem frequentemente usam bases volumétricas (ex.: $0.15
    por 1.000.000 de tokens). Ao restringir a base tarifária a potências inteiras
    positivas de 10 (:func:`_is_power_of_ten`), garante-se que a divisão no sistema
    decimal resulte sempre em um número finito de casas decimais (apenas deslocamento
    de escala), sem dízimas periódicas.

Postura Conservadora para Custo Calculado:
    Conforme a ADR 0005, o Maestro adota postura estritamente conservadora:
    se qualquer dado necessário for incerto, incompleto, divergente (como disparidade entre o
    modelo configurado e o observado) ou não suportado pela política aprovada, o resultado é classificado
    como indisponível (:class:`PostExecutionCost` com status `unavailable`),
    acompanhado de justificativa sanitizada. O sistema não inventa valores, não
    presume consumo zero para dados ausentes e não apresenta estimativas ou subtotais
    como se fossem o custo total.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, DecimalException, Inexact, Rounded, localcontext
from typing import TYPE_CHECKING, Literal

from .contracts import CURRENCY_PATTERN, DECIMAL_PATTERN
from .execution import NormalizedUsage

if TYPE_CHECKING:
    from .routing import EconomicEstimate


def _require_non_blank(value: object, field_name: str) -> None:
    """Valida defensivamente se o valor é uma string contendo ao menos um caractere visível.

    Args:
        value: Objeto a ser validado.
        field_name: Nome do campo para inclusão na mensagem de exceção.

    Raises:
        ValueError: Se o valor não for string ou contiver somente espaços em branco.
    """

    if not isinstance(value, str) or not any(
        not character.isspace() for character in value
    ):
        raise ValueError(f"{field_name} must be a non-blank string.")


def _is_power_of_ten(value: int) -> bool:
    """Verifica se um inteiro é uma potência positiva de dez (1, 10, 100, 1000, ...).

    Algoritmo:
        Divide sucessivamente o número por 10 enquanto o resto for zero.
        Se ao final o quociente for 1, o número original é da forma 10^k (com k >= 0).

    Propriedade da Base Decimal:
        A divisão por 10^k em base decimal apenas move a vírgula fracionária para a
        esquerda, garantindo que o cálculo não gere dízimas periódicas que forçariam
        arredondamentos.
    """

    if value < 1:
        return False
    while value > 1 and value % 10 == 0:
        value //= 10
    return value == 1


@dataclass(frozen=True, slots=True)
class UnitPrice:
    """Tarifa neutra e imutável para uma unidade tarifável independente.

    Exemplo:
        Uma tarifa de $0.15 por 1.000.000 de tokens de entrada é representada com
        unit="input_token", rate="0.15" e base=1000000.
    """

    unit: str
    rate: str
    base: int

    def __post_init__(self) -> None:
        """Valida a unidade, a taxa decimal exata e a base como potência de dez."""

        _require_non_blank(self.unit, "price unit")
        # A taxa deve ser uma string decimal válida e não negativa (ex.: "0.15"),
        # prevenindo contaminação por imprecisão de float antes do cálculo.
        if not isinstance(self.rate, str) or not DECIMAL_PATTERN.fullmatch(
            self.rate
        ):
            raise ValueError("price rate must be a non-negative decimal string.")
        # Em Python, bool é subclasse de int; type(x) is not int rejeita True/False.
        # A base deve ser obrigatoriamente 10^k para garantir divisão decimal exata.
        if type(self.base) is not int or not _is_power_of_ten(self.base):
            raise ValueError(
                "price base must be a positive integer power of ten."
            )


@dataclass(frozen=True, slots=True)
class PriceReference:
    """Referência de preço neutra, validada e imutável vinculada ao snapshot de uma rota.

    Reúne as tarifas por unidade (:class:`UnitPrice`), moeda, versão e metadados de
    origem, além de quatro evidências booleanas de completude declaradas pelo operador:
    - ``context_complete``: atesta que nenhum detalhe tarifário relevante foi omitido.
    - ``units_exhaustive``: atesta que as tarifas cobrem a totalidade das unidades faturáveis.
    - ``no_double_counting``: atesta a inexistência de contagem dupla entre métricas.
    - ``model_identity_exact``: atesta que a identificação do modelo coincide com a tabela de preços.
    """

    id: str
    route_id: str
    provider: str
    model: str
    currency: str
    version: str
    source: str
    rates: tuple[UnitPrice, ...]
    conditions: tuple[str, ...]
    context_complete: bool
    units_exhaustive: bool
    no_double_counting: bool
    model_identity_exact: bool

    def __post_init__(self) -> None:
        """Valida as evidências de completude e canonicaliza coleções imutáveis."""

        for field_name, value in (
            ("price reference id", self.id),
            ("price route id", self.route_id),
            ("price provider", self.provider),
            ("price model", self.model),
            ("price version", self.version),
            ("price source", self.source),
        ):
            _require_non_blank(value, field_name)
        if not isinstance(self.currency, str) or not CURRENCY_PATTERN.fullmatch(
            self.currency
        ):
            raise ValueError(
                "price currency must contain three uppercase ASCII letters."
            )
        if not isinstance(self.rates, tuple) or not self.rates or any(
            not isinstance(rate, UnitPrice) for rate in self.rates
        ):
            raise ValueError("price rates must be a non-empty immutable tuple.")
        units = tuple(rate.unit for rate in self.rates)
        if len(set(units)) != len(units):
            raise ValueError("price units must be unique.")
        if not isinstance(self.conditions, tuple) or any(
            not isinstance(condition, str)
            or not any(not character.isspace() for character in condition)
            for condition in self.conditions
        ):
            raise ValueError("price conditions must be non-blank strings.")
        if len(set(self.conditions)) != len(self.conditions):
            raise ValueError("price conditions must be unique.")
        # As evidências de completude devem ser booleanos explícitos (rejeita int/strings).
        for field_name, value in (
            ("context_complete", self.context_complete),
            ("units_exhaustive", self.units_exhaustive),
            ("no_double_counting", self.no_double_counting),
            ("model_identity_exact", self.model_identity_exact),
        ):
            if type(value) is not bool:
                raise ValueError(f"{field_name} must be an explicit boolean.")

        # Ordenação canônica: em dataclasses congeladas (frozen=True), mutações normais
        # são bloqueadas. O uso de `object.__setattr__` no __post_init__ permite ordenar
        # tarifas e condições deterministicamente, garantindo snapshots idênticos.
        object.__setattr__(
            self, "rates", tuple(sorted(self.rates, key=lambda rate: rate.unit))
        )
        object.__setattr__(self, "conditions", tuple(sorted(self.conditions)))


# No MVP, o status de custo pós-execução é estritamente binário (ADR 0005):
# ou o cálculo é comprovadamente exato (available), ou é declarado indisponível (unavailable).
CostStatus = Literal["available", "unavailable"]

# Conjunto imutável fechado com o vocabulário de unidades tarifáveis da primeira política.
_SUPPORTED_COST_UNITS = frozenset({"input_token", "output_token"})
_UNSUPPORTED_COST_UNIT_REASON = (
    "A primeira política não cobre todas as unidades observadas ou tarifadas."
)


@dataclass(frozen=True, slots=True)
class PostExecutionCost:
    """Resultado conservador do custo calculado pelo Maestro após a execução (ADR 0005).

    Estrutura de união discriminada estrita:
    - ``available``: contém os dados do custo calculado pelo Maestro (valor, moeda, referência,
      hipóteses) e não permite justificativa (reason).
    - ``unavailable``: não contém dados monetários numéricos e exige justificativa sanitizada.

    Essa separação garante que valores parciais ou hipóteses incompletas não
    sejam apresentados como custo calculado disponível, mantendo o custo calculado
    distinto de estimativa anterior, uso observado ou cobrança do provedor.
    """

    status: CostStatus
    amount: str | None = None
    currency: str | None = None
    price_reference: str | None = None
    assumptions: tuple[str, ...] | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        """Garante a mútua exclusão entre os estados available e unavailable."""

        if self.status == "available":
            if (
                self.amount is None
                or self.currency is None
                or self.price_reference is None
                or self.assumptions is None
            ):
                raise ValueError("available cost requires complete monetary facts.")
            if not DECIMAL_PATTERN.fullmatch(self.amount):
                raise ValueError("available cost must be an exact decimal string.")
            if not CURRENCY_PATTERN.fullmatch(self.currency):
                raise ValueError("available cost must use a valid currency.")
            _require_non_blank(self.price_reference, "cost price reference")
            if self.reason is not None:
                raise ValueError("available cost must not contain a reason.")
            return
        if self.status != "unavailable":
            raise ValueError("post-execution cost status is invalid.")
        if any(
            value is not None
            for value in (
                self.amount,
                self.currency,
                self.price_reference,
                self.assumptions,
            )
        ):
            raise ValueError("unavailable cost must not contain monetary facts.")
        _require_non_blank(self.reason, "cost unavailability reason")


def _unavailable(reason: str) -> PostExecutionCost:
    """Fábrica pura que constrói a resposta padrão de custo indisponível com justificativa."""

    return PostExecutionCost(status="unavailable", reason=reason)


def calculate_pre_execution_amount(
    *,
    quantities: Mapping[str, int],
    reference: PriceReference,
) -> str:
    """Calcula o valor monetário exato a partir de uma previsão de uso configurada (ADR 0007).

    Args:
        quantities: Mapeamento de unidades tarifáveis para quantidades inteiras positivas.
        reference: Referência de preço imutável vinculada à rota.

    Returns:
        String com o montante monetário exato formatado conforme a gramática decimal pública.

    Raises:
        ValueError: Se as quantidades ou evidências de preço forem incompletas, contiverem
            unidades não suportadas ou se o montante não puder ser calculado com exatidão.
    """

    # A previsão pré-execução do operador deve cobrir exatamente as duas unidades suportadas
    # (input_token e output_token) com inteiros estritamente positivos (> 0).
    if set(quantities) != _SUPPORTED_COST_UNITS or any(
        type(quantity) is not int or quantity <= 0
        for quantity in quantities.values()
    ):
        raise ValueError(
            "pre-execution quantities must contain the two supported units"
        )
    if {rate.unit for rate in reference.rates} != _SUPPORTED_COST_UNITS:
        raise ValueError("price reference does not cover the supported units")
    # Todas as 4 evidências de completude devem ser declaradas verdadeiras pelo operador.
    if not all(
        (
            reference.context_complete,
            reference.units_exhaustive,
            reference.no_double_counting,
            reference.model_identity_exact,
        )
    ):
        raise ValueError("price reference is not complete")

    try:
        amount = _calculate_exact_amount(reference, quantities)
    except (DecimalException, ArithmeticError, ValueError, KeyError):
        raise ValueError(
            "pre-execution amount cannot be represented exactly"
        ) from None
    if not DECIMAL_PATTERN.fullmatch(amount):
        raise ValueError(
            "pre-execution amount does not match the public decimal grammar"
        )
    return amount


def calculate_post_execution_cost(
    *,
    route_id: str,
    provider: str,
    model: str | None = None,
    configured_model: str | None = None,
    observed_model: str | None = None,
    estimate: EconomicEstimate,
    usage: NormalizedUsage | None,
    reference: PriceReference | None,
) -> PostExecutionCost:
    """Aplica a primeira política conservadora de custo calculado pelo Maestro após a execução (ADR 0005).

    Fluxo e Postura Conservadora:
        Cada requisito de identidade, completude tarifária, vocabulário de unidades e
        correspondência com a estimativa anterior é verificado antes de qualquer operação
        aritmética. Diante de qualquer dado faltante, incerto ou inconsistente, a função
        retorna imediatamente :class:`PostExecutionCost` com status `unavailable` e
        justificativa sanitizada, jamais inferindo valores parciais ou presumindo zero.

    Args:
        route_id: Identificador da rota executada.
        provider: Identificador do provedor executado.
        model: Identificador legado do modelo (mantido para compatibilidade de chamada).
        configured_model: Identificador do modelo configurado na rota.
        observed_model: Identificador do modelo observado na resposta do provedor.
        estimate: Estimativa econômica registrada antes da execução.
        usage: Uso observado e normalizado retornado pelo adaptador.
        reference: Referência de preço configurada no snapshot da rota.

    Returns:
        PostExecutionCost com status available e custo calculado pelo Maestro, ou
        status unavailable com razão explicativa sanitizada.
    """

    # O parâmetro legado `model` permite que chamadores que fornecem apenas uma identidade
    # declarem implicitamente que ela é tanto a configurada quanto a observada.
    if configured_model is None:
        configured_model = model
    if observed_model is None and model is not None:
        observed_model = model

    # Gate 1: O uso deve estar comprovadamente completo (status available).
    # Uso nulo, parcial (uncertain) ou ausente (unavailable) não sustenta cálculo confiável.
    if usage is None or usage.status != "available":
        return _unavailable(
            "O uso completo necessário para calcular o custo não está disponível."
        )
    # Gate 2: A rota deve possuir uma referência de preço configurada no snapshot.
    if reference is None:
        return _unavailable(
            "Não há referência de preço configurada para calcular o custo posterior."
        )
    # Gate 3: Validação das quatro evidências de completude declaradas pelo operador.
    if not reference.context_complete:
        return _unavailable("O contexto tarifário configurado está incompleto.")
    if not reference.units_exhaustive:
        return _unavailable(
            "A referência não comprova que as unidades tarifáveis são exaustivas."
        )
    if not reference.no_double_counting:
        return _unavailable(
            "A referência não comprova ausência de dupla contagem tarifária."
        )
    if not reference.model_identity_exact:
        return _unavailable(
            "A identidade tarifária exata do modelo não foi comprovada."
        )
    # Gate 4: Validação de identidade do modelo.
    if configured_model is None or observed_model is None:
        return _unavailable(
            "A identidade do modelo usado na execução não pôde ser comprovada."
        )
    # Se o provedor reportou um modelo observado diferente do configurado na rota,
    # a referência de preço da rota não é aplicada para evitar distorção no cálculo.
    if observed_model != configured_model:
        return _unavailable(
            "O modelo observado não corresponde ao modelo configurado na rota."
        )
    # Gate 5: Correspondência estrita entre a referência de preço e a rota executada.
    if (
        reference.route_id != route_id
        or reference.provider != provider
        or reference.model != configured_model
    ):
        return _unavailable(
            "A referência de preço não corresponde exatamente à rota executada."
        )
    # Gate 6: Consistência com a estimativa anterior. Se a estimativa foi calculada,
    # a moeda e a referência pós-execução devem coincidir rigorosamente com as registradas.
    if estimate.status in ("available", "uncertain") and (
        estimate.currency != reference.currency
        or estimate.price_reference != reference.id
    ):
        return _unavailable(
            "A referência posterior não corresponde à estimativa registrada."
        )

    # Gate 7: Álgebra de conjuntos para validação do vocabulário tarifável.
    # Garante que nenhuma unidade não suportada (ex.: cache, raciocínio) seja ignorada silenciosamente.
    usage_by_unit = {item.unit: item.quantity for item in usage.items}
    rates_by_unit = {rate.unit: rate for rate in reference.rates}
    if (
        not usage_by_unit.keys() <= _SUPPORTED_COST_UNITS
        or not rates_by_unit.keys() <= _SUPPORTED_COST_UNITS
    ):
        return _unavailable(_UNSUPPORTED_COST_UNIT_REASON)
    # Todas as unidades tarifadas pela referência devem estar presentes no uso.
    missing_units = rates_by_unit.keys() - usage_by_unit.keys()
    if missing_units:
        return _unavailable(
            "O uso não contém todas as unidades tarifáveis exigidas."
        )
    # Nenhuma unidade presente no uso pode ficar sem cobertura tarifária.
    additional_units = usage_by_unit.keys() - rates_by_unit.keys()
    if additional_units:
        return _unavailable(
            "O uso contém unidade material não coberta pela referência de preço."
        )

    # Gate 8: Execução do cálculo aritmético exato sem ponto flutuante.
    try:
        amount = _calculate_exact_amount(reference, usage_by_unit)
    except (DecimalException, ArithmeticError, ValueError, KeyError):
        return _unavailable(
            "O custo não pode ser representado exatamente pela política aprovada."
        )

    # Validação do formato do valor resultante contra o contrato público.
    if not DECIMAL_PATTERN.fullmatch(amount):
        return _unavailable(
            "O custo não pode ser representado exatamente pela gramática pública."
        )
    return PostExecutionCost(
        status="available",
        amount=amount,
        currency=reference.currency,
        price_reference=reference.id,
        assumptions=(),
    )


def _required_precision(
    reference: PriceReference, quantities: Mapping[str, int]
) -> int:
    """Calcula analiticamente a precisão Decimal exata necessária para os produtos e sua soma.

    Algoritmo:
        1. Para cada tarifa, calcula a escala decimal combinada: casas decimais da taxa
           mais a magnitude da base (log10(base) = len(str(base)) - 1).
        2. Alinha os dígitos significativos dos coeficientes e das quantidades inteiras
           com a escala máxima encontrada.
        3. Adiciona dígitos adicionais para absorver o acúmulo da soma das parcelas
           (len(str(len(rates)))) e 4 dígitos de guarda (guard digits).

    Essa precisão calculada sob medida garante que o contexto decimal opere sem
    truncamentos e sem disparar falsos positivos nas armadilhas de arredondamento.
    """

    scales = [
        _fractional_digits(rate.rate) + len(str(rate.base)) - 1
        for rate in reference.rates
    ]
    maximum_scale = max(scales)
    aligned_digits = []
    for rate, scale in zip(reference.rates, scales, strict=True):
        coefficient_digits = len(rate.rate.replace(".", "").lstrip("0")) or 1
        quantity_digits = len(str(quantities[rate.unit]))
        aligned_digits.append(
            coefficient_digits
            + quantity_digits
            + maximum_scale
            - scale
        )
    return max(aligned_digits) + len(str(len(reference.rates))) + 4


def _calculate_exact_amount(
    reference: PriceReference,
    quantities: Mapping[str, int],
) -> str:
    """Multiplica cada quantidade por sua taxa unitária e divide pela base, rejeitando arredondamentos.

    Garantia de Exatidão Decimal:
        Utiliza `decimal.localcontext` para isolar os parâmetros de cálculo do restante da aplicação.
        A precisão é ajustada dinamicamente via `_required_precision`.
        As armadilhas `Inexact` e `Rounded` são ativadas: se qualquer operação tentar
        arredondar ou aproximar um valor, uma exceção é lançada imediatamente (fail-fast),
        impedindo que o Maestro publique valores arredondados.
    """

    with localcontext() as context:
        context.prec = _required_precision(reference, quantities)
        # O valor calculado só pode ser publicado se cada operação for exata.
        # Ativar ambas as armadilhas impede que o Decimal arredonde dados configurados.
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        total = Decimal(0)
        for rate in reference.rates:
            total += (
                Decimal(quantities[rate.unit])
                * Decimal(rate.rate)
                / Decimal(rate.base)
            )
    return _plain_decimal(total)


def _fractional_digits(value: str) -> int:
    """Conta a quantidade de casas decimais explícitas em uma string decimal validada."""

    separator = value.find(".")
    return 0 if separator < 0 else len(value) - separator - 1


def _plain_decimal(value: Decimal) -> str:
    """Serializa um Decimal sem notação científica de expoente e sem zeros à direita redundantes.

    Exemplos:
        Decimal('1.5000') -> '1.5'
        Decimal('2.0') -> '2'
        Decimal('0.00010') -> '0.0001'
    """

    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"

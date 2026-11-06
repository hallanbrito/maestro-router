"""Implementação da OpenAI Responses API para a fronteira neutra de execução.

Este módulo é o tradutor entre o contrato interno do Maestro e o SDK da OpenAI.
Ele não escolhe rotas nem calcula preços: apenas executa a rota já autorizada e
normaliza o resultado para que o restante do núcleo não dependa do provedor.
"""

from __future__ import annotations

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)

from ..execution import (
    ExecutionFailedError,
    ExecutionRoute,
    ExecutionTimeoutError,
    ExecutionUnavailableError,
    NormalizedUsage,
    NormalizedUsageItem,
    TextExecutionRequest,
    TextExecutionResult,
    USAGE_UNAVAILABLE_REASON,
)


_FAILED_MESSAGE = "A execução externa falhou."
_TIMEOUT_MESSAGE = "A execução externa excedeu o timeout aplicável."
_UNAVAILABLE_MESSAGE = "A execução externa estava temporariamente indisponível."
_PARTIAL_USAGE_REASON = (
    "A resposta concluída forneceu somente parte do uso normalizável."
)
_MISSING = object()


class OpenAIResponsesAdapter:
    """Traduz o contrato neutro de execução para a OpenAI Responses API."""

    def __init__(
        self,
        client: AsyncOpenAI,
        *,
        retry_policy_configured: bool = False,
    ) -> None:
        """Armazena um cliente assíncrono da OpenAI construído explicitamente."""

        # Congela a política de repetição quando o adaptador entra no snapshot da
        # aplicação. Recriar opções do SDK a cada requisição poderia reler o estado
        # do processo e produzir um comportamento diferente durante a execução.
        self._client = (
            client
            if retry_policy_configured
            else client.with_options(max_retries=0)
        )

    async def execute(
        self, request: TextExecutionRequest, route: ExecutionRoute
    ) -> TextExecutionResult:
        """Executa o modelo selecionado e converte falhas em erros neutros.

        O adaptador não seleciona rotas, não deduz preços e não expõe o payload
        bruto do provedor. Ele envia uma única requisição sem streaming e devolve
        somente texto validado e uso normalizado.
        """

        try:
            # As repetições automáticas do SDK são desativadas (max_retries=0) na
            # inicialização. Assim, uma autorização de execução do núcleo gera no
            # máximo uma chamada externa, preservando o contrato do Maestro.
            response = await self._client.responses.create(
                model=route.model,
                input=_response_input(request),
                stream=False,
            )
        except APITimeoutError as error:
            raise ExecutionTimeoutError(_TIMEOUT_MESSAGE) from error
        except (APIConnectionError, RateLimitError) as error:
            raise ExecutionUnavailableError(_UNAVAILABLE_MESSAGE) from error
        except APIStatusError as error:
            if error.status_code >= 500:
                raise ExecutionUnavailableError(
                    _UNAVAILABLE_MESSAGE
                ) from error
            raise ExecutionFailedError(_FAILED_MESSAGE) from error
        except OpenAIError as error:
            raise ExecutionFailedError(_FAILED_MESSAGE) from error
        except Exception as error:
            # Formatos inesperados do SDK atravessam a fronteira como a mesma
            # falha sanitizada e neutra, nunca como dados brutos do provedor.
            raise ExecutionFailedError(_FAILED_MESSAGE) from error

        return _normalize_response(response)


def _response_input(request: TextExecutionRequest) -> list[dict[str, object]]:
    """Monta a entrada mínima da Responses API aceita pelo MVP."""

    content = [{"type": "input_text", "text": request.task}]
    if request.context is not None:
        content.append({"type": "input_text", "text": request.context})
    return [{"role": "user", "content": content}]


def _normalize_response(response: object) -> TextExecutionResult:
    """Valida uma resposta textual concluída e a projeta no modelo do núcleo."""

    try:
        if getattr(response, "status", None) != "completed":
            raise ExecutionFailedError(_FAILED_MESSAGE)

        output = getattr(response, "output")
        if not isinstance(output, list) or not _has_valid_text_output(output):
            raise ExecutionFailedError(_FAILED_MESSAGE)

        output_text = getattr(response, "output_text")
        if not isinstance(output_text, str):
            raise ExecutionFailedError(_FAILED_MESSAGE)
        return TextExecutionResult(
            content=output_text,
            usage=_normalize_usage(response),
            observed_model=_normalize_observed_model(response),
        )
    except ExecutionFailedError:
        raise
    except Exception as error:
        raise ExecutionFailedError(_FAILED_MESSAGE) from error


def _normalize_usage(response: object) -> NormalizedUsage:
    """Converte contadores de tokens da OpenAI em unidades neutras de uso.

    Contagens completas de entrada e saída produzem uso ``available``. Apenas
    uma contagem válida produz uso ``uncertain``. Dados ausentes ou malformados
    produzem ``unavailable`` em vez de o Maestro inventar uma quantidade.
    """

    usage = _read_attribute(response, "usage")
    if usage is _MISSING or usage is None:
        return NormalizedUsage(
            status="unavailable", reason=USAGE_UNAVAILABLE_REASON
        )

    items = []
    for external_name, neutral_unit in (
        ("input_tokens", "input_token"),
        ("output_tokens", "output_token"),
    ):
        quantity = _read_attribute(usage, external_name)
        if type(quantity) is int and quantity >= 0:
            items.append(
                NormalizedUsageItem(unit=neutral_unit, quantity=quantity)
            )

    normalized_items = tuple(items)
    if len(normalized_items) == 2:
        return NormalizedUsage(status="available", items=normalized_items)
    if normalized_items:
        return NormalizedUsage(
            status="uncertain",
            items=normalized_items,
            reason=_PARTIAL_USAGE_REASON,
        )
    return NormalizedUsage(
        status="unavailable", reason=USAGE_UNAVAILABLE_REASON
    )


def _normalize_observed_model(response: object) -> str | None:
    """Extrai e valida o identificador de modelo informado pelo provedor.

    Retorna o identificador quando ele não está em branco e não contém
    ``surrogates`` Unicode isolados. Caso contrário, retorna ``None`` para que a
    validação pós-execução rejeite uma identidade de modelo não verificável.
    """
    model = _read_attribute(response, "model")
    if (
        isinstance(model, str)
        and any(not character.isspace() for character in model)
        and not any(0xD800 <= ord(character) <= 0xDFFF for character in model)
    ):
        return model
    return None


def _read_attribute(value: object, name: str) -> object:
    """Lê um atributo do SDK sem permitir que acessores hostis escapem."""

    try:
        return getattr(value, name)
    except Exception:
        return _MISSING


def _has_valid_text_output(output: list[object]) -> bool:
    """Confirma que a saída do provedor contém texto estruturalmente válido."""

    found_text = False
    for item in output:
        if getattr(item, "type", None) != "message":
            continue
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            return False
        for part in content:
            if getattr(part, "type", None) != "output_text":
                continue
            if not isinstance(getattr(part, "text", None), str):
                return False
            found_text = True
    return found_text

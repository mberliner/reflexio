"""
Payloads HTTP y resultados observados de LiteLLM 1.108.5 para regresion de SPEC-104.

Modulo solo de datos (sin prefijo `test_` para que pytest no lo recolecte). Lo
consumen `tests/test_litellm_failure_mapping.py` (regresion de transporte contra
LiteLLM) y, en la implementacion de SPEC-104, los tests del clasificador de la
capa 1 (SC-009).

Verificacion original: 2026-11-23, sin red, interceptando `httpx.Client.send`
contra:
- litellm==1.108.5
- openai==3.57.0
- httpx==0.28.1
- dspy==3.2.1
Re-verificado 2026-11-25 con dspy==3.4.1 + gepa==0.1.4 (D-018 b2): mismo mapeo
y mismos conteos de `CheckedLM` (el transporte no depende de dspy, SPEC-105).

Referencias:
- `specs/SPEC-104-fallas-tecnicas-justas.md` ("Reglas de deteccion de la capa 1",
  FR-011, FR-015, SC-009 y "Limites conocidos")
- `historial/sdd.md` (D-023)

Los payloads HTTP, codigos de estado, mensajes y excepciones de transporte se
conservan tal cual fueron probados en la verificacion del 2026-11-23.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EXPECTED_VERSIONS: dict[str, str] = {
    "litellm": "1.108.5",
    "openai": "3.57.0",
    "httpx": "0.28.1",
    "dspy": "3.5.0",
    "gepa": "0.1.4",
}

JSON_HEADERS: dict[str, str] = {"content-type": "application/json"}

PROVIDER_KWARGS: dict[str, dict[str, Any]] = {
    "azure": {
        "model": "azure/gpt-4.1-mini",
        "api_key": "fake-azure-key",
        "api_base": "https://fake.openai.azure.com",
        "api_version": "2024-02-15-preview",
    },
    "openai": {
        "model": "openai/gpt-4o-mini",
        "api_key": "fake-openai-key",
    },
    "anthropic": {
        "model": "anthropic/claude-sonnet-5-5",
        "api_key": "fake-anthropic-key",
    },
}

ProviderName = Literal["azure", "openai", "anthropic"]
CaseTable = Literal["input_filter", "context_window", "http_200", "retry"]
CaseType = Literal["http_error", "http_200", "transport_error"]
Spec104Class = Literal[
    "entrada",
    "infraestructura",
    "configuracion",
    "filtro_salida",
    "presupuesto",
    "sin_texto",
    "ok",
]


@dataclass(frozen=True)
class FailurePayloadCase:
    """Registro inmutable de un payload o falla de transporte y su mapeo observado."""

    id: str
    table: CaseTable
    provider: ProviderName
    model: str
    case_type: CaseType
    spec104_class: Spec104Class
    status_code: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    transport_exc_type: str | None = None
    transport_exc_message: str | None = None
    # Comportamiento observado hoy en litellm==1.108.5 + openai==3.57.0
    expected_exception: str | None = None
    expected_status_code: int | None = None
    returns_none: bool = False
    expected_body_preserved: bool | None = None
    expected_body_code: str | None = None
    expected_body_innererror_code: str | None = None
    expected_exc_psf_innererror_code: str | None = None
    # Campos esperados para HTTP 200
    expected_finish_reason: str | None = None
    expected_content: str | None = None
    expected_refusal: str | None = None
    expected_has_refusal_attr: bool | None = None
    expected_choice_psf: dict[str, Any] | None = None
    expected_message_psf_subset: dict[str, Any] | None = None
    # Conteos de llamadas HTTP observados por configuracion de reintentos (tabla 4)
    expected_http_calls: dict[str, int] | None = None
    # Marca los casos que reflejan un bug o limite actual documentado en D-023
    d023_quirk: bool = False


def _oai_200_body(
    message: dict[str, Any],
    finish_reason: str | None,
    extra_choice: dict[str, Any] | None = None,
    extra_root: dict[str, Any] | None = None,
) -> dict[str, Any]:
    choice: dict[str, Any] = {
        "index": 0,
        "message": message,
        "finish_reason": finish_reason,
        **(extra_choice or {}),
    }
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "m",
        "choices": [choice],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        **(extra_root or {}),
    }


def _anth_200_body(
    content: list[dict[str, Any]],
    stop_reason: str,
    extra_root: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
        **(extra_root or {}),
    }


# ==================== Tabla 1: Filtros de entrada (HTTP 400) ====================

INPUT_FILTER_CASES: tuple[FailurePayloadCase, ...] = (
    FailurePayloadCase(
        id="azure_400_content_filter_canonico",
        table="input_filter",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": (
                    "The response was filtered due to the prompt triggering Azure "
                    "OpenAI's content management policy. Please modify your prompt "
                    "and retry."
                ),
                "type": None,
                "param": "prompt",
                "code": "content_filter",
                "status": 400,
                "innererror": {
                    "code": "ResponsibleAIPolicyViolation",
                    "content_filter_result": {
                        "hate": {"filtered": False, "severity": "safe"},
                        "jailbreak": {"filtered": True, "detected": True},
                    },
                },
            }
        },
        expected_exception="ContentPolicyViolationError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="content_filter",
        expected_body_innererror_code=None,
        expected_exc_psf_innererror_code="ResponsibleAIPolicyViolation",
        spec104_class="entrada",
    ),
    # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
    FailurePayloadCase(
        id="azure_400_content_filter_innererror_otro_msg",
        table="input_filter",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": "Prompt filtered by safety system",
                "type": "invalid_request_error",
                "param": "prompt",
                "code": "content_filter",
                "innererror": {"code": "ResponsibleAIPolicyViolation"},
            }
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="content_filter",
        expected_body_innererror_code="ResponsibleAIPolicyViolation",
        spec104_class="entrada",
        d023_quirk=True,
    ),
    # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
    FailurePayloadCase(
        id="azure_400_content_filter_solo_code",
        table="input_filter",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": "Prompt was filtered",
                "type": "invalid_request_error",
                "param": "prompt",
                "code": "content_filter",
            }
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="content_filter",
        spec104_class="entrada",
        d023_quirk=True,
    ),
    FailurePayloadCase(
        id="azure_400_content_policy_violation",
        table="input_filter",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": "Your request was rejected.",
                "type": "invalid_request_error",
                "code": "content_policy_violation",
            }
        },
        expected_exception="ContentPolicyViolationError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="content_policy_violation",
        spec104_class="entrada",
    ),
    FailurePayloadCase(
        id="azure_400_generico_param_invalido",
        table="input_filter",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": "Unrecognized request argument supplied: foo",
                "type": "invalid_request_error",
                "param": "foo",
                "code": None,
            }
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code=None,
        spec104_class="configuracion",
    ),
    # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
    FailurePayloadCase(
        id="openai_400_content_policy_violation_canonico",
        table="input_filter",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": "Your request was rejected as a result of our safety system.",
                "type": "invalid_request_error",
                "param": None,
                "code": "content_policy_violation",
            }
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="content_policy_violation",
        spec104_class="entrada",
        d023_quirk=True,
    ),
    FailurePayloadCase(
        id="openai_400_invalid_prompt_usage_policy",
        table="input_filter",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": (
                    "Invalid prompt: your prompt was flagged as potentially violating "
                    "our usage policy."
                ),
                "type": "invalid_request_error",
                "param": None,
                "code": "invalid_prompt",
            }
        },
        expected_exception="ContentPolicyViolationError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="invalid_prompt",
        spec104_class="entrada",
    ),
    FailurePayloadCase(
        id="openai_400_cyber_policy",
        table="input_filter",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": "Blocked for cybersecurity reasons.",
                "type": "invalid_request_error",
                "param": None,
                "code": "cyber_policy",
            }
        },
        expected_exception="ContentPolicyViolationError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="cyber_policy",
        spec104_class="entrada",
    ),
    FailurePayloadCase(
        id="openai_400_generico_param_invalido",
        table="input_filter",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": "Invalid 'temperature': decimal above maximum value.",
                "type": "invalid_request_error",
                "param": "temperature",
                "code": "decimal_above_max_value",
            }
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="decimal_above_max_value",
        spec104_class="configuracion",
    ),
    FailurePayloadCase(
        id="anthropic_400_content_filtering_policy",
        table="input_filter",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Output blocked by content filtering policy",
            },
        },
        expected_exception="ContentPolicyViolationError",
        expected_status_code=400,
        expected_body_preserved=False,
        spec104_class="entrada",
    ),
    # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
    # Segun SPEC-104 "Limites conocidos", cae en configuracion (sin body).
    FailurePayloadCase(
        id="anthropic_400_usage_policy_otro_texto",
        table="input_filter",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "This request violates our usage policy.",
            },
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=False,
        spec104_class="configuracion",
        d023_quirk=True,
    ),
    FailurePayloadCase(
        id="anthropic_400_generico_param_invalido",
        table="input_filter",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "max_tokens: Field required",
            },
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=False,
        spec104_class="configuracion",
    ),
)


# ==================== Tabla 2: Ventana de contexto excedida ====================

CONTEXT_WINDOW_CASES: tuple[FailurePayloadCase, ...] = (
    FailurePayloadCase(
        id="azure_400_context_window_clasico",
        table="context_window",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": (
                    "This model's maximum context length is 128000 tokens. However, "
                    "your messages resulted in 140000 tokens."
                ),
                "type": "invalid_request_error",
                "param": "messages",
                "code": "context_length_exceeded",
            }
        },
        expected_exception="ContextWindowExceededError",
        expected_status_code=400,
        expected_body_preserved=False,
        spec104_class="entrada",
    ),
    # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
    FailurePayloadCase(
        id="azure_400_context_window_wording_nuevo",
        table="context_window",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": (
                    "Your input exceeds the context window of this model. Please "
                    "adjust your input and try again."
                ),
                "type": "invalid_request_error",
                "param": "input",
                "code": "context_length_exceeded",
            }
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="context_length_exceeded",
        spec104_class="entrada",
        d023_quirk=True,
    ),
    # Azure: BadRequestError con code=string_above_max_length (regla 3 -> configuracion)
    FailurePayloadCase(
        id="azure_400_string_too_long_above_max_length",
        table="context_window",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": (
                    "Invalid 'messages[0].content': string too long. Expected a "
                    "string with maximum length 1048576, but got a string with "
                    "length 2000000 instead."
                ),
                "type": "invalid_request_error",
                "param": "messages[0].content",
                "code": "string_above_max_length",
            }
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="string_above_max_length",
        spec104_class="configuracion",
    ),
    # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
    FailurePayloadCase(
        id="azure_400_maximum_context_length_otro_prefijo",
        table="context_window",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": "The maximum context length for this model is 128000 tokens.",
                "type": "invalid_request_error",
                "param": "messages",
                "code": "context_length_exceeded",
            }
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="context_length_exceeded",
        spec104_class="entrada",
        d023_quirk=True,
    ),
    FailurePayloadCase(
        id="openai_400_context_window_clasico",
        table="context_window",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": (
                    "This model's maximum context length is 128000 tokens. However, "
                    "your messages resulted in 140000 tokens."
                ),
                "type": "invalid_request_error",
                "param": "messages",
                "code": "context_length_exceeded",
            }
        },
        expected_exception="ContextWindowExceededError",
        expected_status_code=400,
        expected_body_preserved=False,
        spec104_class="entrada",
    ),
    # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
    FailurePayloadCase(
        id="openai_400_context_window_wording_nuevo",
        table="context_window",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": (
                    "Your input exceeds the context window of this model. Please "
                    "adjust your input and try again."
                ),
                "type": "invalid_request_error",
                "param": "input",
                "code": "context_length_exceeded",
            }
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=True,
        expected_body_code="context_length_exceeded",
        spec104_class="entrada",
        d023_quirk=True,
    ),
    FailurePayloadCase(
        id="openai_400_string_too_long_sin_code",
        table="context_window",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": (
                    "Invalid 'messages[0].content': string too long. Expected a "
                    "string with maximum length 1048576, but got 2000000."
                ),
                "type": "invalid_request_error",
                "param": "messages[0].content",
                "code": None,
            }
        },
        expected_exception="ContextWindowExceededError",
        expected_status_code=400,
        expected_body_preserved=False,
        spec104_class="entrada",
    ),
    # Con openai==3.57.0 el code no aparece en str(e), por lo que la exclusion
    # `string_above_max_length` de LiteLLM no se dispara y lanza ContextWindowExceededError.
    FailurePayloadCase(
        id="openai_400_string_too_long_con_code",
        table="context_window",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "error": {
                "message": (
                    "Invalid 'messages[0].content': string too long. Expected a "
                    "string with maximum length 1048576, but got 2000000."
                ),
                "type": "invalid_request_error",
                "param": "messages[0].content",
                "code": "string_above_max_length",
            }
        },
        expected_exception="ContextWindowExceededError",
        expected_status_code=400,
        expected_body_preserved=False,
        spec104_class="entrada",
    ),
    FailurePayloadCase(
        id="anthropic_400_prompt_is_too_long",
        table="context_window",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "prompt is too long: 205000 tokens > 200000 maximum",
            },
        },
        expected_exception="ContextWindowExceededError",
        expected_status_code=400,
        expected_body_preserved=False,
        spec104_class="entrada",
    ),
    FailurePayloadCase(
        id="anthropic_400_exceed_context_limit",
        table="context_window",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_error",
        status_code=400,
        headers=dict(JSON_HEADERS),
        body={
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": (
                    "input length and `max_tokens` exceed context limit: "
                    "190000 + 16000 > 200000, decrease input length or "
                    "`max_tokens` and try again"
                ),
            },
        },
        expected_exception="ContextWindowExceededError",
        expected_status_code=400,
        expected_body_preserved=False,
        spec104_class="entrada",
    ),
    FailurePayloadCase(
        id="anthropic_413_request_too_large",
        table="context_window",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_error",
        status_code=413,
        headers=dict(JSON_HEADERS),
        body={
            "type": "error",
            "error": {
                "type": "request_too_large",
                "message": "Request exceeds the maximum size",
            },
        },
        expected_exception="BadRequestError",
        expected_status_code=400,
        expected_body_preserved=False,
        spec104_class="entrada",
    ),
    # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
    # Segun SPEC-104 "Limites conocidos", con texto parcial se evalua como completa ("ok").
    FailurePayloadCase(
        id="anthropic_200_model_context_window_exceeded",
        table="context_window",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_anth_200_body(
            [{"type": "text", "text": "Hit ctx limit"}],
            "model_context_window_exceeded",
        ),
        expected_finish_reason="stop",
        expected_content="Hit ctx limit",
        expected_refusal=None,
        expected_has_refusal_attr=False,
        spec104_class="ok",
        d023_quirk=True,
    ),
)


# ==================== Tabla 3: Respuestas HTTP 200 ====================

HTTP_200_CASES: tuple[FailurePayloadCase, ...] = (
    FailurePayloadCase(
        id="azure_200_normal",
        table="http_200",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body({"role": "assistant", "content": "Hello", "refusal": None}, "stop"),
        expected_finish_reason="stop",
        expected_content="Hello",
        expected_refusal=None,
        expected_has_refusal_attr=True,
        spec104_class="ok",
    ),
    FailurePayloadCase(
        id="azure_200_content_filter_vacio",
        table="http_200",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body(
            {"role": "assistant", "content": None, "refusal": None},
            "content_filter",
            extra_choice={
                "content_filter_results": {"hate": {"filtered": True, "severity": "high"}}
            },
            extra_root={
                "prompt_filter_results": [{"prompt_index": 0, "content_filter_results": {}}]
            },
        ),
        expected_finish_reason="content_filter",
        expected_content=None,
        expected_refusal=None,
        expected_has_refusal_attr=True,
        expected_choice_psf={
            "content_filter_results": {"hate": {"filtered": True, "severity": "high"}}
        },
        spec104_class="filtro_salida",
    ),
    FailurePayloadCase(
        id="azure_200_content_filter_parcial",
        table="http_200",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body(
            {"role": "assistant", "content": "Partial output before filter", "refusal": None},
            "content_filter",
            extra_choice={
                "content_filter_results": {"violence": {"filtered": True, "severity": "medium"}}
            },
        ),
        expected_finish_reason="content_filter",
        expected_content="Partial output before filter",
        expected_refusal=None,
        expected_has_refusal_attr=True,
        expected_choice_psf={
            "content_filter_results": {"violence": {"filtered": True, "severity": "medium"}}
        },
        spec104_class="filtro_salida",
    ),
    FailurePayloadCase(
        id="azure_200_refusal",
        table="http_200",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body(
            {
                "role": "assistant",
                "content": None,
                "refusal": "I'm sorry, I can't assist with that.",
            },
            "stop",
        ),
        expected_finish_reason="stop",
        expected_content=None,
        expected_refusal="I'm sorry, I can't assist with that.",
        expected_has_refusal_attr=True,
        spec104_class="filtro_salida",
    ),
    FailurePayloadCase(
        id="azure_200_length_vacio",
        table="http_200",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body({"role": "assistant", "content": None, "refusal": None}, "length"),
        expected_finish_reason="length",
        expected_content=None,
        expected_refusal=None,
        expected_has_refusal_attr=True,
        spec104_class="presupuesto",
    ),
    FailurePayloadCase(
        id="azure_200_length_parcial",
        table="http_200",
        provider="azure",
        model=PROVIDER_KWARGS["azure"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body(
            {"role": "assistant", "content": "Cut off mid-sent", "refusal": None}, "length"
        ),
        expected_finish_reason="length",
        expected_content="Cut off mid-sent",
        expected_refusal=None,
        expected_has_refusal_attr=True,
        spec104_class="presupuesto",
    ),
    FailurePayloadCase(
        id="openai_200_normal",
        table="http_200",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body({"role": "assistant", "content": "Hello", "refusal": None}, "stop"),
        expected_finish_reason="stop",
        expected_content="Hello",
        expected_refusal=None,
        expected_has_refusal_attr=True,
        spec104_class="ok",
    ),
    FailurePayloadCase(
        id="openai_200_refusal_content_none",
        table="http_200",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body(
            {"role": "assistant", "content": None, "refusal": "I cannot help with that."},
            "stop",
        ),
        expected_finish_reason="stop",
        expected_content=None,
        expected_refusal="I cannot help with that.",
        expected_has_refusal_attr=True,
        spec104_class="filtro_salida",
    ),
    FailurePayloadCase(
        id="openai_200_refusal_content_vacio",
        table="http_200",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body(
            {"role": "assistant", "content": "", "refusal": "I cannot help with that."},
            "stop",
        ),
        expected_finish_reason="stop",
        expected_content="",
        expected_refusal="I cannot help with that.",
        expected_has_refusal_attr=True,
        spec104_class="filtro_salida",
    ),
    FailurePayloadCase(
        id="openai_200_content_filter_vacio",
        table="http_200",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body(
            {"role": "assistant", "content": None, "refusal": None}, "content_filter"
        ),
        expected_finish_reason="content_filter",
        expected_content=None,
        expected_refusal=None,
        expected_has_refusal_attr=True,
        spec104_class="filtro_salida",
    ),
    FailurePayloadCase(
        id="openai_200_length_vacio",
        table="http_200",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body({"role": "assistant", "content": None, "refusal": None}, "length"),
        expected_finish_reason="length",
        expected_content=None,
        expected_refusal=None,
        expected_has_refusal_attr=True,
        spec104_class="presupuesto",
    ),
    # Payload de Part 6 (probe_part6.orig.py): sin clave "refusal" en message -> attr ausente
    FailurePayloadCase(
        id="openai_200_length_parcial",
        table="http_200",
        provider="openai",
        model=PROVIDER_KWARGS["openai"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_oai_200_body({"role": "assistant", "content": "Partial..."}, "length"),
        expected_finish_reason="length",
        expected_content="Partial...",
        expected_refusal=None,
        expected_has_refusal_attr=False,
        spec104_class="presupuesto",
    ),
    FailurePayloadCase(
        id="anthropic_200_refusal_vacio",
        table="http_200",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_anth_200_body([], "refusal"),
        expected_finish_reason="content_filter",
        expected_content=None,
        expected_refusal=None,
        expected_has_refusal_attr=False,
        expected_message_psf_subset={"stop_reason": "refusal"},
        spec104_class="filtro_salida",
    ),
    FailurePayloadCase(
        id="anthropic_200_refusal_con_texto_y_stop_details",
        table="http_200",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_anth_200_body(
            [{"type": "text", "text": "I can't assist with that."}],
            "refusal",
            extra_root={
                "stop_details": {
                    "type": "refusal",
                    "category": "cyber",
                    "explanation": "policy",
                }
            },
        ),
        expected_finish_reason="content_filter",
        expected_content="I can't assist with that.",
        expected_refusal=None,
        expected_has_refusal_attr=False,
        expected_message_psf_subset={
            "stop_reason": "refusal",
            "stop_details": {
                "type": "refusal",
                "category": "cyber",
                "explanation": "policy",
            },
        },
        spec104_class="filtro_salida",
    ),
    FailurePayloadCase(
        id="anthropic_200_max_tokens_vacio",
        table="http_200",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_anth_200_body([], "max_tokens"),
        expected_finish_reason="length",
        expected_content=None,
        expected_refusal=None,
        expected_has_refusal_attr=False,
        spec104_class="presupuesto",
    ),
    FailurePayloadCase(
        id="anthropic_200_max_tokens_solo_thinking",
        table="http_200",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_anth_200_body(
            [{"type": "thinking", "thinking": "Let me think...", "signature": "sig"}],
            "max_tokens",
        ),
        expected_finish_reason="length",
        expected_content=None,
        expected_refusal=None,
        expected_has_refusal_attr=False,
        expected_message_psf_subset={
            "thinking_blocks": [
                {"type": "thinking", "thinking": "Let me think...", "signature": "sig"}
            ]
        },
        spec104_class="presupuesto",
    ),
    FailurePayloadCase(
        id="anthropic_200_max_tokens_parcial",
        table="http_200",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_anth_200_body([{"type": "text", "text": "Partial answer"}], "max_tokens"),
        expected_finish_reason="length",
        expected_content="Partial answer",
        expected_refusal=None,
        expected_has_refusal_attr=False,
        spec104_class="presupuesto",
    ),
    FailurePayloadCase(
        id="anthropic_200_end_turn_vacio",
        table="http_200",
        provider="anthropic",
        model=PROVIDER_KWARGS["anthropic"]["model"],
        case_type="http_200",
        status_code=200,
        headers=dict(JSON_HEADERS),
        body=_anth_200_body([], "end_turn"),
        expected_finish_reason="stop",
        expected_content=None,
        expected_refusal=None,
        expected_has_refusal_attr=False,
        spec104_class="sin_texto",
    ),
)


# ==================== Tabla 4: Matriz de reintentos por error y proveedor ====================
# Exactamente los 20 errores x 3 proveedores de probe_litellm_spec104.orig.py.

_RETRY_SHARED_HTTP_PAYLOADS: dict[str, tuple[int, dict[str, Any]]] = {
    "400_generic": (400, {"error": {"message": "bad param", "type": "invalid_request_error"}}),
    "401_auth": (401, {"error": {"message": "Invalid API key", "type": "authentication_error"}}),
    "403_perm": (403, {"error": {"message": "Forbidden", "type": "permission_error"}}),
    "404_not_found": (404, {"error": {"message": "Not found", "type": "not_found_error"}}),
    "408_timeout_http": (408, {"error": {"message": "Request timeout"}}),
    "409_conflict": (409, {"error": {"message": "Conflict"}}),
    "413_too_large": (413, {"error": {"message": "Request too large"}}),
    "422_unprocessable": (422, {"error": {"message": "Unprocessable"}}),
    "429_rate_limit": (
        429,
        {"error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}},
    ),
    "500_internal": (500, {"error": {"message": "Internal server error", "type": "api_error"}}),
    "502_bad_gateway": (502, {"error": {"message": "Bad gateway"}}),
    "503_unavailable": (503, {"error": {"message": "Service unavailable"}}),
    "504_gw_timeout": (504, {"error": {"message": "Gateway timeout"}}),
    "529_overloaded": (
        529,
        {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
    ),
}

_RETRY_PROVIDER_400_PAYLOADS: dict[tuple[ProviderName, str], tuple[int, dict[str, Any]]] = {
    ("azure", "400_content_filter"): (
        400,
        {
            "error": {
                "message": (
                    "The response was filtered due to the prompt triggering Azure "
                    "OpenAI's content management policy."
                ),
                "code": "content_filter",
                "innererror": {"code": "ResponsibleAIPolicyViolation"},
            }
        },
    ),
    ("openai", "400_content_filter"): (
        400,
        {
            "error": {
                "message": "Your request was rejected as a result of our safety system.",
                "type": "invalid_request_error",
                "code": "content_policy_violation",
            }
        },
    ),
    ("anthropic", "400_content_filter"): (
        400,
        {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Output blocked by content filtering policy",
            },
        },
    ),
    ("azure", "400_context_window"): (
        400,
        {
            "error": {
                "message": "This model's maximum context length is 128000 tokens.",
                "type": "invalid_request_error",
                "code": "context_length_exceeded",
            }
        },
    ),
    ("openai", "400_context_window"): (
        400,
        {
            "error": {
                "message": "This model's maximum context length is 128000 tokens.",
                "type": "invalid_request_error",
                "code": "context_length_exceeded",
            }
        },
    ),
    ("anthropic", "400_context_window"): (
        400,
        {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "prompt is too long: 205000 tokens > 200000 maximum",
            },
        },
    ),
}

_RETRY_TRANSPORT_ERRORS: dict[str, tuple[str, str]] = {
    "read_timeout": ("ReadTimeout", "timed out"),
    "connect_timeout": ("ConnectTimeout", "connect timed out"),
    "connect_error": ("ConnectError", "connection refused"),
    "remote_protocol_error": ("RemoteProtocolError", "peer closed"),
}

# Especificacion por (provider, slug):
#   (expected_exception, expected_status_code, returns_none, body_preserved,
#    body_code, exc_psf_innererror_code, spec104_class, calls_dict, d023_quirk)
_CALLS_1_1_4_4 = {"default": 1, "num_retries_0": 1, "num_retries_3": 4}
_CALLS_3_1_7_7 = {"default": 3, "num_retries_0": 1, "num_retries_3": 7}
# OpenAI 422: con drop_params=True devuelve None tras 2 intentos.
_CALLS_OPENAI_422 = {"default": 2, "num_retries_0": 2, "num_retries_3": 2}

_RETRY_SPECS: tuple[
    tuple[
        ProviderName,
        str,
        str | None,
        int | None,
        bool,
        bool | None,
        str | None,
        str | None,
        Spec104Class,
        dict[str, int],
        bool,
    ],
    ...,
] = (
    # --- Azure (20) ---
    (
        "azure",
        "400_generic",
        "BadRequestError",
        400,
        False,
        True,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "azure",
        "400_content_filter",
        "ContentPolicyViolationError",
        400,
        False,
        True,
        "content_filter",
        "ResponsibleAIPolicyViolation",
        "entrada",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "azure",
        "400_context_window",
        "ContextWindowExceededError",
        400,
        False,
        False,
        None,
        None,
        "entrada",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "azure",
        "401_auth",
        "AuthenticationError",
        401,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "azure",
        "403_perm",
        "APIError",
        403,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "azure",
        "404_not_found",
        "NotFoundError",
        404,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "azure",
        "408_timeout_http",
        "Timeout",
        408,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "azure",
        "409_conflict",
        "APIError",
        409,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "azure",
        "413_too_large",
        "APIError",
        413,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "azure",
        "422_unprocessable",
        "BadRequestError",
        422,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "azure",
        "429_rate_limit",
        "RateLimitError",
        429,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "azure",
        "500_internal",
        "InternalServerError",
        500,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "azure",
        "502_bad_gateway",
        "BadGatewayError",
        502,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "azure",
        "503_unavailable",
        "ServiceUnavailableError",
        503,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "azure",
        "504_gw_timeout",
        "Timeout",
        504,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "azure",
        "529_overloaded",
        "APIError",
        529,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "azure",
        "read_timeout",
        "Timeout",
        408,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "azure",
        "connect_timeout",
        "Timeout",
        408,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "azure",
        "connect_error",
        "APIConnectionError",
        500,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "azure",
        "remote_protocol_error",
        "APIConnectionError",
        500,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    # --- OpenAI (20) ---
    (
        "openai",
        "400_generic",
        "BadRequestError",
        400,
        False,
        True,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "openai",
        "400_content_filter",
        "BadRequestError",
        400,
        False,
        True,
        "content_policy_violation",
        None,
        "entrada",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "openai",
        "400_context_window",
        "ContextWindowExceededError",
        400,
        False,
        False,
        None,
        None,
        "entrada",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "openai",
        "401_auth",
        "AuthenticationError",
        401,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "openai",
        "403_perm",
        "APIError",
        403,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "openai",
        "404_not_found",
        "NotFoundError",
        404,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "openai",
        "408_timeout_http",
        "Timeout",
        408,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "openai",
        "409_conflict",
        "APIError",
        409,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    # En OpenAI el mensaje "Request too large" matchea RateLimitError en LiteLLM -> infraestructura
    (
        "openai",
        "413_too_large",
        "RateLimitError",
        429,
        False,
        True,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        True,
    ),
    # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
    # (con drop_params=True devuelve None)
    (
        "openai",
        "422_unprocessable",
        None,
        None,
        True,
        None,
        None,
        None,
        "configuracion",
        _CALLS_OPENAI_422,
        True,
    ),
    (
        "openai",
        "429_rate_limit",
        "RateLimitError",
        429,
        False,
        True,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "openai",
        "500_internal",
        "InternalServerError",
        500,
        False,
        True,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "openai",
        "502_bad_gateway",
        "BadGatewayError",
        502,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "openai",
        "503_unavailable",
        "ServiceUnavailableError",
        503,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "openai",
        "504_gw_timeout",
        "Timeout",
        504,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "openai",
        "529_overloaded",
        "APIError",
        529,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "openai",
        "read_timeout",
        "Timeout",
        408,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "openai",
        "connect_timeout",
        "Timeout",
        408,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "openai",
        "connect_error",
        "InternalServerError",
        500,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    (
        "openai",
        "remote_protocol_error",
        "InternalServerError",
        500,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_3_1_7_7,
        True,
    ),
    # --- Anthropic (20) ---
    (
        "anthropic",
        "400_generic",
        "BadRequestError",
        400,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "anthropic",
        "400_content_filter",
        "ContentPolicyViolationError",
        400,
        False,
        False,
        None,
        None,
        "entrada",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "anthropic",
        "400_context_window",
        "ContextWindowExceededError",
        400,
        False,
        False,
        None,
        None,
        "entrada",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "anthropic",
        "401_auth",
        "AuthenticationError",
        401,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "anthropic",
        "403_perm",
        "PermissionDeniedError",
        403,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "anthropic",
        "404_not_found",
        "NotFoundError",
        404,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "anthropic",
        "408_timeout_http",
        "Timeout",
        408,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
    # En Anthropic 409 llega como BadRequestError(status_code=409);
    # hereda de openai.APIError -> regla 2 (infraestructura)
    (
        "anthropic",
        "409_conflict",
        "BadRequestError",
        409,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
    # Payload generico "Request too large" (sin "request_too_large") ->
    # BadRequestError -> configuracion
    (
        "anthropic",
        "413_too_large",
        "BadRequestError",
        400,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "anthropic",
        "422_unprocessable",
        "BadRequestError",
        422,
        False,
        False,
        None,
        None,
        "configuracion",
        _CALLS_1_1_4_4,
        True,
    ),
    (
        "anthropic",
        "429_rate_limit",
        "RateLimitError",
        429,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
    (
        "anthropic",
        "500_internal",
        "InternalServerError",
        500,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
    (
        "anthropic",
        "502_bad_gateway",
        "BadGatewayError",
        502,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
    (
        "anthropic",
        "503_unavailable",
        "ServiceUnavailableError",
        503,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
    (
        "anthropic",
        "504_gw_timeout",
        "Timeout",
        504,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
    (
        "anthropic",
        "529_overloaded",
        "InternalServerError",
        500,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
    (
        "anthropic",
        "read_timeout",
        "Timeout",
        408,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
    (
        "anthropic",
        "connect_timeout",
        "Timeout",
        408,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
    (
        "anthropic",
        "connect_error",
        "InternalServerError",
        500,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
    (
        "anthropic",
        "remote_protocol_error",
        "InternalServerError",
        500,
        False,
        False,
        None,
        None,
        "infraestructura",
        _CALLS_1_1_4_4,
        False,
    ),
)


def _build_retry_case(
    spec: tuple[
        ProviderName,
        str,
        str | None,
        int | None,
        bool,
        bool | None,
        str | None,
        str | None,
        Spec104Class,
        dict[str, int],
        bool,
    ],
) -> FailurePayloadCase:
    (
        provider,
        slug,
        exc_name,
        exc_status,
        returns_none,
        body_preserved,
        body_code,
        psf_inner_code,
        spec104_class,
        calls,
        d023_quirk,
    ) = spec
    case_id = f"{provider}_retry_{slug}"
    model = PROVIDER_KWARGS[provider]["model"]
    if slug in _RETRY_TRANSPORT_ERRORS:
        t_type, t_msg = _RETRY_TRANSPORT_ERRORS[slug]
        return FailurePayloadCase(
            id=case_id,
            table="retry",
            provider=provider,
            model=model,
            case_type="transport_error",
            transport_exc_type=t_type,
            transport_exc_message=t_msg,
            expected_exception=exc_name,
            expected_status_code=exc_status,
            returns_none=returns_none,
            expected_body_preserved=body_preserved,
            expected_body_code=body_code,
            expected_exc_psf_innererror_code=psf_inner_code,
            spec104_class=spec104_class,
            expected_http_calls=dict(calls),
            d023_quirk=d023_quirk,
        )
    pair = _RETRY_PROVIDER_400_PAYLOADS.get((provider, slug))
    if pair is None:
        pair = _RETRY_SHARED_HTTP_PAYLOADS[slug]
    status_code, payload = pair
    return FailurePayloadCase(
        id=case_id,
        table="retry",
        provider=provider,
        model=model,
        case_type="http_error",
        status_code=status_code,
        headers=dict(JSON_HEADERS),
        body=payload,
        expected_exception=exc_name,
        expected_status_code=exc_status,
        returns_none=returns_none,
        expected_body_preserved=body_preserved,
        expected_body_code=body_code,
        expected_exc_psf_innererror_code=psf_inner_code,
        spec104_class=spec104_class,
        expected_http_calls=dict(calls),
        d023_quirk=d023_quirk,
    )


RETRY_CASES: tuple[FailurePayloadCase, ...] = tuple(_build_retry_case(s) for s in _RETRY_SPECS)

ALL_HTTP_200_CASES: tuple[FailurePayloadCase, ...] = (
    *HTTP_200_CASES,
    *(c for c in CONTEXT_WINDOW_CASES if c.case_type == "http_200"),
)

ALL_FAILURE_CASES: tuple[FailurePayloadCase, ...] = (
    *INPUT_FILTER_CASES,
    *CONTEXT_WINDOW_CASES,
    *HTTP_200_CASES,
    *RETRY_CASES,
)

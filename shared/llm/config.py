"""
LLM Configuration module.

Provides a unified configuration dataclass that works with both:
- dspy.LM (for dspy_gepa_poc)
- litellm.completion (for gepa_standalone)
"""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

# Same regex DSPy uses internally to detect reasoning models (o1/3/4/5, gpt-5 family).
# El sufijo de la familia gpt-5 admite tanto '-' (gpt-5-mini) como '.' para versiones
# menores con punto (gpt-5.4, gpt-5.4-mini): ambos exigen temperature=1.0.
_REASONING_MODEL_PATTERN = re.compile(
    r"^(?:o[1345](?:-(?:mini|nano|pro))?(?:-\d{4}-\d{2}-\d{2})?|gpt-5(?!-chat)(?:[.-].*)?)$"
)
_REASONING_TEMPERATURE = 1.0
_REASONING_MIN_MAX_TOKENS = 16000


def _is_reasoning(model: str) -> bool:
    return bool(_REASONING_MODEL_PATTERN.match(model.split("/")[-1].lower()))


# ==================== SPEC-103: matriz de soporte Anthropic (FR-001, FR-002) ====================
# Unico lugar del codigo que implementa la matriz de specs/SPEC-103-proveedor-anthropic.md.
# Esqueleto de la subfase 1b: la tabla es definitiva; las funciones las implementa 1c.

_ANTHROPIC_PREFIX = "anthropic/"
# Orden canonico de effort: se usa para listar valores aceptados y comparar contra
# off_max_effort. Los frozenset de la tabla no tienen orden.
_EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
_DEFAULT_EFFORT = "medium"
_THINKING_VALUES: tuple[str, ...] = ("default", "off")
_SNAPSHOT_SUFFIX = re.compile(r"-\d{8}$")

ReasoningDefault = Literal["off", "adaptive", "always"]
OffMechanism = Literal["noop", "disabled", "between_tools"]


@dataclass(frozen=True)
class AnthropicFamily:
    """
    Una fila de la matriz de soporte de SPEC-103.

    Attributes:
        aliases: IDs sin prefijo `anthropic/` ni sufijo de snapshot que comparten fila.
        sends_temperature: False = `temperature` se quita de los kwargs (FR-003).
        efforts: Valores de `output_config.effort` aceptados; None = el modelo no
            acepta effort y no se envia nada (FR-004).
        default_reasoning: Razonamiento si no se configura: "off" (apagado),
            "adaptive" o "always" (siempre activo). Con "adaptive"/"always" y
            thinking != "off" se eleva `max_tokens` (FR-006).
        off_mechanism: Que envia `LLM_THINKING_<ROL>=off`: "noop" (nada),
            "disabled" / "between_tools" (`thinking={"type": <valor>}`); None = no
            se permite apagar (error al validar, FR-005).
        off_max_effort: Tope de effort cuando thinking == "off" (comparado con
            `_EFFORTS`); None = sin tope. Solo tiene sentido si off_mechanism no es None.
    """

    aliases: tuple[str, ...]
    sends_temperature: bool
    efforts: frozenset[str] | None
    default_reasoning: ReasoningDefault
    off_mechanism: OffMechanism | None
    off_max_effort: str | None = None


_EFFORTS_LOW_HIGH = frozenset({"low", "medium", "high"})
_EFFORTS_LOW_MAX_NO_XHIGH = frozenset({"low", "medium", "high", "max"})
_EFFORTS_ALL = frozenset(_EFFORTS)

ANTHROPIC_FAMILIES: tuple[AnthropicFamily, ...] = (
    AnthropicFamily(("claude-haiku-4-5",), True, None, "off", "noop"),
    AnthropicFamily(("claude-opus-4-5",), True, _EFFORTS_LOW_HIGH, "off", "noop"),
    AnthropicFamily(("claude-sonnet-4-6",), True, _EFFORTS_LOW_MAX_NO_XHIGH, "off", "noop"),
    AnthropicFamily(("claude-opus-4-6",), True, _EFFORTS_LOW_MAX_NO_XHIGH, "off", "noop"),
    AnthropicFamily(("claude-opus-4-7", "claude-opus-4-8"), False, _EFFORTS_ALL, "off", "noop"),
    AnthropicFamily(("claude-sonnet-5",), False, _EFFORTS_ALL, "adaptive", "disabled"),
    AnthropicFamily(("claude-opus-5",), False, _EFFORTS_ALL, "adaptive", "disabled", "high"),
    AnthropicFamily(("claude-haiku-5-5",), False, _EFFORTS_ALL, "adaptive", "disabled", "high"),
    AnthropicFamily(
        ("claude-sonnet-5-5",), False, _EFFORTS_ALL, "adaptive", "between_tools", "high"
    ),
    AnthropicFamily(("claude-opus-5-5",), False, _EFFORTS_ALL, "adaptive", None),
    AnthropicFamily(
        ("claude-fable-5", "claude-fable-5-1", "claude-fable-5-2"),
        False,
        _EFFORTS_ALL,
        "always",
        None,
    ),
)


def _is_anthropic(model: str) -> bool:
    """
    True si `model` usa el proveedor Anthropic directo (prefijo `anthropic/`).

    La rama Anthropic de `apply_constraints` y los avisos de `validate()` se
    activan solo con este prefijo; IDs `claude-*` sin prefijo no se tratan como
    Anthropic en el armado de kwargs (FR-001 habla de `anthropic/<id>`).
    """
    raise NotImplementedError("SPEC-103 1c")


def resolve_anthropic_family(model: str) -> AnthropicFamily | None:
    """
    Resuelve un ID de modelo a su fila de la matriz (D2).

    Pasos: quitar el prefijo `anthropic/` si esta; si queda otro prefijo con "/"
    (p. ej. `azure/...`) devolver None; quitar un sufijo de snapshot `-YYYYMMDD`
    (`_SNAPSHOT_SUFFIX`, exactamente 8 digitos al final); buscar coincidencia
    exacta en `AnthropicFamily.aliases`. Sin prefijos parciales:
    `claude-opus-5` no resuelve `claude-opus-5-5`, y `claude-opus-5-5-preview` o
    `claude-opus-5-5-2026` devuelven None. Acepta IDs sin prefijo (lo usa
    `normalize_model` en 3b para precios).

    Returns:
        La instancia de `ANTHROPIC_FAMILIES` (misma identidad para alias,
        alias compartidos y snapshots de una fila) o None fuera de la matriz.
    """
    raise NotImplementedError("SPEC-103 1c")


@dataclass
class LLMConfig:
    """
    Unified LLM configuration compatible with DSPy and LiteLLM.

    Attributes:
        model: Model identifier in LiteLLM format (e.g., "azure/gpt-4o", "openai/gpt-4o-mini")
        api_key: API key for authentication
        api_base: Base URL for the API endpoint (required for Azure)
        api_version: API version (for Azure OpenAI)
        temperature: Sampling temperature (0.0 - 2.0)
        max_tokens: Maximum tokens in response
    """

    model: str
    api_key: str | None = None
    api_base: str | None = None
    api_version: str = "2024-02-15-preview"
    temperature: float = 0.7
    max_tokens: int = 1000
    cache: bool = False  # DSPy LM cache (True = cachea respuestas, False = resultados frescos)
    # Timeout por request en segundos. Evita cuelgues indefinidos con reasoning models
    # (gpt-5-mini/gpt-5), que ocasionalmente no devuelven respuesta (D-016). None = sin
    # limite. Default alto (600s): no corta requests legitimas, solo cuelgues reales.
    timeout: float | None = 600.0

    @property
    def is_reasoning_model(self) -> bool:
        """True when the model requires temperature=1.0 and max_tokens>=16000."""
        return _is_reasoning(self.model)

    def apply_reasoning_constraints(self, kwargs: dict) -> dict:
        """
        Enforce reasoning model parameter requirements on an already-built kwargs dict.

        Safe to call on non-reasoning models (returns kwargs unchanged).
        Used by to_kwargs() and call_llm() to re-apply after manual overrides.
        """
        if not self.is_reasoning_model:
            return kwargs
        kwargs["temperature"] = _REASONING_TEMPERATURE
        if (kwargs.get("max_tokens") or 0) < _REASONING_MIN_MAX_TOKENS:
            kwargs["max_tokens"] = _REASONING_MIN_MAX_TOKENS
        return kwargs

    def apply_constraints(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """
        Punto unico de restricciones por modelo (SPEC-103 D4, FR-002 a FR-007).

        Reemplaza a `apply_reasoning_constraints` (1c renombra sus usos y la borra).
        Devuelve un dict NUEVO; nunca muta `kwargs`. Es idempotente:
        `apply_constraints(apply_constraints(k)) == apply_constraints(k)`, asi los
        llamadores pueden partir de `to_kwargs()`, aplicar overrides por llamada
        (`temperature`, `max_tokens`) y volver a llamarla.

        Antes de transformar llama a `_check_params()` (misma regla que
        `validate()`, sin avisos): ningun camino envia una combinacion invalida
        aunque el entry point no haya llamado a `validate()`.

        - Rama OpenAI/Azure (no `anthropic/`): conducta actual de reasoning models
          (temperature=1.0, max_tokens>=16000); el resto intacto (SC-006). effort y
          thinking no se envian.
        - Rama `anthropic/` (siempre): quita `api_base` y `api_version` (FR-007).
        - Rama `anthropic/` en la matriz (familia resuelta):
          1. quita `temperature` si `not family.sends_temperature` (FR-003);
          2. si `family.efforts` no es None: `output_config={"effort": effort or
             "medium"}` (FR-004; nunca `reasoning_effort`);
          3. si thinking == "off" y off_mechanism es "disabled"/"between_tools":
             `thinking={"type": off_mechanism}` (FR-005; "noop" no envia nada);
          4. si default_reasoning != "off" y thinking != "off": `max_tokens =
             max(max_tokens or 0, _REASONING_MIN_MAX_TOKENS)` (FR-006).
        - Rama `anthropic/` fuera de la matriz: solo lo de FR-007 (sin restricciones,
          effort/thinking no se envian; FR-001).

        Raises:
            LLMConfigError: si effort/thinking son invalidos para el modelo.
        """
        raise NotImplementedError("SPEC-103 1c")

    def effective_params(self, max_tokens: int | None = None) -> dict[str, Any]:
        """
        Parametros efectivos que se envian (SPEC-103 D6, FR-010, FR-012).

        Arma los kwargs base (sin restricciones), aplica `max_tokens` por llamada si
        viene (valor del adapter, FR-010) y despues `apply_constraints`. Lo usan
        `describe()` (4a) y `collect_model_info` (4b).

        Returns:
            Dict con claves fijas:
            - model: ID tal cual se configuro.
            - temperature: valor enviado; None si se omite.
            - temperature_requested: valor de config.
            - temperature_omitted: True si la familia no la envia.
            - effort: valor de `output_config.effort` enviado; None si no se envia.
            - thinking: modo de razonamiento efectivo: "adaptive", "always" u "off";
              None si no se sabe (OpenAI/Azure no reasoning o `anthropic/` fuera de
              la matriz). Para OpenAI reasoning models: "always".
            - thinking_param: dict `thinking` enviado o None.
            - max_tokens: valor enviado (tras FR-006).
            - max_tokens_requested: `max_tokens` del argumento o, si es None, de config.
        """
        raise NotImplementedError("SPEC-103 1c")

    def describe(self) -> str:
        """
        Return a formatted description of effective LM config for startup logging.

        Shows model name, reasoning model flag, and effective temperature/max_tokens
        with override notes when reasoning constraints changed the requested values.
        """
        effective = self.to_kwargs()
        tag = " [reasoning model]" if self.is_reasoning_model else ""
        lines = [f"{self.model}{tag}"]

        temp_eff = effective["temperature"]
        if self.is_reasoning_model and self.temperature != temp_eff:
            lines.append(
                f"    temperature: {self.temperature} (config) -> {temp_eff} (reasoning override)"
            )
        else:
            lines.append(f"    temperature: {temp_eff}")

        tok_eff = effective["max_tokens"]
        if self.is_reasoning_model and self.max_tokens != tok_eff:
            lines.append(
                f"    max_tokens:  {self.max_tokens} (config) -> {tok_eff} (reasoning override)"
            )
        else:
            lines.append(f"    max_tokens:  {tok_eff}")

        return "\n".join(lines)

    @classmethod
    def from_env(cls, model_name: str = "task", load_env: bool = True, **overrides) -> "LLMConfig":
        """
        Load configuration from environment variables.

        Args:
            model_name: Name of the model to load (e.g., "task", "reflection", "embedding").
                       Reads from LLM_MODEL_{NAME} environment variable.
            load_env: If True, attempts to load .env files automatically.
            **overrides: Override any config attribute.

        Returns:
            LLMConfig instance with values from environment.

        Precedencia (de mayor a menor): variables YA presentes en el entorno
        (proceso/CI) > `LLM_ENV_FILE` (ruta explicita a un .env) > `.env` del
        directorio actual > defaults. `load_dotenv` usa override=False, asi que lo
        que ya esta en el entorno nunca se pisa.

        Esta funcion es codigo COMPARTIDO: NO conoce los subproyectos. Cada
        subproyecto carga su propio `.env` al importar su `config.py`
        (`load_dotenv(_ENV_FILE)`), por lo que al llegar aca sus variables ya estan
        en el entorno. El antiguo fallback que probaba subdirectorios por nombre
        (`gepa_standalone`, `dspy_gepa_poc`) acoplaba shared/ a los subproyectos y,
        corriendo desde la raiz, cargaba el `.env` equivocado (bug de precedencia):
        se reemplazo por `LLM_ENV_FILE`, un override explicito y sin nombres.
        """
        if load_env:
            from dotenv import load_dotenv

            # 1. .env del directorio actual (conveniencia; no pisa el entorno).
            load_dotenv()

            # 2. Override explicito por ruta (sin hardcodear subproyectos): util para
            #    herramientas que corren desde la raiz sin importar el config de un
            #    subproyecto. Solo si todavia falta la API key.
            if not os.getenv("LLM_API_KEY"):
                env_file = os.getenv("LLM_ENV_FILE")
                if env_file and os.path.exists(env_file):
                    load_dotenv(env_file)

        model_var = f"LLM_MODEL_{model_name.upper()}"

        config = cls(
            model=os.getenv(model_var, "azure/gpt-4.1-mini"),
            api_key=os.getenv("LLM_API_KEY"),
            api_base=os.getenv("LLM_API_BASE"),
            api_version=os.getenv("LLM_API_VERSION", "2024-02-15-preview"),
        )
        config.cache = os.getenv("LLM_CACHE", "false").lower() == "true"
        # Timeout por request (segundos). LLM_TIMEOUT=0 (o invalido) -> sin limite (None).
        try:
            _timeout = float(os.getenv("LLM_TIMEOUT", "600"))
            config.timeout = _timeout if _timeout > 0 else None
        except ValueError:
            config.timeout = 600.0

        # Apply overrides
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        return config

    def to_kwargs(self) -> dict[str, Any]:
        """
        Convert config to kwargs dict for LLM calls.

        Reasoning model constraints (temperature=1.0, max_tokens>=16000) are applied
        automatically when the model matches the reasoning model pattern.

        Returns:
            Dictionary with non-None values suitable for litellm.completion.
            DSPy-specific params (cache) are added in get_dspy_lm().
        """
        kwargs = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_version:
            kwargs["api_version"] = self.api_version
        if self.timeout:
            kwargs["timeout"] = self.timeout

        return self.apply_reasoning_constraints(kwargs)

    def get_dspy_lm(self):
        """
        Get a configured dspy.LM instance.

        For use in dspy_gepa_poc project.

        Returns:
            dspy.LM instance configured with this config.
        """
        import dspy

        kwargs = self.to_kwargs()
        kwargs["cache"] = self.cache
        return dspy.LM(**kwargs)

    def get_lm_function(self, role: str = "task") -> Callable[[str], str]:
        """
        Get a simple LM function for GEPA.

        For use in gepa_standalone project. Uses LiteLLM directly without DSPy.

        Args:
            role: Usage bucket for token tracking ("task" or "reflection").

        Returns:
            Function that takes a prompt string and returns the response string.
        """
        import litellm

        from .usage import record_usage

        litellm.drop_params = True
        kwargs = self.to_kwargs()

        def lm_func(prompt: str) -> str:
            """Call LLM with prompt and return response text."""
            response = litellm.completion(messages=[{"role": "user", "content": prompt}], **kwargs)
            record_usage(role, response)
            return response.choices[0].message.content

        return lm_func

    def validate(self) -> None:
        """
        Validate that required configuration is present.

        Raises:
            ValueError: If required configuration is missing.
        """
        from .errors import LLMConnectionError

        missing = []
        if not self.api_key:
            missing.append("LLM_API_KEY")
        if not self.model:
            missing.append("LLM_MODEL_*")

        # Azure requires api_base
        if self.model.startswith("azure/") and not self.api_base:
            missing.append("LLM_API_BASE (required for Azure)")

        if missing:
            raise LLMConnectionError(
                message="Missing required configuration",
                provider=self.model.split("/")[0] if "/" in self.model else "unknown",
                model=self.model,
                endpoint=self.api_base,
                api_version=self.api_version,
                suggestions=[f"Set {var} in your .env file" for var in missing],
            )

    def validate_connection(self) -> bool:
        """
        Test the LLM connection with a minimal request.

        Returns:
            True if connection is successful.

        Raises:
            LLMConnectionError: If connection fails with diagnostic info.
        """
        import litellm

        from .errors import LLMConnectionError

        try:
            # Usar to_kwargs para evitar pasar parámetros None que rompen el logger de litellm
            litellm.drop_params = True
            kwargs = self.to_kwargs()
            # Use small max_tokens for the probe; reasoning models require >= 16000
            kwargs["max_tokens"] = _REASONING_MIN_MAX_TOKENS if self.is_reasoning_model else 5

            litellm.completion(
                messages=[{"role": "user", "content": "Respond only 'OK'"}], **kwargs
            )
            return True
        except Exception as e:
            error_str = str(e)
            provider = self.model.split("/")[0] if "/" in self.model else "unknown"

            def _truncate(value, limit: int = 500) -> str:
                try:
                    return str(value)[:limit]
                except Exception:
                    return "<unavailable>"

            response_obj = getattr(e, "response", None)
            response_text = (
                getattr(response_obj, "text", None) if response_obj is not None else None
            )
            extra_details = {
                "error_type": type(e).__name__,
                "error_repr": _truncate(repr(e)),
                "error_args": _truncate(getattr(e, "args", None)),
                "status_code": getattr(e, "status_code", None),
                "response_text": _truncate(response_text) if response_text else None,
                "response": _truncate(response_obj) if response_obj else None,
                "request_id": getattr(e, "request_id", None),
            }

            # Parse common errors
            suggestions = []
            if "Virtual Network" in error_str or "VNet" in error_str:
                message = "Azure endpoint requires VNet access"
                suggestions = [
                    "Connect to corporate VPN with VNet access",
                    "Verify your IP is allowed in Azure resource",
                ]
            elif "401" in error_str or "Unauthorized" in error_str:
                message = "Authentication failed - invalid API key"
                suggestions = [
                    "Verify LLM_API_KEY in .env file",
                    "Regenerate API key in Azure/OpenAI portal",
                ]
            elif "404" in error_str or "not found" in error_str.lower():
                message = "Model or deployment not found"
                suggestions = [
                    f"Verify deployment '{self.model}' exists",
                    "Check LLM_MODEL_* values in .env",
                ]
            elif "429" in error_str or "rate limit" in error_str.lower():
                message = "Rate limit exceeded"
                suggestions = [
                    "Wait a few minutes before retrying",
                    "Check quotas in Azure/OpenAI portal",
                ]
            else:
                message = "Connection failed"
                suggestions = [
                    "Check internet connection",
                    f"Verify endpoint: {self.api_base}",
                    "Review error details below",
                ]

            raise LLMConnectionError(
                message=message,
                provider=provider,
                model=self.model,
                endpoint=self.api_base,
                api_version=self.api_version,
                original_error=error_str[:500],
                extra_details=extra_details,
                suggestions=suggestions,
            ) from e

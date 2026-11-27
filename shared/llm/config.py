"""
LLM Configuration module.

Provides a unified configuration dataclass that works with both:
- dspy.LM (for dspy_gepa_poc)
- litellm.completion (for gepa_standalone)
"""

import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Same regex DSPy uses internally to detect reasoning models (o1/3/4/5, gpt-5 family).
# El sufijo de la familia gpt-5 admite tanto '-' (gpt-5-mini) como '.' para versiones
# menores con punto (gpt-5.4, gpt-5.4-mini): ambos exigen temperature=1.0.
_REASONING_MODEL_PATTERN = re.compile(
    r"^(?:o[1345](?:-(?:mini|nano|pro))?(?:-\d{4}-\d{2}-\d{2})?|gpt-5(?!-chat)(?:[.-].*)?)$"
)
_REASONING_TEMPERATURE = 1.0
_REASONING_MIN_MAX_TOKENS = 16000


def complete_text(kwargs: dict[str, Any], messages: list[dict[str, Any]], role: str) -> str:
    """
    Llamada comun a LiteLLM (SPEC-104, D3, FR-001): delega en `checked_completion`
    (`num_retries=0`, reintento propio de infraestructura, clasificacion de la
    respuesta con detalle en DEBUG).

    Es el camino de los tres lugares que llaman al LLM sin DSPy (`get_lm_function`,
    `call_llm` y el adapter de RAG); recibe los kwargs ya restringidos.
    """
    from .call import checked_completion

    return checked_completion(kwargs, messages, role)


def is_empty_text(content: Any) -> bool:
    """True si el contenido de una respuesta es None o queda vacio tras `strip()`."""
    return content is None or not str(content).strip()


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


def strip_snapshot_suffix(model: str) -> str:
    """Quita un sufijo de snapshot `-YYYYMMDD` (exactamente 8 digitos al final)."""
    return _SNAPSHOT_SUFFIX.sub("", model)


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


def provider_of(model: str) -> str:
    """
    Proveedor de un modelo (SPEC-106 D1): prefijo antes de la primera `/` en
    minusculas; sin `/` es `openai` (convencion de LiteLLM). Unica fuente del
    proveedor para `config.py`, `errors.py` y `dspy_lm.py`.
    """
    return model.split("/", 1)[0].lower() if "/" in model else "openai"


_PROVIDER_DEFAULT_HOSTS = {"openai": "api.openai.com", "anthropic": "api.anthropic.com"}


def _env(name: str) -> str | None:
    """Variable de entorno con `strip()`; vacia cuenta como no definida (FR-001)."""
    value = os.getenv(name)
    value = value.strip() if value else ""
    return value or None


def _is_anthropic(model: str) -> bool:
    """
    True si `model` usa el proveedor Anthropic directo (prefijo `anthropic/`).

    La rama Anthropic de `apply_constraints` y los avisos de `validate()` se
    activan solo con este prefijo; IDs `claude-*` sin prefijo no se tratan como
    Anthropic en el armado de kwargs (FR-001 habla de `anthropic/<id>`).
    """
    return model.startswith(_ANTHROPIC_PREFIX)


def resolve_anthropic_family(model: str) -> AnthropicFamily | None:
    """
    Resuelve un ID de modelo a su fila de la matriz (D2).

    Pasos: quitar el prefijo `anthropic/` si esta; si queda otro prefijo con "/"
    (p. ej. `azure/...`) devolver None; quitar un sufijo de snapshot `-YYYYMMDD`
    (`strip_snapshot_suffix`, exactamente 8 digitos al final); buscar coincidencia
    exacta en `AnthropicFamily.aliases`. Sin prefijos parciales:
    `claude-opus-5` no resuelve `claude-opus-5-5`, y `claude-opus-5-5-preview` o
    `claude-opus-5-5-2026` devuelven None. Acepta IDs sin prefijo (lo usa
    `normalize_model` en 3b para precios).

    Returns:
        La instancia de `ANTHROPIC_FAMILIES` (misma identidad para alias,
        alias compartidos y snapshots de una fila) o None fuera de la matriz.
    """
    if model.startswith(_ANTHROPIC_PREFIX):
        model = model[len(_ANTHROPIC_PREFIX) :]
    if "/" in model:
        return None
    model = strip_snapshot_suffix(model)
    for family in ANTHROPIC_FAMILIES:
        if model in family.aliases:
            return family
    return None


_JUDGE_ROLE_VARS = (
    "LLM_API_KEY_JUDGE",
    "LLM_API_BASE_JUDGE",
    "LLM_API_VERSION_JUDGE",
    "LLM_EFFORT_JUDGE",
    "LLM_THINKING_JUDGE",
)


def resolve_judge_config(reflection_config: "LLMConfig") -> "LLMConfig":
    """
    Configuracion del juez del adapter RAG (SPEC-106 D8, FR-004).

    Sin `LLM_MODEL_JUDGE`: la configuracion resuelta del profesor (copia con rol
    `judge`, incluidos los overrides ya aplicados) y un `[WARN]` si alguna
    `LLM_*_JUDGE` esta definida, porque se ignora. Con `LLM_MODEL_JUDGE`: un rol mas
    (`LLMConfig.from_env("judge")`).
    """
    if _env("LLM_MODEL_JUDGE"):
        return LLMConfig.from_env("judge")
    ignored = [name for name in _JUDGE_ROLE_VARS if _env(name)]
    if ignored:
        logger.warning(
            "[WARN] %s definida(s) sin LLM_MODEL_JUDGE: se ignoran, el juez usa la "
            "configuracion del profesor.",
            ", ".join(ignored),
        )
    judge = replace(reflection_config, role="judge", env_role="reflection")
    judge._global_base_ignored = reflection_config._global_base_ignored
    return judge


_CONNECTION_FIELDS = frozenset({"model", "api_key", "api_base", "api_version"})


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
    api_version: str | None = "2024-02-15-preview"
    temperature: float = 0.7
    max_tokens: int = 1000
    cache: bool = False  # DSPy LM cache (True = cachea respuestas, False = resultados frescos)
    # Timeout por request en segundos. Evita cuelgues indefinidos con reasoning models
    # (gpt-5-mini/gpt-5), que ocasionalmente no devuelven respuesta (D-016). None = sin
    # limite. Default alto (600s): no corta requests legitimas, solo cuelgues reales.
    timeout: float | None = 600.0
    # SPEC-103: rol (variables LLM_EFFORT_<ROL>/LLM_THINKING_<ROL>), effort y modo de
    # razonamiento ("default" | "off"). La validez se decide en validate() (D3).
    role: str = "task"
    effort: str | None = None
    thinking: str = "default"
    # SPEC-106 D2: variable de la que salio cada valor de conexion (nunca el valor).
    env_sources: dict[str, str] = field(default_factory=dict, repr=False, compare=False)
    # SPEC-106 FR-003: False si el proveedor del rol difiere del ancla (`task`) y por
    # tanto no hereda las variables globales.
    inherits_global: bool = field(default=True, repr=False, compare=False)
    # SPEC-106 D13: rol cuyas variables de entorno se usaron (None = el propio `role`).
    # El juez heredado del profesor lo fija en "reflection".
    env_role: str | None = field(default=None, repr=False, compare=False)
    # True si hay LLM_API_BASE global que este rol `anthropic/` no hereda (aviso D3).
    _global_base_ignored: bool = field(default=False, init=False, repr=False, compare=False)
    # Aviso de arranque una sola vez por config (D5).
    _warned: bool = field(default=False, init=False, repr=False, compare=False)

    @property
    def is_reasoning_model(self) -> bool:
        """True when the model requires temperature=1.0 and max_tokens>=16000."""
        return _is_reasoning(self.model)

    def _param_names(self) -> tuple[str, str]:
        suffix = (self.env_role or self.role).upper()
        return f"LLM_EFFORT_{suffix}", f"LLM_THINKING_{suffix}"

    def _check_params(self) -> None:
        """
        Reglas de validez de effort/thinking (D5), sin avisos.

        El orden de chequeo define que parametro nombra el error.

        Raises:
            LLMConfigError: combinacion invalida para el modelo.
        """
        from .errors import LLMConfigError

        effort_var, thinking_var = self._param_names()
        if self.effort is not None and self.effort not in _EFFORTS:
            raise LLMConfigError(
                f"{effort_var}={self.effort!r} is not valid for {self.model} "
                f"(role {self.role}). Accepted: {', '.join(_EFFORTS)}",
                self.model,
                effort_var,
                _EFFORTS,
            )
        if self.thinking not in _THINKING_VALUES:
            raise LLMConfigError(
                f"{thinking_var}={self.thinking!r} is not valid for {self.model} "
                f"(role {self.role}). Accepted: {', '.join(_THINKING_VALUES)}",
                self.model,
                thinking_var,
                _THINKING_VALUES,
            )
        family = resolve_anthropic_family(self.model) if _is_anthropic(self.model) else None
        if family is None:
            return

        if self.effort is not None and family.efforts is None:
            raise LLMConfigError(
                f"{effort_var} is set but {self.model} (role {self.role}) does not accept effort",
                self.model,
                effort_var,
            )
        if self.effort is not None and family.efforts is not None:
            if self.effort not in family.efforts:
                accepted = [e for e in _EFFORTS if e in family.efforts]
                raise LLMConfigError(
                    f"{effort_var}={self.effort!r} is not accepted by {self.model} "
                    f"(role {self.role}). Accepted: {', '.join(accepted)}",
                    self.model,
                    effort_var,
                    accepted,
                )
        if self.thinking == "off":
            if family.off_mechanism is None:
                raise LLMConfigError(
                    f"{thinking_var}=off is not supported by {self.model} "
                    f"(role {self.role}): reasoning cannot be turned off",
                    self.model,
                    thinking_var,
                    ["default"],
                )
            if family.off_max_effort is not None:
                effective = self.effort or _DEFAULT_EFFORT
                if _EFFORTS.index(effective) > _EFFORTS.index(family.off_max_effort):
                    allowed = list(_EFFORTS[: _EFFORTS.index(family.off_max_effort) + 1])
                    raise LLMConfigError(
                        f"{thinking_var}=off with effort {effective!r} is not supported by "
                        f"{self.model} (role {self.role}): with thinking off, "
                        f"{effort_var} must be one of {', '.join(allowed)}",
                        self.model,
                        thinking_var,
                        ["default"],
                    )

    def _warn_once(self) -> None:
        """Avisos de arranque (D5): ID fuera de la matriz y LLM_API_BASE ignorado."""
        if self._warned or not _is_anthropic(self.model):
            return
        self._warned = True
        effort_var, thinking_var = self._param_names()
        if resolve_anthropic_family(self.model) is None:
            logger.warning(
                "Model %s is not in the SPEC-103 support matrix: sent without "
                "restrictions (temperature, max_tokens as configured); %s and %s are "
                "not sent.",
                self.model,
                effort_var,
                thinking_var,
            )
        if self._global_base_ignored:
            logger.warning(
                "LLM_API_BASE is not inherited by role %s (%s): the global is not sent to "
                "Anthropic. Set LLM_API_BASE_%s to use a gateway.",
                self.role,
                self.model,
                self.role.upper(),
            )

    def apply_constraints(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """
        Punto unico de restricciones por modelo (SPEC-103 D4, FR-002 a FR-007).

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
        - Rama `anthropic/` (siempre): quita `api_version`; conserva `api_base` (solo
          llega desde `LLM_API_BASE_<ROL>`, explicito; SPEC-106 D3).
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
        self._check_params()
        result = dict(kwargs)

        if not _is_anthropic(self.model):
            if self.is_reasoning_model:
                result["temperature"] = _REASONING_TEMPERATURE
                if (result.get("max_tokens") or 0) < _REASONING_MIN_MAX_TOKENS:
                    result["max_tokens"] = _REASONING_MIN_MAX_TOKENS
            return result

        result.pop("api_version", None)
        family = resolve_anthropic_family(self.model)
        if family is None:
            return result

        if not family.sends_temperature:
            result.pop("temperature", None)
        if family.efforts is not None:
            result["output_config"] = {"effort": self.effort or _DEFAULT_EFFORT}
        if self.thinking == "off" and family.off_mechanism in ("disabled", "between_tools"):
            result["thinking"] = {"type": family.off_mechanism}
        if family.default_reasoning != "off" and self.thinking != "off":
            result["max_tokens"] = max(result.get("max_tokens") or 0, _REASONING_MIN_MAX_TOKENS)
        return result

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
            - provider: proveedor del modelo (`provider_of`, SPEC-106 D1).
            - endpoint_host: host del endpoint efectivo (D7); nunca la credencial.
        """
        base = self._base_kwargs()
        requested = self.max_tokens if max_tokens is None else max_tokens
        base["max_tokens"] = requested
        sent = self.apply_constraints(base)

        mode: str | None = None
        if _is_anthropic(self.model):
            family = resolve_anthropic_family(self.model)
            if family is not None:
                if self.thinking == "off":
                    mode = "off"
                else:
                    mode = family.default_reasoning
        elif self.is_reasoning_model:
            mode = "always"

        return {
            "model": self.model,
            "temperature": sent.get("temperature"),
            "temperature_requested": self.temperature,
            "temperature_omitted": "temperature" not in sent,
            "effort": (sent.get("output_config") or {}).get("effort"),
            "thinking": mode,
            "thinking_param": sent.get("thinking"),
            "max_tokens": sent.get("max_tokens"),
            "max_tokens_requested": requested,
            "provider": provider_of(self.model),
            "endpoint_host": self._effective_host(sent),
        }

    def describe(self, max_tokens: int | None = None) -> str:
        """
        Return a formatted description of the effective LM config (SPEC-103 FR-010).

        Shows temperature sent or omitted (noting an ignored config value), effort,
        reasoning mode and final max_tokens, noting when a config value was raised.

        Args:
            max_tokens: max_tokens fixed per call by the adapter. If None, the one
                in the config is used. The reported value is the one effectively
                sent in those calls, not the `LLMConfig` one.
        """
        effective = self.effective_params(max_tokens)
        tag = " [reasoning model]" if self.is_reasoning_model else ""
        lines = [f"{self.model}{tag}"]

        temp_eff = effective["temperature"]
        if effective["temperature_omitted"]:
            lines.append(f"    temperature: not sent ({self.temperature} in config is ignored)")
        elif self.is_reasoning_model and self.temperature != temp_eff:
            lines.append(
                f"    temperature: {self.temperature} (config) -> {temp_eff} (reasoning override)"
            )
        else:
            lines.append(f"    temperature: {temp_eff}")

        if effective["effort"] is not None:
            origin = "config" if self.effort else "default"
            lines.append(f"    effort:      {effective['effort']} ({origin})")

        if effective["thinking"] is not None:
            lines.append(f"    thinking:    {effective['thinking']}")

        requested = effective["max_tokens_requested"]
        tok_eff = effective["max_tokens"]
        if requested != tok_eff:
            lines.append(
                f"    max_tokens:  {requested} (requested) -> {tok_eff} (reasoning override)"
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
            **overrides: Override de atributos que no son de conexion (p. ej.
                `max_tokens`, `temperature`). Los de conexion (`model`, `api_key`,
                `api_base`, `api_version`) se rechazan con `ValueError`: se
                resuelven solo por variables de entorno (FR-003, D14).

        Returns:
            LLMConfig instance with values from environment.

        Raises:
            ValueError: Si `overrides` incluye un campo de conexion.

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
        rejected = sorted(set(overrides) & _CONNECTION_FIELDS)
        if rejected:
            raise ValueError(
                f"from_env no admite overrides de conexion ({', '.join(rejected)}): "
                "se resuelven por variables LLM_*_<ROL> para no desalinear env_sources"
            )

        if load_env:
            from dotenv import load_dotenv

            # 1. .env del directorio actual (conveniencia; no pisa el entorno).
            load_dotenv()

            # 2. Override explicito por ruta (sin hardcodear subproyectos): util para
            #    herramientas que corren desde la raiz sin importar el config de un
            #    subproyecto. Solo si no hay ninguna credencial (global ni por rol).
            has_credential = any(
                name.startswith("LLM_API_KEY") and value.strip()
                for name, value in os.environ.items()
            )
            if not has_credential:
                env_file = os.getenv("LLM_ENV_FILE")
                if env_file and os.path.exists(env_file):
                    load_dotenv(env_file)

        suffix = model_name.upper()
        # Sin default de modelo (FR-001, D12): un modelo ausente lo rechaza validate().
        model = _env(f"LLM_MODEL_{suffix}") or ""
        task_model = _env("LLM_MODEL_TASK")
        # Proveedor ancla (FR-003): el de `task`, dueno de las variables globales.
        # Sin LLM_MODEL_TASK no hay ancla y ningun rol hereda los globales.
        anchor = provider_of(task_model) if task_model else None
        provider = provider_of(model)
        inherits = bool(model) and anchor is not None and provider == anchor
        is_anthropic = bool(model) and provider == "anthropic"
        sources: dict[str, str] = {"model": f"LLM_MODEL_{suffix}" if model else "unset"}

        def _resolve(field_name: str, role_var: str, global_var: str, allow_global: bool):
            value = _env(role_var)
            if value:
                sources[field_name] = role_var
                return value
            value = _env(global_var) if allow_global else None
            sources[field_name] = global_var if value else "unset"
            return value

        api_key = _resolve("api_key", f"LLM_API_KEY_{suffix}", "LLM_API_KEY", inherits)
        api_base = _resolve(
            "api_base", f"LLM_API_BASE_{suffix}", "LLM_API_BASE", inherits and not is_anthropic
        )
        api_version = _resolve(
            "api_version",
            f"LLM_API_VERSION_{suffix}",
            "LLM_API_VERSION",
            inherits and not is_anthropic,
        )
        if api_version is None and inherits and not is_anthropic:
            api_version = "2024-02-15-preview"
            sources["api_version"] = "default"
        config = cls(
            model=model,
            api_key=api_key,
            api_base=api_base,
            api_version=api_version,
            role=model_name.lower(),
            effort=(_env(f"LLM_EFFORT_{suffix}") or "").lower() or None,
            thinking=(_env(f"LLM_THINKING_{suffix}") or "default").lower(),
        )
        config.env_sources = sources
        config.inherits_global = inherits
        config._global_base_ignored = bool(
            is_anthropic and not _env(f"LLM_API_BASE_{suffix}") and _env("LLM_API_BASE")
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

        Model constraints (reasoning models, Anthropic matrix) are applied through
        `apply_constraints`.

        Returns:
            Dictionary with non-None values suitable for litellm.completion.
            DSPy-specific params (cache) are added in get_dspy_lm().
        """
        return self.apply_constraints(self._base_kwargs())

    def _base_kwargs(self) -> dict[str, Any]:
        """Kwargs de la config tal cual, sin restricciones por modelo."""
        kwargs: dict[str, Any] = {
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

        return kwargs

    @property
    def endpoint_host(self) -> str | None:
        """
        Host del endpoint efectivo (SPEC-106 D7): `hostname` del `api_base` enviado; si
        no hay, el default del proveedor (openai, anthropic); si no se conoce, None.
        """
        return self._effective_host(self.apply_constraints(self._base_kwargs()))

    def _effective_host(self, sent: dict[str, Any]) -> str | None:
        """Host del `api_base` realmente enviado (tras `apply_constraints`) o el del proveedor."""
        from urllib.parse import urlparse

        api_base = sent.get("api_base")
        if api_base:
            return urlparse(api_base).hostname
        return _PROVIDER_DEFAULT_HOSTS.get(provider_of(self.model))

    def connection_summary(self) -> str:
        """Linea `rol | proveedor | modelo | host`; nunca la credencial ni el `api_base`."""
        host = self.endpoint_host or "unknown"
        return f"{self.role} | {provider_of(self.model)} | {self.model} | {host}"

    def get_dspy_lm(self):
        """
        LM de DSPy sobre el punto de llamada propio (SPEC-105).

        For use in dspy_gepa_poc project.

        Returns:
            `dspy.LM` con un `CheckedEngine` (engine propio, SPEC-105 FR-002) que
            lleva los kwargs de esta config y clasifica las fallas segun
            `self.role` (ver `shared/llm/dspy_lm.py`). El engine es `lm.engine`.

        Raises:
            LLMConfigError: si `cache` esta activado. Una respuesta de la cache de
                DSPy no pasa por el punto de llamada: sin uso de tokens ni
                `finish_reason` para la atribucion del baseline (SPEC-105 FR-009).
        """
        from .dspy_lm import CheckedEngine, checked_lm
        from .errors import LLMConfigError

        if self.cache:
            raise LLMConfigError(
                message=(
                    "La cache de DSPy no esta disponible con el punto de llamada propio "
                    "(SPEC-105 FR-009): una respuesta cacheada no pasa por el punto de llamada"
                ),
                model=self.model,
                parameter="cache (models.cache / LLM_CACHE)",
                accepted=("false",),
            )
        kwargs = self.to_kwargs()
        model = kwargs.pop("model")
        # Igual que dspy.LM: en los reasoning models de OpenAI/Azure el tope va
        # como max_completion_tokens.
        if not _is_anthropic(self.model) and self.is_reasoning_model:
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens", None)
        params = {key: value for key, value in kwargs.items() if value is not None}
        return checked_lm(CheckedEngine(model, role=self.role, params=params))

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

        litellm.drop_params = True
        kwargs = self.to_kwargs()

        def lm_func(prompt: str) -> str:
            """Call LLM with prompt and return response text."""
            return complete_text(kwargs, [{"role": "user", "content": prompt}], role)

        return lm_func

    def validate(self) -> None:
        """
        Validate that required configuration is present.

        Raises:
            LLMConnectionError: If required configuration is missing.
            LLMConfigError: If effort/thinking are invalid for the model (SPEC-103).
        """
        from .errors import LLMConnectionError

        role_var = (self.env_role or self.role).upper()

        def _expected(name: str) -> str:
            # El rol que no hereda solo puede usar su variable propia (FR-003).
            if self.inherits_global:
                return f"LLM_{name}_{role_var} or LLM_{name}"
            return f"LLM_{name}_{role_var}"

        if not self.model:
            # Sin modelo no hay proveedor: no se inventa uno (D12).
            raise LLMConnectionError(
                message="Missing required configuration: model is not defined",
                provider="unset",
                model="",
                suggestions=[f"Set LLM_MODEL_{role_var} in your .env file"],
                role=self.role,
                variable=f"LLM_MODEL_{role_var}",
            )

        missing = []
        if not self.api_key:
            missing.append(_expected("API_KEY"))

        # Azure requires api_base
        if provider_of(self.model) == "azure" and not self.api_base:
            missing.append(f"{_expected('API_BASE')} (required for Azure)")

        if missing:
            raise LLMConnectionError(
                message="Missing required configuration",
                provider=provider_of(self.model),
                model=self.model,
                endpoint=self.api_base,
                api_version=self.api_version,
                suggestions=[f"Set {var} in your .env file" for var in missing],
                role=self.role,
                variable=", ".join(missing),
            )

        self._check_params()
        self._warn_once()

    def validate_connection(self) -> bool:
        """
        Test the LLM connection with a minimal request.

        Returns:
            True if connection is successful.

        Raises:
            LLMConnectionError: If connection fails with diagnostic info.
        """
        import litellm

        from .call import probe_completion
        from .errors import LLMConnectionError
        from .failures import FailureClass, LLMCallFailure

        # Config invalida: LLMConfigError sale tal cual, no se envuelve como falla de red.
        # La sonda fija max_tokens=5 y apply_constraints eleva a 16000 si hay razonamiento.
        base = self._base_kwargs()
        base["max_tokens"] = 5
        kwargs = self.apply_constraints(base)

        # Usar kwargs sin None para evitar romper el logger de litellm
        litellm.drop_params = True
        try:
            # SPEC-106 D5: por el punto de llamada comun, un intento, sin uso ni aborto.
            probe_completion(kwargs, self.role)
            return True
        except LLMCallFailure as failure_exc:
            clase = failure_exc.failure.clase
            cause = failure_exc.__cause__
            key_var = self._source_variable("api_key", "API_KEY")
            base_var = self._source_variable("api_base", "API_BASE")
            model_var = self._source_variable("model", "MODEL")

            # Mensaje por clase de SPEC-104 (capa 1), sin leer el texto del error.
            if clase == FailureClass.configuracion:
                message = "Invalid credential, endpoint or model (class configuracion)"
                suggestions = [
                    f"Verify the API key in {key_var}",
                    f"Verify the endpoint in {base_var}: {self.api_base}"
                    if self.api_base
                    else f"Verify the endpoint for provider {provider_of(self.model)}",
                    f"Verify that model/deployment '{self.model}' ({model_var}) exists",
                ]
            elif clase == FailureClass.infraestructura:
                message = (
                    "Provider not reachable now (rate limit 429, timeout or network; "
                    "class infraestructura): retry later"
                )
                suggestions = [
                    "Wait a few minutes before retrying",
                    "Check quotas and limits of the deployment",
                    "Check network access (VPN/VNet) to the endpoint",
                ]
            else:
                message = f"Connection probe failed (class {clase.value})"
                suggestions = ["Review error details below"]

            raise LLMConnectionError(
                message=message,
                provider=provider_of(self.model),
                model=self.model,
                endpoint=self.api_base,
                api_version=self.api_version,
                original_error=str(cause or failure_exc)[:500],
                extra_details=_probe_error_details(cause) if cause is not None else None,
                suggestions=suggestions,
                role=self.role,
                failure_class=clase.value,
                variable=key_var,
            ) from failure_exc

    def _source_variable(self, field_name: str, suffix: str) -> str:
        """
        Variable de la que salio un valor de conexion (`env_sources`, SPEC-106 D2/D4);
        sin fuente concreta, la esperada para el rol segun la regla de herencia.
        """
        source = self.env_sources.get(field_name)
        if source and source not in ("unset", "default"):
            return source
        role_var = f"LLM_{suffix}_{(self.env_role or self.role).upper()}"
        if field_name != "model" and self.inherits_global:
            return f"{role_var} or LLM_{suffix}"
        return role_var


def _probe_error_details(exc: BaseException) -> dict[str, Any]:
    """Detalles diagnosticos de la excepcion de la sonda (sin la credencial)."""

    def _truncate(value: Any, limit: int = 500) -> str:
        try:
            return str(value)[:limit]
        except Exception:
            return "<unavailable>"

    response_obj = getattr(exc, "response", None)
    response_text = getattr(response_obj, "text", None) if response_obj is not None else None
    return {
        "error_type": type(exc).__name__,
        "error_repr": _truncate(repr(exc)),
        "error_args": _truncate(getattr(exc, "args", None)),
        "status_code": getattr(exc, "status_code", None),
        "response_text": _truncate(response_text) if response_text else None,
        "response": _truncate(response_obj) if response_obj else None,
        "request_id": getattr(exc, "request_id", None),
    }

"""
LLM Factory

Fabrica para crear funciones LLM para GEPA.
Usa el modulo compartido shared.llm con LiteLLM.
"""

from collections.abc import Callable

from shared.llm import LLMConfig
from shared.llm.config import complete_text
from shared.llm.reflection import ReflectionGuard


def create_task_lm_function(verbose: bool = False) -> Callable[[str], str]:
    """
    Crea la funcion de Language Model para tareas (modelo estudiante).

    Args:
        verbose: Si True, imprime las respuestas del modelo.

    Returns:
        Funcion que toma un prompt y retorna la respuesta.
    """
    config = LLMConfig.from_env("task")
    base_func = config.get_lm_function(role="task")

    if not verbose:
        return base_func

    def lm_func(prompt: str) -> str:
        content = base_func(prompt)
        print("\n" + "=" * 80)
        print("[TASK LM]")
        print("=" * 80)
        print(content.strip())
        print("=" * 80 + "\n")
        return content

    return lm_func


def create_reflection_lm_function(
    verbose: bool = False,
    temperature: float | None = None,
    max_tokens: int | None = None,
    cache: bool | None = None,
    config: LLMConfig | None = None,
) -> Callable[[str], str]:
    """
    Crea la funcion de Language Model para reflexion requerida por GEPA.
    Usa el modelo de reflexion (profesor).

    Args:
        verbose: Si True, imprime las reflexiones del modelo.
        temperature: Override de temperatura (None = usa default del .env).
        max_tokens: Override de max_tokens (None = usa 2000).
        cache: Override de cache (None = usa default del .env).
        config: Config ya armada (con sus overrides). Si se pasa, se usa tal cual
            y se ignoran temperature, max_tokens y cache.

    Returns:
        `ReflectionLM`: callable que toma un prompt y retorna la respuesta, y
        descarta (lanzando) la propuesta con falla de capa 1 o `formato`
        (SPEC-104 FR-005; ver `shared.llm.reflection.ReflectionGuard`).
    """
    if config is None:
        config = LLMConfig.from_env("reflection", max_tokens=2000)
        if temperature is not None:
            config.temperature = temperature
        if max_tokens is not None:
            config.max_tokens = max_tokens
        if cache is not None:
            config.cache = cache
    base_func = config.get_lm_function(role="reflection")

    if not verbose:
        return ReflectionLM(base_func)

    def lm_func(prompt: str) -> str:
        content = base_func(prompt)
        print("\n" + "=" * 80)
        print("[REFLECTION LM]")
        print("=" * 80)
        print(content.strip())
        print("=" * 80 + "\n")
        return content

    return ReflectionLM(lm_func)


class ReflectionLM:
    """
    `reflection_lm` de `gepa.optimize` con el envoltorio de SPEC-104 FR-005.

    Tambien es un callback de GEPA (`on_proposal_start`): pasado en `callbacks`
    de `gepa.optimize`, el `case_id` de la falla es la iteracion de GEPA.
    """

    def __init__(self, fn: Callable[[str], str]):
        self._fn = fn
        self._guard = ReflectionGuard()

    def __call__(self, prompt: str) -> str:
        return self._guard.run(lambda: self._fn(prompt), lambda text: [text])

    def on_proposal_start(self, event) -> None:
        self._guard.on_proposal_start(event)


def validate_llm_connection() -> bool:
    """
    Valida la conexion con el LLM.

    Returns:
        True si la conexion es exitosa.

    Raises:
        LLMConnectionError: Si la conexion falla.
    """
    config = LLMConfig.from_env("task")
    config.validate()
    return config.validate_connection()


def get_task_config() -> LLMConfig:
    """
    Obtiene la configuracion del modelo de tarea.

    Returns:
        LLMConfig para el modelo de tarea.
    """
    return LLMConfig.from_env("task")


def get_reflection_config() -> LLMConfig:
    """
    Obtiene la configuracion del modelo de reflexion.

    Returns:
        LLMConfig para el modelo de reflexion.
    """
    return LLMConfig.from_env("reflection")


def call_llm(
    prompt: str,
    model_name: str = "task",
    system_prompt: str = None,
    temperature: float = None,
    max_tokens: int = None,
) -> str:
    """
    Fachada de la llamada comun a LiteLLM (`shared.llm.config.complete_text`):
    resuelve la config por rol y aplica los overrides.

    Args:
        prompt: El prompt del usuario.
        model_name: Nombre del modelo ("task", "reflection", etc.).
        system_prompt: Prompt del sistema (opcional).
        temperature: Override de temperatura (opcional).
        max_tokens: Override de max_tokens (opcional).

    Returns:
        Respuesta del modelo como string.
    """
    import litellm

    litellm.drop_params = True
    config = LLMConfig.from_env(model_name)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    kwargs = config.to_kwargs()
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    # Re-apply after manual overrides: callers may pass unadjusted values from YAML
    kwargs = config.apply_constraints(kwargs)

    return complete_text(kwargs, messages, model_name)

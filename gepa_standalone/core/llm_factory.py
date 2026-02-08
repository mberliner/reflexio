"""
LLM Factory

Fabrica para crear funciones LLM para GEPA.
Usa el modulo compartido shared.llm con LiteLLM.
"""

import sys
from collections.abc import Callable
from pathlib import Path

# Add project root to path for shared module access
_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.llm import LLMConfig  # noqa: E402


def create_task_lm_function(verbose: bool = False) -> Callable[[str], str]:
    """
    Crea la funcion de Language Model para tareas (modelo estudiante).

    Args:
        verbose: Si True, imprime las respuestas del modelo.

    Returns:
        Funcion que toma un prompt y retorna la respuesta.
    """
    config = LLMConfig.from_env("task")
    base_func = config.get_lm_function()

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


def create_reflection_lm_function(verbose: bool = False) -> Callable[[str], str]:
    """
    Crea la funcion de Language Model para reflexion requerida por GEPA.
    Usa el modelo de reflexion (profesor).

    Args:
        verbose: Si True, imprime las reflexiones del modelo.

    Returns:
        Funcion que toma un prompt y retorna la respuesta.
    """
    config = LLMConfig.from_env("reflection", max_tokens=2000)
    base_func = config.get_lm_function()

    if not verbose:
        return base_func

    def lm_func(prompt: str) -> str:
        content = base_func(prompt)
        print("\n" + "=" * 80)
        print("[REFLECTION LM]")
        print("=" * 80)
        print(content.strip())
        print("=" * 80 + "\n")
        return content

    return lm_func


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
    Llamada directa al LLM usando LiteLLM.

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

    # Remove model from kwargs since we pass it separately
    model = kwargs.pop("model")

    response = litellm.completion(model=model, messages=messages, **kwargs)
    return response.choices[0].message.content

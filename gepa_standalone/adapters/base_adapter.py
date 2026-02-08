"""
Base Adapter

Clase base abstracta para todos los adaptadores de GEPA.
Usa LiteLLM para conexion con LLMs.
"""

from gepa_standalone.core.llm_factory import call_llm, get_task_config


class BaseAdapter:
    """Clase base para adaptadores GEPA que usan LiteLLM."""

    # Atributo requerido por GEPAAdapter
    propose_new_texts = None

    def __init__(self, temperature: float = 0.0):
        self.temperature = temperature
        self._config = get_task_config()
        # Modelo en formato LiteLLM (ej: "azure/gpt-4.1-mini")
        self.model = self._config.model

    def call_model(self, system_prompt: str, user_content: str, max_tokens: int = 100) -> str:
        """
        Llama al modelo de chat usando LiteLLM.

        Args:
            system_prompt: Prompt del sistema.
            user_content: Contenido del usuario.
            max_tokens: Maximo de tokens en la respuesta.

        Returns:
            Respuesta del modelo como string.
        """
        return call_llm(
            prompt=user_content,
            model_name="task",
            system_prompt=system_prompt,
            temperature=self.temperature,
            max_tokens=max_tokens,
        )

    def evaluate(self, batch, candidate, capture_traces=False):
        """Método abstracto que debe ser implementado por las subclases."""
        raise NotImplementedError("Cada adaptador debe implementar su propio método evaluate()")

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        """Método abstracto que debe ser implementado por las subclases."""
        raise NotImplementedError(
            "Cada adaptador debe implementar su propio método make_reflective_dataset()"
        )

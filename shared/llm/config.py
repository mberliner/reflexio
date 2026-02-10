"""
LLM Configuration module.

Provides a unified configuration dataclass that works with both:
- dspy.LM (for dspy_gepa_poc)
- litellm.completion (for gepa_standalone)
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


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
        """
        if load_env:
            from dotenv import load_dotenv

            # 1. Intentar cargar .env del directorio actual
            load_dotenv()

            # 2. Si no hay API KEY, buscar en directorios raíz y subproyectos
            if not os.getenv("LLM_API_KEY"):
                current = os.getcwd()
                # Subir hasta encontrar la raíz o llegar al tope (5 niveles)
                for _ in range(5):
                    # Probar en el directorio actual
                    load_dotenv(os.path.join(current, ".env"))
                    if os.getenv("LLM_API_KEY"):
                        break

                    # Probar en subcarpetas específicas si estamos en la raíz del proyecto
                    for sub in ["gepa_standalone", "dspy_gepa_poc"]:
                        env_path = os.path.join(current, sub, ".env")
                        if os.path.exists(env_path):
                            load_dotenv(env_path)
                            if os.getenv("LLM_API_KEY"):
                                break
                    if os.getenv("LLM_API_KEY"):
                        break

                    # Subir un nivel
                    parent = os.path.dirname(current)
                    if parent == current:
                        break
                    current = parent

        model_var = f"LLM_MODEL_{model_name.upper()}"

        config = cls(
            model=os.getenv(model_var, "azure/gpt-4.1-mini"),
            api_key=os.getenv("LLM_API_KEY"),
            api_base=os.getenv("LLM_API_BASE"),
            api_version=os.getenv("LLM_API_VERSION", "2024-02-15-preview"),
        )
        config.cache = os.getenv("LLM_CACHE", "false").lower() == "true"

        # Apply overrides
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        return config

    def to_kwargs(self) -> dict[str, Any]:
        """
        Convert config to kwargs dict for LLM calls.

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

        return kwargs

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

    def get_lm_function(self) -> Callable[[str], str]:
        """
        Get a simple LM function for GEPA.

        For use in gepa_standalone project. Uses LiteLLM directly without DSPy.

        Returns:
            Function that takes a prompt string and returns the response string.
        """
        import litellm

        kwargs = self.to_kwargs()

        def lm_func(prompt: str) -> str:
            """Call LLM with prompt and return response text."""
            response = litellm.completion(messages=[{"role": "user", "content": prompt}], **kwargs)
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
            kwargs = self.to_kwargs()
            # Forzar max_tokens pequeño para el test
            kwargs["max_tokens"] = 5

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

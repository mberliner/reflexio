"""
Centralized Configuration for GEPA Standalone

Este modulo maneja las variables de entorno y constantes del proyecto.
La configuracion LLM se maneja en shared/llm.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Cargar variables de entorno desde el .env del proyecto
_PROJECT_DIR = Path(__file__).parent
_ENV_FILE = _PROJECT_DIR / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)


class Config:
    """
    Configuracion de GEPA Standalone.

    La configuracion LLM (api_key, modelos, etc.) se maneja en shared.llm.LLMConfig.
    Esta clase contiene configuracion de paths y adapters.
    Los valores pueden ser sobreescritos dinamicamente desde el YAML del experimento.
    """

    # Path Configuration (Optional Overrides)
    GEPA_ROOT = os.getenv("GEPA_ROOT", None)
    GEPA_EXPERIMENTS_DIR = os.getenv("GEPA_EXPERIMENTS_DIR", None)
    GEPA_RESULTS_DIR = os.getenv("GEPA_RESULTS_DIR", None)

    # Adapter Configuration - Valores por defecto (Hardcoded para consistencia)
    _CLASSIFIER_TEXT_MAX_LENGTH = 1000
    _EXTRACTOR_TEXT_MAX_LENGTH = 1000
    _RAG_CONTEXT_MAX_LENGTH = 1500
    _RAG_MAX_POSITIVE_EXAMPLES = 2
    _EXTRACTOR_MAX_POSITIVE_EXAMPLES = 0

    # Propiedades dinamicas (permiten override en tiempo de ejecucion)
    CLASSIFIER_TEXT_MAX_LENGTH = _CLASSIFIER_TEXT_MAX_LENGTH
    EXTRACTOR_TEXT_MAX_LENGTH = _EXTRACTOR_TEXT_MAX_LENGTH
    RAG_CONTEXT_MAX_LENGTH = _RAG_CONTEXT_MAX_LENGTH
    RAG_MAX_POSITIVE_EXAMPLES = _RAG_MAX_POSITIVE_EXAMPLES
    EXTRACTOR_MAX_POSITIVE_EXAMPLES = _EXTRACTOR_MAX_POSITIVE_EXAMPLES

    @classmethod
    def apply_yaml_config(cls, yaml_config: dict):
        """
        Sobreescribe los valores de configuracion con los definidos en el YAML.
        Busca en la seccion 'adapter' del YAML.
        """
        if not yaml_config or "adapter" not in yaml_config:
            return

        adapter_cfg = yaml_config["adapter"]

        # Mapeo de campos YAML a variables de Config
        mapping = {
            "max_text_length": ["CLASSIFIER_TEXT_MAX_LENGTH", "EXTRACTOR_TEXT_MAX_LENGTH"],
            "rag_context_max_length": ["RAG_CONTEXT_MAX_LENGTH"],
            "rag_max_positive_examples": ["RAG_MAX_POSITIVE_EXAMPLES"],
            "extractor_max_positive_examples": ["EXTRACTOR_MAX_POSITIVE_EXAMPLES"],
        }

        for yaml_key, config_keys in mapping.items():
            if yaml_key in adapter_cfg:
                val = adapter_cfg[yaml_key]
                for ck in config_keys:
                    setattr(cls, ck, val)
                    print(f"[CONFIG] Overriding {ck} from YAML: {val}")

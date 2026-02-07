"""
GEPA Adapters

Adaptadores personalizados para usar GEPA con diferentes tipos de tareas.
"""

from .simple_classifier_adapter import SimpleClassifierAdapter
from .simple_extractor_adapter import SimpleExtractorAdapter

__all__ = ["SimpleClassifierAdapter", "SimpleExtractorAdapter"]

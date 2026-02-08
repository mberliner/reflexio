"""
DSPy + GEPA Integration Project
Integrates DSPy modular framework with GEPA's reflective optimization.
"""

__version__ = "0.2.0"

# Expose key components for easier access
from .config import AppConfig, GEPAConfig, LLMConfig, LLMConnectionError
from .data_loader import CSVDataLoader, load_extraction_dataset, load_sentiment_dataset
from .dynamic_factory import DynamicModuleFactory
from .optimizer import GEPAOptimizer, optimize_with_gepa

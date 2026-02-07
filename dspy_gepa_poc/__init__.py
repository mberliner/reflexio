"""
DSPy + GEPA Integration Project
Integrates DSPy modular framework with GEPA's reflective optimization.
"""

__version__ = "0.2.0"

# Expose key components for easier access
from .config import GEPAConfig, AppConfig, LLMConfig, LLMConnectionError
from .data_loader import CSVDataLoader, load_sentiment_dataset, load_extraction_dataset
from .optimizer import GEPAOptimizer, optimize_with_gepa
from .dynamic_factory import DynamicModuleFactory
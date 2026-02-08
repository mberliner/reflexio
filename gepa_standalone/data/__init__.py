"""
Demo Datasets

Sistema unificado de carga de datos CSV para GEPA standalone.
"""

from .data_loader import get_dataset_info, load_gepa_data, print_dataset_info

__all__ = [
    "load_gepa_data",
    "print_dataset_info",
    "get_dataset_info",
]

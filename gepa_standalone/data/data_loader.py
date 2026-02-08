"""
Cargador Universal de Datos para GEPA

Este módulo proporciona funciones para cargar datos desde CSV
en un formato consistente para todos los ejemplos de GEPA.

Formato CSV:
- Columna 'split': indica train/val/test
- Columna 'text' o similar: entrada del modelo
- Columnas adicionales: etiquetas o campos extraídos

Uso:
    from gepa_standalone.data.data_loader import load_gepa_data

    train, val, test = load_gepa_data("email_urgency.csv")
"""

import csv
import os
from typing import Any

from shared.paths import get_paths


def load_gepa_data(
    csv_filename: str, input_column: str = "text", output_columns: list[str] = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Carga datos desde CSV y los separa por split (train/val/test).

    Args:
        csv_filename: Nombre del archivo CSV (solo nombre, no ruta completa)
        input_column: Nombre de la columna de entrada (default: "text")
        output_columns: Lista de columnas de salida.
            Si es None, usa todas excepto 'split' e input_column

    Returns:
        Tuple de (trainset, valset, testset) donde cada uno es una lista de diccionarios

    Ejemplo para clasificación:
        >>> train, val, test = load_gepa_data("email_urgency.csv")
        >>> print(train[0])
        {'text': 'URGENTE: ...', 'urgency': 'urgent'}

    Ejemplo para extracción:
        >>> train, val, test = load_gepa_data(
        ...     "cv_extraction.csv",
        ...     output_columns=[
        ...         "nombre", "email", "años_experiencia", "skills", "educacion_principal"
        ...     ]
        ... )
        >>> print(train[0])
        {'text': 'JUAN PÉREZ...', 'extracted': {'nombre': 'Juan Pérez', ...}}
    """
    # Determinar ruta completa del CSV usando paths centralizados
    # Esto busca primero en experiments/datasets/ y luego en data/csv/ (legacy)
    csv_path = get_paths().dataset(csv_filename)

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV no encontrado: {csv_path}")

    # Leer CSV
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Validar que el CSV no esté vacío
    if not rows:
        raise ValueError(f"El archivo CSV está vacío: {csv_path}")

    # Determinar columnas de salida si no se especificaron
    if output_columns is None:
        all_columns = rows[0].keys()
        output_columns = [col for col in all_columns if col not in ["split", input_column]]

    # Separar por split y convertir al formato esperado
    trainset = []
    valset = []
    testset = []

    for row in rows:
        split = row["split"].strip().lower()

        # Crear ejemplo en formato GEPA
        if len(output_columns) == 1:
            # Clasificación simple: una sola columna de salida
            example = {input_column: row[input_column], output_columns[0]: row[output_columns[0]]}
        else:
            # Extracción múltiple: diccionario 'extracted' con todos los campos
            example = {
                input_column: row[input_column],
                "extracted": {col: row[col] for col in output_columns},
            }

        # Agregar al split correspondiente
        if split == "train":
            trainset.append(example)
        elif split == "val":
            valset.append(example)
        elif split == "test":
            testset.append(example)
        else:
            raise ValueError(f"Split desconocido: {split}. Use 'train', 'val' o 'test'")

    return trainset, valset, testset


def get_dataset_info(csv_filename: str) -> dict[str, Any]:
    """
    Obtiene información sobre un dataset CSV.

    Args:
        csv_filename: Nombre del archivo CSV

    Returns:
        Diccionario con estadísticas del dataset
    """
    csv_path = get_paths().dataset(csv_filename)

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Validar que el CSV no esté vacío
    if not rows:
        raise ValueError(f"El archivo CSV está vacío: {csv_path}")

    # Contar por split
    splits = {"train": 0, "val": 0, "test": 0}
    for row in rows:
        split = row["split"].strip().lower()
        splits[split] = splits.get(split, 0) + 1

    # Obtener columnas
    columns = list(rows[0].keys())

    # Filtrar columnas None o vacías
    output_columns = [col for col in columns if col and col not in ["split", "text"]]

    return {
        "filename": csv_filename,
        "total_rows": len(rows),
        "splits": splits,
        "columns": columns,
        "input_column": "text",
        "output_columns": output_columns,
    }


def print_dataset_info(csv_filename: str):
    """
    Imprime información sobre un dataset CSV de forma legible.

    Args:
        csv_filename: Nombre del archivo CSV
    """
    info = get_dataset_info(csv_filename)

    print(f"\n{'=' * 60}")
    print(f"Dataset: {info['filename']}")
    print(f"{'=' * 60}")
    print(f"Total ejemplos: {info['total_rows']}")
    print("\nDistribución por split:")
    print(f"  - Train: {info['splits']['train']} ejemplos")
    print(f"  - Val:   {info['splits']['val']} ejemplos")
    print(f"  - Test:  {info['splits']['test']} ejemplos")
    print("\nColumnas:")
    print(f"  - Entrada: {info['input_column']}")
    print(f"  - Salida:  {', '.join(info['output_columns'])}")
    print(f"{'=' * 60}\n")

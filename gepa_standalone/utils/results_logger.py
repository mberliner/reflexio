"""
Results logger for GEPA standalone experiments.

Uses shared logging utilities for consistent formatting across projects.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path for shared module access
_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.logging import (
    BaseCSVLogger,
    STANDARD_COLUMN_MAPPING,
    generate_run_id,
    get_timestamp,
    fmt_score,
    make_path_relative,
)

from gepa_standalone.utils.paths import get_paths


def save_run_details(
    case_name: str,
    run_id: str,
    initial_prompt: str,
    final_prompt: str,
    metadata: Dict[str, Any],
    results: Dict[str, Any],
    timestamp: Optional[datetime] = None
) -> Path:
    """
    Guarda detalles completos de un run en archivos individuales.

    Esta funcion crea un directorio para el run y guarda:
    - initial_prompt.txt: Prompt inicial
    - final_prompt.txt: Prompt optimizado
    - config.json: Metadata del experimento
    - results.json: Scores y resultados detallados

    Args:
        case_name: Nombre del caso (e.g., 'email_urgency', 'cv_extraction')
        run_id: Identificador unico del run (tipicamente UUID corto)
        initial_prompt: Prompt inicial del sistema
        final_prompt: Prompt optimizado final
        metadata: Diccionario con metadata (modelos, fecha, presupuesto, etc.)
        results: Diccionario con resultados (scores, detalles, etc.)
        timestamp: Timestamp opcional (por defecto: ahora)

    Returns:
        Path al directorio del run creado

    Example:
        >>> run_dir = save_run_details(
        ...     case_name="email_urgency",
        ...     run_id="a3f9b2c1",
        ...     initial_prompt="Clasifica emails...",
        ...     final_prompt="Eres un experto clasificador...",
        ...     metadata={"task_model": "gpt-4.1-mini", "reflection_model": "gpt-4o"},
        ...     results={"baseline_score": 0.75, "optimized_score": 0.92}
        ... )
        >>> print(run_dir)
        /path/to/results/runs/email_urgency/2025-12-26_163045_a3f9b2c1
    """
    paths = get_paths()

    # Crear directorio del run
    run_dir = paths.run_dir(case_name, run_id, timestamp)

    # 1. Guardar prompt inicial
    initial_prompt_file = run_dir / "initial_prompt.txt"
    with open(initial_prompt_file, 'w', encoding='utf-8') as f:
        f.write(initial_prompt)

    # 2. Guardar prompt final
    final_prompt_file = run_dir / "final_prompt.txt"
    with open(final_prompt_file, 'w', encoding='utf-8') as f:
        f.write(final_prompt)

    # 3. Guardar config (metadata)
    config_file = run_dir / "config.json"
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # 4. Guardar results
    results_file = run_dir / "results.json"
    # Convertir objetos complejos a diccionarios si es necesario
    serializable_results = {}
    for key, value in results.items():
        if hasattr(value, '__dict__'):
            serializable_results[key] = value.__dict__
        else:
            serializable_results[key] = value

    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(serializable_results, f, indent=2, ensure_ascii=False)

    # 5. Actualizar symlink 'latest'
    latest_symlink = paths.latest_run_symlink(case_name)
    if latest_symlink.exists() or latest_symlink.is_symlink():
        latest_symlink.unlink()
    try:
        latest_symlink.symlink_to(run_dir.name, target_is_directory=True)
    except OSError:
        # En Windows o sistemas sin soporte de symlinks, crear un archivo de texto
        with open(latest_symlink, 'w') as f:
            f.write(str(run_dir))

    print(f"\n>> [LOG] Detalles del run guardados en: {run_dir}")

    return run_dir


class GEPAResultsLogger(BaseCSVLogger):
    """
    Results logger for GEPA standalone experiments.

    Extends BaseCSVLogger with GEPA-specific path resolution and
    legacy format migration support.
    """

    def __init__(self):
        """Initialize the logger using paths from get_paths()."""
        paths = get_paths()
        super().__init__(
            csv_path=paths.summary_csv,
            column_mapping=STANDARD_COLUMN_MAPPING,
        )
        self._paths = paths

    def log_experiment(
        self,
        case_title: str,
        task_model: str,
        reflection_model: str,
        baseline_score: float,
        optimized_score: float,
        robustness_score: float,
        run_directory: str,
        has_positive_reflection: bool = False,
        budget: int = None,
        notes: str = ""
    ) -> str:
        """
        Log an experiment result to the CSV.

        Args:
            case_title: Titulo del caso/experimento
            task_model: Modelo usado para la tarea (estudiante)
            reflection_model: Modelo usado para optimizacion (professor)
            baseline_score: Score baseline antes de optimizar
            optimized_score: Score despues de optimizar en validacion
            robustness_score: Score en conjunto de test (robustez)
            run_directory: Ruta al directorio del run
            has_positive_reflection: Si el caso usa reflexion positiva
            budget: Max metric calls usados en la optimizacion
            notes: Notas adicionales sobre el experimento

        Returns:
            The generated run_id
        """
        # Convert run_dir to relative path
        rel_run_dir = make_path_relative(
            run_directory,
            str(self._paths.results),
            fallback=run_directory
        )

        data = {
            "run_id": generate_run_id(),
            "date": get_timestamp(),
            "case_name": case_title,
            "task_model": task_model,
            "reflection_model": reflection_model,
            "baseline_score": baseline_score,
            "optimized_score": optimized_score,
            "test_score": robustness_score,
            "run_dir": rel_run_dir,
            "positive_reflection": "Si" if has_positive_reflection else "No",
            "budget": budget if budget is not None else "N/A",
            "notes": notes,
        }

        self.append_row(data)
        print(f">> [LOG] Resumen guardado en: {self.csv_path}")

        return data["run_id"]


# Legacy function for backwards compatibility
def log_experiment_result(
    case_title: str,
    task_model: str,
    reflection_model: str,
    baseline_score: float,
    optimized_score: float,
    robustness_score: float,
    run_directory: str,
    has_positive_reflection: bool = False,
    budget: int = None,
    notes: str = ""
):
    """
    Registra los resultados de un experimento GEPA en el CSV de resumen.

    NOTA: Esta funcion es un wrapper de compatibilidad. Prefiera usar
    GEPAResultsLogger directamente para nuevas implementaciones.

    Args:
        case_title: Titulo del caso/experimento
        task_model: Modelo usado para la tarea (estudiante)
        reflection_model: Modelo usado para optimizacion (professor)
        baseline_score: Score baseline antes de optimizar
        optimized_score: Score despues de optimizar en validacion
        robustness_score: Score en conjunto de test (robustez)
        run_directory: Ruta relativa al directorio del run
        has_positive_reflection: Si el caso usa reflexion positiva
        budget: Max metric calls usados en la optimizacion
        notes: Notas adicionales sobre el experimento
    """
    logger = GEPAResultsLogger()
    logger.log_experiment(
        case_title=case_title,
        task_model=task_model,
        reflection_model=reflection_model,
        baseline_score=baseline_score,
        optimized_score=optimized_score,
        robustness_score=robustness_score,
        run_directory=run_directory,
        has_positive_reflection=has_positive_reflection,
        budget=budget,
        notes=notes,
    )

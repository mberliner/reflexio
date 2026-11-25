"""
Universal GEPA Optimizer

Interfaz universal para optimizar prompts con GEPA en cualquier caso de uso.
Soporta configuración mediante archivo YAML o wizard interactivo.

Usage (desde la raiz del repo):
    # Con config YAML existente
    python -m gepa_standalone.universal_optimizer \\
        --config gepa_standalone/experiments/configs/mi_caso.yaml

    # Sin config (activa wizard interactivo)
    python -m gepa_standalone.universal_optimizer
"""

import argparse
import json
import sys
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from gepa import optimize

from gepa_standalone.adapters.simple_classifier_adapter import SimpleClassifierAdapter
from gepa_standalone.adapters.simple_extractor_adapter import SimpleExtractorAdapter
from gepa_standalone.adapters.simple_rag_adapter import SimpleRAGAdapter
from gepa_standalone.adapters.simple_sql_adapter import SimpleSQLAdapter
from gepa_standalone.config import Config
from gepa_standalone.config_schema import ConfigValidator
from gepa_standalone.core.llm_factory import (
    create_reflection_lm_function,
    get_reflection_config,
    get_task_config,
)
from gepa_standalone.data.data_loader import load_gepa_data
from gepa_standalone.utils.results_logger import log_experiment_result, save_run_details
from gepa_standalone.wizard.interactive import InteractiveWizard
from shared.analysis.roi_calculator import cost_from_usage
from shared.display import (
    configure_stdio,
    log_error,
    log_info,
    log_ok,
    log_warn,
    print_detailed_results,
    print_gepa_evolution,
    print_gepa_search_stats,
    print_header,
    print_kv,
    print_prompt,
    print_step,
    print_summary,
)
from shared.display.formatting import format_abort_error, format_metric_line
from shared.llm import LLMConnectionError, RunAborted, get_failure_tracker
from shared.llm.usage import get_tracker
from shared.logging.metadata import (
    MetadataManager,
    collect_model_info,
    generate_seed,
    metrics_coverage,
)
from shared.paths import get_paths
from shared.scoring import MetricSummary, paired_delta, summarize

# Total de pasos del pipeline canonico (compartido con dspy_gepa_poc).
TOTAL_STEPS = 7
# Identificador del motor que aparece en el header del run.
ENGINE = "GEPA-STANDALONE"
# max_tokens de la reflexion cuando el YAML no lo fija.
_REFLECTION_DEFAULT_MAX_TOKENS = 2000


def _csv_score(score: float | None) -> float | str:
    """Una metrica sin casos evaluados va al CSV como "N/A", nunca como 0.0 (FR-003)."""
    return "N/A" if score is None else score


class UniversalOptimizer:
    """Orquestador universal de optimización GEPA."""

    def __init__(self, config_path: str | None = None):
        """
        Initialize optimizer.

        Args:
            config_path: Path to YAML config. If None or doesn't exist, activates wizard.
        """
        self.config_path = config_path
        self.config = None
        self.adapter = None
        self.train_data = None
        self.val_data = None
        self.test_data = None
        self.results = None
        self.task_config = None
        self.reflection_config = None

    def abort_message(self, exc: RunAborted) -> str:
        """Mensaje de una corrida abortada (FR-006), con el modelo del rol que fallo."""
        configs = {
            "task": self.task_config,
            "reflection": self.reflection_config,
            "judge": getattr(self.adapter, "judge_config", None),
        }
        config = configs.get(exc.failure.rol)
        return format_abort_error(exc, config.model if config is not None else None)

    def configure_failure_tracker(self) -> None:
        """Reinicia el contador de fallas y aplica la seccion `failures` del YAML (D7)."""
        tracker = get_failure_tracker()
        tracker.reset()
        section = self.config.get("failures") or {}
        tracker.configure(
            thresholds=section.get("thresholds"),
            min_attempts=section.get("min_attempts"),
            infra_retries=section.get("infra_retries"),
        )

    def _run_models(self) -> dict[str, Any]:
        return collect_model_info(
            self.task_config,
            self.reflection_config,
            judge_config=getattr(self.adapter, "judge_config", None),
            task_max_tokens=self.adapter.task_max_tokens,
            judge_max_tokens=getattr(self.adapter, "judge_max_tokens", None),
        )

    def save_aborted_run(self) -> Path:
        """
        Escribe solo `run.json` (estado `aborted`) de una corrida abortada (FR-008).

        No escribe fila de CSV ni presenta metricas como validas; los artefactos que
        la corrida ya haya dejado (p. ej. `candidates.json`) quedan en el directorio.
        """
        run_dir = get_paths().run_dir(self.config["case"]["name"], run_id=str(uuid.uuid4())[:8])
        usage = get_tracker().snapshot()
        usage["cost_usd"] = cost_from_usage(
            usage, self.task_config.model, self.reflection_config.model
        )
        return self.metadata_mgr.create_run(
            run_dir=run_dir,
            experiment_name=self.config["case"]["name"],
            seed=self.seed,
            models=self._run_models(),
            usage=usage,
            status="aborted",
            failures=get_failure_tracker().snapshot(),
        )

    def build_llm_configs(self):
        """
        Build once the task and reflection LLMConfig with the YAML overrides.

        The same instances are used for validation, adapter reporting, the
        reflection LM and save_results, so run.json reports what was sent.
        """
        models_cfg = self.config.get("models", {})
        self.active_temperature = models_cfg.get("temperature", 0.0)

        self.task_config = get_task_config()
        self.task_config.temperature = self.active_temperature
        self.reflection_config = get_reflection_config()
        if models_cfg.get("temperature") is not None:
            self.reflection_config.temperature = models_cfg["temperature"]
        for cfg in (self.task_config, self.reflection_config):
            if models_cfg.get("max_tokens"):
                cfg.max_tokens = models_cfg["max_tokens"]
        if models_cfg.get("cache") is not None:
            self.reflection_config.cache = models_cfg["cache"]
        if not models_cfg.get("max_tokens"):
            # default usado por create_reflection_lm_function
            self.reflection_config.max_tokens = _REFLECTION_DEFAULT_MAX_TOKENS

    def run(self, verbose: bool = False):
        """Execute complete optimization workflow."""
        # STEP 1: Config
        print_step(1, TOTAL_STEPS, "CONFIG")
        config_path = None
        if self.config_path:
            p = Path(self.config_path)
            if p.exists():
                config_path = p
            else:
                script_dir = Path(__file__).parent
                fallback_path = script_dir / self.config_path
                if fallback_path.exists():
                    config_path = fallback_path

        if config_path:
            self.config_path = str(config_path)
            log_info(f"Loading config from: {self.config_path}")
            self.config = self.load_config()
        else:
            if self.config_path:
                log_warn(f"Config file not found: {self.config_path}")
            log_info("Activating interactive wizard...")
            self.config = self.run_wizard()

        Config.apply_yaml_config(self.config)
        self.validate_config()
        self.build_llm_configs()

        # STEP 2: LLM check
        print_step(2, TOTAL_STEPS, "LLM CONNECTION CHECK")
        self.validate_llm_connections()

        self.metadata_mgr = MetadataManager(get_paths().results)
        self.seed = generate_seed()

        # STEP 3: Data
        print_step(3, TOTAL_STEPS, "DATA")
        self.load_data()

        # STEP 4: Adapter
        print_step(4, TOTAL_STEPS, "ADAPTER")
        self.initialize_adapter()
        initial_prompt = self.load_prompt()
        # SPEC-104 D5: el adapter necesita el baseline para atribuir fallas de la tarea.
        self.adapter.set_baseline(initial_prompt.get("system_prompt", ""))

        # Reset real token tracking just before any task/reflection LLM call so
        # the snapshot in save_results reflects only this run's optimization.
        get_tracker().reset()
        # SPEC-104: contador de fallas limpio por corrida y configurado desde la
        # seccion opcional `failures` del YAML (FR-006).
        self.configure_failure_tracker()

        # STEPS 5-7 (Baseline, Optimization, Test+Summary) ocurren dentro de
        # execute_gepa_pipeline para preservar el flujo actual.
        try:
            self.execute_gepa_pipeline(initial_prompt, verbose=verbose)

            # FR-006: una corrida abortada no llega a save_results (ni al CSV).
            get_failure_tracker().check_abort()
        except RunAborted:
            # FR-008: la corrida abortada deja run.json con estado y conteos, sin CSV.
            try:
                self.save_aborted_run()
            except Exception as e:  # noqa: BLE001 - no debe tapar el motivo del aborto
                log_error(f"No se pudo escribir run.json de la corrida abortada: {e}")
            raise
        run_dir = self.save_results()

        if self.config:
            import shutil

            snapshot_path = run_dir / "config_snapshot.yaml"
            if self.config_path and Path(self.config_path).exists():
                shutil.copy2(self.config_path, snapshot_path)
            else:
                with open(snapshot_path, "w", encoding="utf-8") as f:
                    yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            log_info(f"Config snapshot saved: {snapshot_path}")

        log_ok("Optimization completed.")

        # Resumen final (RUN COMPLETED) como ultima salida, igual que DSPy.
        print_summary(
            metrics=self._summary_metrics,
            config=self._summary_config,
            delta=self._summary_delta,
        )

    def load_config(self) -> dict[str, Any]:
        """
        Load and parse YAML config file.

        Returns:
            Config dictionary

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If config is malformed
        """
        config_path = Path(self.config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            log_ok(f"Config loaded: {config['case']['name']}")
            return config

        except yaml.YAMLError as e:
            log_error("Invalid YAML format in config file:")
            log_error(f"  {e}")
            raise

    def run_wizard(self) -> dict[str, Any]:
        """
        Run interactive wizard to generate config.

        Returns:
            Config dictionary generated by wizard
        """
        wizard = InteractiveWizard()
        config = wizard.run()
        return config

    def validate_config(self):
        """
        Validate config structure and parameters.

        Raises:
            ValueError: If config has validation errors
        """
        errors = ConfigValidator.validate(self.config)

        if errors:
            error_msg = ConfigValidator.display_errors(errors)
            print(error_msg)
            raise ValueError(f"Config validation failed with {len(errors)} error(s)")

        log_ok("Config validation passed")

    def validate_llm_connections(self):
        """
        Validate Task and Reflection LM connections with a real probe.

        Raises:
            LLMConnectionError: If any endpoint is unreachable or misconfigured.
        """
        task_cfg = self.task_config
        ref_cfg = self.reflection_config

        log_info("Validando conexion con Task LM...")
        task_cfg.validate()
        task_cfg.validate_connection()
        log_ok(f"Task LM conectado: {task_cfg.describe()}")

        log_info("Validando conexion con Reflection LM...")
        ref_cfg.validate()
        ref_cfg.validate_connection()
        log_ok(f"Reflection LM conectado: {ref_cfg.describe()}")

    def load_data(self):
        """Load dataset using universal data loader."""
        csv_filename = self.config["data"]["csv_filename"]
        input_column = self.config["data"].get("input_column", "text")
        output_columns = self.config["data"].get("output_columns")

        log_info(f"Loading data from: {csv_filename}")

        # Load using universal function (cuando output_columns es None/vacio,
        # load_gepa_data infiere las columnas excluyendo split, case_id e input_column).
        self.train_data, self.val_data, self.test_data = load_gepa_data(
            csv_filename=csv_filename,
            input_column=input_column,
            output_columns=output_columns or None,
        )

        log_ok(
            f"Loaded: {len(self.train_data)} train, "
            f"{len(self.val_data)} val, {len(self.test_data)} test"
        )

    def initialize_adapter(self):
        """Initialize adapter based on config type."""
        adapter_type = self.config["adapter"]["type"]
        task_cfg = self.task_config
        log_info(f"Initializing {adapter_type} adapter...")

        if adapter_type == "classifier":
            valid_classes = self.config["adapter"]["valid_classes"]
            self.adapter = SimpleClassifierAdapter(
                valid_classes=valid_classes, temperature=self.active_temperature
            )

        elif adapter_type == "extractor":
            required_fields = self.config["adapter"]["required_fields"]
            max_pos = self.config["adapter"].get("extractor_max_positive_examples")
            max_resp = self.config.get("models", {}).get("max_tokens")
            opt_cfg = self.config.get("optimization", {})
            ignore_fields = opt_cfg.get("ignore_in_metric", [])

            self.adapter = SimpleExtractorAdapter(
                required_fields=required_fields,
                temperature=self.active_temperature,
                max_positive_examples=max_pos,
                max_response_tokens=max_resp,
                ignore_fields=ignore_fields,
                field_configs=opt_cfg.get("field_configs"),
                default_mode=opt_cfg.get("match_mode", "exact"),
                fuzzy_threshold=opt_cfg.get("fuzzy_threshold", 0.85),
                list_separators=opt_cfg.get("list_separators", ",;"),
            )

        elif adapter_type == "sql":
            self.adapter = SimpleSQLAdapter(temperature=self.active_temperature)

        elif adapter_type == "rag":
            max_pos = self.config["adapter"].get("max_positive_examples")
            rag_kwargs = {}
            judge_retries = (self.config.get("failures") or {}).get("judge_retries")
            if judge_retries is not None:  # FR-009: reintentos del juez desde el YAML
                rag_kwargs["judge_retries"] = judge_retries
            self.adapter = SimpleRAGAdapter(
                temperature=self.active_temperature, max_positive_examples=max_pos, **rag_kwargs
            )

        else:
            raise ValueError(f"Unsupported adapter type: {adapter_type}")

        # FR-010: reportar los parametros efectivos de las llamadas del adapter.
        print_kv("Task LM", task_cfg.describe(max_tokens=self.adapter.task_max_tokens))
        judge_max = getattr(self.adapter, "judge_max_tokens", None)
        if judge_max is not None:
            print_kv("Judge LM", self.adapter.judge_config.describe(max_tokens=judge_max))
        log_ok(f"Adapter initialized: {adapter_type}")

    def _eval_repeated(self, data, prompt) -> tuple[MetricSummary, float, Any]:
        """
        Evalua un prompt sobre un conjunto k=self.eval_repeats veces y devuelve
        `(resumen, rango, ultimo_resultado)`.

        El resumen (SPEC-104 FR-003) promedia solo los casos evaluados y trae
        `n_evaluados/n_total`; un caso NE no suma ni resta. El rango (en puntos
        porcentuales) es la dispersion entre repeticiones de la media de sus casos
        evaluados: una proxy simple del ruido del LLM. Si es mayor que la
        diferencia entre dos prompts, la "mejora" es indistinguible del ruido.
        `ultimo_resultado` es el `EvaluationBatch` de la ultima repeticion, para
        reutilizarlo sin una evaluacion extra (FR-014).
        """
        k = max(1, int(getattr(self, "eval_repeats", 1)))
        repeats: list[list[tuple[Any, float, bool]]] = []
        means: list[float] = []
        eval_result = None
        for _ in range(k):
            eval_result = self.adapter.evaluate(data, prompt)
            get_failure_tracker().check_abort()
            cases = [
                (output["case_id"], score, output.get("evaluated", True))
                for output, score in zip(eval_result.outputs, eval_result.scores, strict=True)
            ]
            repeats.append(cases)
            scored = [score for _, score, evaluated in cases if evaluated]
            if scored:
                means.append(sum(scored) / len(scored))
        rng = (max(means) - min(means)) * 100 if len(means) > 1 else 0.0
        return summarize(repeats), rng, eval_result

    def load_prompt(self) -> dict[str, str]:
        """
        Load initial prompt from JSON file.

        Returns:
            Prompt dictionary with 'system_prompt' key
        """
        prompt_filename = self.config["prompt"]["filename"]
        prompt_path = get_paths().prompt(prompt_filename)

        log_info(f"Loading prompt from: {prompt_filename}")

        with open(prompt_path, encoding="utf-8") as f:
            prompt = json.load(f)

        return prompt

    def execute_gepa_pipeline(self, initial_prompt: dict[str, str], verbose: bool = False):
        """
        Execute complete GEPA optimization pipeline.

        Args:
            initial_prompt: Initial prompt dictionary
            verbose: If True, show reflection analysis in console
        """
        case_title = self.config["case"].get("title", self.config["case"]["name"])

        print_header(f"[{ENGINE}] {case_title}")
        log_info(f"Command: {' '.join(sys.argv)}")

        from gepa_standalone.data.data_loader import print_dataset_info

        print_dataset_info(self.config["data"]["csv_filename"])

        print_prompt("PROMPT INICIAL", initial_prompt["system_prompt"])

        # Cuantas veces repetir evaluacion final (mitigacion de ruido LLM no
        # determinista). Default 1 = comportamiento legacy.
        self.eval_repeats = int(self.config["optimization"].get("eval_repeats", 1))

        # STEP 5: Baseline
        print_step(5, TOTAL_STEPS, "BASELINE PERFORMANCE")
        log_info(f"Evaluando prompt inicial en validacion (k={self.eval_repeats} repeticiones)...")
        baseline, baseline_range, _ = self._eval_repeated(self.val_data, initial_prompt)
        print_kv("Baseline accuracy", format_metric_line(baseline, baseline_range))
        get_failure_tracker().check_abort()

        # STEP 6: Optimization
        print_step(6, TOTAL_STEPS, "GEPA OPTIMIZATION")
        ref_cfg = self.reflection_config
        print_kv("Reflection LM", ref_cfg.describe())

        reflection_lm = create_reflection_lm_function(verbose=verbose, config=ref_cfg)

        # Snapshot parameters for consistency
        self.active_max_metric_calls = self.config["optimization"]["max_metric_calls"]
        self.active_skip_perfect_score = self.config["optimization"].get("skip_perfect_score", True)

        result = optimize(
            seed_candidate=initial_prompt,
            trainset=self.train_data,
            valset=self.val_data,
            adapter=self.adapter,
            task_lm=None,
            reflection_lm=reflection_lm,
            max_metric_calls=self.active_max_metric_calls,
            skip_perfect_score=self.active_skip_perfect_score,
            display_progress_bar=self.config["optimization"].get("display_progress_bar", True),
            # FR-005 / FR-013: el envoltorio de reflexion recibe la iteracion de GEPA
            # como case_id de sus fallas.
            callbacks=[reflection_lm],
        )
        # FR-006: GEPA atrapa las excepciones del reflection_lm y de la tarea; el
        # corte es por estado, consultado tras cada paso.
        get_failure_tracker().check_abort()

        optimized_prompt = result.best_candidate

        # Evolucion (mejor de cada etapa) y estadisticas de busqueda, comunes a
        # ambos motores via shared.display.
        print_gepa_evolution(
            result.candidates,
            result.val_aggregate_scores,
            best_idx=result.best_idx,
            discovery_eval_counts=getattr(result, "discovery_eval_counts", None),
        )
        best_val = None
        if result.val_aggregate_scores and result.best_idx is not None:
            best_val = result.val_aggregate_scores[result.best_idx]
        print_gepa_search_stats(
            num_candidates=len(result.candidates),
            total_metric_calls=result.total_metric_calls,
            best_idx=result.best_idx,
            best_score=best_val,
            num_full_val_evals=getattr(result, "num_full_val_evals", None),
        )

        # STEP 7: Test + Summary
        print_step(7, TOTAL_STEPS, "TEST + SUMMARY")
        prompt_changed = optimized_prompt["system_prompt"] != initial_prompt["system_prompt"]
        if not prompt_changed:
            log_warn(
                "GEPA no modifico el prompt: la diferencia baseline/optimized se "
                "interpretara como ruido de muestreo del LLM."
            )

        log_info(f"Midiendo desempeno del mejor prompt en val (k={self.eval_repeats})...")
        optimized, opt_range, _ = self._eval_repeated(self.val_data, optimized_prompt)
        print_kv("Optimized (val)", format_metric_line(optimized, opt_range))
        get_failure_tracker().check_abort()

        log_info(f"Verificando generalizacion en test (k={self.eval_repeats})...")
        test, test_range, eval_test = self._eval_repeated(self.test_data, optimized_prompt)
        print_kv("Test accuracy", format_metric_line(test, test_range))
        get_failure_tracker().check_abort()

        # FR-014: detalle de la ultima evaluacion de test ya calculada, sin una
        # segunda evaluacion (ni gasto de tokens extra).
        print_detailed_results(eval_test)

        print_prompt("PROMPT ORIGINAL", initial_prompt["system_prompt"])
        print_prompt("PROMPT OPTIMIZADO", optimized_prompt["system_prompt"])

        # FR-003: delta pareado sobre los casos de val evaluados con ambos prompts.
        delta = paired_delta(baseline, optimized)
        self.metric_summaries = {"baseline": baseline, "optimized": optimized, "test": test}
        self.paired_delta = delta

        # Resumen final: se difiere a run() para que el bloque RUN COMPLETED
        # quede como ultima salida, despues de save_results (igual que DSPy).
        self._summary_metrics = {"Baseline": baseline, "Optimized": optimized, "Test": test}
        self._summary_delta = delta
        self._summary_config = {
            "Task LM": self.adapter.model,
            "Reflection LM": self.reflection_config.model,
            "Budget used": f"{result.total_metric_calls} metric calls",
            "Eval repeats": str(self.eval_repeats),
            "Prompt changed": "Si" if prompt_changed else "No (delta=ruido)",
        }

        # Store results for logging
        effective_delta = delta.delta if prompt_changed else 0.0
        self.results = {
            "initial_prompt": initial_prompt["system_prompt"],
            "final_prompt": optimized_prompt["system_prompt"],
            "baseline_score": baseline.score,
            "baseline_range": baseline_range / 100,
            "optimized_score": optimized.score,
            "optimized_range": opt_range / 100,
            "test_score": test.score,
            "test_range": test_range / 100,
            "prompt_changed": prompt_changed,
            "effective_delta": effective_delta,
            "eval_repeats": self.eval_repeats,
            "total_metric_calls": result.total_metric_calls,
            "metrics": {name: m.to_dict() for name, m in self.metric_summaries.items()},
            "paired_delta": delta.to_dict(),
        }

    def save_results(self) -> Path:
        """
        Save final results and log to master CSV.

        Returns:
            Path to the run directory
        """
        run_id = str(uuid.uuid4())[:8]

        # Determine model names; restore configured temperature for accurate logging
        task_config = self.task_config
        reflect_config = self.reflection_config

        # Write reproducibility metadata (3 levels)
        self.metadata_mgr.ensure_environment()
        self.metadata_mgr.ensure_experiment(
            experiment_name=self.config["case"]["name"],
            dataset_path=get_paths().dataset(self.config["data"]["csv_filename"]),
            base_config={
                "adapter_type": self.config["adapter"]["type"],
                "optimization": self.config.get("optimization", {}),
            },
        )

        # Prepare metadata
        metadata = {
            "case": self.config["case"]["name"],
            "task_model": task_config.model,
            "reflection_model": reflect_config.model,
            "max_metric_calls": self.config["optimization"]["max_metric_calls"],
            "timestamp": datetime.now().isoformat(),
        }

        # Save detailed results
        run_dir = save_run_details(
            case_name=self.config["case"]["name"],
            run_id=run_id,
            initial_prompt=self.results["initial_prompt"],
            final_prompt=self.results["final_prompt"],
            metadata=metadata,
            results=self.results,
        )

        # Real token usage captured during this run -> cost with same pricing table
        usage = get_tracker().snapshot()
        cost = cost_from_usage(usage, task_config.model, reflect_config.model)
        usage["cost_usd"] = cost

        # Write run-level metadata (includes real usage block)
        delta = getattr(self, "paired_delta", None)
        self.metadata_mgr.create_run(
            run_dir=run_dir,
            experiment_name=self.config["case"]["name"],
            seed=self.seed,
            models=self._run_models(),
            usage=usage,
            status="completed",
            failures=get_failure_tracker().snapshot(),
            metrics=metrics_coverage(self.metric_summaries),
            paired_delta=delta.to_dict() if delta is not None else None,
        )

        # Log to master CSV (real tokens + cost; European comma decimal)
        log_experiment_result(
            case_title=self.config["case"].get("title", self.config["case"]["name"]),
            task_model=task_config.model,
            reflection_model=reflect_config.model,
            baseline_score=_csv_score(self.results["baseline_score"]),
            optimized_score=_csv_score(self.results["optimized_score"]),
            robustness_score=_csv_score(self.results["test_score"]),
            run_directory=str(run_dir),
            budget=metadata["max_metric_calls"],
            tokens_task=usage["task"]["prompt_tokens"] + usage["task"]["completion_tokens"],
            tokens_reflection=(
                usage["reflection"]["prompt_tokens"] + usage["reflection"]["completion_tokens"]
            ),
            cost_real_usd=f"{cost:.6f}".replace(".", ","),
        )

        return run_dir


def main():
    """Main entry point."""
    configure_stdio()
    parser = argparse.ArgumentParser(
        description="Universal GEPA Optimizer - Interfaz unica para todos los casos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples (run from repo root; -m is required so 'import shared' resolves):
  # Run with existing config
  python -m gepa_standalone.universal_optimizer \\
      --config gepa_standalone/experiments/configs/email_urgency.yaml

  # Run without config (activates wizard)
  python -m gepa_standalone.universal_optimizer

For more info, see: gepa_standalone/experiments/configs/
        """,
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to YAML config file. If not provided or doesn't exist, wizard mode activates.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show real-time reflection analysis from the Teacher model.",
    )

    args = parser.parse_args()

    # Initialize and run optimizer
    optimizer = UniversalOptimizer(config_path=args.config)

    try:
        optimizer.run(verbose=args.verbose)
    except LLMConnectionError as e:
        # Connection failure: print formatted diagnostic and terminate
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except RunAborted as e:
        log_error(optimizer.abort_message(e))
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nOptimizacion cancelada por el usuario.")
        sys.exit(130)
    except Exception as e:
        log_error(f"Optimization failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

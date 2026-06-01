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
    log_error,
    log_info,
    log_ok,
    log_warn,
    print_detailed_results,
    print_header,
    print_kv,
    print_step,
    print_summary,
)
from shared.llm import LLMConnectionError
from shared.llm.usage import get_tracker
from shared.logging.metadata import MetadataManager, collect_model_info, generate_seed
from shared.paths import get_paths

# Total de pasos del pipeline canonico (compartido con dspy_gepa_poc).
TOTAL_STEPS = 7
# Identificador del motor que aparece en el header del run.
ENGINE = "GEPA-STANDALONE"


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

        # Reset real token tracking just before any task/reflection LLM call so
        # the snapshot in save_results reflects only this run's optimization.
        get_tracker().reset()

        # STEPS 5-7 (Baseline, Optimization, Test+Summary) ocurren dentro de
        # execute_gepa_pipeline para preservar el flujo actual.
        self.execute_gepa_pipeline(initial_prompt, verbose=verbose)

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
        models_cfg = self.config.get("models", {})

        task_cfg = get_task_config()
        if models_cfg.get("temperature") is not None:
            task_cfg.temperature = models_cfg["temperature"]
        if models_cfg.get("max_tokens"):
            task_cfg.max_tokens = models_cfg["max_tokens"]

        ref_cfg = get_reflection_config()
        if models_cfg.get("temperature") is not None:
            ref_cfg.temperature = models_cfg["temperature"]
        if models_cfg.get("max_tokens"):
            ref_cfg.max_tokens = models_cfg["max_tokens"]

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

        # If output_columns not specified, infer from CSV
        if not output_columns:
            csv_path = get_paths().dataset(csv_filename)
            with open(csv_path, encoding="utf-8") as f:
                import csv

                reader = csv.DictReader(f)
                all_cols = reader.fieldnames
                output_columns = [c for c in all_cols if c not in ["split", input_column]]

        # Load using universal function
        self.train_data, self.val_data, self.test_data = load_gepa_data(
            csv_filename=csv_filename, input_column=input_column, output_columns=output_columns
        )

        log_ok(
            f"Loaded: {len(self.train_data)} train, "
            f"{len(self.val_data)} val, {len(self.test_data)} test"
        )

    def initialize_adapter(self):
        """Initialize adapter based on config type."""
        adapter_type = self.config["adapter"]["type"]
        models_cfg = self.config.get("models", {})
        # Capture actual temperature used for reporting consistency
        self.active_temperature = models_cfg.get("temperature", 0.0)

        task_cfg = get_task_config()
        task_cfg.temperature = self.active_temperature
        if models_cfg.get("max_tokens"):
            task_cfg.max_tokens = models_cfg["max_tokens"]
        print_kv("Task LM", task_cfg.describe())
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
            self.adapter = SimpleRAGAdapter(
                temperature=self.active_temperature, max_positive_examples=max_pos
            )

        else:
            raise ValueError(f"Unsupported adapter type: {adapter_type}")

        log_ok(f"Adapter initialized: {adapter_type}")

    def _eval_repeated(self, data, prompt) -> tuple[float, float]:
        """
        Evalua un prompt sobre un conjunto k=self.eval_repeats veces y
        devuelve (media, rango). Si k=1 devuelve (score, 0.0).

        El rango es una proxy simple de la dispersion del LLM no-determinista.
        Si el rango es mayor que la diferencia entre dos prompts, la
        "mejora" entre ellos es indistinguible del ruido.
        """
        k = max(1, int(getattr(self, "eval_repeats", 1)))
        scores: list[float] = []
        for _ in range(k):
            eval_result = self.adapter.evaluate(data, prompt)
            if eval_result.scores:
                scores.append(sum(eval_result.scores) / len(eval_result.scores))
            else:
                scores.append(0.0)
        mean = sum(scores) / len(scores)
        rng = max(scores) - min(scores) if len(scores) > 1 else 0.0
        return mean, rng

    def _has_positive_reflection(self) -> bool:
        """Determine if this run uses positive reflection."""
        adapter_type = self.config["adapter"]["type"]
        if adapter_type in ["extractor", "rag"]:
            max_pos = self.config["adapter"].get("max_positive_examples", 0)
            return max_pos > 0
        return False

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

        print(f"\nPROMPT INICIAL:\n{initial_prompt['system_prompt']}")

        # Cuantas veces repetir evaluacion final (mitigacion de ruido LLM no
        # determinista). Default 1 = comportamiento legacy.
        self.eval_repeats = int(self.config["optimization"].get("eval_repeats", 1))

        # STEP 5: Baseline
        print_step(5, TOTAL_STEPS, "BASELINE PERFORMANCE")
        log_info(f"Evaluando prompt inicial en validacion (k={self.eval_repeats} repeticiones)...")
        baseline_avg, baseline_range = self._eval_repeated(self.val_data, initial_prompt)
        print_kv(
            "Baseline accuracy",
            f"{baseline_avg * 100:.1f}% (rango {baseline_range * 100:.1f} pp)",
        )

        # STEP 6: Optimization
        print_step(6, TOTAL_STEPS, "GEPA OPTIMIZATION")
        models_config = self.config.get("models", {})

        ref_cfg = get_reflection_config()
        if models_config.get("temperature") is not None:
            ref_cfg.temperature = models_config["temperature"]
        if models_config.get("max_tokens") is not None:
            ref_cfg.max_tokens = models_config["max_tokens"]
        else:
            ref_cfg.max_tokens = 2000  # default usado por create_reflection_lm_function
        print_kv("Reflection LM", ref_cfg.describe())

        reflection_lm = create_reflection_lm_function(
            verbose=verbose,
            temperature=models_config.get("temperature"),
            max_tokens=models_config.get("max_tokens"),
            cache=models_config.get("cache"),
        )

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
        )

        optimized_prompt = result.best_candidate

        # STEP 7: Test + Summary
        print_step(7, TOTAL_STEPS, "TEST + SUMMARY")
        prompt_changed = optimized_prompt["system_prompt"] != initial_prompt["system_prompt"]
        if not prompt_changed:
            log_warn(
                "GEPA no modifico el prompt: la diferencia baseline/optimized se "
                "interpretara como ruido de muestreo del LLM."
            )

        log_info(f"Midiendo desempeno del mejor prompt en val (k={self.eval_repeats})...")
        opt_avg, opt_range = self._eval_repeated(self.val_data, optimized_prompt)
        print_kv("Optimized (val)", f"{opt_avg * 100:.1f}% (rango {opt_range * 100:.1f} pp)")

        log_info(f"Verificando generalizacion en test (k={self.eval_repeats})...")
        test_avg, test_range = self._eval_repeated(self.test_data, optimized_prompt)
        print_kv("Test accuracy", f"{test_avg * 100:.1f}% (rango {test_range * 100:.1f} pp)")

        # Detalle del ultimo test eval (para inspeccion humana)
        eval_test = self.adapter.evaluate(self.test_data, optimized_prompt)
        print_detailed_results(eval_test)

        print_summary(
            metrics={
                "Baseline": baseline_avg,
                "Optimized": opt_avg,
                "Test": test_avg,
            },
            config={
                "Task LM": self.adapter.model,
                "Reflection LM": get_reflection_config().model,
                "Budget used": f"{result.total_metric_calls} metric calls",
                "Eval repeats": str(self.eval_repeats),
                "Prompt changed": "Si" if prompt_changed else "No (delta=ruido)",
            },
        )

        print(f"\nPROMPT ORIGINAL:\n{initial_prompt['system_prompt']}")
        print(f"\nPROMPT OPTIMIZADO:\n{optimized_prompt['system_prompt']}")

        # Store results for logging
        effective_delta = (opt_avg - baseline_avg) if prompt_changed else 0.0
        self.results = {
            "initial_prompt": initial_prompt["system_prompt"],
            "final_prompt": optimized_prompt["system_prompt"],
            "baseline_score": baseline_avg,
            "baseline_range": baseline_range,
            "optimized_score": opt_avg,
            "optimized_range": opt_range,
            "test_score": test_avg,
            "test_range": test_range,
            "prompt_changed": prompt_changed,
            "effective_delta": effective_delta,
            "eval_repeats": self.eval_repeats,
            "total_metric_calls": result.total_metric_calls,
        }

    def save_results(self) -> Path:
        """
        Save final results and log to master CSV.

        Returns:
            Path to the run directory
        """
        run_id = str(uuid.uuid4())[:8]

        # Determine model names; restore configured temperature for accurate logging
        task_config = get_task_config()
        task_config.temperature = self.active_temperature
        reflect_config = get_reflection_config()

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
        self.metadata_mgr.create_run(
            run_dir=run_dir,
            experiment_name=self.config["case"]["name"],
            seed=self.seed,
            models=collect_model_info(task_config, reflect_config),
            usage=usage,
        )

        # Log to master CSV (real tokens + cost; European comma decimal)
        log_experiment_result(
            case_title=self.config["case"]["title"],
            task_model=task_config.model,
            reflection_model=reflect_config.model,
            baseline_score=self.results["baseline_score"],
            optimized_score=self.results["optimized_score"],
            robustness_score=self.results["test_score"],
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
    except KeyboardInterrupt:
        print("\n\nOptimizacion cancelada por el usuario.")
        sys.exit(130)
    except Exception as e:
        log_error(f"Optimization failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

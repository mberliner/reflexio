import argparse
import sys
from datetime import datetime
from pathlib import Path

import dspy
from dspy.evaluate import Evaluate

from dspy_gepa_poc import AppConfig, CSVDataLoader, GEPAOptimizer, LLMConfig, LLMConnectionError
from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory
from dspy_gepa_poc.metrics import create_dynamic_metric
from dspy_gepa_poc.results_logger import ResultsLogger
from shared.display import (
    log_error,
    log_info,
    log_ok,
    log_warn,
    print_header,
    print_kv,
    print_step,
    print_summary,
)
from shared.logging.metadata import MetadataManager, collect_model_info, generate_seed
from shared.paths import get_dspy_paths

# Total de pasos del pipeline canonico (compartido con gepa_standalone).
TOTAL_STEPS = 7
# Identificador del motor que aparece en el header del run.
ENGINE = "DSPY+GEPA"

# Scores <= 1.0 are normalized (0.0-1.0), > 1.0 are raw percentages
NORMALIZED_SCORE_MAX = 1.0


class ConfigurationError(Exception):
    """Error de configuracion con mensaje claro para el usuario."""

    pass


class ReflexioDeclarativa:
    """
    Orquestador principal para experimentos DSPy + GEPA.
    Replica la funcionalidad del optimizador universal pero adaptado a la
    arquitectura de Reflexio Nexus.
    """

    def __init__(self, config_path: str):
        log_info(f"Loading config from: {config_path}")
        self.config = AppConfig(yaml_path=config_path)
        run_ts = datetime.now()
        self.run_id = run_ts.strftime("%Y%m%d_%H%M%S")
        self.logger = ResultsLogger()

        self.results_dir = get_dspy_paths().run_dir(
            case_name=self.config.raw_config["case"]["name"], timestamp=run_ts
        )
        self.metadata_mgr = MetadataManager(get_dspy_paths().results)
        log_ok(f"Config loaded: {self.config.raw_config['case']['name']}")
        log_info(f"Results dir: {self.results_dir}")

    def setup_models(self):
        """Configure Task and Reflection LMs with connection validation."""
        self.task_config = LLMConfig.from_env("task")
        self.reflection_config = LLMConfig.from_env("reflection")

        models_config = self.config.raw_config.get("models", {})
        if "temperature" in models_config:
            self.task_config.temperature = models_config["temperature"]
            self.reflection_config.temperature = models_config["temperature"]
        if "max_tokens" in models_config:
            self.task_config.max_tokens = models_config["max_tokens"]
            self.reflection_config.max_tokens = models_config["max_tokens"]
        if "cache" in models_config:
            self.task_config.cache = models_config["cache"]
            self.reflection_config.cache = models_config["cache"]

        self.seed = generate_seed()

        self.task_config.validate()
        self.reflection_config.validate()

        print_kv("Task LM", self.task_config.describe())
        lm = self.task_config.get_dspy_lm()

        log_info("Validando conexion con Task LM...")
        self.task_config.validate_connection()
        log_ok("Task LM conectado")

        dspy.configure(lm=lm)

        print_kv("Reflection LM", self.reflection_config.describe())
        self.reflection_lm = self.reflection_config.get_dspy_lm()

        log_info("Validando conexion con Reflection LM...")
        self.reflection_config.validate_connection()
        log_ok("Reflection LM conectado")

    def load_data(self):
        """Load datasets based on config."""
        log_info(f"Loading dataset: {self.config.dataset_path}")
        loader = CSVDataLoader()

        # Determine input keys: acepta 'input_column' (string, legacy)
        # o 'input_columns' (lista, multi-input).
        data_cfg = self.config.raw_config["data"]
        if "input_columns" in data_cfg:
            input_keys = data_cfg["input_columns"]
            if not isinstance(input_keys, list):
                input_keys = [input_keys]
        else:
            input_keys = [data_cfg["input_column"]]

        # Load the CSV
        self.trainset, self.valset, self.testset = loader.load_dataset(
            filename=data_cfg["csv_filename"], input_keys=input_keys
        )
        log_ok(
            f"Loaded: {len(self.trainset)} train, {len(self.valset)} val, {len(self.testset)} test"
        )

    def create_module_and_metric(self):
        """Factory method to instantiate the correct Module and Metric."""
        module_type = self.config.raw_config["module"]["type"]
        log_info(f"Creating module for type: {module_type}")

        if module_type == "dynamic":
            # 1. Create Module from YAML
            sig_config = self.config.raw_config.get("signature")
            if not sig_config:
                raise ValueError(
                    "Module type is 'dynamic' but no 'signature' section found in config."
                )

            predictor_type = self.config.raw_config.get("optimization", {}).get(
                "predictor_type", "cot"
            )
            self.student = DynamicModuleFactory.create_module(
                sig_config, predictor_type=predictor_type
            )

            # 2. Create Dynamic Metric
            # Allows ignoring certain fields (like 'reasoning') during strict evaluation
            sig_config = self.config.raw_config.get("signature", {})
            output_fields = [out["name"] for out in sig_config.get("outputs", [])]

            # Get fields to ignore from config (modular)
            opt_config = self.config.raw_config.get("optimization", {})
            ignore_fields = opt_config.get("ignore_in_metric", [])
            eval_fields = [f for f in output_fields if f not in ignore_fields]

            # Match mode configuration
            match_mode = opt_config.get("match_mode", "exact")
            fuzzy_threshold = opt_config.get("fuzzy_threshold", 0.85)

            log_info(
                f"Evaluating fields: {eval_fields} (Ignored: {ignore_fields}, Match: {match_mode})"
            )

            self.metric = create_dynamic_metric(
                eval_fields, match_mode=match_mode, fuzzy_threshold=fuzzy_threshold
            )

            # 2.5 Validate metric fields against module outputs
            self._validate_metric_fields(eval_fields, output_fields)

            log_ok(f"Dynamic module created with outputs: {output_fields}")

            # 3. Modular Few-Shot Injection
            # If enabled, injects K examples from the trainset into the prompt
            opt_config = self.config.raw_config.get("optimization", {})
            if opt_config.get("use_few_shot", False):
                k = opt_config.get("few_shot_count", 3)
                log_info(f"Injecting {k} few-shot examples from trainset into the student.")
                from dspy.teleprompt import LabeledFewShot

                teleprompter = LabeledFewShot(k=k)
                self.student = teleprompter.compile(self.student, trainset=self.trainset)

        else:
            raise ValueError(
                f"Unsupported module type: {module_type}. "
                f"Only 'dynamic' is supported in this version."
            )

    def _validate_metric_fields(self, eval_fields: list, output_fields: list) -> None:
        """
        Valida que los campos de evaluacion existan en los outputs del modulo.

        Args:
            eval_fields: Campos que la metrica evaluara
            output_fields: Campos de salida definidos en la signature

        Raises:
            ConfigurationError: Si hay campos invalidos
        """
        invalid_fields = set(eval_fields) - set(output_fields)
        if invalid_fields:
            raise ConfigurationError(
                f"\n{'=' * 60}\n"
                f"ERROR DE CONFIGURACION: Campos de metrica invalidos\n"
                f"{'=' * 60}\n\n"
                f"Los siguientes campos en 'ignore_in_metric' o eval no existen "
                f"en outputs:\n"
                f"  Campos invalidos: {sorted(invalid_fields)}\n"
                f"  Campos disponibles: {sorted(output_fields)}\n\n"
                f"Acciones sugeridas:\n"
                f"  1. Verificar nombres en seccion 'signature.outputs' del YAML\n"
                f"  2. Corregir typos en 'optimization.ignore_in_metric'\n"
                f"{'=' * 60}"
            )

        if not eval_fields:
            log_warn("No hay campos para evaluar. Todos los outputs estan en ignore_in_metric.")

    def run(self):
        """Execute the optimization pipeline."""
        case_name = self.config.raw_config["case"]["name"]
        print_header(f"[{ENGINE}] {case_name}")
        log_info(f"Command: {' '.join(sys.argv)}")

        # STEP 1: Config (ya validado en __init__, anunciamos el step)
        print_step(1, TOTAL_STEPS, "CONFIG")
        log_ok(f"Case: {case_name}")

        # STEP 2: LLM check
        print_step(2, TOTAL_STEPS, "LLM CONNECTION CHECK")
        self.setup_models()

        # STEP 3: Data
        print_step(3, TOTAL_STEPS, "DATA")
        self.load_data()

        # STEP 4: Module/metric
        print_step(4, TOTAL_STEPS, "MODULE & METRIC")
        self.create_module_and_metric()

        num_threads = self.config.raw_config.get("optimization", {}).get("num_threads", 1)

        # STEP 5: Baseline
        print_step(5, TOTAL_STEPS, "BASELINE PERFORMANCE")
        log_info("Evaluando prompt inicial en conjunto de validacion...")
        evaluator_val = Evaluate(
            devset=self.valset, metric=self.metric, num_threads=num_threads, display_progress=True
        )
        baseline_score = self._to_float_score(evaluator_val(self.student))
        print_kv("Baseline accuracy", self._format_score(baseline_score))

        # STEP 6: Optimization
        print_step(6, TOTAL_STEPS, "GEPA OPTIMIZATION")
        optimizer = GEPAOptimizer(
            metric=self.metric, reflection_lm=self.reflection_lm, config=self.config.gepa
        )

        self.optimized_student = optimizer.compile(
            student=self.student, trainset=self.trainset, valset=self.valset
        )

        # STEP 7: Test + Summary
        print_step(7, TOTAL_STEPS, "TEST + SUMMARY")
        log_info("Midiendo desempeno del mejor prompt en val...")
        optimized_score = self._to_float_score(evaluator_val(self.optimized_student))
        print_kv("Optimized (val)", self._format_score(optimized_score))

        if len(self.testset) > 0:
            log_info("Verificando generalizacion en conjunto de prueba...")
            evaluator_test = Evaluate(
                devset=self.testset,
                metric=self.metric,
                num_threads=num_threads,
                display_progress=True,
            )
            test_score = self._to_float_score(evaluator_test(self.optimized_student))
            print_kv("Test accuracy", self._format_score(test_score))
        else:
            log_warn("No test set available. Skipping robustness test.")
            test_score = 0.0

        self.save_results(baseline_score, optimized_score, test_score)

        # Resumen final unificado (mismo formato que gepa_standalone).
        print_summary(
            metrics={
                "Baseline": baseline_score,
                "Optimized": optimized_score,
                "Test": test_score,
            },
            config={
                "Task LM": self.task_config.model,
                "Reflection LM": self.reflection_config.model,
                "Budget": f"{self.config.gepa.max_metric_calls} metric calls",
            },
        )

    def save_results(self, baseline_score: float, optimized_score: float, test_score: float):
        """Save the optimized module and config."""
        log_info(f"Saving results to {self.results_dir}...")

        model_path = self.results_dir / "optimized_program.json"
        self.optimized_student.save(str(model_path))
        log_ok(f"Model saved: {model_path}")

        import yaml

        config_out = self.results_dir / "config_snapshot.yaml"
        with open(config_out, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.config.raw_config, f, allow_unicode=True)
        log_ok(f"Config snapshot saved: {config_out}")

        # Prepare notes (free-form metadata, budget goes in dedicated column)
        opt_config = self.config.raw_config.get("optimization", {})
        few_shot_info = f"Few-Shot: {'Yes' if opt_config.get('use_few_shot') else 'No'}"
        if opt_config.get("use_few_shot"):
            few_shot_info += f" (k={opt_config.get('few_shot_count', 3)})"

        # Write reproducibility metadata (3 levels)
        self.metadata_mgr.ensure_environment()
        self.metadata_mgr.ensure_experiment(
            experiment_name=self.config.raw_config["case"]["name"],
            dataset_path=Path(self.config.dataset_path),
            base_config={
                "module_type": self.config.raw_config["module"]["type"],
                "optimization": opt_config,
            },
        )
        self.metadata_mgr.create_run(
            run_dir=self.results_dir,
            experiment_name=self.config.raw_config["case"]["name"],
            seed=self.seed,
            models=collect_model_info(self.task_config, self.reflection_config),
        )

        # Log to master CSV
        self.logger.log_run(
            {
                "case_name": self.config.raw_config["case"]["name"],
                "module_type": self.config.raw_config["module"]["type"],
                "task_model": self.task_config.model,
                "reflection_model": self.reflection_config.model,
                "budget_type": self.config.gepa.auto_budget,
                "max_calls": self.config.gepa.max_metric_calls,
                "budget": self.config.gepa.max_metric_calls,
                "baseline_score": baseline_score,
                "optimized_score": optimized_score,  # Best Validation Score
                "test_score": test_score,  # Held-out Test Score
                "run_dir": str(self.results_dir),
                "notes": f"Strategy: {self.config.gepa.auto_budget}, {few_shot_info}",
            }
        )

        log_ok("Run logged successfully.")

    @staticmethod
    def _to_float_score(score_value) -> float:
        if isinstance(score_value, dict):
            score_value = score_value.get("score", 0.0)
        elif hasattr(score_value, "score"):
            score_value = score_value.score

        try:
            return float(score_value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _format_score(score_value: float) -> str:
        return f"{score_value:.2f}%" if score_value > NORMALIZED_SCORE_MAX else f"{score_value:.2%}"


def main():
    parser = argparse.ArgumentParser(
        description="Ejecutar optimización GEPA para DSPy (Reflexio Declarativa)"
    )
    parser.add_argument("--config", help="Ruta al archivo de configuración YAML", required=True)
    args = parser.parse_args()

    try:
        optimizer = ReflexioDeclarativa(args.config)
        optimizer.run()
    except ConfigurationError as e:
        # Error de configuracion con mensaje claro
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except LLMConnectionError as e:
        # Error ya formateado, solo imprimir y salir
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nOptimizacion cancelada por el usuario.")
        sys.exit(130)
    except Exception as e:
        log_error(f"Run failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

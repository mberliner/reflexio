import argparse
import sys
from datetime import datetime
from pathlib import Path

import dspy

# Allow running the script directly by adding project root to sys.path
# This makes 'python dspy_gepa_poc/reflexio_declarativa.py' work
if __name__ == "__main__" and __package__ is None:
    # Calculate project root (one level up from the folder containing this script)
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

# Importar componentes internos
from dspy.evaluate import Evaluate

from dspy_gepa_poc import AppConfig, CSVDataLoader, GEPAOptimizer, LLMConfig, LLMConnectionError
from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory
from dspy_gepa_poc.metrics import create_dynamic_metric
from dspy_gepa_poc.results_logger import ResultsLogger
from shared.display import print_header, print_section
from shared.paths import get_dspy_paths

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
        print(f"Iniciando Reflexio Declarativa con config: {config_path}")
        self.config = AppConfig(yaml_path=config_path)
        run_ts = datetime.now()
        self.run_id = run_ts.strftime("%Y%m%d_%H%M%S")
        self.logger = ResultsLogger()

        # Setup output paths using shared paths
        self.results_dir = get_dspy_paths().run_dir(
            case_name=self.config.raw_config["case"]["name"], timestamp=run_ts
        )
        print(f"Results will be saved to: {self.results_dir}")

    def setup_models(self):
        """Configure Task and Reflection LMs with connection validation."""
        print("Setting up Language Models...")

        # Load configurations from environment
        self.task_config = LLMConfig.from_env("task")
        self.reflection_config = LLMConfig.from_env("reflection")

        # Apply overrides from YAML config if specified
        models_config = self.config.raw_config.get("models", {})
        if "temperature" in models_config:
            self.task_config.temperature = models_config["temperature"]
        if "cache" in models_config:
            self.task_config.cache = models_config["cache"]
            self.reflection_config.cache = models_config["cache"]

        task_model_name = self.task_config.model
        reflection_model_name = self.reflection_config.model

        # Validate configuration
        self.task_config.validate()
        self.reflection_config.validate()

        # Configure Main Task LM
        print(f"  Configurando Task LM: {task_model_name}")
        lm = self.task_config.get_dspy_lm()

        # Validate Task LM connection
        print("  Validando conexion con Task LM...")
        self.task_config.validate_connection()
        print("  [OK] Task LM conectado")

        dspy.configure(lm=lm)

        # Configure Reflection LM (for GEPA)
        print(f"  Configurando Reflection LM: {reflection_model_name}")
        self.reflection_lm = self.reflection_config.get_dspy_lm()

        # Validate Reflection LM connection
        print("  Validando conexion con Reflection LM...")
        self.reflection_config.validate_connection()
        print("  [OK] Reflection LM conectado")

        print("Language Models configurados correctamente.")

    def load_data(self):
        """Load datasets based on config."""
        print(f"Loading dataset: {self.config.dataset_path}")
        loader = CSVDataLoader()

        # Determine input keys based on config
        input_key = self.config.raw_config["data"]["input_column"]

        # Load the CSV
        self.trainset, self.valset, self.testset = loader.load_dataset(
            filename=self.config.raw_config["data"]["csv_filename"], input_keys=[input_key]
        )
        print(
            f"Loaded {len(self.trainset)} training, {len(self.valset)} validation, "
            f"and {len(self.testset)} test examples."
        )

    def create_module_and_metric(self):
        """Factory method to instantiate the correct Module and Metric."""
        module_type = self.config.raw_config["module"]["type"]
        print(f"Creating module for type: {module_type}")

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

            print(
                f"Evaluating fields: {eval_fields} (Ignored: {ignore_fields}, Match: {match_mode})"
            )

            self.metric = create_dynamic_metric(
                eval_fields, match_mode=match_mode, fuzzy_threshold=fuzzy_threshold
            )

            # 2.5 Validate metric fields against module outputs
            self._validate_metric_fields(eval_fields, output_fields)

            print(f"Dynamic module created with outputs: {output_fields}")

            # 3. Modular Few-Shot Injection
            # If enabled, injects K examples from the trainset into the prompt
            opt_config = self.config.raw_config.get("optimization", {})
            if opt_config.get("use_few_shot", False):
                k = opt_config.get("few_shot_count", 3)
                print(f"Modular: Injecting {k} few-shot examples from trainset into the student.")
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

        # Warn if eval_fields is empty
        if not eval_fields:
            print(
                "  [WARN] No hay campos para evaluar. Todos los outputs estan en ignore_in_metric."
            )

    def run(self):
        """Execute the optimization pipeline."""
        self.setup_models()
        self.load_data()
        self.create_module_and_metric()

        case_name = self.config.raw_config["case"]["name"]
        print_header(f"GEPA Optimization: {case_name}")

        print(
            f"\nDataset: {len(self.trainset)} train, "
            f"{len(self.valset)} val, {len(self.testset)} test"
        )
        num_threads = self.config.raw_config.get("optimization", {}).get("num_threads", 1)

        # 1. BASELINE
        print_section("BASELINE PERFORMANCE")
        print(">> Evaluando prompt inicial en conjunto de validacion...")
        evaluator_val = Evaluate(
            devset=self.valset, metric=self.metric, num_threads=num_threads, display_progress=True
        )
        baseline_score = self._to_float_score(evaluator_val(self.student))
        print(f"Precision Baseline: {self._format_score(baseline_score)}")

        # 2. GEPA OPTIMIZATION
        print_section("GEPA OPTIMIZATION")
        optimizer = GEPAOptimizer(
            metric=self.metric, reflection_lm=self.reflection_lm, config=self.config.gepa
        )

        self.optimized_student = optimizer.compile(
            student=self.student, trainset=self.trainset, valset=self.valset
        )

        # 3. OPTIMIZED PERFORMANCE
        print_section("OPTIMIZED PERFORMANCE")
        print(">> Midiendo desempeno del mejor prompt encontrado...")
        optimized_score = self._to_float_score(evaluator_val(self.optimized_student))
        print(f"Precision Optimizada (Val): {self._format_score(optimized_score)}")

        # 4. ROBUSTNESS TEST
        print_section("ROBUSTNESS TEST")
        print(">> Verificando generalizacion en conjunto de prueba...")
        if len(self.testset) > 0:
            evaluator_test = Evaluate(
                devset=self.testset,
                metric=self.metric,
                num_threads=num_threads,
                display_progress=True,
            )
            test_score = self._to_float_score(evaluator_test(self.optimized_student))
            print(f"Precision Test: {self._format_score(test_score)}")
        else:
            print("No test set available. Skipping robustness test.")
            test_score = 0.0

        # Save Artifacts
        self.save_results(baseline_score, optimized_score, test_score)

    def save_results(self, baseline_score: float, optimized_score: float, test_score: float):
        """Save the optimized module and config."""
        print(f"\nSaving results to {self.results_dir}...")

        # Save optimized DSPy module (JSON)
        model_path = self.results_dir / "optimized_program.json"
        self.optimized_student.save(str(model_path))
        print(f"  - Model saved: {model_path}")

        # Save Configuration used (YAML)
        import yaml

        config_out = self.results_dir / "config_snapshot.yaml"
        with open(config_out, "w") as f:
            yaml.safe_dump(self.config.raw_config, f)
        print(f"  - Config snapshot saved: {config_out}")

        # Prepare notes (free-form metadata, budget goes in dedicated column)
        opt_config = self.config.raw_config.get("optimization", {})
        few_shot_info = f"Few-Shot: {'Yes' if opt_config.get('use_few_shot') else 'No'}"
        if opt_config.get("use_few_shot"):
            few_shot_info += f" (k={opt_config.get('few_shot_count', 3)})"

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

        print("\nOptimization Run Completed Successfully!")

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
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

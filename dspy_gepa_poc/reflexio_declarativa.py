import argparse
import sys
from datetime import datetime
from pathlib import Path

import dspy
from dspy.evaluate import Evaluate

from dspy_gepa_poc import AppConfig, CSVDataLoader, GEPAOptimizer, LLMConfig, LLMConnectionError
from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory
from dspy_gepa_poc.metrics import (
    create_dynamic_metric,
    create_dynamic_metric_with_feedback,
    create_pipeline_metric_with_feedback,
)
from dspy_gepa_poc.results_logger import ResultsLogger
from shared.analysis.roi_calculator import cost_from_usage
from shared.display import (
    configure_stdio,
    log_error,
    log_info,
    log_ok,
    log_warn,
    print_gepa_evolution,
    print_gepa_search_stats,
    print_header,
    print_kv,
    print_prompt,
    print_step,
    print_summary,
)
from shared.llm.usage import get_tracker, record_dspy_history
from shared.logging.metadata import MetadataManager, collect_model_info, generate_seed
from shared.paths import get_dspy_paths

# Total de pasos del pipeline canonico (compartido con gepa_standalone).
TOTAL_STEPS = 7
# Identificador del motor que aparece en el header del run.
ENGINE = "DSPY+GEPA"

# Scores <= 1.0 are normalized (0.0-1.0), > 1.0 are raw percentages
NORMALIZED_SCORE_MAX = 1.0


def _coerce_candidate(candidate: object) -> dict[str, str]:
    """Normaliza un candidato GEPA a un dict JSON-serializable (componente -> texto)."""
    if isinstance(candidate, dict):
        return {str(k): str(v) for k, v in candidate.items()}
    return {"_repr": str(candidate)}


def build_candidates_payload(
    candidates: list,
    val_scores: list,
    *,
    best_idx: int | None = None,
    total_metric_calls: int = 0,
    discovery_eval_counts: list | None = None,
) -> dict:
    """Arma el payload de candidatos GEPA para persistir, incluidos los rechazados.

    Marca `is_improvement` (supero el mejor score visto hasta el momento = lo que la
    metrica adopto en su cadena de mejora) para distinguir, por contraste, las
    propuestas que la metrica NO tomo (las que quedan en False y no son `is_best`).
    """
    n = min(len(candidates), len(val_scores))
    running_max = float("-inf")
    items: list[dict] = []
    for i in range(n):
        score = val_scores[i]
        is_improvement = i == 0 or score > running_max
        running_max = max(running_max, score)
        item: dict = {
            "idx": i,
            "val_score": score,
            "is_best": best_idx is not None and i == best_idx,
            "is_improvement": is_improvement,
            "instructions": _coerce_candidate(candidates[i]),
        }
        if discovery_eval_counts and i < len(discovery_eval_counts):
            item["metric_calls"] = discovery_eval_counts[i]
        items.append(item)
    return {
        "num_candidates": n,
        "best_idx": best_idx,
        "total_metric_calls": total_metric_calls,
        "candidates": items,
    }


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
        _case = self.config.raw_config["case"]
        log_ok(f"Config loaded: {_case.get('title', _case['name'])}")
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
        # Keep a reference to read real token usage from its history after the run.
        self.task_lm = lm

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
            field_configs = opt_config.get("field_configs")
            use_feedback = opt_config.get("metric_feedback", bool(field_configs))

            log_info(
                f"Evaluating fields: {eval_fields} (Ignored: {ignore_fields}, "
                f"Match: {match_mode}, Feedback: {use_feedback})"
            )

            if use_feedback:
                self.metric = create_dynamic_metric_with_feedback(
                    eval_fields,
                    field_configs=field_configs,
                    default_mode=match_mode if match_mode != "exact" else "normalized",
                    fuzzy_threshold=fuzzy_threshold,
                )
            else:
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

        elif module_type == "rule_derived":
            # El LLM emite p1..p5 + alto_impacto; el color (clasificacion) se DERIVA
            # con fast_gate_rule.derive_color. Fiel al Marco y auditable (D-013).
            sig_config = self.config.raw_config.get("signature")
            if not sig_config:
                raise ValueError("Module type is 'rule_derived' but no 'signature' section found.")

            opt_config = self.config.raw_config.get("optimization", {})
            predictor_type = opt_config.get("predictor_type", "cot")
            self.student = DynamicModuleFactory.create_rule_derived_module(
                sig_config, predictor_type=predictor_type
            )

            output_fields = [out["name"] for out in sig_config.get("outputs", [])]
            ignore_fields = opt_config.get("ignore_in_metric", [])
            eval_fields = [f for f in output_fields if f not in ignore_fields]

            match_mode = opt_config.get("match_mode", "exact")
            fuzzy_threshold = opt_config.get("fuzzy_threshold", 0.85)
            field_configs = opt_config.get("field_configs")
            use_feedback = opt_config.get("metric_feedback", bool(field_configs))

            log_info(
                f"rule_derived: eval={eval_fields} (Ignored: {ignore_fields}, "
                f"Match: {match_mode}, Feedback: {use_feedback})"
            )

            if use_feedback:
                self.metric = create_dynamic_metric_with_feedback(
                    eval_fields,
                    field_configs=field_configs,
                    default_mode=match_mode if match_mode != "exact" else "normalized",
                    fuzzy_threshold=fuzzy_threshold,
                )
            else:
                self.metric = create_dynamic_metric(
                    eval_fields, match_mode=match_mode, fuzzy_threshold=fuzzy_threshold
                )

            self._validate_metric_fields(eval_fields, output_fields)
            log_ok(f"rule_derived module created with outputs: {output_fields}")

            if opt_config.get("use_few_shot", False):
                k = opt_config.get("few_shot_count", 3)
                log_info(f"Injecting {k} few-shot examples from trainset into the student.")
                from dspy.teleprompt import LabeledFewShot

                teleprompter = LabeledFewShot(k=k)
                self.student = teleprompter.compile(self.student, trainset=self.trainset)

        elif module_type == "pipeline":
            stages = self.config.raw_config.get("stages")
            routing = self.config.raw_config.get("routing")
            if not stages or not routing:
                raise ConfigurationError(
                    "Module type 'pipeline' requires 'stages' and 'routing' sections in config."
                )

            self.student = DynamicModuleFactory.create_pipeline_module(stages, routing)

            # Outputs por etapa
            triage_outputs = [o["name"] for o in stages[0]["signature"]["outputs"]]
            fastgate_outputs = [o["name"] for o in stages[1]["signature"]["outputs"]]
            all_outputs = triage_outputs + fastgate_outputs

            opt_config = self.config.raw_config.get("optimization", {})
            ignore_fields = opt_config.get("ignore_in_metric", [])
            eval_fields = [f for f in all_outputs if f not in ignore_fields]

            triage_eval = [f for f in triage_outputs if f in eval_fields]
            fastgate_eval = [f for f in fastgate_outputs if f in eval_fields]

            match_mode = opt_config.get("match_mode", "normalized")
            fuzzy_threshold = opt_config.get("fuzzy_threshold", 0.85)
            field_configs = opt_config.get("field_configs", {})

            log_info(
                f"Pipeline metric: triage={triage_eval}, fast_gate={fastgate_eval}, "
                f"ignored={ignore_fields}, default_mode={match_mode}"
            )

            self.metric = create_pipeline_metric_with_feedback(
                gate_field=routing["gate_field"],
                gate_value=routing["gate_value"],
                triage_fields=triage_eval,
                fastgate_fields=fastgate_eval,
                field_configs=field_configs,
                default_mode=match_mode if match_mode != "exact" else "normalized",
                fuzzy_threshold=fuzzy_threshold,
            )

            self._validate_metric_fields(eval_fields, all_outputs)
            log_ok(f"Pipeline module created: {len(stages)} stages, outputs={all_outputs}")

            # Few-shot opcional (consistente con rama dinamica)
            if opt_config.get("use_few_shot", False):
                k = opt_config.get("few_shot_count", 3)
                log_info(f"Injecting {k} few-shot examples from trainset into the pipeline.")
                from dspy.teleprompt import LabeledFewShot

                teleprompter = LabeledFewShot(k=k)
                self.student = teleprompter.compile(self.student, trainset=self.trainset)

        else:
            raise ValueError(
                f"Unsupported module type: {module_type}. "
                "Supported: 'dynamic', 'rule_derived', 'pipeline'."
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
        case = self.config.raw_config["case"]
        print_header(f"[{ENGINE}] {case.get('title', case['name'])}")
        log_info(f"Command: {' '.join(sys.argv)}")

        # STEP 1: Config (ya validado en __init__, anunciamos el step)
        print_step(1, TOTAL_STEPS, "CONFIG")
        log_ok(f"Case: {case.get('title', case['name'])}")

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
        self.eval_repeats = int(
            self.config.raw_config.get("optimization", {}).get("eval_repeats", 1)
        )

        # Snapshot de instructions iniciales (por predictor) para detectar si
        # GEPA realmente modifico el prompt al final.
        self._initial_instructions = self._snapshot_instructions(self.student)
        print_prompt("PROMPT INICIAL", self._initial_instructions)

        # STEP 5: Baseline
        print_step(5, TOTAL_STEPS, "BASELINE PERFORMANCE")
        log_info(f"Evaluando prompt inicial en validacion (k={self.eval_repeats} repeticiones)...")
        evaluator_val = Evaluate(
            devset=self.valset, metric=self.metric, num_threads=num_threads, display_progress=True
        )
        baseline_score, baseline_range = self._eval_repeated(evaluator_val, self.student)
        print_kv(
            "Baseline accuracy",
            f"{self._format_score(baseline_score)} (rango {baseline_range:.1f} pp)",
        )

        # STEP 6: Optimization
        print_step(6, TOTAL_STEPS, "GEPA OPTIMIZATION")
        optimizer = GEPAOptimizer(
            metric=self.metric, reflection_lm=self.reflection_lm, config=self.config.gepa
        )

        self.optimized_student = optimizer.compile(
            student=self.student, trainset=self.trainset, valset=self.valset
        )

        # Evolucion (mejor de cada etapa) y estadisticas de busqueda, leidas del
        # detailed_results de GEPA. Unifica la vision con gepa_standalone.
        detailed = optimizer.get_detailed_results()
        if detailed is not None:
            candidates = getattr(detailed, "candidates", None)
            val_scores = getattr(detailed, "val_aggregate_scores", None)
            best_idx = getattr(detailed, "best_idx", None)
            if candidates and val_scores:
                print_gepa_evolution(
                    candidates,
                    val_scores,
                    best_idx=best_idx,
                    discovery_eval_counts=getattr(detailed, "discovery_eval_counts", None),
                )
                best_val = (
                    val_scores[best_idx]
                    if best_idx is not None and best_idx < len(val_scores)
                    else None
                )
                print_gepa_search_stats(
                    num_candidates=len(candidates),
                    total_metric_calls=getattr(detailed, "total_metric_calls", 0),
                    best_idx=best_idx,
                    best_score=best_val,
                    num_full_val_evals=getattr(detailed, "num_full_val_evals", None),
                )
                # Persistir TODOS los candidatos (incl. los que la metrica no adopto),
                # que de otro modo solo viven en la consola y se pierden al cerrar.
                self._save_candidates(
                    build_candidates_payload(
                        candidates,
                        val_scores,
                        best_idx=best_idx,
                        total_metric_calls=getattr(detailed, "total_metric_calls", 0),
                        discovery_eval_counts=getattr(detailed, "discovery_eval_counts", None),
                    )
                )
        else:
            log_warn("GEPA no expuso detailed_results: se omite evolucion y stats de busqueda.")

        # STEP 7: Test + Summary
        print_step(7, TOTAL_STEPS, "TEST + SUMMARY")
        final_instructions = self._snapshot_instructions(self.optimized_student)
        prompt_changed = final_instructions != self._initial_instructions
        if not prompt_changed:
            log_warn(
                "GEPA no modifico las instructions del modulo: el delta "
                "baseline/optimized se interpretara como ruido del LLM."
            )

        print_prompt("PROMPT ORIGINAL", self._initial_instructions)
        print_prompt("PROMPT OPTIMIZADO", final_instructions)

        log_info(f"Midiendo desempeno del mejor prompt en val (k={self.eval_repeats})...")
        optimized_score, optimized_range = self._eval_repeated(
            evaluator_val, self.optimized_student
        )
        print_kv(
            "Optimized (val)",
            f"{self._format_score(optimized_score)} (rango {optimized_range:.1f} pp)",
        )

        if len(self.testset) > 0:
            log_info(f"Verificando generalizacion en test (k={self.eval_repeats})...")
            evaluator_test = Evaluate(
                devset=self.testset,
                metric=self.metric,
                num_threads=num_threads,
                display_progress=True,
            )
            test_score, test_range = self._eval_repeated(evaluator_test, self.optimized_student)
            print_kv(
                "Test accuracy",
                f"{self._format_score(test_score)} (rango {test_range:.1f} pp)",
            )
        else:
            log_warn("No test set available. Skipping robustness test.")
            test_score = 0.0
            test_range = 0.0

        self.prompt_changed = prompt_changed
        self.effective_delta = (optimized_score - baseline_score) if prompt_changed else 0.0
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
                "Eval repeats": str(self.eval_repeats),
                "Prompt changed": "Si" if prompt_changed else "No (delta=ruido)",
            },
        )

    def _save_candidates(self, payload: dict) -> None:
        """Vuelca el payload de candidatos GEPA a `candidates.json` en el run dir."""
        import json

        self.results_dir.mkdir(parents=True, exist_ok=True)
        path = self.results_dir / "candidates.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log_ok(f"GEPA candidates saved: {path} ({payload['num_candidates']} candidatos)")

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
        # Real token usage: DSPy calls litellm internally, so read it from each
        # LM's history (task LM + reflection LM) into the shared tracker.
        tracker = get_tracker()
        tracker.reset()
        task_history = getattr(self.task_lm, "history", None)
        reflection_history = getattr(self.reflection_lm, "history", None)
        record_dspy_history("task", task_history)
        record_dspy_history("reflection", reflection_history)
        # dspy.LM.history is capped at settings.max_history_size (default 10000):
        # once reached, oldest entries are dropped and token/cost totals would be
        # undercounted. Warn so an incomplete count is never read as authoritative.
        max_hist = getattr(dspy.settings, "max_history_size", None)
        if max_hist:
            for label, history in (("Task", task_history), ("Reflection", reflection_history)):
                if history is not None and len(history) >= max_hist:
                    log_warn(
                        f"{label} LM history alcanzo el tope de {max_hist} entradas; "
                        "los tokens/costo reales registrados pueden estar subestimados."
                    )
        usage = tracker.snapshot()
        cost = cost_from_usage(usage, self.task_config.model, self.reflection_config.model)
        usage["cost_usd"] = cost

        self.metadata_mgr.create_run(
            run_dir=self.results_dir,
            experiment_name=self.config.raw_config["case"]["name"],
            seed=self.seed,
            models=collect_model_info(self.task_config, self.reflection_config),
            usage=usage,
        )

        # Log to master CSV
        _case = self.config.raw_config["case"]
        self.logger.log_run(
            {
                "case_name": _case.get("title", _case["name"]),
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
                "tokens_task": usage["task"]["prompt_tokens"] + usage["task"]["completion_tokens"],
                "tokens_reflection": (
                    usage["reflection"]["prompt_tokens"] + usage["reflection"]["completion_tokens"]
                ),
                "cost_real_usd": f"{cost:.6f}".replace(".", ","),
                "notes": (
                    f"Strategy: {self.config.gepa.auto_budget}, {few_shot_info}, "
                    f"prompt_changed={'yes' if getattr(self, 'prompt_changed', False) else 'no'}, "
                    f"k={getattr(self, 'eval_repeats', 1)}"
                ),
            }
        )

        log_ok("Run logged successfully.")

    @staticmethod
    def _snapshot_instructions(module) -> dict[str, str]:
        """
        Captura el campo .signature.instructions de cada predictor del modulo.
        Permite detectar despues si GEPA modifico el prompt.
        """
        snapshot: dict[str, str] = {}
        try:
            for name, predictor in module.named_predictors():
                sig = getattr(predictor, "signature", None)
                instr = getattr(sig, "instructions", "") if sig is not None else ""
                snapshot[name] = instr or ""
        except Exception:
            # Si el modulo no expone predictors estandar, snapshot vacio
            return {}
        return snapshot

    def _eval_repeated(self, evaluator, student) -> tuple[float, float]:
        """
        Ejecuta evaluator(student) k veces y devuelve (media, rango). Si k=1,
        comportamiento equivalente al legacy con rango=0.
        """
        k = max(1, int(getattr(self, "eval_repeats", 1)))
        scores: list[float] = []
        for _ in range(k):
            scores.append(self._to_float_score(evaluator(student)))
        mean = sum(scores) / len(scores)
        rng = max(scores) - min(scores) if len(scores) > 1 else 0.0
        return mean, rng

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
    configure_stdio()
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

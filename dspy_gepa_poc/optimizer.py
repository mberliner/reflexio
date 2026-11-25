"""
GEPA optimizer integration for DSPy programs.
"""

from collections.abc import Callable

import dspy

from shared.display import log_info, print_kv, print_section
from shared.llm.dspy_lm import dspy_reflection_proposer

from .config import GEPAConfig


class GEPAOptimizer:
    """
    Wrapper class for GEPA optimizer with configuration management.
    """

    _compiled_program: dspy.Module | None

    def __init__(self, metric: Callable, reflection_lm: dspy.LM, config: GEPAConfig | None = None):
        """
        Initialize GEPA optimizer.

        Args:
            metric: Evaluation metric (float or dspy.Prediction with score/feedback)
            reflection_lm: Strong language model for reflection
            config: GEPA configuration (uses defaults if not provided)
        """
        self.config = config or GEPAConfig()
        self.metric = metric
        self.reflection_lm = reflection_lm
        self._compiled_program = None

        # Initialize GEPA optimizer with configuration
        # Use only core parameters that are universally supported
        # SPEC-105 FR-010: la reflexion (prompt, guard de SPEC-104 FR-005 y extraccion)
        # es del repo; dspy solo recibe el proposer por su parametro publico. Tambien
        # es el callback `on_proposal_start` (la iteracion de GEPA como case_id, FR-013).
        self.reflection_proposer = dspy_reflection_proposer(reflection_lm)
        gepa_params = {
            "metric": metric,
            "reflection_lm": reflection_lm,
            "instruction_proposer": self.reflection_proposer,
            "gepa_kwargs": {"callbacks": [self.reflection_proposer]},
        }

        # Priority: Manual budget > Auto budget
        if self.config.max_metric_calls is not None:
            log_info(f"Using manual budget: {self.config.max_metric_calls} metric calls")
            gepa_params["max_metric_calls"] = self.config.max_metric_calls
        else:
            gepa_params["auto"] = self.config.auto_budget

        # Sin filtrar por firma ni fallback: si un upgrade de dspy cambia estos
        # parametros, `dspy.GEPA` falla con TypeError en CI en vez de degradar en
        # silencio (SPEC-105 FR-007; contrato en tests/test_lib_contracts.py).
        self.optimizer = dspy.GEPA(
            **gepa_params,
            track_stats=self.config.track_stats,
            reflection_minibatch_size=self.config.reflection_minibatch_size,
            skip_perfect_score=self.config.skip_perfect_score,
            candidate_selection_strategy=self.config.candidate_selection_strategy,
            use_merge=self.config.use_merge,
            max_merge_invocations=self.config.max_merge_invocations,
        )

    def compile(
        self,
        student: dspy.Module,
        trainset: list[dspy.Example],
        valset: list[dspy.Example] | None = None,
    ) -> dspy.Module:
        """
        Compile (optimize) a DSPy program using GEPA.

        Args:
            student: The DSPy module to optimize
            trainset: Training examples
            valset: Validation examples (optional)

        Returns:
            Optimized DSPy module
        """
        log_info(f"Starting GEPA optimization with budget: {self.config.auto_budget}")
        print_kv("Training set size", len(trainset))
        if valset:
            print_kv("Validation set size", len(valset))

        # Run GEPA optimization
        optimized_program = self.optimizer.compile(
            student=student, trainset=trainset, valset=valset
        )

        # dspy.GEPA.compile() setea `detailed_results` en el programa devuelto
        # (new_prog.detailed_results = ...), no en `self.optimizer`. Guardamos el
        # programa compilado para que get_detailed_results() lea del lugar correcto.
        self._compiled_program = optimized_program

        # Print statistics if available
        if self.config.track_stats and hasattr(optimized_program, "detailed_results"):
            print_section("GEPA Optimization Statistics")
            self._print_stats()

        return optimized_program

    def _print_stats(self):
        """Print optimization statistics."""
        if hasattr(self._compiled_program, "detailed_results"):
            results = self._compiled_program.detailed_results
            log_info(f"Detailed results available: {results}")
        else:
            log_info("No detailed statistics available.")

    def get_detailed_results(self):
        """
        Get GEPA's detailed results (DspyGEPAResult) tracked during optimization.

        Available when track_stats was enabled. dspy.GEPA.compile() sets
        `detailed_results` on the returned program, not on the optimizer instance.
        Exposes the explored candidates, their validation scores and search metadata
        so the entry point can render the GEPA evolution and search-stats blocks.
        Returns None if unavailable.
        """
        return getattr(self._compiled_program, "detailed_results", None)

    def get_best_outputs(self):
        """
        Get the best outputs tracked during optimization.

        Returns:
            Best outputs if track_best_outputs was enabled, None otherwise
        """
        return getattr(self._compiled_program, "best_outputs", None)


def optimize_with_gepa(
    module: dspy.Module,
    trainset: list[dspy.Example],
    valset: list[dspy.Example],
    metric: Callable,
    reflection_lm: dspy.LM,
    config: GEPAConfig | None = None,
) -> dspy.Module:
    """
    Convenience function to optimize a DSPy module with GEPA.

    Args:
        module: DSPy module to optimize
        trainset: Training examples
        valset: Validation examples
        metric: Evaluation metric
        reflection_lm: Reflection language model
        config: GEPA configuration

    Returns:
        Optimized module
    """
    optimizer = GEPAOptimizer(metric=metric, reflection_lm=reflection_lm, config=config)

    return optimizer.compile(student=module, trainset=trainset, valset=valset)

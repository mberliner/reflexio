"""
GEPA optimizer integration for DSPy programs.
"""

from collections.abc import Callable

import dspy

from shared.display import print_section

from .config import GEPAConfig


class GEPAOptimizer:
    """
    Wrapper class for GEPA optimizer with configuration management.
    """

    def __init__(self, metric: Callable, reflection_lm: dspy.LM, config: GEPAConfig | None = None):
        """
        Initialize GEPA optimizer.

        Args:
            metric: Evaluation metric function (can return score or dict with feedback)
            reflection_lm: Strong language model for reflection
            config: GEPA configuration (uses defaults if not provided)
        """
        self.config = config or GEPAConfig()
        self.metric = metric
        self.reflection_lm = reflection_lm

        # Initialize GEPA optimizer with configuration
        # Use only core parameters that are universally supported
        gepa_params = {
            "metric": metric,
            "reflection_lm": reflection_lm,
        }

        # Priority: Manual budget > Auto budget
        if self.config.max_metric_calls is not None:
            print(f"Using manual budget: {self.config.max_metric_calls} metric calls")
            gepa_params["max_metric_calls"] = self.config.max_metric_calls
        else:
            gepa_params["auto"] = self.config.auto_budget

        # Add optional parameters only if they exist in this version of GEPA
        try:
            self.optimizer = dspy.GEPA(
                **gepa_params,
                reflection_minibatch_size=self.config.reflection_minibatch_size,
                skip_perfect_score=self.config.skip_perfect_score,
                candidate_selection_strategy=self.config.candidate_selection_strategy,
                use_merge=self.config.use_merge,
                max_merge_invocations=self.config.max_merge_invocations,
                # New parameters for adapters
                max_text_length=self.config.max_text_length,
                max_positive_examples=self.config.max_positive_examples,
            )
        except TypeError:
            # Fallback to basic parameters if some are not supported
            print(
                "Note: Using basic GEPA configuration "
                "(some parameters not supported in this version)"
            )
            self.optimizer = dspy.GEPA(**gepa_params)

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
        print(f"Starting GEPA optimization with budget: {self.config.auto_budget}")
        print(f"Training set size: {len(trainset)}")
        if valset:
            print(f"Validation set size: {len(valset)}")

        # Run GEPA optimization
        optimized_program = self.optimizer.compile(
            student=student, trainset=trainset, valset=valset
        )

        # Print statistics if available
        if self.config.track_stats and hasattr(self.optimizer, "detailed_results"):
            print_section("GEPA Optimization Statistics")
            self._print_stats()

        return optimized_program

    def _print_stats(self):
        """Print optimization statistics."""
        if hasattr(self.optimizer, "detailed_results"):
            results = self.optimizer.detailed_results
            print(f"Detailed results available: {results}")
        else:
            print("No detailed statistics available.")

    def get_best_outputs(self):
        """
        Get the best outputs tracked during optimization.

        Returns:
            Best outputs if track_best_outputs was enabled, None otherwise
        """
        if hasattr(self.optimizer, "best_outputs"):
            return self.optimizer.best_outputs
        return None


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

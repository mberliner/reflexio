"""
Evaluation metrics for DSPy + GEPA optimization.
"""

import re
from collections.abc import Callable
from difflib import SequenceMatcher
from typing import Any

import dspy


def _compare_exact(expected: str, actual: str) -> bool:
    """Comparacion exacta tras strip/lower."""
    return expected == actual


def _normalize_text(text: str) -> str:
    """Elimina puntuacion y normaliza espacios."""
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _compare_normalized(expected: str, actual: str) -> bool:
    """Comparacion tras normalizar puntuacion y espacios."""
    return _normalize_text(expected) == _normalize_text(actual)


def _compare_fuzzy(expected: str, actual: str, threshold: float) -> bool:
    """Comparacion por similitud con umbral. Intenta normalized primero."""
    if _compare_normalized(expected, actual):
        return True
    ratio = SequenceMatcher(None, _normalize_text(expected), _normalize_text(actual)).ratio()
    return ratio >= threshold


def create_dynamic_metric(
    eval_fields: list[str],
    normalize: bool = True,
    match_mode: str = "exact",
    fuzzy_threshold: float = 0.85,
) -> Callable[[dspy.Example, dspy.Prediction, Any], bool | float]:
    """
    Factory para crear metricas dinamicas basadas en campos de evaluacion.

    Args:
        eval_fields: Lista de nombres de campos a evaluar
        normalize: Si True, retorna score normalizado cuando no hay match perfecto
        match_mode: Estrategia de comparacion: "exact", "normalized", "fuzzy"
        fuzzy_threshold: Umbral de similitud para modo fuzzy (0.0-1.0)

    Returns:
        Funcion metrica compatible con DSPy/GEPA
    """

    def dynamic_metric(example, pred, trace=None, pred_name=None, pred_trace=None):
        matches = 0
        total = len(eval_fields)

        for field in eval_fields:
            expected = str(getattr(example, field, "")).strip().lower()
            actual = str(getattr(pred, field, "")).strip().lower()

            if match_mode == "normalized":
                is_match = _compare_normalized(expected, actual)
            elif match_mode == "fuzzy":
                is_match = _compare_fuzzy(expected, actual, fuzzy_threshold)
            else:
                is_match = _compare_exact(expected, actual)

            if is_match:
                matches += 1

        if matches == total:
            return True
        return matches / total if (normalize and total > 0) else False

    return dynamic_metric


def sentiment_accuracy_metric(gold: dspy.Example, pred: dspy.Prediction, trace=None) -> float:
    """
    Simple accuracy metric for sentiment classification.

    Args:
        gold: Ground truth example
        pred: Model prediction
        trace: Execution trace (optional)

    Returns:
        Score between 0.0 and 1.0
    """
    return float(gold.sentiment.lower() == pred.sentiment.lower())


def sentiment_with_feedback_metric(
    gold: dspy.Example, pred: dspy.Prediction, trace=None, pred_name: str = None, pred_trace=None
) -> float | dict[str, float | str]:
    """
    Sentiment metric with textual feedback for GEPA optimization.

    This metric returns both a score and textual feedback to guide
    the GEPA optimizer in improving prompts.

    Args:
        gold: Ground truth example
        pred: Model prediction
        trace: Execution trace
        pred_name: Name of the predictor
        pred_trace: Predictor-specific trace

    Returns:
        Float for normal evaluation, Dictionary with 'score' and 'feedback' for GEPA
    """
    correct = gold.sentiment.lower() == pred.sentiment.lower()
    score = 1.0 if correct else 0.0

    # If GEPA is requesting feedback (pred_name is set), return dict
    if pred_name is not None or pred_trace is not None:
        if correct:
            feedback = f"Correct classification as '{pred.sentiment}'. Good reasoning provided."
        else:
            feedback = (
                f"Incorrect classification. Expected '{gold.sentiment}' "
                f"but got '{pred.sentiment}'. The text was: '{gold.text}'. "
                f"Consider analyzing the emotional tone and word choice more carefully."
            )
        return {"score": score, "feedback": feedback}

    # Otherwise, return just the score for normal evaluation
    return score


def extraction_accuracy_metric(gold: dspy.Example, pred: dspy.Prediction, trace=None) -> float:
    """
    Metric for information extraction accuracy.
    Checks how many fields were correctly extracted.

    Args:
        gold: Ground truth example
        pred: Model prediction
        trace: Execution trace

    Returns:
        Score between 0.0 and 1.0 (proportion of correct fields)
    """
    if not hasattr(gold, "extracted_info"):
        return 0.0

    expected = gold.extracted_info
    total_fields = len(expected)
    correct_fields = 0

    for field_name, expected_value in expected.items():
        if hasattr(pred, field_name):
            pred_value = getattr(pred, field_name)
            # Normalize for comparison
            if str(pred_value).strip().lower() == str(expected_value).strip().lower():
                correct_fields += 1

    return correct_fields / total_fields if total_fields > 0 else 0.0


def extraction_with_feedback_metric(
    gold: dspy.Example, pred: dspy.Prediction, trace=None, pred_name: str = None, pred_trace=None
) -> float | dict[str, float | str]:
    """
    Information extraction metric with textual feedback for GEPA.

    Args:
        gold: Ground truth example
        pred: Model prediction
        trace: Execution trace
        pred_name: Name of the predictor
        pred_trace: Predictor-specific trace

    Returns:
        Float for normal evaluation, Dictionary with 'score' and 'feedback' for GEPA
    """
    if not hasattr(gold, "extracted_info"):
        if pred_name is not None or pred_trace is not None:
            return {"score": 0.0, "feedback": "No ground truth information available."}
        return 0.0

    expected = gold.extracted_info
    total_fields = len(expected)
    correct_fields = 0
    errors = []

    for field_name, expected_value in expected.items():
        if hasattr(pred, field_name):
            pred_value = getattr(pred, field_name)
            # Normalize for comparison
            if str(pred_value).strip().lower() == str(expected_value).strip().lower():
                correct_fields += 1
            else:
                errors.append(f"{field_name}: expected '{expected_value}', got '{pred_value}'")
        else:
            errors.append(f"{field_name}: field not extracted")

    score = correct_fields / total_fields if total_fields > 0 else 0.0

    # If GEPA is requesting feedback, return dict
    if pred_name is not None or pred_trace is not None:
        if score == 1.0:
            feedback = "Perfect extraction! All fields correctly identified."
        else:
            feedback = (
                f"Extracted {correct_fields}/{total_fields} fields correctly. "
                f"Errors: {'; '.join(errors)}. "
                f"Focus on parsing dates, names, and numeric values more accurately."
            )
        return {"score": score, "feedback": feedback}

    # Otherwise, return just the score
    return score


def combined_metric(gold: dspy.Example, pred: dspy.Prediction, trace=None) -> float:
    """
    Combined metric that checks both correctness and reasoning quality.

    Args:
        gold: Ground truth example
        pred: Model prediction
        trace: Execution trace

    Returns:
        Score between 0.0 and 1.0
    """
    # Check if prediction is correct
    if hasattr(gold, "sentiment"):
        correctness = sentiment_accuracy_metric(gold, pred, trace)
    else:
        correctness = extraction_accuracy_metric(gold, pred, trace)

    # Check if reasoning is provided and non-empty
    has_reasoning = (
        hasattr(pred, "reasoning") and pred.reasoning and len(pred.reasoning.strip()) > 10
    )
    reasoning_score = 1.0 if has_reasoning else 0.5

    # Combine scores (70% correctness, 30% reasoning quality)
    return 0.7 * correctness + 0.3 * reasoning_score

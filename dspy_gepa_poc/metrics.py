"""
Evaluation metrics for DSPy + GEPA optimization.
"""

import re
import unicodedata
from collections.abc import Callable
from difflib import SequenceMatcher
from typing import Any

import dspy


def _compare_exact(expected: str, actual: str) -> bool:
    """Comparacion exacta tras strip/lower."""
    return expected == actual


def _strip_accents(text: str) -> str:
    """Elimina diacriticos (tildes) preservando caracteres base."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _normalize_text(text: str) -> str:
    """Elimina puntuacion, tildes y normaliza espacios + case."""
    text = _strip_accents(text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
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


def _tokenize_list(text: str, separators: str = ",;") -> set[str]:
    """
    Tokeniza una cadena tipo lista en un set normalizado.

    Acepta varios separadores (default coma o punto y coma) y normaliza cada
    elemento (lower, sin tildes, sin puntuacion interna). Items vacios se
    descartan. Para items con sufijo ':valor' (p.ej. 'Python:5', 'ingles:b2')
    se conserva solo la clave para tolerar diferencias en el valor.
    """
    if not text:
        return set()
    pattern = f"[{re.escape(separators)}]"
    tokens = re.split(pattern, text)
    out: set[str] = set()
    for tok in tokens:
        norm = _normalize_text(tok)
        if not norm:
            continue
        # Conservar solo la 'clave' antes del primer ':' para Python:5 -> python
        key = norm.split(" ")[0] if ":" not in tok else _normalize_text(tok.split(":", 1)[0])
        out.add(key or norm)
    return out


def _score_set(
    expected: str, actual: str, separators: str = ",;"
) -> tuple[float, set[str], set[str]]:
    """
    Score de Jaccard-like: |intersect| / |expected|. Retorna (score, missing, extra).
    Si expected esta vacio, se considera match perfecto solo si actual tambien lo esta.
    """
    exp = _tokenize_list(expected, separators)
    act = _tokenize_list(actual, separators)
    if not exp:
        return (1.0 if not act else 0.0, set(), act)
    inter = exp & act
    missing = exp - act
    extra = act - exp
    return (len(inter) / len(exp), missing, extra)


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


# Modos de comparacion soportados por field_configs
_VALID_FIELD_MODES = {"exact", "normalized", "fuzzy", "set"}


def _score_field(
    expected_raw: str,
    actual_raw: str,
    mode: str,
    fuzzy_threshold: float,
    separators: str,
) -> tuple[float, str]:
    """
    Calcula score [0,1] y mensaje de diagnostico para un campo.

    Returns:
        (score, diag): diag es '' si match perfecto.
    """
    expected = str(expected_raw or "").strip().lower()
    actual = str(actual_raw or "").strip().lower()

    if mode == "set":
        score, missing, extra = _score_set(expected, actual, separators)
        if score == 1.0 and not extra:
            return 1.0, ""
        parts = []
        if missing:
            parts.append(f"faltan: {sorted(missing)}")
        if extra:
            parts.append(f"sobran: {sorted(extra)}")
        return score, f"esperado '{expected_raw}' vs obtenido '{actual_raw}' ({'; '.join(parts)})"

    if mode == "normalized":
        ok = _compare_normalized(expected, actual)
    elif mode == "fuzzy":
        ok = _compare_fuzzy(expected, actual, fuzzy_threshold)
    else:  # exact
        ok = _compare_exact(expected, actual)

    if ok:
        return 1.0, ""
    return 0.0, f"esperado '{expected_raw}' vs obtenido '{actual_raw}'"


def create_dynamic_metric_with_feedback(
    eval_fields: list[str],
    field_configs: dict[str, dict[str, Any]] | None = None,
    default_mode: str = "normalized",
    fuzzy_threshold: float = 0.85,
    list_separators: str = ",;",
) -> Callable[..., float | dict[str, float | str]]:
    """
    Factory para metrica dinamica con scoring por campo y feedback textual.

    A diferencia de `create_dynamic_metric`, esta version:
      - Soporta un comparador distinto por campo via `field_configs[name]['mode']`
        (modos: exact, normalized, fuzzy, set).
      - Acepta scoring parcial en listas (mode='set' con Jaccard sobre la
        cobertura del esperado).
      - Cuando GEPA solicita feedback (`pred_name is not None`), devuelve
        `{'score', 'feedback'}` con diagnostico campo-por-campo.

    Args:
        eval_fields: Lista ordenada de campos a evaluar.
        field_configs: Mapa opcional `{nombre: {mode, fuzzy_threshold?, separators?}}`.
        default_mode: Modo aplicado a campos sin override en `field_configs`.
        fuzzy_threshold: Umbral por defecto para modo fuzzy.
        list_separators: Separadores por defecto para modo set.

    Returns:
        Funcion metrica compatible con DSPy/GEPA.
    """
    if default_mode not in _VALID_FIELD_MODES:
        raise ValueError(
            f"default_mode invalido: '{default_mode}'. Validos: {sorted(_VALID_FIELD_MODES)}"
        )
    field_configs = field_configs or {}
    for fname, cfg in field_configs.items():
        mode = cfg.get("mode", default_mode)
        if mode not in _VALID_FIELD_MODES:
            raise ValueError(
                f"Modo invalido para campo '{fname}': '{mode}'. "
                f"Validos: {sorted(_VALID_FIELD_MODES)}"
            )

    def dynamic_metric_fb(example, pred, trace=None, pred_name=None, pred_trace=None):
        total = len(eval_fields)
        if total == 0:
            return 0.0

        total_score = 0.0
        diagnostics: list[str] = []

        for field in eval_fields:
            cfg = field_configs.get(field, {})
            mode = cfg.get("mode", default_mode)
            threshold = cfg.get("fuzzy_threshold", fuzzy_threshold)
            seps = cfg.get("separators", list_separators)

            expected_raw = getattr(example, field, "")
            actual_raw = getattr(pred, field, "")
            score, diag = _score_field(expected_raw, actual_raw, mode, threshold, seps)
            total_score += score
            if diag:
                diagnostics.append(f"  - {field} [{mode}]: {diag}")

        avg = total_score / total

        if pred_name is not None or pred_trace is not None:
            if avg == 1.0:
                feedback = f"Extraccion perfecta: {total}/{total} campos correctos."
            else:
                correct = sum(1 for _ in range(0))  # placeholder for clarity
                correct = total - len(diagnostics)
                header = f"Score {avg:.2f} ({correct}/{total} campos perfectos). Errores por campo:"
                feedback = header + "\n" + "\n".join(diagnostics)
            return {"score": avg, "feedback": feedback}

        return avg

    return dynamic_metric_fb


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

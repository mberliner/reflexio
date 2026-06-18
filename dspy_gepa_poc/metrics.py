"""
Evaluation metrics for DSPy + GEPA optimization.

Los primitivos de comparacion (exact/normalized/fuzzy/set) viven en
`shared.scoring.field_match` para que DSPy y el extractor de GEPA compartan la
misma logica. Aqui se re-exportan con los nombres historicos (prefijo '_') que
usan tests y scripts; las factories de metricas DSPy siguen viviendo en este
modulo porque dependen de tipos `dspy`.
"""

from collections.abc import Callable
from typing import Any

import dspy

from shared.scoring.field_match import VALID_FIELD_MODES as _VALID_FIELD_MODES
from shared.scoring.field_match import compare_exact as _compare_exact
from shared.scoring.field_match import compare_fuzzy as _compare_fuzzy
from shared.scoring.field_match import compare_normalized as _compare_normalized
from shared.scoring.field_match import normalize_text as _normalize_text
from shared.scoring.field_match import score_field as _score_field
from shared.scoring.field_match import score_set as _score_set
from shared.scoring.field_match import strip_accents as _strip_accents
from shared.scoring.field_match import tokenize_list as _tokenize_list

__all__ = [
    "_VALID_FIELD_MODES",
    "_compare_exact",
    "_compare_fuzzy",
    "_compare_normalized",
    "_normalize_text",
    "_score_field",
    "_score_set",
    "_strip_accents",
    "_tokenize_list",
    "create_dynamic_metric",
    "create_dynamic_metric_with_feedback",
    "create_rule_derived_metric_with_feedback",
    "create_pipeline_metric_with_feedback",
    "sentiment_accuracy_metric",
    "sentiment_with_feedback_metric",
    "extraction_accuracy_metric",
    "extraction_with_feedback_metric",
    "combined_metric",
]


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


def create_rule_derived_metric_with_feedback(
    eval_fields: list[str],
    is_true_fn: Callable[[object], bool],
    question_fields: tuple[str, ...] = ("p1", "p2", "p3", "p4", "p5"),
    alto_impacto_field: str = "alto_impacto",
    derived_field: str = "clasificacion",
    field_configs: dict[str, dict[str, Any]] | None = None,
    default_mode: str = "normalized",
    fuzzy_threshold: float = 0.85,
    list_separators: str = ",;",
) -> Callable[..., float | dict[str, float | str]]:
    """Factory de metrica para modulos `rule_derived` con feedback consciente de la regla.

    El score es identico al de `create_dynamic_metric_with_feedback` (promedio sobre
    `eval_fields`), para que la comparacion contra el punto estable previo se mantenga.
    Lo que cambia es el FEEDBACK: cuando el campo derivado (`clasificacion`) sale mal,
    el reflection_lm recibia "esperado Rojo, obtenido Negro" sobre un campo que el
    predictor NO emite (es calculado) y por tanto no puede corregir. Esta version
    traduce el error de color al juicio responsable: muestra los bits gold vs pred,
    como la regla derivo cada color (conteo de Si u override Negro) y que juicios
    revisar. Asi el reflection_lm trabaja sobre la palanca real (p1..p5/alto_impacto).

    El color a mostrar (gold y pred) se lee de `derived_field`: el gold viene del CSV
    y el pred ya lo calculo el modulo con la regla, por eso no hace falta re-derivar.

    Args:
        eval_fields: campos a puntuar (tipicamente [alto_impacto, clasificacion]).
        is_true_fn: interpreta el booleano del juicio ('si'/'No'/bool); se inyecta
            para no acoplar este modulo con `flujo_intents` (`ficha._is_true`).
        question_fields: nombres de las 5 preguntas que alimentan el conteo.
        alto_impacto_field: nombre del juicio de alto impacto (cuello + override Negro).
        derived_field: nombre del campo de color derivado.
        field_configs: overrides por campo (mode, fuzzy_threshold, separators).
        default_mode: modo de comparacion default.
        fuzzy_threshold: threshold default para modo fuzzy.
        list_separators: separadores para modo set.

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

    def _bits(source: Any) -> list[bool]:
        return [is_true_fn(getattr(source, f, "")) for f in question_fields]

    def _fmt_bits(source: Any) -> str:
        labels = [
            f"{f}={'Si' if b else 'No'}"
            for f, b in zip(question_fields, _bits(source), strict=True)
        ]
        alto = "Si" if is_true_fn(getattr(source, alto_impacto_field, "")) else "No"
        return " ".join(labels) + f" | {alto_impacto_field}={alto}"

    def _explain(source: Any) -> str:
        bits = _bits(source)
        alto = is_true_fn(getattr(source, alto_impacto_field, ""))
        # P5 es el ultimo de question_fields por convencion del Marco.
        if bits and bits[-1] and alto:
            return f"override Negro ({question_fields[-1]}=Si Y {alto_impacto_field}=Si)"
        return f"conteo Si={sum(bits)}"

    def rule_derived_metric_fb(example, pred, trace=None, pred_name=None, pred_trace=None):
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
            score, diag = _score_field(
                getattr(example, field, ""), getattr(pred, field, ""), mode, threshold, seps
            )
            total_score += score
            if diag:
                diagnostics.append(f"  - {field} [{mode}]: {diag}")

        avg = total_score / total

        if pred_name is not None or pred_trace is not None:
            if avg == 1.0:
                feedback = f"Clasificacion perfecta: {total}/{total} campos correctos."
            else:
                correct = total - len(diagnostics)
                lines = [
                    f"Score {avg:.2f} ({correct}/{total} campos perfectos). Errores por campo:",
                    *diagnostics,
                ]
                gold_color = str(getattr(example, derived_field, "")).strip()
                pred_color = str(getattr(pred, derived_field, "")).strip()
                if gold_color and gold_color.lower() != pred_color.lower():
                    diff = [
                        f
                        for f in (*question_fields, alto_impacto_field)
                        if is_true_fn(getattr(example, f, "")) != is_true_fn(getattr(pred, f, ""))
                    ]
                    lines.append(
                        f"El color '{derived_field}' es DERIVADO por regla (no lo edites; "
                        "se calcula contando los Si de p1..p5: 0-1 Verde, 2-3 Amarillo, "
                        f"4-5 Rojo; Negro si {question_fields[-1]}=Si Y "
                        f"{alto_impacto_field}=Si). Asi salio cada color:"
                    )
                    lines.append(
                        f"  - Gold: {_fmt_bits(example)} -> {_explain(example)} -> {gold_color}"
                    )
                    lines.append(f"  - Pred: {_fmt_bits(pred)} -> {_explain(pred)} -> {pred_color}")
                    if diff:
                        lines.append(
                            f"  - Para que el color de '{gold_color}' y no '{pred_color}', "
                            f"corregi estos juicios: {', '.join(diff)}."
                        )
                feedback = "\n".join(lines)
            return {"score": avg, "feedback": feedback}

        return avg

    return rule_derived_metric_fb


def create_pipeline_metric_with_feedback(
    gate_field: str,
    gate_value: str,
    triage_fields: list[str],
    fastgate_fields: list[str],
    field_configs: dict[str, dict[str, Any]] | None = None,
    default_mode: str = "normalized",
    fuzzy_threshold: float = 0.85,
    list_separators: str = ",;",
    triage_weight: float = 0.3,
) -> Callable[..., float | dict[str, float | str]]:
    """
    Metrica condicional jerarquica para pipelines triage+clasificacion.

    Logica:
      - Siempre evalua triage_fields (decision + etapa).
      - Si example.<gate_field> == gate_value (caso que avanza), evalua
        tambien fastgate_fields y combina con peso triage_weight para triage
        y (1-triage_weight) para fast_gate.
      - Si example.<gate_field> != gate_value (rechazo/devolucion), solo
        cuenta triage; fastgate_fields se omiten (el modulo ya inyecta
        valores fijos como 'no_aplica').

    Devuelve dict {score, feedback} cuando GEPA lo pide (pred_name not None),
    diferenciando los errores por etapa.

    Args:
        gate_field: nombre del campo que dispara la condicion (ej 'triage_decision').
        gate_value: valor esperado para invocar la segunda etapa (ej 'avanza_fast_gate').
        triage_fields: campos a evaluar siempre.
        fastgate_fields: campos a evaluar solo cuando aplica.
        field_configs: overrides por campo (mode, fuzzy_threshold, separators).
        default_mode: modo de comparacion default (exact/normalized/fuzzy/set).
        fuzzy_threshold: threshold default para modo fuzzy.
        list_separators: separadores para modo set.
        triage_weight: peso de la etapa triage cuando aplican ambas.
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

    def _evaluate_group(example: Any, pred: Any, fields: list[str]) -> tuple[float, int, list[str]]:
        """Devuelve (score_promedio, perfectos, diagnosticos)."""
        if not fields:
            return 1.0, 0, []
        total_score = 0.0
        perfect = 0
        diagnostics: list[str] = []
        for field in fields:
            cfg = field_configs.get(field, {})
            mode = cfg.get("mode", default_mode)
            threshold = cfg.get("fuzzy_threshold", fuzzy_threshold)
            seps = cfg.get("separators", list_separators)
            expected_raw = getattr(example, field, "")
            actual_raw = getattr(pred, field, "")
            score, diag = _score_field(expected_raw, actual_raw, mode, threshold, seps)
            total_score += score
            if score == 1.0:
                perfect += 1
            if diag:
                diagnostics.append(f"  - {field} [{mode}]: {diag}")
        return total_score / len(fields), perfect, diagnostics

    def pipeline_metric_fb(example, pred, trace=None, pred_name=None, pred_trace=None):
        triage_avg, triage_ok, triage_diag = _evaluate_group(example, pred, triage_fields)

        expected_gate = str(getattr(example, gate_field, "")).strip()
        is_avanza = expected_gate == gate_value

        if is_avanza and fastgate_fields:
            fg_avg, fg_ok, fg_diag = _evaluate_group(example, pred, fastgate_fields)
            avg = triage_weight * triage_avg + (1.0 - triage_weight) * fg_avg
        else:
            fg_avg, fg_ok, fg_diag = 1.0, 0, []
            avg = triage_avg

        if pred_name is not None or pred_trace is not None:
            parts: list[str] = []
            t_total = len(triage_fields)
            parts.append(
                f"Triage: {triage_ok}/{t_total} campos perfectos (score {triage_avg:.2f})."
            )
            if triage_diag:
                parts.append("Errores triage:")
                parts.extend(triage_diag)
            if is_avanza and fastgate_fields:
                fg_total = len(fastgate_fields)
                parts.append(
                    f"Fast Gate: {fg_ok}/{fg_total} campos perfectos (score {fg_avg:.2f})."
                )
                if fg_diag:
                    parts.append("Errores fast_gate:")
                    parts.extend(fg_diag)
            elif not is_avanza:
                parts.append(f"Fast Gate: omitido (caso de triage='{expected_gate}', no avanza).")
            header = f"Score total {avg:.2f}."
            feedback = header + "\n" + "\n".join(parts)
            return {"score": avg, "feedback": feedback}

        return avg

    return pipeline_metric_fb


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

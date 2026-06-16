"""Tests de build_candidates_payload / _coerce_candidate (sin LLM).

Verifican que se persisten TODOS los candidatos GEPA (incluidos los que la metrica
no adopto) con la marca `is_improvement`/`is_best` que permite distinguirlos.
"""

from dspy_gepa_poc.reflexio_declarativa import _coerce_candidate, build_candidates_payload


def test_coerce_candidate_dict():
    out = _coerce_candidate({"predict": "instr A", "other": 3})
    assert out == {"predict": "instr A", "other": "3"}


def test_coerce_candidate_non_dict():
    out = _coerce_candidate(["x", "y"])
    assert out == {"_repr": "['x', 'y']"}


def test_payload_marks_improvements_and_best():
    candidates = [{"p": "seed"}, {"p": "peor"}, {"p": "mejor"}]
    val_scores = [0.5, 0.4, 0.9]  # idx 1 NO mejora (rechazado por la metrica)
    payload = build_candidates_payload(candidates, val_scores, best_idx=2, total_metric_calls=42)

    assert payload["num_candidates"] == 3
    assert payload["best_idx"] == 2
    assert payload["total_metric_calls"] == 42

    by_idx = {c["idx"]: c for c in payload["candidates"]}
    # semilla siempre cuenta como improvement
    assert by_idx[0]["is_improvement"] is True
    # idx 1 no supero el running max -> NO tomado por la metrica
    assert by_idx[1]["is_improvement"] is False
    assert by_idx[1]["is_best"] is False
    # idx 2 mejora y es el mejor final
    assert by_idx[2]["is_improvement"] is True
    assert by_idx[2]["is_best"] is True
    assert by_idx[2]["instructions"] == {"p": "mejor"}


def test_payload_includes_metric_calls_when_available():
    payload = build_candidates_payload(
        [{"p": "a"}, {"p": "b"}],
        [0.1, 0.2],
        discovery_eval_counts=[5, 11],
    )
    assert payload["candidates"][0]["metric_calls"] == 5
    assert payload["candidates"][1]["metric_calls"] == 11


def test_payload_handles_mismatched_lengths():
    # val_scores mas corto: se trunca al minimo, sin romper
    payload = build_candidates_payload([{"p": "a"}, {"p": "b"}], [0.7])
    assert payload["num_candidates"] == 1
    assert "metric_calls" not in payload["candidates"][0]

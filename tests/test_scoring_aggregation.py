"""Tests de la agregacion sobre casos evaluados y del delta pareado (SPEC-104 4a).

Verifican FR-003, SC-002 y SC-007 y los escenarios Given/When/Then de la spec,
sin llamar al modelo. La entrada es la forma de D6: por repeticion, una lista de
`(case_id, score, evaluated)`.
"""

import json

import pytest

from shared.scoring import aggregation as agg


def _repeat(scores, ne=()):
    """Una repeticion: score por case_id; los de `ne` quedan no evaluados (score 0.0)."""
    return [(cid, 0.0 if cid in ne else s, cid not in ne) for cid, s in scores.items()]


def _cases(n, value=1.0):
    return {f"val:{i}": value for i in range(n)}


class TestSummarize:
    def test_metric_only_over_evaluated_cases(self):
        # Escenario: 30 casos, 3 NE -> metrica sobre 27, reporte 27/30.
        cases = _cases(30)
        ne = {"val:0", "val:1", "val:2"}
        summary = agg.summarize([_repeat(cases, ne)])
        assert summary.score == pytest.approx(1.0)
        assert (summary.n_evaluados, summary.n_total) == (27, 30)
        assert summary.ratio_label() == "27/30"

    def test_sc002_ne_cases_do_not_change_metric(self):
        # SC-002: mismo prompt y respuestas fijas; 10% NE no altera la metrica
        # sobre los mismos casos evaluados.
        scores = {f"val:{i}": (1.0 if i % 2 == 0 else 0.0) for i in range(30)}
        ne = {"val:1", "val:2", "val:3"}
        clean = agg.summarize([_repeat(scores)])
        with_ne = agg.summarize([_repeat(scores, ne)])
        evaluated = [s for c, s in scores.items() if c not in ne]
        assert with_ne.score == pytest.approx(sum(evaluated) / len(evaluated))
        same_cases = agg.summarize([_repeat({c: s for c, s in scores.items() if c not in ne})])
        assert with_ne.score == pytest.approx(same_cases.score)
        assert clean.n_evaluados == 30
        assert with_ne.ratio_label() == "27/30"

    def test_ne_is_not_counted_as_zero(self):
        # Un NE con score tecnico 0.0 no baja el promedio.
        summary = agg.summarize([[("a", 1.0, True), ("b", 0.0, False)]])
        assert summary.score == pytest.approx(1.0)

    def test_evaluated_zero_score_counts(self):
        # Un score 0 de un caso evaluado (p. ej. entrada_candidato) si cuenta.
        summary = agg.summarize([[("a", 1.0, True), ("b", 0.0, True)]])
        assert summary.score == pytest.approx(0.5)
        assert summary.n_evaluados == 2

    def test_all_ne_is_sin_casos_evaluados_not_zero(self):
        summary = agg.summarize([[("a", 0.0, False), ("b", 0.0, False)]])
        assert summary.score is None
        assert summary.sin_casos_evaluados is True
        assert (summary.n_evaluados, summary.n_total) == (0, 2)
        assert summary.format_score() == "sin casos evaluados"

    def test_empty_batch_does_not_divide_by_zero(self):
        summary = agg.summarize([[]])
        assert summary.score is None
        assert summary.sin_casos_evaluados is True
        assert (summary.n_evaluados, summary.n_total) == (0, 0)

    def test_no_repeats_does_not_divide_by_zero(self):
        summary = agg.summarize([])
        assert summary.score is None
        assert summary.sin_casos_evaluados is True

    def test_format_score_uses_percent(self):
        summary = agg.summarize([[("a", 1.0, True), ("b", 0.0, True)]])
        assert summary.format_score() == "50.00%"

    def test_duplicate_case_id_in_one_repeat_is_error(self):
        with pytest.raises(ValueError, match="case_id"):
            agg.summarize([[("a", 1.0, True), ("a", 0.0, True)]])

    def test_missing_case_id_is_error(self):
        with pytest.raises(ValueError, match="case_id"):
            agg.summarize([[(None, 1.0, True)]])

    def test_rejects_malformed_entry(self):
        with pytest.raises(ValueError):
            agg.summarize([[("a", 1.0)]])


class TestEvalRepeats:
    def test_case_score_is_mean_of_evaluated_repeats(self):
        r1 = [("a", 1.0, True), ("b", 0.0, True)]
        r2 = [("a", 0.0, True), ("b", 0.0, True)]
        summary = agg.summarize([r1, r2])
        assert summary.per_case == {"a": 0.5, "b": 0.0}
        assert summary.score == pytest.approx(0.25)

    def test_ne_repeat_is_excluded_from_case_mean(self):
        # FR-003: promedio de las repeticiones evaluadas; la NE no cuenta como 0.
        r1 = [("a", 1.0, True)]
        r2 = [("a", 0.0, False)]
        summary = agg.summarize([r1, r2])
        assert summary.per_case == {"a": 1.0}
        assert summary.score == pytest.approx(1.0)

    def test_case_evaluated_in_at_least_one_repeat_counts(self):
        r1 = [("a", 0.0, False), ("b", 1.0, True)]
        r2 = [("a", 1.0, True), ("b", 1.0, True)]
        summary = agg.summarize([r1, r2])
        assert (summary.n_evaluados, summary.n_total) == (2, 2)

    def test_case_ne_in_all_repeats_is_not_evaluated(self):
        r1 = [("a", 0.0, False), ("b", 1.0, True)]
        r2 = [("a", 0.0, False), ("b", 1.0, True)]
        summary = agg.summarize([r1, r2])
        assert (summary.n_evaluados, summary.n_total) == (1, 2)
        assert "a" not in summary.per_case

    def test_ne_repeats_reported_separately(self):
        # Repeticiones NE = pares (caso, repeticion) no evaluados.
        r1 = [("a", 0.0, False), ("b", 1.0, True)]
        r2 = [("a", 1.0, True), ("b", 0.0, False)]
        r3 = [("a", 1.0, True), ("b", 1.0, True)]
        summary = agg.summarize([r1, r2, r3])
        assert summary.ne_repeats == 2
        assert summary.repeats == 3

    def test_no_ne_repeats_when_all_evaluated(self):
        summary = agg.summarize([_repeat(_cases(3))])
        assert summary.ne_repeats == 0
        assert summary.repeats == 1

    def test_all_repeats_ne_is_sin_casos(self):
        summary = agg.summarize([[("a", 0.0, False)], [("a", 0.0, False)]])
        assert summary.sin_casos_evaluados is True
        assert summary.ne_repeats == 2


class TestPairedDelta:
    def test_scenario_28_29_intersection_27(self):
        # Given baseline 28/30, optimizado 29/30 e interseccion de 27, When se
        # reporta, Then el delta se calcula sobre los 27 y se muestran ambos
        # scores con su n_evaluados / n_total.
        ids = [f"val:{i}" for i in range(30)]
        base_ne = {"val:0", "val:1"}
        opt_ne = {"val:2"}
        # Interseccion = 30 - |{0,1} U {2}| = 27.
        base = {c: (1.0 if c in ("val:5", "val:6") else 0.0) for c in ids}
        opt = {c: (1.0 if c in ("val:5", "val:7") else 0.0) for c in ids}
        b = agg.summarize([_repeat(base, base_ne)])
        o = agg.summarize([_repeat(opt, opt_ne)])
        delta = agg.paired_delta(b, o)
        assert (b.n_evaluados, b.n_total) == (28, 30)
        assert (o.n_evaluados, o.n_total) == (29, 30)
        assert delta.n_pareados == 27
        # Sobre los 27 pareados: baseline acierta 5 y 6, optimizado 5 y 7.
        assert delta.baseline_score == pytest.approx(2 / 27)
        assert delta.optimized_score == pytest.approx(2 / 27)
        assert delta.delta == pytest.approx(0.0)

    def test_sc007_delta_differs_from_difference_of_means(self):
        # SC-007: conjuntos distintos y fallas no simetricas.
        base = [("a", 1.0, True), ("b", 1.0, True), ("c", 0.0, False)]
        opt = [("a", 1.0, True), ("b", 0.0, False), ("c", 0.0, True)]
        b = agg.summarize([base])
        o = agg.summarize([opt])
        naive = o.score - b.score  # (1+0)/2 - 1.0 = -0.5
        delta = agg.paired_delta(b, o)
        assert delta.n_pareados == 1
        assert delta.delta == pytest.approx(0.0)
        assert delta.delta != pytest.approx(naive)

    def test_delta_is_optimized_minus_baseline(self):
        b = agg.summarize([[("a", 0.2, True), ("b", 0.4, True)]])
        o = agg.summarize([[("a", 0.6, True), ("b", 0.4, True)]])
        delta = agg.paired_delta(b, o)
        assert delta.baseline_score == pytest.approx(0.3)
        assert delta.optimized_score == pytest.approx(0.5)
        assert delta.delta == pytest.approx(0.2)

    def test_scores_reported_on_own_cases_alongside_delta(self):
        b = agg.summarize([[("a", 1.0, True), ("b", 0.0, True), ("c", 0.0, True)]])
        o = agg.summarize([[("a", 1.0, True), ("b", 1.0, True)]])
        delta = agg.paired_delta(b, o)
        assert b.score == pytest.approx(1 / 3)
        assert o.score == pytest.approx(1.0)
        assert delta.n_pareados == 2
        assert delta.delta == pytest.approx(0.5)

    def test_empty_intersection_is_sin_casos_not_zero(self):
        b = agg.summarize([[("a", 1.0, True), ("b", 0.0, False)]])
        o = agg.summarize([[("a", 0.0, False), ("b", 1.0, True)]])
        delta = agg.paired_delta(b, o)
        assert delta.n_pareados == 0
        assert delta.delta is None
        assert delta.baseline_score is None
        assert delta.optimized_score is None
        assert delta.sin_casos_evaluados is True
        assert delta.format_delta() == "sin casos evaluados"

    def test_n_evaluados_zero_on_one_side_is_sin_casos(self):
        b = agg.summarize([[("a", 0.0, False)]])
        o = agg.summarize([[("a", 1.0, True)]])
        delta = agg.paired_delta(b, o)
        assert delta.delta is None
        assert delta.sin_casos_evaluados is True

    def test_identical_sets_equal_difference_of_means(self):
        b = agg.summarize([[("a", 0.0, True), ("b", 1.0, True)]])
        o = agg.summarize([[("a", 1.0, True), ("b", 1.0, True)]])
        delta = agg.paired_delta(b, o)
        assert delta.delta == pytest.approx(o.score - b.score)

    def test_pairing_uses_repeat_means(self):
        b = agg.summarize([[("a", 0.0, True)], [("a", 1.0, True)]])
        o = agg.summarize([[("a", 1.0, True)], [("a", 1.0, True)]])
        delta = agg.paired_delta(b, o)
        assert delta.baseline_score == pytest.approx(0.5)
        assert delta.delta == pytest.approx(0.5)

    def test_format_delta_signed_percent(self):
        b = agg.summarize([[("a", 0.2, True)]])
        o = agg.summarize([[("a", 0.7, True)]])
        assert agg.paired_delta(b, o).format_delta() == "+50.00%"
        assert agg.paired_delta(o, b).format_delta() == "-50.00%"


class TestSerialization:
    def test_summary_to_dict_is_json_serializable(self):
        summary = agg.summarize([[("a", 1.0, True), ("b", 0.0, False)]])
        data = summary.to_dict()
        json.dumps(data)
        assert data["n_evaluados"] == 1
        assert data["n_total"] == 2
        assert data["score"] == pytest.approx(1.0)
        assert data["sin_casos_evaluados"] is False

    def test_sin_casos_serializes_score_as_none(self):
        data = agg.summarize([[("a", 0.0, False)]]).to_dict()
        assert data["score"] is None
        assert data["sin_casos_evaluados"] is True

    def test_delta_to_dict(self):
        b = agg.summarize([[("a", 0.2, True)]])
        o = agg.summarize([[("a", 0.7, True)]])
        data = agg.paired_delta(b, o).to_dict()
        json.dumps(data)
        assert data["n_pareados"] == 1
        assert data["delta"] == pytest.approx(0.5)

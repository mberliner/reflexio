"""Tests del modulo compartido shared.scoring.field_match.

Fija el contrato publico del scoring por campo (exact/normalized/fuzzy/set) y
verifica que los alias historicos de dspy_gepa_poc.metrics re-exportan los MISMOS
objetos, garantizando que DSPy y GEPA puntuan identico.
"""

from shared.scoring import field_match as fm


class TestNormalization:
    def test_strip_accents(self):
        assert fm.strip_accents("Ingeniería") == "Ingenieria"

    def test_normalize_text(self):
        assert fm.normalize_text("México, D.F.") == "mexico d f"
        assert fm.normalize_text("  Año  Nuevo!  ") == "ano nuevo"


class TestComparators:
    def test_exact(self):
        assert fm.compare_exact("python", "python")
        assert not fm.compare_exact("python", "Python")

    def test_normalized(self):
        assert fm.compare_normalized("México", "mexico")

    def test_fuzzy_threshold(self):
        assert fm.compare_fuzzy("ingeniero", "ingeniera", 0.8)
        assert not fm.compare_fuzzy("python", "javascript", 0.9)


class TestTokenizeAndSet:
    def test_tokenize_separators(self):
        assert fm.tokenize_list("Python, Django; AWS") == {"python", "django", "aws"}

    def test_tokenize_strips_value_after_colon(self):
        assert fm.tokenize_list("Python:5; Django:3") == {"python", "django"}

    def test_tokenize_empty(self):
        assert fm.tokenize_list("") == set()
        assert fm.tokenize_list("   ;  , ") == set()

    def test_score_set_partial(self):
        score, missing, extra = fm.score_set("python, django, aws", "python, django", ",;")
        assert score == 2 / 3
        assert missing == {"aws"}
        assert extra == set()


class TestScoreField:
    def test_set_perfect_order_insensitive(self):
        score, diag = fm.score_field("Python; Django", "django; python", "set", 0.85, ";,")
        assert score == 1.0
        assert diag == ""

    def test_exact_mismatch_diag(self):
        score, diag = fm.score_field("a", "b", "exact", 0.85, ",")
        assert score == 0.0
        assert "esperado 'a'" in diag

    def test_fuzzy_pass(self):
        score, _ = fm.score_field("Ingenieria, UBA", "Ingeniería, UBA", "fuzzy", 0.85, ",")
        assert score == 1.0


class TestBackwardCompatAliases:
    def test_metrics_aliases_are_same_objects(self):
        from dspy_gepa_poc import metrics as m

        assert m._normalize_text is fm.normalize_text
        assert m._score_set is fm.score_set
        assert m._tokenize_list is fm.tokenize_list
        assert m._score_field is fm.score_field
        assert m._compare_exact is fm.compare_exact
        assert m._compare_fuzzy is fm.compare_fuzzy
        assert m._compare_normalized is fm.compare_normalized
        assert m._strip_accents is fm.strip_accents
        assert m._VALID_FIELD_MODES is fm.VALID_FIELD_MODES

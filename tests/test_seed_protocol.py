"""Tests del veredicto senal-vs-ruido de shared.utils.seed_protocol.

Cubre la funcion pura ``verdict`` (sin LLM ni subprocess): codifica el criterio
de exito de docs/PROTOCOLO_N_SEEDS.md. Cada test construye agregados sinteticos
en escala 0-100 (scale=1.0) y verifica el primario y los flags resultantes.
"""

from shared.utils import seed_protocol as sp


def _agg(baseline, optimizado, robustez):
    """Arma el dict de agregados que consume ``verdict`` desde listas de scores."""
    return {
        "baseline": sp.summarize(baseline),
        "optimizado": sp.summarize(optimizado),
        "robustez": sp.summarize(robustez),
    }


class TestPrimario:
    def test_mejora_rangos_disjuntos_por_encima(self):
        new = _agg(baseline=[60, 62], optimizado=[88, 90], robustez=[88, 90])
        ref = _agg(baseline=[60, 62], optimizado=[80, 82], robustez=[80, 82])
        v = sp.verdict(new, ref, scale=1.0)
        assert v.primary == "MEJORA"
        assert "SOBREAJUSTE" not in v.flags
        assert "TECHO" not in v.flags

    def test_regresion_rangos_disjuntos_por_debajo(self):
        new = _agg(baseline=[60, 62], optimizado=[70, 72], robustez=[70, 72])
        ref = _agg(baseline=[60, 62], optimizado=[80, 82], robustez=[80, 82])
        v = sp.verdict(new, ref, scale=1.0)
        assert v.primary == "REGRESION"

    def test_ruido_rangos_solapados(self):
        new = _agg(baseline=[60, 62], optimizado=[79, 82], robustez=[79, 82])
        ref = _agg(baseline=[60, 62], optimizado=[80, 83], robustez=[80, 83])
        v = sp.verdict(new, ref, scale=1.0)
        assert v.primary == "RUIDO"

    def test_sin_referencia_cuando_before_vacio(self):
        new = _agg(baseline=[60, 62], optimizado=[70, 72], robustez=[70, 72])
        v = sp.verdict(new, {}, scale=1.0)
        assert v.primary == "SIN REFERENCIA"


class TestFlags:
    def test_techo_baseline_saturado_y_delta_plano(self):
        # baseline media 91 >= 85, Opt-Base ~ +0.5 <= 0.5 -> TECHO.
        new = _agg(baseline=[90, 92], optimizado=[91, 92], robustez=[90, 91])
        ref = _agg(baseline=[90, 92], optimizado=[90, 92], robustez=[90, 92])
        v = sp.verdict(new, ref, scale=1.0)
        assert "TECHO" in v.flags
        assert v.primary == "RUIDO"

    def test_no_techo_si_hay_gradiente(self):
        # baseline alto pero Opt-Base = +5 -> NO es techo (la optimizacion mueve).
        new = _agg(baseline=[86, 86], optimizado=[91, 91], robustez=[90, 91])
        ref = _agg(baseline=[86, 86], optimizado=[80, 82], robustez=[80, 82])
        v = sp.verdict(new, ref, scale=1.0)
        assert "TECHO" not in v.flags

    def test_sobreajuste_gap_val_test(self):
        # gap Opt(95.5) - Rob(80.5) = 15 > 3 -> SOBREAJUSTE.
        new = _agg(baseline=[60, 60], optimizado=[95, 96], robustez=[80, 81])
        ref = _agg(baseline=[60, 60], optimizado=[79, 82], robustez=[79, 82])
        v = sp.verdict(new, ref, scale=1.0)
        assert "SOBREAJUSTE" in v.flags

    def test_estabiliza_cuando_cae_el_rango(self):
        # rango nuevo (1) < rango referencia (4), disjunto y por encima -> MEJORA [ESTABILIZA].
        new = _agg(baseline=[60, 62], optimizado=[89, 90], robustez=[89, 90])
        ref = _agg(baseline=[60, 62], optimizado=[80, 84], robustez=[80, 84])
        v = sp.verdict(new, ref, scale=1.0)
        assert v.primary == "MEJORA"
        assert "ESTABILIZA" in v.flags


class TestComparabilidadModelos:
    """FR-008: la referencia previa debe igualar los modelos del lote nuevo."""

    @staticmethod
    def _row(task, prof):
        return {"Modelo Tarea": task, "Modelo Profesor": prof}

    def test_no_filtra_sin_lote_nuevo(self):
        before = [self._row("azure/gpt-5-mini", "azure/gpt-5")]
        filtered, excluded = sp.filter_reference_by_models(before, [])
        assert filtered == before and excluded == 0

    def test_conserva_solo_filas_con_mismos_modelos(self):
        before = [
            self._row("azure/gpt-5-mini", "azure/gpt-5"),
            self._row("azure/gpt-5-mini", "azure/gpt-5"),
            self._row("azure/gpt-4.1-mini", "azure/gpt-5"),  # task distinto
        ]
        new_rows = [self._row("azure/gpt-5-mini", "azure/gpt-5")]
        filtered, excluded = sp.filter_reference_by_models(before, new_rows)
        assert len(filtered) == 2 and excluded == 1

    def test_excluye_todo_si_ningun_modelo_coincide(self):
        before = [self._row("azure/gpt-4.1-mini", "azure/gpt-5")]
        new_rows = [self._row("azure/gpt-5-mini", "azure/gpt-5")]
        filtered, excluded = sp.filter_reference_by_models(before, new_rows)
        assert filtered == [] and excluded == 1


class TestEscalaYRender:
    def test_scale_lleva_gepa_0_1_a_0_100(self):
        # Mismos numeros que TECHO pero en escala 0-1; scale=100 los normaliza.
        new = _agg(baseline=[0.90, 0.92], optimizado=[0.91, 0.92], robustez=[0.90, 0.91])
        ref = _agg(baseline=[0.90, 0.92], optimizado=[0.90, 0.92], robustez=[0.90, 0.92])
        v = sp.verdict(new, ref, scale=100.0)
        assert "TECHO" in v.flags

    def test_tag_concatena_primario_y_flags(self):
        verd = sp.Verdict(primary="RUIDO", flags=["TECHO", "ESTABILIZA"], reasons=[])
        assert verd.tag() == "RUIDO [TECHO] [ESTABILIZA]"

    def test_reasons_no_vacio(self):
        new = _agg(baseline=[60, 62], optimizado=[88, 90], robustez=[88, 90])
        ref = _agg(baseline=[60, 62], optimizado=[80, 82], robustez=[80, 82])
        v = sp.verdict(new, ref, scale=1.0)
        assert v.reasons and all(isinstance(r, str) for r in v.reasons)

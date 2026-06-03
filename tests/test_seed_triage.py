"""Tests del triaje de casos (shared.utils.seed_triage).

Cubre la funcion pura ``diagnose`` (clasificacion RESUELTO/DUDOSO/SIN DATOS segun
resultados previos y prerequisitos) y los helpers ``_matches`` y
``gold_is_unverified``. Sin LLM ni subprocess.
"""

from shared.utils import seed_triage as st

TARGET = ("azure/gpt-5-mini", "azure/gpt-5")


def _row(task, prof, base, opt, rob):
    return {
        "Modelo Tarea": task,
        "Modelo Profesor": prof,
        "Baseline Score": str(base),
        "Optimizado Score": str(opt),
        "Robustez Score": str(rob),
    }


def _diag(rows, dataset_exists=True, gold_unverified=False, target=TARGET):
    return st.diagnose(
        name="caso",
        framework="gepa",
        config_path="x.yaml",
        rows=rows,
        target=target,
        dataset_exists=dataset_exists,
        gold_unverified=gold_unverified,
    )


class TestMatches:
    def test_par_exacto(self):
        assert st._matches(("azure/gpt-5-mini", "azure/gpt-5"), TARGET)

    def test_task_distinto_no_matchea(self):
        assert not st._matches(("azure/gpt-4.1-mini", "azure/gpt-5"), TARGET)

    def test_componente_objetivo_vacio_es_comodin(self):
        # target sin reflection -> no filtra por reflection.
        assert st._matches(("azure/gpt-5-mini", "lo-que-sea"), ("azure/gpt-5-mini", ""))


class TestStatus:
    def test_sin_datos_cuando_no_hay_filas(self):
        d = _diag([])
        assert d.status == "SIN DATOS" and d.n_comparable == 0

    def test_sin_referencia_comparable_es_dudoso(self):
        rows = [_row("azure/gpt-4.1-mini", "azure/gpt-5", 50, 80, 80)] * 3
        d = _diag(rows)
        assert d.status == "DUDOSO" and d.n_comparable == 0
        assert any("sin referencia comparable" in r for r in d.reasons)

    def test_resuelto_en_techo_y_estable(self):
        rows = [_row(*TARGET, 88, 88, 90) for _ in range(3)]
        d = _diag(rows)
        assert d.status == "RESUELTO"
        assert any("techo" in r for r in d.reasons)

    def test_dudoso_mejora_sin_confirmar(self):
        rows = [_row(*TARGET, 50, 80, 80) for _ in range(3)]  # Rob 80 < techo, delta +30
        d = _diag(rows)
        assert d.status == "DUDOSO"
        assert any("mejora sin confirmar" in r for r in d.reasons)

    def test_dudoso_alta_varianza(self):
        rows = [
            _row(*TARGET, 88, 88, 80),
            _row(*TARGET, 88, 88, 85),
            _row(*TARGET, 88, 88, 90),  # rango Rob = 10 > 5
        ]
        d = _diag(rows)
        assert d.status == "DUDOSO"
        assert any("alta varianza" in r for r in d.reasons)

    def test_dudoso_poca_evidencia(self):
        rows = [_row(*TARGET, 88, 88, 90)]  # n=1 < 3, aunque este en techo
        d = _diag(rows)
        assert d.status == "DUDOSO"
        assert any("poca evidencia" in r for r in d.reasons)


class TestPrerequisitos:
    def test_dataset_ausente_bloquea_seleccion(self):
        rows = [_row(*TARGET, 50, 80, 80) for _ in range(3)]
        d = _diag(rows, dataset_exists=False)
        assert d.blockers and not d.selectable

    def test_gold_no_verificado_advierte_pero_no_bloquea(self):
        rows = [_row(*TARGET, 50, 80, 80) for _ in range(3)]
        d = _diag(rows, gold_unverified=True)
        assert d.warnings and d.selectable
        assert any("gold_verificado" in w for w in d.warnings)


class TestGoldDetection:
    def test_detecta_gold_no(self, tmp_path):
        f = tmp_path / "ds.csv"
        f.write_text("text,split,gold_verificado\nhola,test,no\n", encoding="utf-8")
        assert st.gold_is_unverified(f) is True

    def test_sin_columna_gold_es_falso(self, tmp_path):
        f = tmp_path / "ds.csv"
        f.write_text("text,split\nhola,test\n", encoding="utf-8")
        assert st.gold_is_unverified(f) is False

    def test_gold_si_es_falso(self, tmp_path):
        f = tmp_path / "ds.csv"
        f.write_text("text,split,gold_verificado\nhola,test,si\n", encoding="utf-8")
        assert st.gold_is_unverified(f) is False

    def test_ruta_inexistente_es_falso(self, tmp_path):
        assert st.gold_is_unverified(tmp_path / "no_existe.csv") is False

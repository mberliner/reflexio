"""Tests del triaje de casos (shared.utils.seed_triage).

Cubre la funcion pura ``diagnose`` (clasificacion RESUELTO/DUDOSO/SIN DATOS segun
resultados previos y prerequisitos) y los helpers ``_matches`` y
``gold_is_unverified``. Sin LLM ni subprocess.
"""

from shared.utils import seed_triage as st

TARGET = ("azure/gpt-5-mini", "azure/gpt-5", "")


def _row(task, prof, judge, base, opt, rob):
    return {
        "Modelo Tarea": task,
        "Modelo Profesor": prof,
        "Modelo Juez": judge,
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
        assert st._matches(("azure/gpt-5-mini", "azure/gpt-5", ""), TARGET)

    def test_task_distinto_no_matchea(self):
        assert not st._matches(("azure/gpt-4.1-mini", "azure/gpt-5", ""), TARGET)

    def test_componente_objetivo_vacio_es_comodin(self):
        # target sin reflection -> no filtra por reflection.
        assert st._matches(("azure/gpt-5-mini", "lo-que-sea", "x"), ("azure/gpt-5-mini", "", ""))


class TestStatus:
    def test_sin_datos_cuando_no_hay_filas(self):
        d = _diag([])
        assert d.status == "SIN DATOS" and d.n_comparable == 0

    def test_sin_referencia_comparable_es_dudoso(self):
        rows = [_row("azure/gpt-4.1-mini", "azure/gpt-5", "", 50, 80, 80)] * 3
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


RAG_TARGET = ("azure/gpt-4.1-mini", "anthropic/claude-sonnet-5-5", "azure/gpt-4o")


class TestTernaComparabilidad:
    """SPEC-106 FR-006 / D11: la clave es (tarea, profesor, juez), cadena cruda."""

    def test_azure_y_openai_del_mismo_modelo_no_son_comparables(self):
        assert not st._matches(("azure/gpt-4o", "p", ""), ("openai/gpt-4o", "p", ""))

    def test_cambiar_solo_el_juez_separa_las_filas(self):
        rows = [_row(RAG_TARGET[0], RAG_TARGET[1], "azure/gpt-4.1", 50, 80, 80)] * 3
        d = _diag(rows, target=RAG_TARGET)
        assert d.status == "DUDOSO" and d.n_comparable == 0
        assert any("sin referencia comparable" in r for r in d.reasons)

    def test_mismo_juez_es_comparable(self):
        rows = [_row(*RAG_TARGET, 88, 88, 90) for _ in range(3)]
        assert _diag(rows, target=RAG_TARGET).n_comparable == 3

    def test_fila_rag_sin_migrar_no_es_comparable_y_sugiere_migrar(self):
        rows = [_row(RAG_TARGET[0], RAG_TARGET[1], "", 88, 88, 90)] * 3
        d = _diag(rows, target=RAG_TARGET)
        assert d.n_comparable == 0
        assert any("migrate_metrics_csv" in r for r in d.reasons)

    def test_otro_modelo_no_sugiere_migrar(self):
        rows = [_row("azure/otro", "p", "j", 50, 80, 80)] * 3
        d = _diag(rows, target=RAG_TARGET)
        assert not any("migrate" in r for r in d.reasons)


class TestTargetModelsTerna:
    @staticmethod
    def _env(monkeypatch, tmp_path, **env):
        monkeypatch.setattr(st, "REPO_ROOT", tmp_path)
        for k in ("LLM_MODEL_TASK", "LLM_MODEL_REFLECTION", "LLM_MODEL_JUDGE"):
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    def test_rag_incluye_juez_explicito(self, monkeypatch, tmp_path):
        self._env(
            monkeypatch,
            tmp_path,
            LLM_MODEL_TASK="azure/t",
            LLM_MODEL_REFLECTION="anthropic/p",
            LLM_MODEL_JUDGE="azure/j",
        )
        assert st.target_models("gepa", "rag") == ("azure/t", "anthropic/p", "azure/j")

    def test_rag_sin_juez_usa_el_profesor(self, monkeypatch, tmp_path):
        self._env(monkeypatch, tmp_path, LLM_MODEL_TASK="azure/t", LLM_MODEL_REFLECTION="azure/p")
        assert st.target_models("gepa", "rag") == ("azure/t", "azure/p", "azure/p")

    def test_no_rag_deja_juez_vacio(self, monkeypatch, tmp_path):
        self._env(
            monkeypatch,
            tmp_path,
            LLM_MODEL_TASK="azure/t",
            LLM_MODEL_REFLECTION="azure/p",
            LLM_MODEL_JUDGE="azure/j",
        )
        assert st.target_models("dspy", "classification") == ("azure/t", "azure/p", "")

    def test_juez_desde_env_del_subproyecto(self, monkeypatch, tmp_path):
        self._env(monkeypatch, tmp_path)
        sub = tmp_path / "gepa_standalone"
        sub.mkdir()
        (sub / ".env").write_text("LLM_MODEL_TASK=azure/t\nLLM_MODEL_JUDGE=azure/j\n")
        assert st.target_models("gepa", "rag") == ("azure/t", "", "azure/j")

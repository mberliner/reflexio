"""
SPEC-106 subfase 4a: registro del proveedor y host por rol, columna `Modelo Juez`,
logger sobre CSV sin migrar y migracion (FR-006, SC-006, D7, D10).

Sin red ni llamadas al LLM: se verifica solo lo que se registra (`run.json` y CSV).
"""

from __future__ import annotations

import csv
import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

from gepa_standalone.universal_optimizer import UniversalOptimizer
from shared.llm import LLMConfig
from shared.logging import ExperimentLogger
from shared.logging.csv_writer import STANDARD_COLUMN_MAPPING
from shared.logging.metadata import MetadataManager, collect_model_info
from shared.paths import GEPAPaths
from shared.utils.migrate_metrics_csv import migrate_csv

SECRET = "sk-secret-VALUE-123"

# Encabezado previo a SPEC-106 (el vigente en `main`: sin `Modelo Juez`).
PRE_106_HEADERS = [h for h in STANDARD_COLUMN_MAPPING.values() if h != "Modelo Juez"]


def _cfg(model: str, role: str, **kw) -> LLMConfig:
    return LLMConfig(model=model, api_key=SECRET, role=role, **kw)


def _read(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def _write_pre_106(csv_path, rows: list[dict]) -> None:
    """CSV maestro sin `Modelo Juez`, con las filas dadas (claves por encabezado)."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(PRE_106_HEADERS)
        for row in rows:
            writer.writerow([row.get(h, "") for h in PRE_106_HEADERS])


def _make_run(results_dir, name: str, *, run_json: dict | None, snapshot: str | None) -> str:
    run_dir = results_dir / "runs" / "caso" / name
    run_dir.mkdir(parents=True)
    if run_json is not None:
        (run_dir / "run.json").write_text(json.dumps(run_json), encoding="utf-8")
    if snapshot is not None:
        (run_dir / "config_snapshot.yaml").write_text(snapshot, encoding="utf-8")
    return f"runs/caso/{name}"


def _gepa_paths(tmp_path) -> GEPAPaths:
    return GEPAPaths(root_override=tmp_path)


# ==================== run.json: proveedor y host por rol ====================


class TestRunJsonProviderAndHost:
    def test_each_role_records_provider_and_host_without_credential(self):
        task = _cfg("azure/gpt-4.1-mini", "task", api_base="https://res.openai.azure.com/")
        reflection = _cfg("anthropic/claude-sonnet-5-5", "reflection")
        judge = _cfg("openai/gpt-4o", "judge", api_base="https://proxy.interno/v1")

        info = collect_model_info(task, reflection, judge_config=judge)

        assert info["task"]["provider"] == "azure"
        assert info["task"]["endpoint_host"] == "res.openai.azure.com"
        assert info["reflection"]["provider"] == "anthropic"
        assert info["reflection"]["endpoint_host"] == "api.anthropic.com"
        assert info["judge"]["provider"] == "openai"
        assert info["judge"]["endpoint_host"] == "proxy.interno"
        assert SECRET not in json.dumps(info)

    def test_models_keep_the_model_with_provider_prefix(self):
        info = collect_model_info(_cfg("azure/gpt-4.1-mini", "task"), _cfg("openai/gpt-4o", "r"))
        assert info["task"]["model"] == "azure/gpt-4.1-mini"
        assert info["reflection"]["model"] == "openai/gpt-4o"

    def test_without_judge_no_judge_role_is_registered(self):
        info = collect_model_info(_cfg("azure/gpt-4.1-mini", "task"), _cfg("openai/gpt-4o", "r"))
        assert "judge" not in info

    def test_run_json_written_by_metadata_manager_has_the_keys(self, tmp_path):
        info = collect_model_info(
            _cfg("azure/gpt-4.1-mini", "task", api_base="https://res.openai.azure.com"),
            _cfg("anthropic/claude-sonnet-5-5", "reflection"),
        )
        mgr = MetadataManager(tmp_path / "results")
        run_dir = tmp_path / "runs" / "caso" / "r1"
        run_dir.mkdir(parents=True)
        mgr.create_run(
            run_dir=run_dir,
            experiment_name="caso",
            seed=1,
            models=info,
            usage={},
            status="completed",
        )
        data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        assert data["models"]["reflection"]["provider"] == "anthropic"
        assert data["models"]["reflection"]["endpoint_host"] == "api.anthropic.com"
        assert SECRET not in (run_dir / "run.json").read_text(encoding="utf-8")


# ==================== columna Modelo Juez ====================


class TestJudgeModelColumn:
    def test_column_is_right_after_the_teacher_model(self):
        headers = list(STANDARD_COLUMN_MAPPING.values())
        assert headers[headers.index("Modelo Profesor") + 1] == "Modelo Juez"
        assert STANDARD_COLUMN_MAPPING["judge_model"] == "Modelo Juez"

    def test_rag_row_records_the_effective_judge(self, tmp_path):
        logger = ExperimentLogger(paths=_gepa_paths(tmp_path))
        logger.log_run(
            {
                "case_name": "rag",
                "task_model": "azure/gpt-4.1-mini",
                "reflection_model": "anthropic/claude-sonnet-5-5",
                "judge_model": "openai/gpt-4o",
                "run_dir": "N/A",
            }
        )
        row = _read(_gepa_paths(tmp_path).summary_csv)[0]
        assert row["Modelo Juez"] == "openai/gpt-4o"

    def test_non_rag_row_leaves_the_judge_empty(self, tmp_path):
        logger = ExperimentLogger(paths=_gepa_paths(tmp_path))
        logger.log_run({"case_name": "cls", "reflection_model": "azure/gpt-4o", "run_dir": "N/A"})
        row = _read(_gepa_paths(tmp_path).summary_csv)[0]
        assert row["Modelo Juez"] == ""

    def test_log_experiment_result_forwards_the_judge(self, tmp_path, monkeypatch):
        from gepa_standalone.utils import results_logger

        monkeypatch.setattr(results_logger, "get_gepa_paths", lambda: _gepa_paths(tmp_path))
        common = {
            "task_model": "azure/gpt-4.1-mini",
            "reflection_model": "azure/gpt-4o",
            "baseline_score": 0.5,
            "optimized_score": 0.7,
            "robustness_score": 0.6,
            "run_directory": "N/A",
        }
        results_logger.log_experiment_result(case_title="rag", judge_model="azure/gpt-4o", **common)
        results_logger.log_experiment_result(case_title="cls", **common)

        rows = _read(_gepa_paths(tmp_path).summary_csv)
        assert rows[0]["Modelo Juez"] == "azure/gpt-4o"
        assert rows[1]["Modelo Juez"] == ""


class TestOptimizerLogsTheJudge:
    @staticmethod
    def _save(tmp_path, monkeypatch, adapter) -> MagicMock:
        opt = UniversalOptimizer()
        opt.config = {
            "case": {"name": "caso"},
            "data": {"csv_filename": "x.csv"},
            "adapter": {"type": "rag"},
            "optimization": {"max_metric_calls": 10},
        }
        opt.task_config = _cfg("azure/gpt-4.1-mini", "task")
        opt.reflection_config = _cfg("anthropic/claude-sonnet-5-5", "reflection")
        opt.metadata_mgr = MetadataManager(tmp_path / "results")
        opt.seed = 7
        opt.adapter = adapter
        opt.results = {
            "initial_prompt": "a",
            "final_prompt": "b",
            "baseline_score": 0.5,
            "optimized_score": 0.7,
            "test_score": None,
        }
        opt.metric_summaries = {}
        paths = SimpleNamespace(
            results=tmp_path / "results",
            dataset=lambda name: tmp_path / name,
        )
        monkeypatch.setattr("gepa_standalone.universal_optimizer.get_paths", lambda: paths)
        monkeypatch.setattr(
            "gepa_standalone.universal_optimizer.save_run_details",
            lambda **kw: tmp_path / "runs" / "caso" / "ok",
        )
        monkeypatch.setattr("gepa_standalone.universal_optimizer.metrics_coverage", lambda s: {})
        (tmp_path / "runs" / "caso" / "ok").mkdir(parents=True)
        csv_row = MagicMock()
        monkeypatch.setattr("gepa_standalone.universal_optimizer.log_experiment_result", csv_row)
        opt.save_results()
        return csv_row

    def test_rag_passes_the_judge_model(self, tmp_path, monkeypatch):
        adapter = SimpleNamespace(
            task_max_tokens=100,
            judge_config=_cfg("openai/gpt-4o", "judge"),
            judge_max_tokens=50,
        )
        csv_row = self._save(tmp_path, monkeypatch, adapter)
        assert csv_row.call_args.kwargs["judge_model"] == "openai/gpt-4o"

    def test_without_judge_the_judge_model_is_empty(self, tmp_path, monkeypatch):
        adapter = SimpleNamespace(task_max_tokens=100)
        csv_row = self._save(tmp_path, monkeypatch, adapter)
        assert csv_row.call_args.kwargs["judge_model"] == ""


# ==================== logger sobre CSV sin migrar ====================


class TestLoggerOnUnmigratedCsv:
    def test_new_column_is_written_not_dropped(self, tmp_path, caplog):
        paths = _gepa_paths(tmp_path)
        _write_pre_106(
            paths.summary_csv,
            [{"Run ID": "old", "Caso": "rag", "Modelo Tarea": "t", "Modelo Profesor": "p"}],
        )

        with caplog.at_level(logging.WARNING):
            ExperimentLogger(paths=paths).log_run(
                {"case_name": "rag", "judge_model": "openai/gpt-4o", "run_dir": "N/A"}
            )

        rows = _read(paths.summary_csv)
        assert "Modelo Juez" in rows[0]
        assert rows[1]["Modelo Juez"] == "openai/gpt-4o"
        assert rows[0]["Modelo Juez"] == ""
        assert any("migrate_metrics_csv" in r.getMessage() for r in caplog.records)

    def test_existing_rows_and_unknown_columns_are_preserved(self, tmp_path):
        paths = _gepa_paths(tmp_path)
        headers = [*PRE_106_HEADERS, "Columna Propia"]
        paths.summary_csv.parent.mkdir(parents=True, exist_ok=True)
        with paths.summary_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(headers)
            row = dict.fromkeys(headers, "")
            row.update({"Run ID": "old", "Modelo Profesor": "p", "Columna Propia": "x"})
            writer.writerow([row[h] for h in headers])

        ExperimentLogger(paths=paths).log_run({"case_name": "n", "run_dir": "N/A"})

        rows = _read(paths.summary_csv)
        assert rows[0]["Run ID"] == "old"
        assert rows[0]["Modelo Profesor"] == "p"
        assert rows[0]["Columna Propia"] == "x"
        assert len(rows) == 2

    def test_header_current_is_untouched_and_silent(self, tmp_path, caplog):
        paths = _gepa_paths(tmp_path)
        ExperimentLogger(paths=paths).log_run({"case_name": "a", "run_dir": "N/A"})
        with caplog.at_level(logging.WARNING):
            ExperimentLogger(paths=paths).log_run({"case_name": "b", "run_dir": "N/A"})
        assert len(_read(paths.summary_csv)) == 2
        assert not any("migrate_metrics_csv" in r.getMessage() for r in caplog.records)


# ==================== migracion ====================


class TestMigrationOfJudgeModel:
    @staticmethod
    def _csv(tmp_path):
        return tmp_path / "results" / "experiments" / "metricas_optimizacion.csv"

    def test_rag_detected_by_run_json_gets_the_teacher(self, tmp_path):
        results = tmp_path / "results"
        run = _make_run(
            results, "r1", run_json={"models": {"judge": {"model": "x"}}}, snapshot=None
        )
        _write_pre_106(
            self._csv(tmp_path),
            [{"Run ID": "r1", "Modelo Profesor": "azure/gpt-4o", "Run Directory": run}],
        )

        migrate_csv(self._csv(tmp_path))

        assert _read(self._csv(tmp_path))[0]["Modelo Juez"] == "azure/gpt-4o"

    def test_rag_detected_by_config_snapshot_gets_the_teacher(self, tmp_path):
        results = tmp_path / "results"
        run = _make_run(
            results,
            "r2",
            run_json={"models": {"task": {}, "reflection": {}}},
            snapshot="adapter:\n  type: rag\n",
        )
        _write_pre_106(
            self._csv(tmp_path),
            [{"Run ID": "r2", "Modelo Profesor": "azure/gpt-4o", "Run Directory": run}],
        )

        migrate_csv(self._csv(tmp_path))

        assert _read(self._csv(tmp_path))[0]["Modelo Juez"] == "azure/gpt-4o"

    def test_non_rag_stays_empty_and_unknown_is_reported(self, tmp_path):
        results = tmp_path / "results"
        cls_run = _make_run(
            results, "r3", run_json={"models": {}}, snapshot="adapter:\n  type: classifier\n"
        )
        _write_pre_106(
            self._csv(tmp_path),
            [
                {"Run ID": "r3", "Modelo Profesor": "p", "Run Directory": cls_run},
                {"Run ID": "r4", "Modelo Profesor": "p", "Run Directory": "runs/caso/ausente"},
            ],
        )

        result = migrate_csv(self._csv(tmp_path))

        rows = _read(self._csv(tmp_path))
        assert rows[0]["Modelo Juez"] == ""
        assert rows[1]["Modelo Juez"] == ""
        assert result["judge_unknown"] == 1

    def test_existing_judge_is_never_overwritten(self, tmp_path):
        results = tmp_path / "results"
        run = _make_run(results, "r5", run_json={"models": {"judge": {}}}, snapshot=None)
        headers = list(STANDARD_COLUMN_MAPPING.values())
        csv_path = self._csv(tmp_path)
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(headers)
            row = dict.fromkeys(headers, "")
            row.update(
                {"Modelo Profesor": "p", "Modelo Juez": "openai/gpt-4o", "Run Directory": run}
            )
            writer.writerow([row[h] for h in headers])

        migrate_csv(csv_path)

        assert _read(csv_path)[0]["Modelo Juez"] == "openai/gpt-4o"


# ==================== SC-006 ====================


class TestSC006:
    """Sobre una copia del CSV maestro: la primera corrida RAG deja `Modelo Juez`, con o
    sin migracion previa, y las filas RAG previas migradas conservan al profesor."""

    @staticmethod
    def _prepare(tmp_path) -> GEPAPaths:
        paths = _gepa_paths(tmp_path)
        run = _make_run(
            paths.results,
            "prev",
            run_json={"models": {"judge": {"model": "azure/gpt-4o"}}},
            snapshot=None,
        )
        _write_pre_106(
            paths.summary_csv,
            [
                {
                    "Run ID": "prev",
                    "Caso": "rag",
                    "Modelo Tarea": "azure/gpt-4.1-mini",
                    "Modelo Profesor": "azure/gpt-4o",
                    "Run Directory": run,
                }
            ],
        )
        return paths

    @staticmethod
    def _first_rag_run(paths) -> None:
        ExperimentLogger(paths=paths).log_run(
            {
                "case_name": "rag",
                "task_model": "azure/gpt-4.1-mini",
                "reflection_model": "azure/gpt-4o",
                "judge_model": "azure/gpt-4o",
                "run_dir": "N/A",
            }
        )

    def test_without_prior_migration(self, tmp_path):
        paths = self._prepare(tmp_path)

        self._first_rag_run(paths)
        migrate_csv(paths.summary_csv)

        rows = _read(paths.summary_csv)
        assert [r["Modelo Juez"] for r in rows] == ["azure/gpt-4o", "azure/gpt-4o"]
        assert rows[0]["Modelo Profesor"] == rows[0]["Modelo Juez"]

    def test_with_prior_migration(self, tmp_path):
        paths = self._prepare(tmp_path)

        migrate_csv(paths.summary_csv)
        self._first_rag_run(paths)

        rows = _read(paths.summary_csv)
        assert [r["Modelo Juez"] for r in rows] == ["azure/gpt-4o", "azure/gpt-4o"]

    def test_migrated_previous_row_is_comparable_with_a_new_run_judged_by_the_teacher(
        self, tmp_path
    ):
        paths = self._prepare(tmp_path)
        migrate_csv(paths.summary_csv)
        self._first_rag_run(paths)

        old, new = _read(paths.summary_csv)
        key = ("Modelo Tarea", "Modelo Profesor", "Modelo Juez")
        assert tuple(old[k] for k in key) == tuple(new[k] for k in key)

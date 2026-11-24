"""
Corridas completas de ambos orquestadores con LLM simulado (SPEC-104, 5a).

`UniversalOptimizer.run()` y `ReflexioDeclarativa.run()` corren de punta a punta
sobre un YAML, un CSV y (en `gepa_standalone`) un prompt reales escritos en
`tmp_path`, con GEPA y DSPy reales. Solo se simula el transporte del LLM, con
respuestas reales de LiteLLM (`make_completion_response` de `tests/conftest.py`)
o excepciones reales de LiteLLM; la sonda de conexion (`validate_connection`,
fuera del camino de llamada de SPEC-104) se anula.

Cada corrida devuelve un `RunOutcome` con lo que la corrida deja escrito
(`run.json`, filas del CSV maestro, `results.json` de `gepa_standalone`), las
llamadas al LLM por modelo y los registros de log a nivel WARNING o superior.

Lo usan `tests/test_sc006_no_failure_regression.py` y
`tests/test_sc005_logs_vs_run_json.py`.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import make_completion_response

TASK_MODEL = "azure/gpt-4.1-mini"
REFLECTION_MODEL = "azure/gpt-4o"  # con precio en DEFAULT_PRICING: sin WARNING de costo
TOKENS_PER_CALL = 15  # make_completion_response: 10 de prompt + 5 de completion

# Respuesta del LLM simulado: texto (respuesta 200 sana), `litellm.ModelResponse`
# armada con `make_completion_response` o una excepcion real de LiteLLM.
Rule = Callable[[str, str, str], Any]


@dataclass
class RunOutcome:
    """Lo que deja una corrida completa (o abortada) de un orquestador."""

    orchestrator: Any
    run_json: dict[str, Any]
    run_dir: Path
    csv_rows: list[dict[str, str]]
    calls: list[tuple[str, str, str]]
    records: list[logging.LogRecord]
    error: BaseException | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def calls_to(self, model: str) -> list[tuple[str, str, str]]:
        return [c for c in self.calls if c[0] == model]


class _Recorder(logging.Handler):
    """Captura todos los registros WARNING o superior del proceso (logger raiz)."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _FakeTransport:
    """Responde por (modelo, system, user) segun `rule` y registra cada llamada."""

    def __init__(self, rule: Rule):
        self.rule = rule
        self.calls: list[tuple[str, str, str]] = []
        self._lock = threading.Lock()

    def respond(self, model: str, messages: list[dict[str, Any]]):
        system = next((str(m["content"]) for m in messages if m["role"] == "system"), "")
        user = " ".join(str(m.get("content")) for m in messages if m["role"] != "system")
        with self._lock:
            self.calls.append((model, system, user))
        out = self.rule(model, system, user)
        if isinstance(out, BaseException):
            raise out
        if isinstance(out, str):
            return make_completion_response(out, "stop")
        return out


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_master_csv(results_root: Path) -> list[dict[str, str]]:
    path = results_root / "experiments" / "metricas_optimizacion.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))  # EUROPEAN_CSV_CONFIG


def _single_run_json(results_root: Path) -> tuple[dict[str, Any], Path]:
    found = sorted(results_root.rglob("run.json"))
    assert len(found) == 1, f"se esperaba un run.json, hay {len(found)}: {found}"
    return json.loads(found[0].read_text(encoding="utf-8")), found[0].parent


def _run_capturing(run: Callable[[], None]) -> tuple[list[logging.LogRecord], BaseException | None]:
    recorder = _Recorder()
    root = logging.getLogger()
    previous = root.level
    root.addHandler(recorder)
    root.setLevel(min(previous, logging.WARNING) if previous else logging.WARNING)
    error = None
    try:
        run()
    except Exception as exc:  # noqa: BLE001 - el test decide si la corrida debia abortar
        error = exc
    finally:
        root.removeHandler(recorder)
        root.setLevel(previous)
    return recorder.records, error


def _common_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL_TASK", TASK_MODEL)
    monkeypatch.setenv("LLM_MODEL_REFLECTION", REFLECTION_MODEL)
    monkeypatch.setenv("LLM_API_KEY", "test-key-123")
    monkeypatch.setenv("LLM_API_BASE", "https://test.openai.azure.com/")
    monkeypatch.setenv("LLM_API_VERSION", "2024-02-15-preview")
    monkeypatch.setenv("LLM_CACHE", "false")
    monkeypatch.setattr("shared.llm.call.time.sleep", lambda s: None)
    monkeypatch.setattr("shared.llm.config.LLMConfig.validate_connection", lambda self: None)


def _yaml_block(name: str, value: dict[str, Any] | None) -> str:
    return f"{name}: {json.dumps(value)}\n" if value else ""


# ==================== gepa_standalone ====================

GEPA_BASE = "Clasifica el saludo."
GEPA_OPT = "Clasifica el saludo con cuidado."
GEPA_CLASSES = ["greeting", "farewell"]


JUDGE_MARKER = "evaluador experto de sistemas RAG"  # prompt de sistema del juez de RAG

# Por adapter: columnas del CSV, seccion `data` y seccion `adapter` del YAML. El
# caso `<prefix><i>` es el texto (clasificador) o la pregunta (RAG).
_GEPA_ADAPTERS = {
    "classifier": (
        ["split", "text", "label"],
        "{csv_filename: casos.csv, input_column: text, output_columns: [label]}",
        f"{{type: classifier, valid_classes: {json.dumps(GEPA_CLASSES)}}}",
    ),
    "rag": (
        ["split", "question", "context", "answer"],
        "{csv_filename: casos.csv, input_column: question, output_columns: [context, answer]}",
        "{type: rag}",
    ),
}


def gepa_case(text: str) -> str:
    """Identificador del caso (`t<i>`, `v<i>` o `x<i>`) dentro de un mensaje."""
    return re.search(r"\b[tvx]\d+\b", text).group(0)


def _gepa_row(adapter: str, case: str) -> dict[str, str]:
    if adapter == "rag":
        return {"question": case, "context": f"contexto de {case}", "answer": f"respuesta {case}"}
    return {"text": case, "label": "farewell" if int(case[1:]) % 2 else "greeting"}


def run_gepa_standalone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rule: Rule,
    *,
    adapter: str = "classifier",
    sizes: tuple[int, int, int] = (4, 6, 4),
    max_metric_calls: int = 30,
    failures: dict[str, Any] | None = None,
) -> RunOutcome:
    """
    `UniversalOptimizer.run()` completo: clasificador `greeting`/`farewell` (par ->
    greeting) o RAG con juez (el juez usa el modelo de reflexion; su prompt de
    sistema contiene `JUDGE_MARKER`).
    """
    import litellm

    from gepa_standalone import universal_optimizer as module
    from shared.paths import gepa_paths

    _common_env(monkeypatch)
    root = tmp_path / "gepa_root"
    paths = gepa_paths.GEPAPaths(root_override=root)
    monkeypatch.setattr(gepa_paths, "_paths_instance", paths)
    monkeypatch.setattr("gepa_standalone.data.data_loader.print_dataset_info", lambda *_: None)

    columns, data_yaml, adapter_yaml = _GEPA_ADAPTERS[adapter]
    rows = []
    for split, prefix, n in zip(("train", "val", "test"), ("t", "v", "x"), sizes, strict=True):
        rows += [{"split": split, **_gepa_row(adapter, f"{prefix}{i}")} for i in range(n)]
    _write_csv(paths.datasets / "casos.csv", columns, rows)
    (paths.prompts / "casos.json").write_text(
        json.dumps({"system_prompt": GEPA_BASE}), encoding="utf-8"
    )
    config = tmp_path / "casos.yaml"
    config.write_text(
        "case: {name: saludos, title: Saludos}\n"
        f"data: {data_yaml}\n"
        "prompt: {filename: casos.json}\n"
        f"adapter: {adapter_yaml}\n"
        "models: {cache: false, temperature: 0.0}\n"
        f"optimization: {{max_metric_calls: {max_metric_calls}, skip_perfect_score: false,"
        " display_progress_bar: false, eval_repeats: 1}\n" + _yaml_block("failures", failures),
        encoding="utf-8",
    )

    transport = _FakeTransport(rule)

    def completion(*args, **kwargs):
        return transport.respond(kwargs["model"], kwargs["messages"])

    monkeypatch.setattr(litellm, "completion", completion)
    optimizer = module.UniversalOptimizer(str(config))
    records, error = _run_capturing(optimizer.run)
    run_json, run_dir = _single_run_json(paths.results)
    extra = {}
    results_path = run_dir / "results.json"
    if results_path.exists():
        extra["results_json"] = json.loads(results_path.read_text(encoding="utf-8"))
    return RunOutcome(
        orchestrator=optimizer,
        run_json=run_json,
        run_dir=run_dir,
        csv_rows=_read_master_csv(paths.results),
        calls=transport.calls,
        records=records,
        error=error,
        extra=extra,
    )


# ==================== dspy_gepa_poc ====================

DSPY_SEED = "Responde si o no a la pregunta."
DSPY_OPT = "Responde si o no a la pregunta, con cuidado."


def dspy_answer(text: str) -> str:
    """Respuesta de un predictor DSPy (`ChatAdapter`) con el campo `answer`."""
    return f"[[ ## answer ## ]]\n{text}\n\n[[ ## completed ## ]]"


def dspy_question(user: str) -> str:
    """Pregunta (`t<i>`, `v<i>` o `x<i>`) del mensaje de usuario de DSPy."""
    marker = "[[ ## question ## ]]"
    return user.split(marker, 1)[1].split()[0]


def dspy_gold(question: str) -> str:
    """Respuesta esperada: par -> `si`, impar -> `no`."""
    return "no" if int(question[1:]) % 2 else "si"


def run_dspy_gepa_poc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rule: Rule,
    *,
    sizes: tuple[int, int, int] = (4, 6, 4),
    max_metric_calls: int = 30,
    failures: dict[str, Any] | None = None,
) -> RunOutcome:
    """`ReflexioDeclarativa.run()` completo de un modulo dinamico `question -> answer`."""
    from dspy_gepa_poc import reflexio_declarativa as module
    from dspy_gepa_poc.config import AppConfig
    from shared.paths import dspy_paths

    _common_env(monkeypatch)
    root = tmp_path / "dspy_root"
    paths = dspy_paths.DSPyPaths(root_override=root)
    monkeypatch.setattr(dspy_paths, "_dspy_paths_instance", paths)
    monkeypatch.setattr(AppConfig, "DATASETS_DIR", str(paths.datasets))

    rows = []
    for split, prefix, n in zip(("train", "val", "test"), ("t", "v", "x"), sizes, strict=True):
        rows += [
            {"split": split, "question": f"{prefix}{i}", "answer": dspy_gold(f"{prefix}{i}")}
            for i in range(n)
        ]
    _write_csv(paths.datasets / "sino.csv", ["split", "question", "answer"], rows)
    config = tmp_path / "sino.yaml"
    config.write_text(
        "case: {name: sino, title: Si o no}\n"
        "module: {type: dynamic}\n"
        "signature:\n"
        f'  instruction: "{DSPY_SEED}"\n'
        "  inputs: [{name: question, desc: La pregunta.}]\n"
        "  outputs: [{name: answer, desc: si o no.}]\n"
        "data: {csv_filename: sino.csv, input_column: question}\n"
        "models: {temperature: 0.0, cache: false}\n"
        f"optimization: {{max_metric_calls: {max_metric_calls}, predictor_type: predict,"
        " use_few_shot: false, match_mode: exact, ignore_in_metric: [], num_threads: 1,"
        " eval_repeats: 1}\n" + _yaml_block("failures", failures),
        encoding="utf-8",
    )

    transport = _FakeTransport(rule)

    def litellm_completion(request, num_retries, cache=None):
        return transport.respond(request["model"], request["messages"])

    monkeypatch.setattr("dspy.clients.lm.litellm_completion", litellm_completion)
    orchestrator = module.ReflexioDeclarativa(str(config))
    records, error = _run_capturing(orchestrator.run)
    run_json, run_dir = _single_run_json(paths.results)
    return RunOutcome(
        orchestrator=orchestrator,
        run_json=run_json,
        run_dir=run_dir,
        csv_rows=_read_master_csv(paths.results),
        calls=transport.calls,
        records=records,
        error=error,
    )

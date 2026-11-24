"""
SPEC-104 SC-005: los conteos de `run.json` coinciden con las fallas registradas a
nivel WARNING o superior en el log, en corridas completadas y abortadas.

Corridas completas de ambos orquestadores (`tests/orchestrator_e2e.py`) con fallas
inyectadas en el transporte del LLM (excepciones reales de LiteLLM y respuestas
reales via `make_completion_response`). Para cada corrida se capturan todos los
registros WARNING o superior del proceso y se exige:

- Cada falla aparece una sola vez a nivel WARNING (FR-007), con rol, clave e
  identificador del caso; el conteo por (clave, rol) de esas lineas es igual a
  `run.json["failures"]["counts"]`.
- El aborto es una linea ERROR aparte, que no es una falla (D4: `abort` no cuenta).
  Una falla `configuracion` deja su WARNING (la falla, que cuenta) y el ERROR del
  aborto: se comparan por separado. Corrida completada: ninguna linea de aborto y
  `abort` nulo; corrida abortada: exactamente una, igual a `run.json["abort"]`.
- Ninguna otra linea WARNING o superior: los intentos intermedios (reintentos de
  infraestructura, fallback de `ChatAdapter`, fallas repetidas de `entrada_dato`)
  van a DEBUG.
"""

import json
import logging
import re
from collections import Counter

import litellm

from shared.llm import RunAborted
from tests.conftest import make_completion_response
from tests.orchestrator_e2e import (
    DSPY_OPT,
    GEPA_OPT,
    JUDGE_MARKER,
    REFLECTION_MODEL,
    TASK_MODEL,
    dspy_answer,
    dspy_gold,
    dspy_question,
    gepa_case,
    run_dspy_gepa_poc,
    run_gepa_standalone,
)

# Lineas de `FailureTracker.record` (WARNING) y del aborto (ERROR). La causa puede
# tener espacios (p. ej. el `formato` del juez); el motivo del aborto es texto libre.
FAILURE_LINE = re.compile(
    r"^Falla de LLM: rol=(?P<rol>\S+) clave=(?P<clave>\S+) atribucion=(?P<atribucion>\S+) "
    r"causa=(?P<causa>.+) finish_reason=(?P<finish_reason>\S+) case_id=(?P<case_id>\S+)"
    r"(?: baseline_finish_reason=\S+)?$"
)
ABORT_LINE = re.compile(
    r"^Corrida abortada: clase=(?P<clase>\S+) rol=(?P<rol>\S+) "
    r"conteo=(?P<conteo>\d+)/(?P<intentos>\d+) causa=(?P<rest>.+)$"
)

# Umbrales holgados para las corridas que deben completarse con fallas de varias
# clases (seccion `failures` del YAML, FR-006); los minimos por defecto rigen.
RELAXED = {
    "thresholds": {
        "infraestructura": {"task": 0.9},
        "entrada_dato": {"task": 0.9},
        "total": {"reflection": 0.9},
    }
}


def _rate_limit():
    return litellm.RateLimitError(message="slow down", llm_provider="azure", model=TASK_MODEL)


def _content_policy():
    return litellm.ContentPolicyViolationError(
        message="blocked by policy", llm_provider="azure", model=TASK_MODEL
    )


def _auth_error():
    return litellm.AuthenticationError(message="bad key", llm_provider="azure", model=TASK_MODEL)


def _length():
    return make_completion_response(None, "length")


class _Reflection:
    """Reflexion: las primeras `bad` propuestas sin bloque de instruccion, luego validas."""

    def __init__(self, proposal, bad=1):
        self.proposal = proposal
        self.bad = bad
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.bad:
            return "propuesta sin bloque de instruccion"
        return f"```\n{self.proposal}\n```"


def _split_log(outcome):
    """(lineas de falla, lineas de aborto, resto) de los registros WARNING o superior."""
    failures, aborts, others = [], [], []
    for record in outcome.records:
        message = record.getMessage()
        failure, abort = FAILURE_LINE.match(message), ABORT_LINE.match(message)
        if failure and record.levelname == "WARNING":
            failures.append(failure.groupdict())
        elif abort and record.levelname == "ERROR":
            aborts.append(abort.groupdict())
        else:
            others.append(f"{record.levelname} {record.name}: {message}")
    return failures, aborts, others


def _counts(failure_lines):
    counts: dict[str, dict[str, int]] = {}
    for (clave, rol), n in Counter((f["clave"], f["rol"]) for f in failure_lines).items():
        counts.setdefault(clave, {})[rol] = n
    return counts


def assert_log_matches_run_json(outcome):
    """SC-005: conteos de `run.json` == fallas registradas a WARNING o superior."""
    failure_lines, abort_lines, others = _split_log(outcome)
    run_json = outcome.run_json

    assert others == []
    assert _counts(failure_lines) == run_json["failures"]["counts"]
    for line in failure_lines:
        assert line["case_id"] != "None", line  # FR-007: con identificador del caso

    if run_json["status"] == "completed":
        assert abort_lines == []
        assert run_json["abort"] is None
    else:
        assert run_json["status"] == "aborted"
        assert len(abort_lines) == 1
        line, abort = abort_lines[0], run_json["abort"]
        assert (line["clase"], line["rol"], int(line["conteo"])) == (
            abort["clase"],
            abort["rol"],
            abort["conteo"],
        )
        assert line["rest"].startswith(f"{abort['causa']}. ")
        assert int(line["intentos"]) == run_json["failures"]["abort"]["intentos"]
    return failure_lines, abort_lines


# ==================== gepa_standalone ====================


class TestGepaStandalone:
    def test_completed_run_with_failures_of_every_task_class(self, tmp_path, monkeypatch):
        reflection = _Reflection(GEPA_OPT)

        def rule(model, system, user):
            if model == REFLECTION_MODEL:
                return reflection()
            optimized = GEPA_OPT in system
            if user == "v5":
                return _rate_limit()  # infraestructura persistente: NE con cualquier prompt
            if user == "v3":
                return _content_policy()  # el baseline tambien: entrada_dato (caso unico)
            if optimized and user == "x1":
                return _length()  # el baseline no se corta: presupuesto_candidato
            if optimized and user == "x2":
                return "quizas"  # fuera de valid_classes: formato del clasificador
            i = int(user[1:])
            if optimized:
                return "farewell" if i % 2 else "greeting"
            return "greeting"

        outcome = run_gepa_standalone(tmp_path, monkeypatch, rule, failures=RELAXED)

        assert outcome.error is None
        failure_lines, _ = assert_log_matches_run_json(outcome)
        counts = outcome.run_json["failures"]["counts"]
        # Cada clase inyectada quedo registrada (el test no es vacuo).
        assert counts["infraestructura"]["task"] >= 2  # baseline y optimizado en val
        assert counts["entrada_dato"] == {"task": 1}  # repeticiones del caso a DEBUG
        assert counts["presupuesto_candidato"] == {"task": 1}
        assert counts["formato"]["task"] == 1
        assert counts["formato"]["reflection"] == 1
        assert outcome.run_json["failures"]["entrada_dato"] == ["val:3"]
        reflection_ids = {f["case_id"] for f in failure_lines if f["rol"] == "reflection"}
        assert all(cid.startswith("iteracion:") for cid in reflection_ids)

    def test_completed_rag_run_with_judge_failures(self, tmp_path, monkeypatch, caplog):
        reflection = _Reflection(GEPA_OPT)

        def rule(model, system, user):
            case = gepa_case(user)
            if JUDGE_MARKER in system:
                if case == "v1":
                    return "sin puntaje"  # ilegible en todos los reintentos: formato del juez
                if case == "v2":
                    return _length()  # juez cortado por max_tokens: presupuesto del juez
                good = f"Respuesta Generada: respuesta {case}" in user
                return json.dumps({"puntaje": 1.0 if good else 0.0, "razon": "ok"})
            if model == REFLECTION_MODEL:
                return reflection()
            if case == "v5":
                return _rate_limit()
            if case == "v3":
                return _content_policy()
            return f"respuesta {case}" if GEPA_OPT in system else "no se"

        relaxed = {
            "thresholds": {
                **RELAXED["thresholds"],
                "presupuesto": {"judge": 0.9},
                "formato": {"judge": 0.9},
            }
        }
        with caplog.at_level(logging.DEBUG, logger="gepa_standalone.adapters.simple_rag_adapter"):
            outcome = run_gepa_standalone(
                tmp_path, monkeypatch, rule, adapter="rag", failures=relaxed
            )

        assert outcome.error is None
        failure_lines, _ = assert_log_matches_run_json(outcome)
        counts = outcome.run_json["failures"]["counts"]
        assert counts["infraestructura"]["task"] >= 2
        assert counts["entrada_dato"] == {"task": 1}
        assert counts["formato"]["reflection"] == 1
        judge_ids = {f["case_id"] for f in failure_lines if f["rol"] == "judge"}
        assert judge_ids == {"val:1", "val:2"}

        # FR-007 / FR-009 en el juez: una falla por caso evaluado, no por llamada. El
        # puntaje ilegible se pide 1 + judge_retries (2) veces por evaluacion; los
        # intentos intermedios van a DEBUG y no suman al contador.
        judge_calls = [c for c in outcome.calls if JUDGE_MARKER in c[1]]
        v1_calls = [c for c in judge_calls if gepa_case(c[2]) == "v1"]
        v2_calls = [c for c in judge_calls if gepa_case(c[2]) == "v2"]
        assert len(v1_calls) % 3 == 0
        assert counts["formato"]["judge"] == len(v1_calls) // 3 >= 2  # baseline y optimizado
        assert counts["presupuesto"]["judge"] == len(v2_calls) >= 2  # capa 1: sin reintento
        retries = [
            r
            for r in caplog.records
            if r.getMessage().startswith("Puntaje del juez invalido (intento")
        ]
        assert len(retries) == len(v1_calls)
        assert {r.levelno for r in retries} == {logging.DEBUG}

    def test_configuracion_aborts_with_one_warning_and_one_error(self, tmp_path, monkeypatch):
        def rule(model, system, user):
            return _auth_error() if user == "v2" else "greeting"

        outcome = run_gepa_standalone(tmp_path, monkeypatch, rule)

        assert isinstance(outcome.error, RunAborted)
        failure_lines, abort_lines = assert_log_matches_run_json(outcome)
        # La falla cuenta (WARNING) y el aborto es otra linea (ERROR).
        assert [(f["clave"], f["rol"], f["case_id"]) for f in failure_lines] == [
            ("configuracion", "task", "val:2")
        ]
        assert abort_lines[0]["clase"] == "configuracion"
        assert outcome.csv_rows == []

    def test_threshold_abort_counts_match_the_log(self, tmp_path, monkeypatch):
        def rule(model, system, user):
            return _rate_limit() if user in ("v1", "v3") else "greeting"

        outcome = run_gepa_standalone(
            tmp_path, monkeypatch, rule, failures={"min_attempts": {"task": 4}}
        )

        assert isinstance(outcome.error, RunAborted)
        failure_lines, abort_lines = assert_log_matches_run_json(outcome)
        assert set(outcome.run_json["failures"]["counts"]) == {"infraestructura"}
        assert abort_lines[0]["clase"] == "infraestructura"
        assert outcome.csv_rows == []

    def test_reflection_abort_swallowed_by_gepa_counts_match_the_log(self, tmp_path, monkeypatch):
        # Toda propuesta sin bloque: GEPA atrapa la excepcion y sigue; el estado aborta.
        reflection = _Reflection(GEPA_OPT, bad=10**6)

        def rule(model, system, user):
            if model == REFLECTION_MODEL:
                return reflection()
            return "greeting"  # el baseline falla los impares: GEPA reflexiona

        outcome = run_gepa_standalone(tmp_path, monkeypatch, rule, max_metric_calls=60)

        assert isinstance(outcome.error, RunAborted)
        failure_lines, abort_lines = assert_log_matches_run_json(outcome)
        assert set(outcome.run_json["failures"]["counts"]) == {"formato"}
        assert abort_lines[0]["rol"] == "reflection"
        assert outcome.csv_rows == []


# ==================== dspy_gepa_poc ====================


class TestDspyGepaPoc:
    def test_completed_run_with_failures_of_every_task_class(self, tmp_path, monkeypatch):
        reflection = _Reflection(DSPY_OPT)

        def rule(model, system, user):
            if model == REFLECTION_MODEL:
                return reflection()
            optimized = DSPY_OPT in system
            question = dspy_question(user)
            if question == "v5":
                return _rate_limit()
            if question == "v3":
                return _content_policy()
            if optimized and question == "x1":
                return _length()
            if optimized and question == "x2":
                return "respuesta sin los campos del adapter"  # AdapterParseError: formato
            return dspy_answer(dspy_gold(question) if optimized else "si")

        outcome = run_dspy_gepa_poc(tmp_path, monkeypatch, rule, failures=RELAXED)

        assert outcome.error is None
        failure_lines, _ = assert_log_matches_run_json(outcome)
        counts = outcome.run_json["failures"]["counts"]
        assert counts["infraestructura"]["task"] >= 2
        assert counts["entrada_dato"] == {"task": 1}
        assert counts["presupuesto_candidato"] == {"task": 1}
        assert counts["formato"]["task"] == 1
        assert counts["formato"]["reflection"] == 1
        assert outcome.run_json["failures"]["entrada_dato"] == ["val:3"]
        reflection_ids = {f["case_id"] for f in failure_lines if f["rol"] == "reflection"}
        assert all(cid.startswith("iteracion:") for cid in reflection_ids)

    def test_configuracion_aborts_with_one_warning_and_one_error(self, tmp_path, monkeypatch):
        def rule(model, system, user):
            if dspy_question(user) == "v2":
                return _auth_error()
            return dspy_answer("si")

        outcome = run_dspy_gepa_poc(tmp_path, monkeypatch, rule)

        assert isinstance(outcome.error, RunAborted)
        failure_lines, abort_lines = assert_log_matches_run_json(outcome)
        assert [(f["clave"], f["rol"], f["case_id"]) for f in failure_lines] == [
            ("configuracion", "task", "val:2")
        ]
        assert abort_lines[0]["clase"] == "configuracion"
        assert outcome.csv_rows == []

    def test_threshold_abort_counts_match_the_log(self, tmp_path, monkeypatch):
        def rule(model, system, user):
            if dspy_question(user) in ("v1", "v3"):
                return _rate_limit()
            return dspy_answer("si")

        outcome = run_dspy_gepa_poc(
            tmp_path, monkeypatch, rule, failures={"min_attempts": {"task": 4}}
        )

        assert isinstance(outcome.error, RunAborted)
        failure_lines, abort_lines = assert_log_matches_run_json(outcome)
        assert set(outcome.run_json["failures"]["counts"]) == {"infraestructura"}
        assert abort_lines[0]["clase"] == "infraestructura"
        assert outcome.csv_rows == []

    def test_reflection_abort_swallowed_by_gepa_counts_match_the_log(self, tmp_path, monkeypatch):
        reflection = _Reflection(DSPY_OPT, bad=10**6)

        def rule(model, system, user):
            if model == REFLECTION_MODEL:
                return reflection()
            return dspy_answer("si")

        outcome = run_dspy_gepa_poc(tmp_path, monkeypatch, rule, max_metric_calls=60)

        assert isinstance(outcome.error, RunAborted)
        failure_lines, abort_lines = assert_log_matches_run_json(outcome)
        assert set(outcome.run_json["failures"]["counts"]) == {"formato"}
        assert abort_lines[0]["rol"] == "reflection"
        assert outcome.csv_rows == []

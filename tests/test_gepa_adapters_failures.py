"""
SPEC-104 3c: fallas tecnicas justas en los adapters de `gepa_standalone`.

Verifica el comportamiento que pide la spec (no el del codigo previo) con respuestas
y errores reales de LiteLLM: `litellm.completion` real corre contra los payloads de
`tests/litellm_failure_payloads.py` interceptados en el transporte HTTP, y las
respuestas sanas salen de `make_completion_response`.

Requisitos: FR-001 (los adapters reportan al contador), FR-002 (ningun caso
desaparece), FR-004 (atribucion contra el baseline), FR-010 (`formato` por adapter),
FR-012 y SC-008 (un caso NE nunca llega al dataset reflexivo), SC-001.
"""

import logging
from unittest.mock import MagicMock

import litellm
import pytest
from gepa import EvaluationBatch

from gepa_standalone.adapters.simple_classifier_adapter import SimpleClassifierAdapter
from gepa_standalone.adapters.simple_extractor_adapter import SimpleExtractorAdapter
from gepa_standalone.adapters.simple_rag_adapter import SimpleRAGAdapter
from gepa_standalone.adapters.simple_sql_adapter import SimpleSQLAdapter
from shared.llm import RunAborted, get_failure_tracker
from tests.conftest import make_completion_response, project_warnings
from tests.litellm_failure_payloads import ALL_FAILURE_CASES
from tests.test_litellm_failure_mapping import intercept_httpx

REAL_COMPLETION = litellm.completion

INPUT_FILTER = "azure_400_content_filter_canonico"
LENGTH = "azure_200_length_vacio"
OUTPUT_FILTER = "azure_200_content_filter_vacio"


PAYLOAD_IDS = frozenset(c.id for c in ALL_FAILURE_CASES)


def _payload(case_id):
    return next(c for c in ALL_FAILURE_CASES if c.id == case_id)


def _transport_error_case():
    return next(c for c in ALL_FAILURE_CASES if c.case_type == "transport_error")


def _system_and_user(kwargs):
    messages = kwargs["messages"]
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    return system, messages[-1]["content"]


class Script:
    """
    `litellm.completion` que decide por (system, user): devuelve un `ModelResponse` real,
    o ejecuta la llamada real de LiteLLM contra un payload de falla interceptado en HTTP.
    """

    def __init__(self, monkeypatch, rule):
        self.rule = rule
        self.calls = []
        monkeypatch.setattr("litellm.completion", self)

    def __call__(self, *args, **kwargs):
        system, user = _system_and_user(kwargs)
        self.calls.append((system, user))
        action = self.rule(system, user)
        if action in PAYLOAD_IDS:
            with intercept_httpx(_payload(action)):
                return REAL_COMPLETION(*args, **kwargs)
        return make_completion_response(action)

    def calls_with(self, system):
        return [c for c in self.calls if c[0] == system]


@pytest.fixture
def env(mock_env, monkeypatch):
    monkeypatch.setenv("LLM_MODEL_REFLECTION", "azure/gpt-4.1-mini")
    monkeypatch.setenv("LLM_API_BASE", "https://test.openai.azure.com/")
    return monkeypatch


def _classifier(prompt_base="base"):
    adapter = SimpleClassifierAdapter(valid_classes=["greeting", "farewell"])
    adapter.set_baseline(prompt_base)
    return adapter


def _sql(prompt_base="base"):
    adapter = SimpleSQLAdapter()
    adapter.set_baseline(prompt_base)
    return adapter


def _extractor(prompt_base="base"):
    adapter = SimpleExtractorAdapter(required_fields=["name"])
    adapter.set_baseline(prompt_base)
    return adapter


def _rag(prompt_base="base"):
    adapter = SimpleRAGAdapter()
    adapter.set_baseline(prompt_base)
    return adapter


def _classifier_batch(n=3, fail_ids=()):
    return [
        {
            "case_id": f"c{i}",
            "text": "FALLA" if f"c{i}" in fail_ids else "hola",
            "label": "greeting",
        }
        for i in range(n)
    ]


def _sql_batch(n=3, fail_ids=()):
    ex = {"schema": "t(a)", "expected_sql": "SELECT 1"}
    return [
        {
            "case_id": f"c{i}",
            "question": "FALLA" if f"c{i}" in fail_ids else "q",
            "extracted": ex,
        }
        for i in range(n)
    ]


def _extractor_batch(n=3, fail_ids=()):
    return [
        {
            "case_id": f"c{i}",
            "text": "FALLA" if f"c{i}" in fail_ids else "Ana",
            "extracted": {"name": "Ana"},
        }
        for i in range(n)
    ]


def _rag_batch(n=3, fail_ids=()):
    return [
        {
            "case_id": f"c{i}",
            "question": "FALLA" if f"c{i}" in fail_ids else "q",
            "context": "c",
            "answer": "Paris",
        }
        for i in range(n)
    ]


ADAPTERS = {
    "classifier": (_classifier, _classifier_batch, "greeting"),
    "sql": (_sql, _sql_batch, "SELECT 1"),
    "extractor": (_extractor, _extractor_batch, '{"name": "Ana"}'),
    "rag": (_rag, _rag_batch, "Paris"),
}


def _healthy_rag_reply(system, ok_text):
    return '{"puntaje": 1.0, "razon": "ok"}' if "evaluador" in system else ok_text


def _scripted_adapter(env, kind, fail_payload, baseline_payload=None, fail_ids=("c1",)):
    """Adapter + lote + script: los casos `fail_ids` fallan con el candidato `cand`."""
    make, make_batch, ok_text = ADAPTERS[kind]

    def rule(system, user):
        failing = "FALLA" in user
        if system == "cand" and failing:
            return fail_payload
        if system == "base" and failing and baseline_payload is not None:
            return baseline_payload
        return _healthy_rag_reply(system, ok_text)

    script = Script(env, rule)
    return make(), make_batch(3, fail_ids), script


# ==================== SC-001 y FR-002: ningun caso desaparece ====================

FAILURE_PAYLOADS = [INPUT_FILTER, LENGTH, OUTPUT_FILTER]


class TestNoCaseDisappears:
    @pytest.mark.parametrize("kind", list(ADAPTERS))
    @pytest.mark.parametrize("payload", FAILURE_PAYLOADS)
    @pytest.mark.parametrize("traces", [False, True])
    def test_evaluated_plus_ne_equals_batch(self, env, kind, payload, traces):
        adapter, batch, _ = _scripted_adapter(env, kind, payload)

        result = adapter.evaluate(batch, {"system_prompt": "cand"}, capture_traces=traces)

        assert len(result.outputs) == len(result.scores) == len(batch)
        evaluated = [o for o in result.outputs if o["evaluated"]]
        not_evaluated = [o for o in result.outputs if not o["evaluated"]]
        assert len(evaluated) + len(not_evaluated) == len(batch)
        assert [o["case_id"] for o in result.outputs] == [c["case_id"] for c in batch]
        if traces:
            assert len(result.trajectories) == len(batch)
            assert [t["case_id"] for t in result.trajectories] == [c["case_id"] for c in batch]
        # El caso con falla recibe 0.0 tecnico; los demas, el score real
        assert result.scores[1] == 0.0
        assert result.scores[0] == result.scores[2] == 1.0

    @pytest.mark.parametrize("kind", list(ADAPTERS))
    def test_infrastructure_failure_keeps_the_case_as_ne(self, env, kind):
        make, make_batch, ok_text = ADAPTERS[kind]
        transport = _transport_error_case()

        def completion(*args, **kwargs):
            system, user = _system_and_user(kwargs)
            if "FALLA" in user:
                with intercept_httpx(transport):
                    return REAL_COMPLETION(*args, **kwargs)
            return make_completion_response(_healthy_rag_reply(system, ok_text))

        env.setattr("litellm.completion", completion)
        get_failure_tracker().configure(infra_retries=0)
        adapter, batch = make(), make_batch(3, ("c1",))

        result = adapter.evaluate(batch, {"system_prompt": "cand"})

        assert len(result.outputs) == 3
        assert result.outputs[1]["evaluated"] is False
        assert result.outputs[1]["failure"]["clase"] == "infraestructura"
        assert get_failure_tracker().snapshot()["counts"]["infraestructura"]["task"] == 1


# ==================== FR-004: atribucion contra el baseline ====================


class TestAttribution:
    @pytest.mark.parametrize("kind", list(ADAPTERS))
    def test_input_filter_baseline_ok_is_candidate_score_zero(self, env, kind):
        adapter, batch, script = _scripted_adapter(env, kind, INPUT_FILTER)

        result = adapter.evaluate(batch, {"system_prompt": "cand"})

        out = result.outputs[1]
        assert out["failure"]["clave"] == "entrada_candidato"
        assert out["failure"]["atribucion"] == "candidato"
        assert out["evaluated"] is True
        assert result.scores[1] == 0.0
        snapshot = get_failure_tracker().snapshot()
        assert snapshot["counts"]["entrada_candidato"]["task"] == 1
        assert snapshot["entrada_dato"] == []
        assert len(script.calls_with("base")) == 1  # una sola llamada baseline

    @pytest.mark.parametrize("kind", list(ADAPTERS))
    def test_input_filter_baseline_also_rejected_is_external_ne(self, env, kind):
        adapter, batch, script = _scripted_adapter(
            env, kind, INPUT_FILTER, baseline_payload=INPUT_FILTER
        )

        result = adapter.evaluate(batch, {"system_prompt": "cand"})

        out = result.outputs[1]
        assert out["failure"]["clave"] == "entrada_dato"
        assert out["failure"]["atribucion"] == "externa"
        assert out["evaluated"] is False
        assert get_failure_tracker().snapshot()["entrada_dato"] == ["c1"]

    @pytest.mark.parametrize("kind", list(ADAPTERS))
    def test_budget_baseline_ok_is_candidate_score_zero(self, env, kind):
        adapter, batch, _ = _scripted_adapter(env, kind, LENGTH)

        result = adapter.evaluate(batch, {"system_prompt": "cand"})

        out = result.outputs[1]
        assert out["failure"]["clave"] == "presupuesto_candidato"
        assert out["failure"]["finish_reason"] == "length"
        assert out["evaluated"] is True

    @pytest.mark.parametrize("kind", list(ADAPTERS))
    def test_healthy_baseline_finish_reason_is_recorded(self, env, kind):
        """FR-004: la atribucion MUST registrar el `finish_reason` de ambas llamadas, tambien
        cuando el baseline respondio sano (`stop`)."""
        adapter, batch, _ = _scripted_adapter(env, kind, LENGTH)

        result = adapter.evaluate(batch, {"system_prompt": "cand"})

        assert result.outputs[1]["failure"]["baseline_finish_reason"] == "stop"

    @pytest.mark.parametrize("kind", list(ADAPTERS))
    def test_budget_baseline_also_cut_is_external_ne(self, env, kind):
        adapter, batch, _ = _scripted_adapter(env, kind, LENGTH, baseline_payload=LENGTH)

        result = adapter.evaluate(batch, {"system_prompt": "cand"})

        out = result.outputs[1]
        assert out["failure"]["clave"] == "presupuesto"
        assert out["failure"]["atribucion"] == "externa"
        assert out["failure"]["finish_reason"] == "length"
        assert out["failure"]["baseline_finish_reason"] == "length"
        assert out["evaluated"] is False

    def test_baseline_fails_with_other_class_case_becomes_that_class(self, env):
        """Candidato `entrada`, baseline `presupuesto`: la falla del caso es la del
        baseline (`presupuesto`, externa) y queda NE (FR-004)."""
        adapter, batch, _ = _scripted_adapter(env, "classifier", INPUT_FILTER, LENGTH)

        result = adapter.evaluate(batch, {"system_prompt": "cand"})

        out = result.outputs[1]
        assert out["failure"]["clave"] == "presupuesto"
        assert out["evaluated"] is False
        counts = get_failure_tracker().snapshot()["counts"]
        assert "entrada_candidato" not in counts and "entrada_dato" not in counts

    def test_evaluating_the_baseline_prompt_is_external_without_extra_call(self, env):
        adapter, batch, script = _scripted_adapter(env, "classifier", INPUT_FILTER)
        script.rule = lambda system, user: INPUT_FILTER if "FALLA" in user else "greeting"

        result = adapter.evaluate(batch, {"system_prompt": "base"})

        assert result.outputs[1]["failure"]["clave"] == "entrada_dato"
        assert result.outputs[1]["evaluated"] is False
        assert len(script.calls) == 3  # un llamado por caso, ninguno extra para el baseline

    def test_baseline_call_is_cached_across_candidates_and_failure_classes(self, env):
        """Una sola llamada baseline por caso en toda la corrida: la comparten dos
        candidatos y las dos clases (`entrada` y `presupuesto`)."""

        def rule(system, user):
            if "FALLA" not in user:
                return "greeting"
            return {"cand1": INPUT_FILTER, "cand2": LENGTH}.get(system, "greeting")

        script = Script(env, rule)
        adapter = _classifier()
        batch = _classifier_batch(2, ("c1",))

        adapter.evaluate(batch, {"system_prompt": "cand1"})
        adapter.evaluate(batch, {"system_prompt": "cand2"})
        adapter.evaluate(batch, {"system_prompt": "cand1"})

        assert len(script.calls_with("base")) == 1

    def test_attribution_uses_the_same_max_tokens_as_the_task(self, env):
        seen = []

        def completion(*args, **kwargs):
            system, user = _system_and_user(kwargs)
            seen.append((system, kwargs.get("max_tokens")))
            if system == "cand" and "FALLA" in user:
                with intercept_httpx(_payload(LENGTH)):
                    return REAL_COMPLETION(*args, **kwargs)
            return make_completion_response("greeting")

        env.setattr("litellm.completion", completion)
        adapter = _classifier()

        adapter.evaluate(_classifier_batch(2, ("c1",)), {"system_prompt": "cand"})

        task_tokens = {mt for s, mt in seen if s == "cand"}
        baseline_tokens = {mt for s, mt in seen if s == "base"}
        assert baseline_tokens == task_tokens == {adapter.task_max_tokens}

    def test_infrastructure_baseline_leaves_case_ne_and_is_not_cached(self, env):
        """Un resultado `infraestructura` del baseline deja el caso NE esa vez y se vuelve
        a consultar la proxima vez que el caso lo necesite (parada de 3b)."""
        transport = _transport_error_case()
        state = {"baseline_calls": 0}

        def completion(*args, **kwargs):
            system, user = _system_and_user(kwargs)
            if system == "cand" and "FALLA" in user:
                with intercept_httpx(_payload(INPUT_FILTER)):
                    return REAL_COMPLETION(*args, **kwargs)
            if system == "base" and "FALLA" in user:
                state["baseline_calls"] += 1
                if state["baseline_calls"] == 1:
                    with intercept_httpx(transport):
                        return REAL_COMPLETION(*args, **kwargs)
            return make_completion_response("greeting")

        env.setattr("litellm.completion", completion)
        get_failure_tracker().configure(infra_retries=0)
        adapter = _classifier()
        batch = _classifier_batch(2, ("c1",))

        first = adapter.evaluate(batch, {"system_prompt": "cand"})
        second = adapter.evaluate(batch, {"system_prompt": "cand"})

        assert first.outputs[1]["failure"]["clase"] == "infraestructura"
        assert first.outputs[1]["evaluated"] is False
        assert second.outputs[1]["failure"]["clave"] == "entrada_candidato"
        assert second.outputs[1]["evaluated"] is True
        assert state["baseline_calls"] == 2

    def test_attribution_call_does_not_count_as_attempt_or_failure(self, env):
        adapter, batch, _ = _scripted_adapter(env, "classifier", INPUT_FILTER)

        adapter.evaluate(batch, {"system_prompt": "cand"})

        snapshot = get_failure_tracker().snapshot()
        assert snapshot["attempts"]["task"] == 3  # un intento por caso, no por llamada HTTP
        assert sum(snapshot["counts"]["entrada_candidato"].values()) == 1
        assert list(snapshot["counts"]) == ["entrada_candidato"]

    def test_attribution_tokens_are_recorded_in_usage(self, env):
        from shared.llm import get_tracker

        get_tracker().reset()
        adapter, batch, _ = _scripted_adapter(env, "classifier", INPUT_FILTER)

        adapter.evaluate(batch, {"system_prompt": "cand"})

        # 2 casos sanos del candidato + la llamada baseline (sana) del caso c1; la del
        # candidato con falla de HTTP no tiene respuesta. El gasto de atribucion es real.
        assert get_tracker().snapshot()["task"]["calls"] == 3

    def test_run_aborted_inside_attribution_propagates(self, env):
        """Si el baseline dispara `configuracion`, la corrida aborta (no se traga)."""

        def completion(*args, **kwargs):
            system, user = _system_and_user(kwargs)
            if "FALLA" in user:
                with intercept_httpx(_payload(INPUT_FILTER if system == "cand" else _auth())):
                    return REAL_COMPLETION(*args, **kwargs)
            return make_completion_response("greeting")

        env.setattr("litellm.completion", completion)
        adapter = _classifier()

        with pytest.raises(RunAborted):
            adapter.evaluate(_classifier_batch(3, ("c0", "c1")), {"system_prompt": "cand"})

    def test_missing_baseline_for_attributable_failure_is_a_clear_error(self, env):
        Script(env, lambda s, u: INPUT_FILTER if "FALLA" in u else "greeting")
        adapter = SimpleClassifierAdapter(valid_classes=["greeting"])

        with pytest.raises(RuntimeError, match="set_baseline"):
            adapter.evaluate(_classifier_batch(2, ("c1",)), {"system_prompt": "cand"})

    def test_missing_baseline_is_fine_for_other_classes(self, env):
        Script(env, lambda s, u: OUTPUT_FILTER if "FALLA" in u else "greeting")
        adapter = SimpleClassifierAdapter(valid_classes=["greeting"])

        result = adapter.evaluate(_classifier_batch(2, ("c1",)), {"system_prompt": "cand"})

        assert result.outputs[1]["failure"]["clave"] == "filtro_salida"

    def test_missing_case_id_is_value_error(self, env):
        Script(env, lambda s, u: "greeting")
        adapter = _classifier()

        with pytest.raises(ValueError, match="case_id"):
            adapter.evaluate([{"text": "x", "label": "greeting"}], {"system_prompt": "cand"})


def _auth():
    """Payload de autenticacion (`configuracion`) del conjunto de evidencia."""
    return next(c.id for c in ALL_FAILURE_CASES if c.status_code == 401)


# ==================== FR-012 y SC-008: el dataset reflexivo ====================


class TestReflectiveDatasetExcludesNE:
    def _eval(self, env, kind, payload, baseline_payload):
        adapter, batch, _ = _scripted_adapter(env, kind, payload, baseline_payload)
        result = adapter.evaluate(batch, {"system_prompt": "cand"}, capture_traces=True)
        return adapter, result

    @pytest.mark.parametrize("kind", list(ADAPTERS))
    @pytest.mark.parametrize(
        ("payload", "baseline_payload"),
        [(OUTPUT_FILTER, None), (INPUT_FILTER, INPUT_FILTER), (LENGTH, LENGTH)],
    )
    @pytest.mark.parametrize("use_traces", [True, False])
    def test_ne_case_never_enters(self, env, kind, payload, baseline_payload, use_traces):
        adapter, result = self._eval(env, kind, payload, baseline_payload)
        assert result.outputs[1]["evaluated"] is False
        batch = result
        if not use_traces:
            batch = EvaluationBatch(outputs=result.outputs, scores=result.scores, trajectories=None)

        dataset = adapter.make_reflective_dataset(
            {"system_prompt": "cand"}, batch, ["system_prompt"]
        )["system_prompt"]

        text = str(dataset)
        assert "FALLA" not in text
        # los casos sanos con score perfecto no son negativos
        assert not [r for r in dataset if r.get("Type", "negative_example") == "negative_example"]

    @pytest.mark.parametrize("kind", list(ADAPTERS))
    @pytest.mark.parametrize(
        ("payload", "key"),
        [(INPUT_FILTER, "entrada_candidato"), (LENGTH, "presupuesto_candidato")],
    )
    def test_candidate_failure_enters_as_negative_naming_the_cause(self, env, kind, payload, key):
        adapter, result = self._eval(env, kind, payload, None)
        assert result.outputs[1]["failure"]["clave"] == key

        dataset = adapter.make_reflective_dataset(
            {"system_prompt": "cand"}, result, ["system_prompt"]
        )["system_prompt"]

        negatives = [r for r in dataset if key in str(r)]
        assert len(negatives) == 1
        others = [r for r in dataset if r not in negatives]
        assert all(r.get("Type") == "positive_example" for r in others)

    def test_outputs_decide_when_trajectories_lack_the_flag(self, env):
        """D6: `make_reflective_dataset` decide por `outputs[i]["evaluated"]`."""
        adapter, result = self._eval(env, "classifier", OUTPUT_FILTER, None)
        trajectories = [
            {k: v for k, v in t.items() if k != "evaluated"} for t in result.trajectories
        ]
        batch = EvaluationBatch(
            outputs=result.outputs, scores=result.scores, trajectories=trajectories
        )

        dataset = adapter.make_reflective_dataset(
            {"system_prompt": "cand"}, batch, ["system_prompt"]
        )

        assert "FALLA" not in str(dataset)

    def test_rag_judge_failure_case_never_enters(self, env):
        def rule(system, user):
            if "evaluador" in system and "FALLA" in user:
                return LENGTH
            return _healthy_rag_reply(system, "Paris")

        # La respuesta de la tarea al caso FALLA contiene el texto para que el juez lo vea
        def rule_task(system, user):
            if system == "cand" and "FALLA" in user:
                return "respuesta FALLA"
            return rule(system, user)

        Script(env, rule_task)
        adapter = _rag()
        result = adapter.evaluate(_rag_batch(3, ("c1",)), {"system_prompt": "cand"})
        assert result.outputs[1]["evaluated"] is False
        assert result.outputs[1]["failure"]["rol"] == "judge"

        dataset = adapter.make_reflective_dataset(
            {"system_prompt": "cand"}, result, ["system_prompt"]
        )["system_prompt"]

        assert "FALLA" not in str(dataset)

    def test_scored_zero_wrong_answer_still_enters(self, env):
        """Un caso evaluado con score bajo sigue entrando (la exclusion es solo de NE)."""
        Script(env, lambda s, u: "farewell")
        adapter = _classifier()
        result = adapter.evaluate(_classifier_batch(2), {"system_prompt": "cand"})

        dataset = adapter.make_reflective_dataset(
            {"system_prompt": "cand"}, result, ["system_prompt"]
        )["system_prompt"]

        assert len(dataset) == 2


# ==================== FR-010: `formato` por adapter ====================


class TestFormatFailures:
    def test_classifier_response_outside_valid_classes_is_format_score_zero(self, env, caplog):
        Script(env, lambda s, u: "no_se_que_decir" if "FALLA" in u else "greeting")
        adapter = _classifier()

        with caplog.at_level(logging.WARNING):
            result = adapter.evaluate(_classifier_batch(3, ("c1",)), {"system_prompt": "cand"})

        out = result.outputs[1]
        assert result.scores == [1.0, 0.0, 1.0]
        assert out["failure"]["clave"] == "formato"
        assert out["evaluated"] is True  # score 0 del candidato (tabla: formato = score 0)
        assert get_failure_tracker().snapshot()["counts"]["formato"]["task"] == 1
        assert len(project_warnings(caplog)) == 1

    @pytest.mark.parametrize("reply", ["GREETING", "  greeting\n", "Greeting"])
    def test_classifier_normalizes_before_deciding_format(self, env, reply):
        Script(env, lambda s, u: reply)
        adapter = _classifier()

        result = adapter.evaluate(_classifier_batch(1), {"system_prompt": "cand"})

        assert result.scores == [1.0]
        assert result.outputs[0]["failure"] is None
        assert get_failure_tracker().snapshot()["counts"] == {}

    @pytest.mark.parametrize("reply", ["no hay json aqui", "[1, 2, 3]", '{"name": "Ana"'])
    def test_extractor_unparseable_json_is_format_score_zero(self, env, reply):
        Script(env, lambda s, u: reply if "FALLA" in u else '{"name": "Ana"}')
        adapter = _extractor()

        result = adapter.evaluate(_extractor_batch(3, ("c1",)), {"system_prompt": "cand"})

        assert result.scores == [1.0, 0.0, 1.0]
        assert result.outputs[1]["failure"]["clave"] == "formato"
        assert result.outputs[1]["evaluated"] is True

    @pytest.mark.parametrize(
        "reply", ['{"name": "Ana"}', 'Aqui esta: {"name": "Ana"} listo', '{"name": "Ana", "x": 1}']
    )
    def test_extractor_parseable_json_is_not_a_format_failure(self, env, reply):
        Script(env, lambda s, u: reply)
        adapter = _extractor()

        result = adapter.evaluate(_extractor_batch(1), {"system_prompt": "cand"})

        assert result.scores == [1.0]
        assert result.outputs[0]["failure"] is None

    def test_extractor_empty_json_object_is_valid_and_scores_by_fields(self, env):
        Script(env, lambda s, u: "{}")
        adapter = _extractor()

        result = adapter.evaluate(_extractor_batch(1), {"system_prompt": "cand"})

        assert result.scores == [0.0]
        assert result.outputs[0]["failure"] is None

    @pytest.mark.parametrize("kind", ["classifier", "extractor"])
    def test_format_failure_enters_reflective_dataset_naming_the_cause(self, env, kind):
        bad = "no_se_que_decir" if kind == "classifier" else "texto sin json"
        make, make_batch, ok = ADAPTERS[kind]
        Script(env, lambda s, u: bad if "FALLA" in u else ok)
        adapter, batch = make(), make_batch(3, ("c1",))
        result = adapter.evaluate(batch, {"system_prompt": "cand"}, capture_traces=True)

        dataset = adapter.make_reflective_dataset(
            {"system_prompt": "cand"}, result, ["system_prompt"]
        )["system_prompt"]

        negatives = [r for r in dataset if "FALLA" in str(r)]
        assert len(negatives) == 1
        assert "formato" in str(negatives[0])

    @pytest.mark.parametrize("kind", ["sql", "rag"])
    def test_free_text_adapters_have_no_format_failures(self, env, kind):
        make, make_batch, _ = ADAPTERS[kind]
        free_text = "texto libre cualquiera"
        judge_reply = '{"puntaje": 0.5, "razon": "x"}'
        Script(env, lambda s, u: judge_reply if "evaluador" in s else free_text)
        adapter = make()

        adapter.evaluate(make_batch(2), {"system_prompt": "cand"})

        assert "formato" not in get_failure_tracker().snapshot()["counts"]


# ==================== Abort y excepciones de programacion ====================


class TestAbortAndProgrammingErrors:
    @pytest.mark.parametrize("kind", list(ADAPTERS))
    def test_run_aborted_propagates_from_every_adapter(self, env, kind):
        make, make_batch, _ = ADAPTERS[kind]
        completion = MagicMock(return_value=make_completion_response("x"))
        env.setattr("litellm.completion", completion)
        get_failure_tracker().abort(
            __import__("shared.llm", fromlist=["LLMFailure"]).LLMFailure(
                __import__("shared.llm", fromlist=["FailureClass"]).FailureClass.configuracion,
                "task",
                "AuthenticationError",
            ),
            "test",
        )

        with pytest.raises(RunAborted):
            make().evaluate(make_batch(2), {"system_prompt": "cand"})

        assert completion.call_count == 0

    @pytest.mark.parametrize("kind", list(ADAPTERS))
    def test_non_llm_exceptions_are_not_swallowed(self, env, kind):
        """Un error de programacion no se descarta ni puntua 0 (D6)."""
        make, make_batch, _ = ADAPTERS[kind]
        adapter = make()
        env.setattr(adapter, "_task_call", MagicMock(side_effect=KeyError("bug")))

        with pytest.raises(KeyError):
            adapter.evaluate(make_batch(2), {"system_prompt": "cand"})

    def test_all_ne_batch_does_not_raise_a_runtime_error(self, env):
        """Un lote todo NE no es "todos fallaron": lo resuelven 4a y los umbrales."""
        get_failure_tracker().configure(thresholds={"filtro_salida": {"task": 1.0}})
        Script(env, lambda s, u: OUTPUT_FILTER)
        adapter = _classifier()

        result = adapter.evaluate(_classifier_batch(3), {"system_prompt": "cand"})

        assert len(result.outputs) == 3
        assert all(o["evaluated"] is False for o in result.outputs)


# ==================== El orquestador fija el baseline ====================


class TestOrchestratorSetsBaseline:
    def test_run_calls_set_baseline_after_load_prompt(self, env, tmp_path, monkeypatch):
        from gepa_standalone import universal_optimizer as uo

        optimizer = uo.UniversalOptimizer(config_path=None)
        captured = {}

        env.setattr(uo, "Config", MagicMock())
        env.setattr(uo, "MetadataManager", MagicMock())
        env.setattr(uo, "get_paths", MagicMock())
        env.setattr(uo, "print_summary", MagicMock())
        env.setattr(optimizer, "run_wizard", lambda: {"adapter": {"type": "classifier"}})
        env.setattr(optimizer, "validate_config", lambda: None)
        env.setattr(optimizer, "build_llm_configs", lambda: None)
        env.setattr(optimizer, "validate_llm_connections", lambda: None)
        env.setattr(optimizer, "load_data", lambda: None)
        env.setattr(
            optimizer,
            "initialize_adapter",
            lambda: setattr(optimizer, "adapter", SimpleClassifierAdapter(["greeting"])),
        )
        env.setattr(optimizer, "load_prompt", lambda: {"system_prompt": "PROMPT BASE"})

        def pipeline(initial_prompt, verbose=False):
            captured["baseline"] = optimizer.adapter._baseline_prompt
            captured["initial"] = initial_prompt
            optimizer._summary_metrics = {}
            optimizer._summary_config = {}
            optimizer._summary_delta = None

        env.setattr(optimizer, "execute_gepa_pipeline", pipeline)
        env.setattr(optimizer, "save_results", lambda: tmp_path)

        optimizer.run()

        assert captured["baseline"] == "PROMPT BASE"
        assert captured["initial"] == {"system_prompt": "PROMPT BASE"}

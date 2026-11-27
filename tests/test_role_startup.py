"""
SPEC-106 subfase 2b: validacion al arrancar solo de los roles usados (FR-005, FR-007, D6).

- SC-005: una credencial invalida en tarea o profesor, en ambos subproyectos, sale como
  `LLMConnectionError` con el rol y su variable, antes de la primera llamada de
  optimizacion y sin `run.json`.
- La validacion local de todos los roles va antes de la primera sonda: un error local
  del profesor sale sin ninguna llamada de red (tampoco la de la tarea).
- `baseline_only.py` usa solo la tarea: un profesor mal configurado no falla.
- El arranque imprime `rol | proveedor | modelo | host` por rol, sin credencial.

Sin red: `litellm.completion` se simula con respuestas reales (`make_completion_response`)
y excepciones tipadas de LiteLLM, a traves del punto de llamada comun.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import litellm
import pytest

from dspy_gepa_poc.reflexio_declarativa import ReflexioDeclarativa
from gepa_standalone.universal_optimizer import UniversalOptimizer
from shared.llm import LLMConfig
from shared.llm.errors import LLMConnectionError
from tests.conftest import make_completion_response, patch_litellm_completion

TASK_KEY = "azure-task-key-VALUE"
REFLECTION_KEY = "anthropic-reflection-key-VALUE"
BAD = "bad-key-VALUE"

_ENV_VARS = (
    "LLM_MODEL_TASK",
    "LLM_MODEL_REFLECTION",
    "LLM_MODEL_JUDGE",
    "LLM_API_KEY",
    "LLM_API_BASE",
    "LLM_API_VERSION",
    "LLM_API_KEY_TASK",
    "LLM_API_BASE_TASK",
    "LLM_API_KEY_REFLECTION",
    "LLM_API_BASE_REFLECTION",
    "LLM_ENV_FILE",
    "LLM_CACHE",
)


@pytest.fixture(autouse=True)
def cross_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Escenario 1 de la spec: tarea Azure con globales, profesor Claude con su clave."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_MODEL_TASK", "azure/gpt-4.1-mini")
    monkeypatch.setenv("LLM_API_KEY", TASK_KEY)
    monkeypatch.setenv("LLM_API_BASE", "https://fake.openai.azure.com")
    monkeypatch.setenv("LLM_MODEL_REFLECTION", "anthropic/claude-sonnet-5-5")
    monkeypatch.setenv("LLM_API_KEY_REFLECTION", REFLECTION_KEY)
    monkeypatch.setenv("LLM_CACHE", "false")


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """
    `litellm.completion` simulado: responde bien salvo con una credencial `BAD`, que
    falla como un 401 real. Devuelve la lista de llamadas (los kwargs de cada una).
    """
    calls: list[dict] = []

    def fake(request, num_retries):
        calls.append(request)
        if request.get("api_key") == BAD:
            raise litellm.AuthenticationError(
                message="invalid credentials",
                llm_provider=request["model"].split("/")[0],
                model=request["model"],
            )
        return make_completion_response(content="OK", model=request["model"])

    patch_litellm_completion(monkeypatch, fake)
    return calls


def _gepa() -> UniversalOptimizer:
    opt = UniversalOptimizer()
    opt.config = {"models": {}}
    opt.build_llm_configs()
    return opt


@pytest.fixture
def dspy_orchestrator(monkeypatch: pytest.MonkeyPatch) -> ReflexioDeclarativa:
    monkeypatch.setattr("dspy_gepa_poc.reflexio_declarativa.configure_dspy", lambda lm: None)
    orchestrator = ReflexioDeclarativa.__new__(ReflexioDeclarativa)
    orchestrator.config = SimpleNamespace(raw_config={})
    return orchestrator


def _assert_only_probes(calls: list[dict], expected: int) -> None:
    """
    Solo hubo sondas: la cantidad esperada, todas con el mismo mensaje de sonda y
    `max_tokens` de sonda (5, o 16000 si el rol tiene razonamiento por defecto).
    """
    assert len(calls) == expected
    assert len({repr(c["messages"]) for c in calls}) == 1
    assert all(c["max_tokens"] in (5, 16000) for c in calls)


# ==================== SC-005: credencial invalida por rol ====================


class TestInvalidCredentialByRole:
    @pytest.mark.parametrize(
        ("role", "bad_var", "expected_probes"),
        [("task", "LLM_API_KEY", 1), ("reflection", "LLM_API_KEY_REFLECTION", 2)],
    )
    def test_gepa_fails_before_optimization_without_run_json(
        self,
        role: str,
        bad_var: str,
        expected_probes: int,
        provider: list[dict],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        monkeypatch.setenv(bad_var, BAD)
        opt = UniversalOptimizer()
        opt.config = {"case": {"name": "caso"}, "models": {}}
        optimization_steps = MagicMock()
        monkeypatch.setattr(opt, "validate_config", lambda: None)
        monkeypatch.setattr(opt, "run_wizard", lambda: opt.config)
        monkeypatch.setattr("gepa_standalone.universal_optimizer.Config", MagicMock())
        for name in ("load_data", "initialize_adapter", "load_prompt", "execute_gepa_pipeline"):
            monkeypatch.setattr(opt, name, optimization_steps)

        with pytest.raises(LLMConnectionError) as exc_info:
            opt.run()

        err = exc_info.value
        assert err.role == role
        assert err.failure_class == "configuracion"
        assert err.variable == bad_var
        optimization_steps.assert_not_called()
        _assert_only_probes(provider, expected_probes)
        assert list(tmp_path.rglob("run.json")) == []

    @pytest.mark.parametrize(
        ("role", "bad_var", "expected_probes"),
        [("task", "LLM_API_KEY", 1), ("reflection", "LLM_API_KEY_REFLECTION", 2)],
    )
    def test_dspy_fails_before_optimization_without_run_json(
        self,
        role: str,
        bad_var: str,
        expected_probes: int,
        provider: list[dict],
        monkeypatch: pytest.MonkeyPatch,
        dspy_orchestrator: ReflexioDeclarativa,
        tmp_path,
    ) -> None:
        monkeypatch.setenv(bad_var, BAD)
        steps = MagicMock()
        for name in ("load_data", "create_module_and_metric", "save_aborted_run"):
            monkeypatch.setattr(dspy_orchestrator, name, steps)
        dspy_orchestrator.config = SimpleNamespace(
            raw_config={"case": {"name": "caso"}}, dataset_path="x.csv"
        )
        monkeypatch.setattr(
            ReflexioDeclarativa,
            "_run_pipeline",
            lambda self: (self.setup_models(), self.load_data()),
        )

        with pytest.raises(LLMConnectionError) as exc_info:
            dspy_orchestrator.run()

        err = exc_info.value
        assert err.role == role
        assert err.failure_class == "configuracion"
        assert err.variable == bad_var
        steps.assert_not_called()
        _assert_only_probes(provider, expected_probes)
        assert list(tmp_path.rglob("run.json")) == []


# ==================== Validacion local antes de la primera sonda ====================


class TestLocalValidationBeforeFirstProbe:
    def test_gepa_reflection_without_credential_leaves_without_any_call(
        self, provider: list[dict], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LLM_API_KEY_REFLECTION")
        opt = _gepa()

        with pytest.raises(LLMConnectionError) as exc_info:
            opt.validate_llm_connections()

        err = exc_info.value
        assert err.role == "reflection"
        assert err.variable == "LLM_API_KEY_REFLECTION"
        assert provider == []

    def test_dspy_reflection_without_credential_leaves_without_any_call(
        self,
        provider: list[dict],
        monkeypatch: pytest.MonkeyPatch,
        dspy_orchestrator: ReflexioDeclarativa,
    ) -> None:
        monkeypatch.delenv("LLM_API_KEY_REFLECTION")

        with pytest.raises(LLMConnectionError) as exc_info:
            dspy_orchestrator.setup_models()

        assert exc_info.value.role == "reflection"
        assert provider == []

    def test_gepa_validates_the_judge_when_the_run_has_one(self, provider: list[dict]) -> None:
        opt = _gepa()
        opt.judge_config = LLMConfig(model="anthropic/claude-sonnet-5-5", role="judge")

        with pytest.raises(LLMConnectionError) as exc_info:
            opt.validate_llm_connections()

        assert exc_info.value.role == "judge"
        assert provider == []

    def test_gepa_without_judge_probes_only_task_and_reflection(self, provider: list[dict]) -> None:
        _gepa().validate_llm_connections()

        _assert_only_probes(provider, 2)


# ==================== baseline_only usa solo la tarea (escenario 10) ====================


class TestBaselineOnlyUsesOnlyTask:
    def test_misconfigured_reflection_does_not_fail(
        self,
        provider: list[dict],
        monkeypatch: pytest.MonkeyPatch,
        dspy_orchestrator: ReflexioDeclarativa,
    ) -> None:
        monkeypatch.delenv("LLM_API_KEY_REFLECTION")
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "")

        dspy_orchestrator.setup_models(roles=("task",))

        assert dspy_orchestrator.reflection_config is None
        assert dspy_orchestrator.reflection_lm is None
        assert dspy_orchestrator.task_config.role == "task"
        _assert_only_probes(provider, 1)
        assert provider[0]["model"] == "azure/gpt-4.1-mini"

    def test_script_asks_for_the_task_role_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dspy_gepa_poc.scripts import baseline_only

        stop = RuntimeError("paso por setup_models")
        orchestrator = MagicMock()
        orchestrator.setup_models.side_effect = stop
        monkeypatch.setattr(baseline_only, "ReflexioDeclarativa", lambda path: orchestrator)

        with pytest.raises(RuntimeError, match="paso por setup_models"):
            baseline_only.run_baseline("caso.yaml")

        orchestrator.setup_models.assert_called_once_with(roles=("task",))

    def test_abort_message_tolerates_a_missing_reflection(
        self, dspy_orchestrator: ReflexioDeclarativa
    ) -> None:
        from shared.llm import FailureClass, LLMFailure, RunAborted

        dspy_orchestrator.reflection_config = None
        exc = RunAborted(LLMFailure(FailureClass.presupuesto, "reflection", "length"), "x", 1, 2)

        assert isinstance(dspy_orchestrator.abort_message(exc), str)


# ==================== FR-007: impresion de rol, proveedor, modelo y host ====================


class TestStartupPrintsEndpointPerRole:
    EXPECTED = (
        "task | azure | azure/gpt-4.1-mini | fake.openai.azure.com",
        "reflection | anthropic | anthropic/claude-sonnet-5-5 | api.anthropic.com",
    )

    def _assert_summary(self, text: str) -> None:
        for line in self.EXPECTED:
            assert line in text
        assert TASK_KEY not in text
        assert REFLECTION_KEY not in text

    def test_gepa(self, provider: list[dict], capsys: pytest.CaptureFixture[str]) -> None:
        _gepa().validate_llm_connections()

        out = capsys.readouterr()
        self._assert_summary(out.out + out.err)

    def test_dspy(
        self,
        provider: list[dict],
        capsys: pytest.CaptureFixture[str],
        dspy_orchestrator: ReflexioDeclarativa,
    ) -> None:
        dspy_orchestrator.setup_models()

        out = capsys.readouterr()
        self._assert_summary(out.out + out.err)

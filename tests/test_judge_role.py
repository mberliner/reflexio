"""
SPEC-106 subfase 3b: el juez como rol (FR-004, FR-005, D8).

- Escenarios 7 a 9: sin `LLM_MODEL_JUDGE` el juez usa la configuracion del profesor;
  con `LLM_MODEL_JUDGE` se valida en el Step 2 y llama a su propio endpoint; fuera de
  RAG no se valida ni se registra.
- SC-005 para el juez: credencial invalida o ausente, antes de la primera llamada de
  optimizacion, nombrando el rol y su variable, sin `run.json`.
- `[WARN]` con `LLM_*_JUDGE` sin `LLM_MODEL_JUDGE`; overrides del YAML aplicados al
  juez; el adapter no lee el entorno para el juez.

Sin red: `litellm.completion` se simula con respuestas reales (`make_completion_response`)
y excepciones tipadas de LiteLLM, a traves del punto de llamada comun.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import litellm
import pytest

from gepa_standalone.adapters.simple_rag_adapter import SimpleRAGAdapter
from gepa_standalone.universal_optimizer import UniversalOptimizer
from shared.llm import LLMConfig
from shared.llm.errors import LLMConnectionError
from shared.llm.usage import get_tracker
from shared.logging.metadata import collect_model_info
from tests.conftest import make_completion_response, patch_litellm_completion

TASK_KEY = "azure-task-key-VALUE"
REFLECTION_KEY = "anthropic-reflection-key-VALUE"
JUDGE_KEY = "openai-judge-key-VALUE"
BAD = "bad-key-VALUE"
CASE = {"case_id": "c0", "question": "q", "context": "ctx", "answer": "Paris"}

_ENV_VARS = (
    "LLM_MODEL_TASK",
    "LLM_MODEL_REFLECTION",
    "LLM_MODEL_JUDGE",
    "LLM_API_KEY",
    "LLM_API_BASE",
    "LLM_API_VERSION",
    "LLM_API_KEY_TASK",
    "LLM_API_KEY_REFLECTION",
    "LLM_API_KEY_JUDGE",
    "LLM_API_BASE_JUDGE",
    "LLM_API_VERSION_JUDGE",
    "LLM_EFFORT_JUDGE",
    "LLM_THINKING_JUDGE",
    "LLM_ENV_FILE",
    "LLM_CACHE",
)


@pytest.fixture(autouse=True)
def cross_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tarea Azure con globales, profesor Claude con su clave. Sin variables del juez."""
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
    `litellm.completion` simulado: el juez (mensaje de sistema "evaluador") responde un
    JSON de puntaje; el resto, `OK`. Una credencial `BAD` falla como un 401 real.
    Devuelve la lista de llamadas (los kwargs de cada una).
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
        system = request["messages"][0]["content"]
        content = json.dumps({"puntaje": 1.0, "razon": "ok"}) if "evaluador" in system else "OK"
        return make_completion_response(content=content, model=request["model"])

    patch_litellm_completion(monkeypatch, fake)
    return calls


def _optimizer(adapter_type: str = "rag", **models) -> UniversalOptimizer:
    opt = UniversalOptimizer()
    opt.config = {"case": {"name": "caso"}, "adapter": {"type": adapter_type}, "models": models}
    opt.build_llm_configs()
    return opt


def _judge_calls(calls: list[dict]) -> list[dict]:
    return [c for c in calls if "evaluador" in c["messages"][0]["content"]]


def _evaluate(opt: UniversalOptimizer) -> None:
    """Una evaluacion del juez a traves del adapter RAG inyectado, como la corrida."""
    opt.initialize_adapter()
    score, _ = opt.adapter._evaluate_with_judge("q", "Paris", "Paris")
    assert score == 1.0


# ==================== Escenario 7: sin LLM_MODEL_JUDGE ====================


class TestJudgeWithoutOwnModel:
    def test_judge_is_the_resolved_teacher_config(self) -> None:
        opt = _optimizer(temperature=0.3, cache=True)

        judge = opt.judge_config
        assert judge.role == "judge"
        assert judge is not opt.reflection_config
        assert judge.model == opt.reflection_config.model == "anthropic/claude-sonnet-5-5"
        assert judge.api_key == REFLECTION_KEY
        assert judge.api_base == opt.reflection_config.api_base
        assert judge.temperature == opt.reflection_config.temperature == 0.3
        assert judge.effort == opt.reflection_config.effort
        assert judge.thinking == opt.reflection_config.thinking

    def test_judge_call_goes_to_the_teacher_endpoint_and_its_usage_to_the_judge_bucket(
        self, provider: list[dict]
    ) -> None:
        opt = _optimizer()

        _evaluate(opt)

        (call,) = _judge_calls(provider)
        assert call["model"] == "anthropic/claude-sonnet-5-5"
        assert call["api_key"] == REFLECTION_KEY
        usage = get_tracker().snapshot()
        assert usage["judge"]["calls"] == 1
        assert usage["reflection"]["calls"] == 0

    def test_run_json_models_report_the_judge_equal_to_the_teacher(self) -> None:
        opt = _optimizer()
        opt.initialize_adapter()

        models = opt._run_models()

        assert models["judge"]["model"] == models["reflection"]["model"]

    def test_judge_vars_without_judge_model_warn_and_are_ignored(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_API_KEY_JUDGE", JUDGE_KEY)
        monkeypatch.setenv("LLM_EFFORT_JUDGE", "high")

        with caplog.at_level(logging.WARNING, logger="shared.llm.config"):
            opt = _optimizer()

        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        warn = next(m for m in messages if "[WARN]" in m)
        assert "LLM_API_KEY_JUDGE" in warn and "LLM_EFFORT_JUDGE" in warn
        assert "LLM_MODEL_JUDGE" in warn
        assert JUDGE_KEY not in warn
        assert opt.judge_config.api_key == REFLECTION_KEY
        assert opt.judge_config.effort == opt.reflection_config.effort

    def test_inherited_judge_is_not_probed_apart(
        self,
        provider: list[dict],
        caplog: pytest.LogCaptureFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        opt = _optimizer()

        with caplog.at_level(logging.INFO):
            opt.validate_llm_connections()

        # Una sonda por endpoint: tarea y profesor; el juez comparte el del profesor.
        assert [c["model"] for c in provider] == [
            "azure/gpt-4.1-mini",
            "anthropic/claude-sonnet-5-5",
        ]
        out = capsys.readouterr()
        text = out.out + out.err + caplog.text
        assert "judge | anthropic | anthropic/claude-sonnet-5-5" in text
        assert "conexion del profesor" in text

    def test_inherited_judge_local_errors_name_the_teacher_variables(self) -> None:
        opt = _optimizer()
        judge = opt.judge_config
        judge.api_key = None

        with pytest.raises(LLMConnectionError) as exc_info:
            judge.validate()

        err = exc_info.value
        assert err.role == "judge"
        assert "LLM_API_KEY_REFLECTION" in err.variable
        assert "JUDGE" not in err.variable
        assert all("JUDGE" not in s for s in err.suggestions)

        judge.api_key = REFLECTION_KEY
        judge.model = ""
        with pytest.raises(LLMConnectionError) as exc_info:
            judge.validate()
        assert exc_info.value.variable == "LLM_MODEL_REFLECTION"

    def test_inherited_judge_param_errors_name_the_teacher_variables(self) -> None:
        from shared.llm.errors import LLMConfigError

        opt = _optimizer()
        judge = opt.judge_config
        judge.effort = "bogus"

        with pytest.raises(LLMConfigError) as exc_info:
            judge.validate()

        assert "LLM_EFFORT_REFLECTION" in str(exc_info.value)
        assert "LLM_EFFORT_JUDGE" not in str(exc_info.value)

    def test_inherited_judge_source_variables_are_the_teacher_ones(self) -> None:
        opt = _optimizer()
        judge = opt.judge_config
        judge.env_sources = {}

        # El profesor Anthropic no hereda los globales (FR-003): el juez, tampoco.
        assert judge._source_variable("api_key", "API_KEY") == "LLM_API_KEY_REFLECTION"
        assert judge._source_variable("model", "MODEL") == "LLM_MODEL_REFLECTION"

    def test_inherited_judge_with_yaml_override_is_still_validated(
        self, provider: list[dict]
    ) -> None:
        opt = _optimizer()
        opt.judge_config.api_key = None

        with pytest.raises(LLMConnectionError) as exc_info:
            opt.validate_llm_connections()

        assert exc_info.value.role == "judge"
        assert provider == []

    def test_no_warning_without_judge_vars(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="shared.llm.config"):
            _optimizer()

        assert not [r for r in caplog.records if "LLM_MODEL_JUDGE" in r.getMessage()]


# ==================== Escenario 8: con LLM_MODEL_JUDGE ====================


@pytest.fixture
def own_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL_JUDGE", "openai/gpt-4.1")
    monkeypatch.setenv("LLM_API_KEY_JUDGE", JUDGE_KEY)
    monkeypatch.setenv("LLM_API_BASE_JUDGE", "https://judge.interno/v1")


@pytest.mark.usefixtures("own_judge")
class TestJudgeWithOwnModel:
    def test_judge_resolves_as_one_more_role(self) -> None:
        opt = _optimizer()

        judge = opt.judge_config
        assert judge.role == "judge"
        assert judge.model == "openai/gpt-4.1"
        assert judge.api_key == JUDGE_KEY
        assert judge.api_base == "https://judge.interno/v1"
        assert judge.env_sources["api_key"] == "LLM_API_KEY_JUDGE"

    def test_judge_is_validated_in_step_2_and_calls_its_own_endpoint(
        self, provider: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        opt = _optimizer()

        opt.validate_llm_connections()

        probes = [c for c in provider if c["model"] == "openai/gpt-4.1"]
        # Con LLM_MODEL_JUDGE el juez se sondea como un rol mas (tarea, profesor y juez).
        assert len(probes) == 1 and probes[0]["api_key"] == JUDGE_KEY
        assert len(provider) == 3
        out = capsys.readouterr()
        assert "judge | openai | openai/gpt-4.1 | judge.interno" in out.out + out.err
        assert JUDGE_KEY not in out.out + out.err

        provider.clear()
        _evaluate(opt)
        (call,) = _judge_calls(provider)
        assert call["model"] == "openai/gpt-4.1"
        assert call["api_key"] == JUDGE_KEY
        assert call["api_base"] == "https://judge.interno/v1"

    def test_judge_does_not_inherit_the_azure_globals(self) -> None:
        opt = _optimizer()

        assert opt.judge_config.api_version is None
        assert TASK_KEY not in repr(opt.judge_config.to_kwargs())

    def test_run_json_models_report_the_judge_model(self) -> None:
        opt = _optimizer()
        opt.initialize_adapter()

        models = opt._run_models()

        assert models["judge"]["model"] == "openai/gpt-4.1"
        assert models["reflection"]["model"] == "anthropic/claude-sonnet-5-5"


# ==================== Escenario 9: caso no RAG ====================


class TestJudgeOutsideRag:
    @pytest.mark.usefixtures("own_judge")
    def test_judge_is_not_built_validated_nor_registered(
        self, provider: list[dict], caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="gepa_standalone.universal_optimizer"):
            opt = _optimizer("classifier")

        assert opt.judge_config is None
        assert "LLM_MODEL_JUDGE ignorado" in caplog.text

        opt.validate_llm_connections()
        assert {c["model"] for c in provider} == {
            "azure/gpt-4.1-mini",
            "anthropic/claude-sonnet-5-5",
        }
        assert get_tracker().snapshot()["judge"]["calls"] == 0
        assert "judge" not in collect_model_info(opt.task_config, opt.reflection_config)

    def test_without_the_variable_nothing_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger="gepa_standalone.universal_optimizer"):
            opt = _optimizer("classifier")

        assert opt.judge_config is None
        assert "LLM_MODEL_JUDGE" not in caplog.text


# ==================== SC-005: credencial del juez ====================


@pytest.mark.usefixtures("own_judge")
class TestInvalidJudgeCredential:
    def test_bad_judge_key_fails_before_optimization_without_run_json(
        self, provider: list[dict], monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setenv("LLM_API_KEY_JUDGE", BAD)
        opt = UniversalOptimizer()
        opt.config = {"case": {"name": "caso"}, "adapter": {"type": "rag"}, "models": {}}
        optimization_steps = MagicMock()
        monkeypatch.setattr(opt, "validate_config", lambda: None)
        monkeypatch.setattr(opt, "run_wizard", lambda: opt.config)
        monkeypatch.setattr("gepa_standalone.universal_optimizer.Config", MagicMock())
        for name in ("load_data", "initialize_adapter", "load_prompt", "execute_gepa_pipeline"):
            monkeypatch.setattr(opt, name, optimization_steps)

        with pytest.raises(LLMConnectionError) as exc_info:
            opt.run()

        err = exc_info.value
        assert err.role == "judge"
        assert err.failure_class == "configuracion"
        assert err.variable == "LLM_API_KEY_JUDGE"
        optimization_steps.assert_not_called()
        assert len(provider) == 3
        assert list(tmp_path.rglob("run.json")) == []

    def test_missing_judge_key_leaves_without_any_call(
        self, provider: list[dict], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LLM_API_KEY_JUDGE")
        monkeypatch.setenv("LLM_MODEL_JUDGE", "anthropic/claude-haiku-4-5")
        opt = _optimizer()

        with pytest.raises(LLMConnectionError) as exc_info:
            opt.validate_llm_connections()

        err = exc_info.value
        assert err.role == "judge"
        assert err.variable == "LLM_API_KEY_JUDGE"
        assert provider == []


# ==================== Overrides del YAML y adapter sin entorno ====================


class TestYamlOverridesAndInjection:
    @pytest.mark.parametrize("with_own_model", [False, True])
    def test_yaml_overrides_apply_to_the_judge(
        self, with_own_model: bool, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        if with_own_model:
            monkeypatch.setenv("LLM_MODEL_JUDGE", "openai/gpt-4.1")
            monkeypatch.setenv("LLM_API_KEY_JUDGE", JUDGE_KEY)

        opt = _optimizer(temperature=0.2, max_tokens=777, cache=True)

        assert opt.judge_config.temperature == 0.2
        assert opt.judge_config.max_tokens == 777
        assert opt.judge_config.cache is True

    @pytest.mark.parametrize("with_own_model", [False, True])
    def test_judge_does_not_take_the_reflection_default_max_tokens(
        self, with_own_model: bool, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        if with_own_model:
            monkeypatch.setenv("LLM_MODEL_JUDGE", "openai/gpt-4.1")
            monkeypatch.setenv("LLM_API_KEY_JUDGE", JUDGE_KEY)

        opt = _optimizer()

        assert opt.reflection_config.max_tokens == 2000
        assert opt.judge_config.max_tokens != 2000

    def test_adapter_uses_the_injected_config_and_does_not_read_the_environment(
        self, provider: list[dict], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        injected = LLMConfig(
            model="openai/injected-judge", api_key="injected-key", role="judge", temperature=0.0
        )
        adapter = SimpleRAGAdapter(injected)
        monkeypatch.setenv("LLM_MODEL_JUDGE", "openai/from-env")
        monkeypatch.setenv("LLM_API_KEY_JUDGE", "key-from-env")

        score, _ = adapter._evaluate_with_judge("q", "Paris", "Paris")

        assert score == 1.0
        (call,) = _judge_calls(provider)
        assert call["model"] == "openai/injected-judge"
        assert call["api_key"] == "injected-key"
        assert adapter.judge_config is injected
        assert adapter.judge_model == "openai/injected-judge"

    def test_adapter_requires_the_judge_config(self) -> None:
        with pytest.raises(TypeError):
            SimpleRAGAdapter()  # type: ignore[call-arg]

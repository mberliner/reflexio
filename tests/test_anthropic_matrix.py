"""
Tests sin red de SPEC-103 (proveedor Anthropic): matriz de soporte, combinaciones
invalidas, parseo de variables y regresion Azure/OpenAI.

Los pedidos HTTP se interceptan con las fixtures `capture_anthropic_post` y
`capture_azure_post` (tests/conftest.py); nunca se llama a la API.

Los tests de la fase RED estan marcados `xfail(strict=True)` con la subfase que
los cierra (plan: docs/plans/PLAN_SPEC-103_proveedor_anthropic.md). Los de
SC-006 y los que ya se cumplen hoy no llevan marca: son la guardia.

Cobertura SC-001: un caso por conducta distinta, no el producto cartesiano. Los
cuatro caminos comparten `apply_constraints` y los alias de una misma fila se
comportan igual (la resolucion de alias y snapshot se prueba aparte).
"""

import logging

import litellm
import pytest

from shared.llm.config import LLMConfig

EXPECTED_ANTHROPIC_VERSION_HEADER = "2023-06-01"
REQUESTED_MAX_TOKENS = 100
REQUESTED_TEMPERATURE = 0.1
ALL_EFFORTS = ("low", "medium", "high", "xhigh", "max")

# (alias, envia temperature, efforts aceptados o None, razonamiento por defecto)
# Una fila por fila de la matriz de la spec.
MATRIX = [
    ("claude-haiku-4-5", True, None, "off"),
    ("claude-opus-4-5", True, ("low", "medium", "high"), "off"),
    ("claude-sonnet-4-6", True, ("low", "medium", "high", "max"), "off"),
    ("claude-opus-4-6", True, ("low", "medium", "high", "max"), "off"),
    ("claude-opus-4-7", False, ALL_EFFORTS, "off"),
    ("claude-sonnet-5", False, ALL_EFFORTS, "adaptive"),
    ("claude-opus-5", False, ALL_EFFORTS, "adaptive"),
    ("claude-haiku-5-5", False, ALL_EFFORTS, "adaptive"),
    ("claude-sonnet-5-5", False, ALL_EFFORTS, "adaptive"),
    ("claude-opus-5-5", False, ALL_EFFORTS, "adaptive"),
    ("claude-fable-5", False, ALL_EFFORTS, "always"),
]

# Todos los alias de la matriz (alias compartidos de una misma fila incluidos).
ALL_ALIASES = [row[0] for row in MATRIX] + [
    "claude-opus-4-8",
    "claude-fable-5-1",
    "claude-fable-5-2",
]

# (alias, mecanismo esperado en el cuerpo: dict de thinking o None si es no-op)
OFF_CASES = [
    ("claude-sonnet-4-6", None),
    ("claude-sonnet-5", {"type": "disabled"}),
    ("claude-haiku-5-5", {"type": "disabled"}),
    ("claude-sonnet-5-5", {"type": "between_tools"}),
]


def _cfg(alias: str, **kwargs) -> LLMConfig:
    """Config Anthropic con la API nueva (role/effort/thinking explicitos)."""
    params = {
        "model": f"anthropic/{alias}",
        "api_key": "x",
        "temperature": REQUESTED_TEMPERATURE,
        "max_tokens": REQUESTED_MAX_TOKENS,
        "role": "task",
        "effort": None,
        "thinking": "default",
    }
    params.update(kwargs)
    return LLMConfig(**params)


def _config_error():
    """LLMConfigError (D5), resuelta tarde para no romper la coleccion en RED."""
    import shared.llm.errors as errors

    return errors.LLMConfigError


@pytest.fixture(autouse=True)
def _no_usage_and_drop_params(monkeypatch):
    monkeypatch.setattr(litellm, "drop_params", False)
    monkeypatch.setattr("shared.llm.usage.record_usage", lambda *a, **kw: None)


@pytest.fixture
def anthropic_env(monkeypatch):
    """Entorno minimo para from_env/call_llm sin `.env` ni variables heredadas."""
    for var in (
        "LLM_API_BASE",
        "LLM_API_VERSION",
        "LLM_CACHE",
        "LLM_EFFORT_TASK",
        "LLM_EFFORT_REFLECTION",
        "LLM_THINKING_TASK",
        "LLM_THINKING_REFLECTION",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "x")

    def _set(task: str, reflection: str | None = None) -> None:
        monkeypatch.setenv("LLM_MODEL_TASK", f"anthropic/{task}")
        monkeypatch.setenv("LLM_MODEL_REFLECTION", f"anthropic/{reflection or task}")

    return _set


def _assert_common_wire(captured: dict, alias: str) -> None:
    body = captured["body"]
    assert body["model"] == alias
    assert "api_base" not in body
    assert "api_version" not in body
    assert captured["headers"].get("anthropic-version") == EXPECTED_ANTHROPIC_VERSION_HEADER


def _assert_default_body(body: dict, sends_temp: bool, efforts, reasoning: str) -> None:
    if sends_temp:
        assert body["temperature"] == REQUESTED_TEMPERATURE
    else:
        assert "temperature" not in body
    if efforts is None:
        assert "output_config" not in body
    else:
        assert body["output_config"] == {"effort": "medium"}
    assert "thinking" not in body
    if reasoning == "off":
        assert body["max_tokens"] == REQUESTED_MAX_TOKENS
    else:
        assert body["max_tokens"] >= 16000


# ==================== SC-001: get_lm_function (una fila por conducta) ====================


class TestMatrixGetLmFunction:
    @pytest.mark.parametrize(("alias", "sends_temp", "efforts", "reasoning"), MATRIX)
    def test_default_values(self, capture_anthropic_post, alias, sends_temp, efforts, reasoning):
        assert _cfg(alias).get_lm_function(role="task")("hi") == "ok"

        _assert_common_wire(capture_anthropic_post, alias)
        _assert_default_body(capture_anthropic_post["body"], sends_temp, efforts, reasoning)

    @pytest.mark.parametrize(
        ("alias", "efforts"), [(row[0], row[2]) for row in MATRIX if row[2] is not None]
    )
    def test_explicit_effort_uses_output_config_without_thinking(
        self, capture_anthropic_post, alias, efforts
    ):
        effort = efforts[-1]
        _cfg(alias, effort=effort).get_lm_function(role="task")("hi")

        body = capture_anthropic_post["body"]
        assert body["output_config"] == {"effort": effort}
        assert "thinking" not in body
        assert "reasoning_effort" not in body

    @pytest.mark.parametrize(("alias", "expected_thinking"), OFF_CASES)
    def test_thinking_off_per_mechanism(self, capture_anthropic_post, alias, expected_thinking):
        _cfg(alias, thinking="off").get_lm_function(role="task")("hi")

        body = capture_anthropic_post["body"]
        if expected_thinking is None:
            assert "thinking" not in body
        else:
            assert body["thinking"] == expected_thinking
        assert body["max_tokens"] == REQUESTED_MAX_TOKENS

    def test_off_with_high_effort_allowed_where_cap_is_high(self, capture_anthropic_post):
        _cfg("claude-haiku-5-5", thinking="off", effort="high").get_lm_function(role="task")("hi")

        body = capture_anthropic_post["body"]
        assert body["thinking"] == {"type": "disabled"}
        assert body["output_config"] == {"effort": "high"}

    def test_azure_leftovers_never_sent(self, capture_anthropic_post, anthropic_env, monkeypatch):
        # D3: los globales no se heredan; por from_env no llegan a la config del rol.
        anthropic_env("claude-opus-5-5")
        monkeypatch.setenv("LLM_API_BASE", "https://x.openai.azure.com")
        monkeypatch.setenv("LLM_API_VERSION", "2024-02-15-preview")
        config = LLMConfig.from_env("task", load_env=False)
        config.get_lm_function(role="task")("hi")

        _assert_common_wire(capture_anthropic_post, "claude-opus-5-5")
        assert capture_anthropic_post["url"].startswith("https://api.anthropic.com")


# ==================== SC-001: call_llm y get_dspy_lm (2 filas) ====================


class TestMatrixCallLlm:
    @pytest.mark.parametrize(
        ("alias", "sends_temp", "efforts", "reasoning"),
        [row for row in MATRIX if row[0] in ("claude-sonnet-4-6", "claude-opus-5-5")],
    )
    def test_call_llm_overrides_then_constraints(
        self, capture_anthropic_post, anthropic_env, alias, sends_temp, efforts, reasoning
    ):
        from gepa_standalone.core.llm_factory import call_llm

        anthropic_env(alias)
        result = call_llm("hi", temperature=REQUESTED_TEMPERATURE, max_tokens=50)

        assert result == "ok"
        _assert_common_wire(capture_anthropic_post, alias)
        body = capture_anthropic_post["body"]
        assert ("temperature" in body) is sends_temp
        assert body["output_config"] == {"effort": "medium"}
        assert "thinking" not in body
        assert body["max_tokens"] == (50 if reasoning == "off" else 16000)

    def test_call_llm_reads_effort_from_env(
        self, capture_anthropic_post, anthropic_env, monkeypatch
    ):
        from gepa_standalone.core.llm_factory import call_llm

        anthropic_env("claude-opus-5-5")
        monkeypatch.setenv("LLM_EFFORT_TASK", " HIGH ")
        call_llm("hi")

        assert capture_anthropic_post["body"]["output_config"] == {"effort": "high"}


class TestMatrixGetDspyLm:
    @pytest.mark.parametrize(
        ("alias", "sends_temp", "efforts", "reasoning"),
        [row for row in MATRIX if row[0] in ("claude-sonnet-4-6", "claude-opus-5-5")],
    )
    def test_dspy_lm_without_drop_params(
        self, capture_anthropic_post, alias, sends_temp, efforts, reasoning
    ):
        lm = _cfg(alias).get_dspy_lm()
        assert litellm.drop_params is False

        lm("hi")

        _assert_common_wire(capture_anthropic_post, alias)
        body = capture_anthropic_post["body"]
        assert ("temperature" in body) is sends_temp
        assert body["output_config"] == {"effort": "medium"}
        assert "thinking" not in body
        assert body["max_tokens"] == (REQUESTED_MAX_TOKENS if reasoning == "off" else 16000)


class TestMatrixSimpleRagAdapter:
    def test_rag_task_and_judge_share_constraints(
        self, capture_anthropic_post, anthropic_env, monkeypatch
    ):
        from gepa_standalone.adapters.simple_rag_adapter import SimpleRAGAdapter

        anthropic_env("claude-sonnet-4-6", reflection="claude-opus-5-5")
        monkeypatch.setenv("LLM_EFFORT_REFLECTION", "high")
        adapter = SimpleRAGAdapter(temperature=REQUESTED_TEMPERATURE)
        messages = [{"role": "user", "content": "hi"}]

        adapter._complete(messages, max_tokens=400)
        task_body = capture_anthropic_post["body"]
        assert task_body["model"] == "claude-sonnet-4-6"
        assert task_body["temperature"] == REQUESTED_TEMPERATURE
        assert task_body["max_tokens"] == 400
        assert task_body["output_config"] == {"effort": "medium"}

        adapter._complete(messages, max_tokens=200, is_judge=True)
        judge_body = capture_anthropic_post["body"]
        assert judge_body["model"] == "claude-opus-5-5"
        assert "temperature" not in judge_body
        assert judge_body["max_tokens"] >= 16000
        assert judge_body["output_config"] == {"effort": "high"}


# ==================== validate_connection (FR-007) ====================


class TestValidateConnection:
    def test_probe_respects_reasoning_minimum(self, capture_anthropic_post):
        assert _cfg("claude-opus-5-5").validate_connection() is True

        body = capture_anthropic_post["body"]
        assert body["max_tokens"] >= 16000
        assert "temperature" not in body
        assert body["output_config"] == {"effort": "medium"}

    def test_probe_keeps_small_max_tokens_when_reasoning_off(self, capture_anthropic_post):
        assert _cfg("claude-haiku-5-5", thinking="off").validate_connection() is True

        body = capture_anthropic_post["body"]
        assert body["max_tokens"] == 5
        assert body["thinking"] == {"type": "disabled"}


# ==================== Resolucion de alias y snapshot (FR-001, D2) ====================


class TestStripSnapshotSuffix:
    def test_strips_only_eight_digit_suffix(self):
        from shared.llm.config import strip_snapshot_suffix

        assert strip_snapshot_suffix("claude-opus-5-5-20260514") == "claude-opus-5-5"
        assert strip_snapshot_suffix("claude-opus-5-5") == "claude-opus-5-5"
        assert strip_snapshot_suffix("claude-opus-5-5-2026") == "claude-opus-5-5-2026"
        assert strip_snapshot_suffix("gpt-4o-123456789") == "gpt-4o-123456789"


class TestResolveAnthropicFamily:
    @pytest.mark.parametrize("alias", ALL_ALIASES)
    def test_alias_snapshot_and_prefix_resolve_to_same_family(self, alias):
        from shared.llm.config import resolve_anthropic_family

        family = resolve_anthropic_family(f"anthropic/{alias}")
        assert family is not None
        assert resolve_anthropic_family(alias) is family
        assert resolve_anthropic_family(f"anthropic/{alias}-20260514") is family

    def test_no_partial_prefix_matching(self):
        from shared.llm.config import resolve_anthropic_family

        opus_5 = resolve_anthropic_family("anthropic/claude-opus-5")
        opus_5_5 = resolve_anthropic_family("anthropic/claude-opus-5-5")
        assert opus_5 is not None
        assert opus_5_5 is not None
        assert opus_5 is not opus_5_5
        assert resolve_anthropic_family("anthropic/claude-opus-5-5-preview") is None
        assert resolve_anthropic_family("anthropic/claude-opus-5-5-2026") is None

    @pytest.mark.parametrize(
        "model",
        ["anthropic/claude-sonnet-4-5", "anthropic/claude-future-9", "azure/gpt-4o", "gpt-4o"],
    )
    def test_ids_outside_matrix_resolve_to_none(self, model):
        from shared.llm.config import resolve_anthropic_family

        assert resolve_anthropic_family(model) is None

    def test_snapshot_gets_alias_constraints_without_warning(self, capture_anthropic_post, caplog):
        from shared.llm.config import resolve_anthropic_family

        model = "claude-sonnet-5-5-20260514"
        config = _cfg(model)
        with caplog.at_level(logging.WARNING):
            config.validate()
        config.get_lm_function(role="task")("hi")

        assert resolve_anthropic_family(config.model) is resolve_anthropic_family(
            "anthropic/claude-sonnet-5-5"
        )
        body = capture_anthropic_post["body"]
        assert body["model"] == model
        assert "temperature" not in body
        assert body["max_tokens"] >= 16000
        assert model not in caplog.text


# ==================== apply_constraints (D4) ====================


class TestApplyConstraints:
    def test_returns_new_dict_without_mutating_input(self):
        config = _cfg("claude-opus-5-5")
        original = {
            "model": config.model,
            "temperature": 0.9,
            "max_tokens": 50,
            "api_base": "https://x.openai.azure.com",
            "api_version": "2024-02-15-preview",
        }
        snapshot = dict(original)

        result = config.apply_constraints(original)

        assert original == snapshot
        assert result is not original
        assert "temperature" not in result
        assert result["api_base"] == "https://x.openai.azure.com"  # explicito: se conserva (D3)
        assert "api_version" not in result
        assert result["max_tokens"] == 16000
        assert result["output_config"] == {"effort": "medium"}

    def test_per_call_temperature_override_is_removed_when_not_sent(self):
        result = _cfg("claude-opus-4-7").apply_constraints(
            {"model": "anthropic/claude-opus-4-7", "temperature": 0.0, "max_tokens": 50}
        )

        assert "temperature" not in result

    def test_per_call_temperature_override_is_kept_when_sent(self):
        result = _cfg("claude-haiku-4-5").apply_constraints(
            {"model": "anthropic/claude-haiku-4-5", "temperature": 0.0, "max_tokens": 50}
        )

        assert result["temperature"] == 0.0
        assert result["max_tokens"] == 50
        assert "output_config" not in result

    def test_thinking_off_does_not_raise_max_tokens(self):
        result = _cfg("claude-sonnet-5-5", thinking="off").apply_constraints(
            {"model": "anthropic/claude-sonnet-5-5", "max_tokens": 50}
        )

        assert result["max_tokens"] == 50
        assert result["thinking"] == {"type": "between_tools"}


# ==================== Valores efectivos (D6) ====================


class TestEffectiveParams:
    def test_omitted_temperature_and_raised_max_tokens_are_reported(self):
        params = _cfg("claude-opus-5-5", max_tokens=400).effective_params()

        assert params["model"] == "anthropic/claude-opus-5-5"
        assert params["temperature"] is None
        assert params["temperature_omitted"] is True
        assert params["effort"] == "medium"
        assert params["max_tokens"] == 16000
        assert params["max_tokens_requested"] == 400

    def test_per_call_max_tokens_is_reported(self):
        params = _cfg("claude-haiku-4-5").effective_params(max_tokens=50)

        assert params["temperature"] == REQUESTED_TEMPERATURE
        assert params["temperature_omitted"] is False
        assert params["effort"] is None
        assert params["max_tokens"] == 50
        assert params["max_tokens_requested"] == 50


# ==================== SC-002 / FR-004 / FR-005 / FR-008: validacion ====================

INVALID_COMBINATIONS = [
    # (alias, effort, thinking, parametro que debe nombrar el mensaje)
    ("claude-opus-5-5", None, "off", "LLM_THINKING"),
    ("claude-fable-5", None, "off", "LLM_THINKING"),
    ("claude-fable-5-2", None, "off", "LLM_THINKING"),
    ("claude-opus-4-5", "xhigh", "default", "LLM_EFFORT"),
    ("claude-opus-4-5", "max", "default", "LLM_EFFORT"),
    ("claude-sonnet-4-6", "xhigh", "default", "LLM_EFFORT"),
    ("claude-haiku-4-5", "low", "default", "LLM_EFFORT"),
    ("claude-haiku-4-5", "medium", "default", "LLM_EFFORT"),
    ("claude-haiku-5-5", "xhigh", "off", "LLM_THINKING"),
    ("claude-haiku-5-5", "max", "off", "LLM_THINKING"),
    ("claude-sonnet-5-5", "xhigh", "off", "LLM_THINKING"),
    ("claude-opus-5", "max", "off", "LLM_THINKING"),
    ("claude-sonnet-5", "extreme", "default", "LLM_EFFORT"),
    ("claude-sonnet-5", None, "maybe", "LLM_THINKING"),
]

VALID_COMBINATIONS = [
    ("claude-sonnet-4-6", None, "off"),
    ("claude-haiku-4-5", None, "off"),
    ("claude-opus-4-5", "high", "default"),
    ("claude-haiku-5-5", "high", "off"),
    ("claude-sonnet-5-5", "low", "off"),
    ("claude-opus-5", "high", "off"),
    ("claude-sonnet-5", "max", "off"),
    ("claude-opus-5-5", "max", "default"),
    ("claude-fable-5-2", "xhigh", "default"),
]


class TestValidateCombinations:
    @pytest.mark.parametrize(("alias", "effort", "thinking", "parameter"), INVALID_COMBINATIONS)
    def test_invalid_combination_fails_naming_model_and_parameter(
        self, alias, effort, thinking, parameter
    ):
        config = _cfg(alias, effort=effort, thinking=thinking, role="task")

        with pytest.raises(_config_error()) as exc_info:
            config.validate()

        message = str(exc_info.value)
        assert alias in message
        assert parameter in message
        assert "TASK" in message

    @pytest.mark.parametrize(
        ("alias", "effort", "valid_values"),
        [
            ("claude-opus-4-5", "xhigh", ("low", "medium", "high")),
            ("claude-sonnet-5-5", "banana", ALL_EFFORTS),
        ],
    )
    def test_effort_error_lists_accepted_values(self, alias, effort, valid_values):
        with pytest.raises(_config_error()) as exc_info:
            _cfg(alias, effort=effort).validate()

        message = str(exc_info.value)
        for value in valid_values:
            assert value in message

    def test_unknown_thinking_error_lists_allowed_values(self):
        with pytest.raises(_config_error()) as exc_info:
            _cfg("claude-sonnet-5-5", thinking="maybe").validate()

        message = str(exc_info.value)
        assert "default" in message
        assert "off" in message

    def test_error_names_the_role(self):
        with pytest.raises(_config_error()) as exc_info:
            _cfg("claude-opus-5-5", thinking="off", role="reflection").validate()

        assert "REFLECTION" in str(exc_info.value)

    def test_config_error_is_a_connection_error(self):
        from shared.llm.errors import LLMConnectionError

        assert issubclass(_config_error(), LLMConnectionError)

    @pytest.mark.parametrize(("alias", "effort", "thinking"), VALID_COMBINATIONS)
    def test_valid_combination_passes(self, alias, effort, thinking):
        _cfg(alias, effort=effort, thinking=thinking).validate()

    def test_unknown_values_are_not_rejected_before_validate(self, anthropic_env, monkeypatch):
        anthropic_env("claude-sonnet-5-5")
        monkeypatch.setenv("LLM_EFFORT_TASK", "banana")
        monkeypatch.setenv("LLM_THINKING_TASK", "maybe")

        config = LLMConfig.from_env("task", load_env=False)

        assert config.effort == "banana"
        assert config.thinking == "maybe"
        with pytest.raises(_config_error()):
            config.validate()


# ==================== FR-008: parseo de variables ====================


class TestEnvParsing:
    @pytest.mark.parametrize("role", ["task", "reflection"])
    def test_effort_and_thinking_ignore_case_and_spaces(self, anthropic_env, monkeypatch, role):
        anthropic_env("claude-sonnet-5-5")
        monkeypatch.setenv(f"LLM_EFFORT_{role.upper()}", "  XHigh ")
        monkeypatch.setenv(f"LLM_THINKING_{role.upper()}", " OFF\t")

        config = LLMConfig.from_env(role, load_env=False)

        assert config.role == role
        assert config.effort == "xhigh"
        assert config.thinking == "off"

    def test_other_role_variables_do_not_leak(self, anthropic_env, monkeypatch):
        anthropic_env("claude-sonnet-5-5")
        monkeypatch.setenv("LLM_EFFORT_REFLECTION", "max")
        monkeypatch.setenv("LLM_THINKING_REFLECTION", "off")

        config = LLMConfig.from_env("task", load_env=False)

        assert config.effort is None
        assert config.thinking == "default"

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_values_mean_not_configured(self, anthropic_env, monkeypatch, blank):
        anthropic_env("claude-sonnet-5-5")
        monkeypatch.setenv("LLM_EFFORT_TASK", blank)
        monkeypatch.setenv("LLM_THINKING_TASK", blank)

        config = LLMConfig.from_env("task", load_env=False)

        assert config.effort is None
        assert config.thinking == "default"

    def test_unset_variables_default(self, anthropic_env):
        anthropic_env("claude-sonnet-5-5")

        config = LLMConfig.from_env("task", load_env=False)

        assert config.effort is None
        assert config.thinking == "default"
        assert config.role == "task"


# ==================== FR-001 / FR-007: avisos de arranque y LLM_API_BASE ====================


class TestStartupWarnings:
    @pytest.mark.parametrize(
        "model", ["claude-sonnet-4-5", "claude-future-9", "claude-opus-5-5-preview"]
    )
    def test_model_outside_matrix_warns_naming_id_and_works_unrestricted(
        self, capture_anthropic_post, caplog, model
    ):
        config = _cfg(model)
        with caplog.at_level(logging.WARNING):
            config.validate()

        assert model in caplog.text

        config.get_lm_function(role="task")("hi")
        body = capture_anthropic_post["body"]
        assert body["temperature"] == REQUESTED_TEMPERATURE
        assert body["max_tokens"] == REQUESTED_MAX_TOKENS
        assert "output_config" not in body
        assert "thinking" not in body

    def test_matrix_model_does_not_warn(self, caplog):
        with caplog.at_level(logging.WARNING):
            _cfg("claude-opus-5-5").validate()

        assert "claude-opus-5-5" not in caplog.text

    def test_global_api_base_warns_and_is_not_sent_but_role_api_base_is(
        self, anthropic_env, monkeypatch, caplog
    ):
        anthropic_env("claude-haiku-4-5")
        monkeypatch.setenv("LLM_API_BASE", "https://x.openai.azure.com")
        config = LLMConfig.from_env("task", load_env=False)
        with caplog.at_level(logging.WARNING):
            config.validate()

        assert "LLM_API_BASE" in caplog.text
        kwargs = config.to_kwargs()
        assert "api_base" not in kwargs
        assert "api_version" not in kwargs

        monkeypatch.setenv("LLM_API_BASE_TASK", "https://gateway.interno")
        kwargs = LLMConfig.from_env("task", load_env=False).to_kwargs()
        assert kwargs["api_base"] == "https://gateway.interno"
        assert "api_version" not in kwargs

    def test_validate_does_not_require_api_base_or_version(self):
        config = LLMConfig(model="anthropic/claude-haiku-4-5", api_key="x", api_base=None)

        config.validate()


# ==================== SC-006: regresion Azure/OpenAI (guardia, sin xfail) ====================

# to_kwargs() literales de la implementacion previa al cambio, con la config por defecto
# salvo temperatura y max_tokens explicitos.
AZURE_OPENAI_TO_KWARGS = [
    (
        "azure/gpt-4.1-mini",
        0.1,
        400,
        {
            "model": "azure/gpt-4.1-mini",
            "temperature": 0.1,
            "max_tokens": 400,
            "api_key": "x",
            "api_base": "https://x.openai.azure.com",
            "api_version": "2024-02-15-preview",
            "timeout": 600.0,
        },
    ),
    (
        "azure/gpt-5.4-mini",
        0.1,
        400,
        {
            "model": "azure/gpt-5.4-mini",
            "temperature": 1.0,
            "max_tokens": 16000,
            "api_key": "x",
            "api_base": "https://x.openai.azure.com",
            "api_version": "2024-02-15-preview",
            "timeout": 600.0,
        },
    ),
    (
        "azure/gpt-4o",
        0.7,
        2000,
        {
            "model": "azure/gpt-4o",
            "temperature": 0.7,
            "max_tokens": 2000,
            "api_key": "x",
            "api_base": "https://x.openai.azure.com",
            "api_version": "2024-02-15-preview",
            "timeout": 600.0,
        },
    ),
    (
        "openai/gpt-4o-mini",
        0.3,
        500,
        {
            "model": "openai/gpt-4o-mini",
            "temperature": 0.3,
            "max_tokens": 500,
            "api_key": "x",
            "api_base": "https://x.openai.azure.com",
            "api_version": "2024-02-15-preview",
            "timeout": 600.0,
        },
    ),
]


class TestAzureOpenAIConfigRegression:
    @pytest.mark.parametrize(
        ("model", "temperature", "max_tokens", "expected"), AZURE_OPENAI_TO_KWARGS
    )
    def test_to_kwargs_is_unchanged(self, model, temperature, max_tokens, expected):
        config = LLMConfig(
            model=model,
            api_key="x",
            api_base="https://x.openai.azure.com",
            api_version="2024-02-15-preview",
            temperature=temperature,
            max_tokens=max_tokens,
        )

        assert config.to_kwargs() == expected

    @pytest.mark.parametrize(
        ("model", "temperature", "max_tokens", "expected"),
        [row for row in AZURE_OPENAI_TO_KWARGS if row[0].startswith("azure/")],
    )
    def test_azure_wire_body_is_unchanged(
        self, capture_azure_post, model, temperature, max_tokens, expected
    ):
        config = LLMConfig(
            model=model,
            api_key="x",
            api_base="https://x.openai.azure.com",
            api_version="2024-02-15-preview",
            temperature=temperature,
            max_tokens=max_tokens,
        )

        assert config.get_lm_function(role="task")("hi") == "ok"

        body = capture_azure_post["body"]
        deployment = model.split("/", 1)[1]
        token_key = "max_completion_tokens" if expected["max_tokens"] == 16000 else "max_tokens"
        assert body["model"] == deployment
        assert body["temperature"] == expected["temperature"]
        assert body[token_key] == expected["max_tokens"]
        assert "output_config" not in body
        assert "thinking" not in body
        assert capture_azure_post["query"].get("api-version") == "2024-02-15-preview"

    def test_apply_reasoning_constraints_still_behaves_for_non_anthropic(self):
        config = LLMConfig(model="azure/gpt-4o", api_key="x", temperature=0.7, max_tokens=50)

        assert config.to_kwargs()["max_tokens"] == 50
        assert "output_config" not in config.to_kwargs()
        assert "thinking" not in config.to_kwargs()

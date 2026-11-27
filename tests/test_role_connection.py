"""
SPEC-106 (subfase 1a): conexion por rol, proveedor ancla y no fuga.

Tests RED: fallan con el codigo de hoy y los cierra SPEC-106 1b (D1 a D4 y D7 del
plan). 1b quita la marca `xfail`. FR-001, FR-002 (golden aparte), FR-003, FR-007
(metodo) y SC-003. Sin red: `litellm.completion` se parchea para fallar si se llama.
"""

import logging
import os

import pytest

from shared.llm.config import LLMConfig
from shared.llm.errors import LLMConnectionError
from tests.conftest import make_completion_response, patch_litellm_completion, project_warnings

_AZURE_TASK = {
    "LLM_MODEL_TASK": "azure/gpt-4.1-mini",
    "LLM_API_KEY": "key-global-azure",
    "LLM_API_BASE": "https://recurso.openai.azure.com/",
}
_CLAUDE = "anthropic/claude-sonnet-4-6"


def _set_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for name in list(os.environ):
        if name.startswith("LLM_"):
            monkeypatch.delenv(name)
    for name, value in env.items():
        monkeypatch.setenv(name, value)


def _forbid_network(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """`litellm.completion` que registra cada llamada; el test exige lista vacia."""
    calls: list[dict] = []

    def fake(request, num_retries):
        calls.append(request)
        return make_completion_response()

    patch_litellm_completion(monkeypatch, fake)
    return calls


def _error_text(exc_info) -> str:
    return exc_info.value.format_error()


class TestProviderOf:
    @pytest.mark.parametrize(
        ("model", "provider"),
        [
            ("azure/gpt-4.1-mini", "azure"),
            ("openai/gpt-4o", "openai"),
            ("anthropic/claude-sonnet-4-6", "anthropic"),
            ("Anthropic/Claude", "anthropic"),
            ("gpt-4o", "openai"),
            ("bedrock/anthropic.claude-v2", "bedrock"),
        ],
    )
    def test_provider_is_prefix_lowercase_and_openai_without_prefix(self, model, provider):
        from shared.llm.config import provider_of

        assert provider_of(model) == provider

    def test_exported_from_package(self):
        from shared.llm import provider_of

        assert provider_of("azure/x") == "azure"

    def test_azure_openai_anthropic_are_distinct_providers(self):
        from shared.llm.config import provider_of

        assert len({provider_of(m) for m in ("azure/m", "openai/m", "anthropic/m")}) == 3

    def test_dspy_engine_uses_the_same_function(self, monkeypatch):
        from shared.llm.config import provider_of

        _set_env(monkeypatch, {**_AZURE_TASK, "LLM_MODEL_REFLECTION": "gpt-4o"})
        engine = LLMConfig.from_env("reflection", load_env=False).get_dspy_lm().engine

        assert engine._provider == provider_of("gpt-4o") == "openai"


class TestRoleVariables:
    def test_role_variables_take_precedence_over_global(self, monkeypatch):
        _set_env(
            monkeypatch,
            {
                **_AZURE_TASK,
                "LLM_MODEL_REFLECTION": "azure/gpt-4.1",
                "LLM_API_KEY_REFLECTION": "key-reflection",
                "LLM_API_BASE_REFLECTION": "https://otro.openai.azure.com/",
                "LLM_API_VERSION_REFLECTION": "2025-01-01",
            },
        )

        reflection = LLMConfig.from_env("reflection", load_env=False)
        task = LLMConfig.from_env("task", load_env=False)

        assert (reflection.api_key, reflection.api_base, reflection.api_version) == (
            "key-reflection",
            "https://otro.openai.azure.com/",
            "2025-01-01",
        )
        assert task.api_key == "key-global-azure"
        assert task.api_base == "https://recurso.openai.azure.com/"

    def test_empty_role_variable_counts_as_undefined(self, monkeypatch):
        _set_env(
            monkeypatch,
            {**_AZURE_TASK, "LLM_MODEL_REFLECTION": _CLAUDE, "LLM_API_KEY_REFLECTION": "  "},
        )
        _forbid_network(monkeypatch)

        reflection = LLMConfig.from_env("reflection", load_env=False)
        assert reflection.api_key is None
        with pytest.raises(LLMConnectionError) as exc_info:
            reflection.validate()
        assert "LLM_API_KEY_REFLECTION" in _error_text(exc_info)

        # Mismo proveedor que el ancla: vacio = no definido = hereda el global.
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "azure/gpt-4.1")
        assert LLMConfig.from_env("reflection", load_env=False).api_key == "key-global-azure"

    def test_judge_and_additional_roles_resolve_their_own_variables(self, monkeypatch):
        _set_env(
            monkeypatch,
            {
                **_AZURE_TASK,
                "LLM_MODEL_JUDGE": _CLAUDE,
                "LLM_API_KEY_JUDGE": "key-judge",
            },
        )

        judge = LLMConfig.from_env("judge", load_env=False)

        assert judge.model == _CLAUDE
        assert judge.api_key == "key-judge"


class TestNoLeakBetweenProviders:
    """FR-003 / SC-003: la conexion global pertenece al proveedor de `task`."""

    def test_anthropic_role_without_own_key_fails_locally_without_network(self, monkeypatch):
        _set_env(monkeypatch, {**_AZURE_TASK, "LLM_MODEL_REFLECTION": _CLAUDE})
        calls = _forbid_network(monkeypatch)
        reflection = LLMConfig.from_env("reflection", load_env=False)

        assert "key-global-azure" not in reflection.to_kwargs().values()
        assert "key-global-azure" not in reflection._base_kwargs().values()
        with pytest.raises(LLMConnectionError) as exc_info:
            reflection.validate()

        text = _error_text(exc_info)
        assert "reflection" in text
        assert "anthropic" in text
        assert "LLM_API_KEY_REFLECTION" in text
        assert "key-global-azure" not in text
        assert exc_info.value.provider == "anthropic"
        assert calls == []

    def test_azure_role_with_other_anchor_names_its_endpoint_variables(self, monkeypatch):
        _set_env(
            monkeypatch,
            {
                "LLM_MODEL_TASK": _CLAUDE,
                "LLM_API_KEY": "key-global-claude",
                "LLM_MODEL_REFLECTION": "azure/gpt-4.1",
            },
        )
        reflection = LLMConfig.from_env("reflection", load_env=False)

        assert reflection.api_key is None
        with pytest.raises(LLMConnectionError) as exc_info:
            reflection.validate()
        text = _error_text(exc_info)
        assert "LLM_API_KEY_REFLECTION" in text
        assert "key-global-claude" not in text

    def test_same_provider_role_inherits_and_message_names_both_variables(self, monkeypatch):
        _set_env(
            monkeypatch,
            {"LLM_MODEL_TASK": "azure/gpt-4.1-mini", "LLM_API_BASE": "https://r.azure.com/"},
        )
        with pytest.raises(LLMConnectionError) as exc_info:
            LLMConfig.from_env("task", load_env=False).validate()

        assert "LLM_API_KEY_TASK" in _error_text(exc_info)
        assert "LLM_API_KEY" in _error_text(exc_info)

    def test_api_version_and_its_default_are_not_inherited_by_other_provider(self, monkeypatch):
        _set_env(
            monkeypatch,
            {
                **_AZURE_TASK,
                "LLM_API_VERSION": "2024-10-21",
                "LLM_MODEL_REFLECTION": "openai/gpt-4o",
                "LLM_API_KEY_REFLECTION": "key-openai",
            },
        )
        reflection = LLMConfig.from_env("reflection", load_env=False)

        assert reflection.api_version is None
        assert reflection.api_base is None
        assert "api_version" not in reflection.to_kwargs()
        assert "api_base" not in reflection.to_kwargs()

    def test_default_api_version_is_not_inherited_when_global_is_absent(self, monkeypatch):
        _set_env(
            monkeypatch,
            {
                **_AZURE_TASK,
                "LLM_MODEL_REFLECTION": _CLAUDE,
                "LLM_API_KEY_REFLECTION": "key-claude",
            },
        )

        assert LLMConfig.from_env("task", load_env=False).api_version == "2024-02-15-preview"
        assert LLMConfig.from_env("reflection", load_env=False).api_version is None


class TestAnthropicApiBase:
    """FR-003, enmienda a SPEC-103 FR-007 (D3)."""

    def test_role_api_base_is_sent_without_api_version_and_without_warning(
        self, monkeypatch, caplog
    ):
        _set_env(
            monkeypatch,
            {
                **_AZURE_TASK,
                "LLM_MODEL_REFLECTION": _CLAUDE,
                "LLM_API_KEY_REFLECTION": "key-claude",
                "LLM_API_BASE_REFLECTION": "https://gateway.interno",
            },
        )
        reflection = LLMConfig.from_env("reflection", load_env=False)

        with caplog.at_level(logging.WARNING):
            reflection.validate()
        kwargs = reflection.to_kwargs()

        assert kwargs["api_base"] == "https://gateway.interno"
        assert kwargs["api_key"] == "key-claude"
        assert "api_version" not in kwargs
        assert [r for r in project_warnings(caplog) if "LLM_API_BASE" in r.getMessage()] == []

    def test_global_api_base_is_not_sent_and_warns_that_it_is_not_inherited(
        self, monkeypatch, caplog
    ):
        _set_env(
            monkeypatch,
            {
                "LLM_MODEL_TASK": _CLAUDE,
                "LLM_API_KEY": "key-claude",
                "LLM_API_BASE": "https://gateway.global",
            },
        )
        task = LLMConfig.from_env("task", load_env=False)

        with caplog.at_level(logging.WARNING):
            task.validate()

        assert "api_base" not in task.to_kwargs()
        messages = [r.getMessage() for r in project_warnings(caplog)]
        assert any("LLM_API_BASE" in m and "inherit" in m.lower() for m in messages)


class TestEnvSources:
    def test_names_the_variable_each_value_came_from_never_the_value(self, monkeypatch):
        _set_env(
            monkeypatch,
            {
                **_AZURE_TASK,
                "LLM_MODEL_REFLECTION": "azure/gpt-4.1",
                "LLM_API_KEY_REFLECTION": "key-reflection",
            },
        )

        task = LLMConfig.from_env("task", load_env=False)
        reflection = LLMConfig.from_env("reflection", load_env=False)

        assert task.env_sources == {
            "model": "LLM_MODEL_TASK",
            "api_key": "LLM_API_KEY",
            "api_base": "LLM_API_BASE",
            "api_version": "default",
        }
        assert reflection.env_sources == {
            "model": "LLM_MODEL_REFLECTION",
            "api_key": "LLM_API_KEY_REFLECTION",
            "api_base": "LLM_API_BASE",
            "api_version": "default",
        }
        secrets = {"key-global-azure", "key-reflection", "https://recurso.openai.azure.com/"}
        assert secrets.isdisjoint(reflection.env_sources.values())
        assert "env_sources" not in repr(reflection)


class TestEnvFile:
    """FR-005 (ultimo punto): `LLM_ENV_FILE` se carga si no hay ninguna credencial."""

    @staticmethod
    def _spy_load_dotenv(monkeypatch) -> list[str | None]:
        calls: list[str | None] = []

        def fake_load_dotenv(dotenv_path=None, *args, **kwargs):
            calls.append(str(dotenv_path) if dotenv_path is not None else None)
            return False

        monkeypatch.setattr("dotenv.load_dotenv", fake_load_dotenv)
        return calls

    def test_loaded_without_any_credential_and_not_with_a_role_key(self, monkeypatch, tmp_path):
        env_file = tmp_path / "llm.env"
        env_file.write_text("LLM_API_KEY=desde-archivo\n", encoding="utf-8")
        calls = self._spy_load_dotenv(monkeypatch)

        _set_env(monkeypatch, {"LLM_ENV_FILE": str(env_file)})
        LLMConfig.from_env("task")
        assert str(env_file) in calls

        calls.clear()
        _set_env(
            monkeypatch,
            {"LLM_ENV_FILE": str(env_file), "LLM_API_KEY_TASK": "key-task"},
        )
        LLMConfig.from_env("task")
        assert str(env_file) not in calls


class TestEndpointAndSummary:
    """FR-007 (metodo) y D7: host efectivo, nunca la credencial."""

    @pytest.mark.parametrize(
        ("env", "role", "host"),
        [
            ({**_AZURE_TASK}, "task", "recurso.openai.azure.com"),
            (
                {
                    "LLM_MODEL_TASK": "openai/gpt-4o",
                    "LLM_API_KEY": "k",
                },
                "task",
                "api.openai.com",
            ),
            (
                {
                    "LLM_MODEL_TASK": "openai/gpt-4o",
                    "LLM_API_KEY": "k",
                    "LLM_API_BASE": "https://proxy.interno:8443/v1",
                },
                "task",
                "proxy.interno",
            ),
            ({"LLM_MODEL_TASK": _CLAUDE, "LLM_API_KEY": "k"}, "task", "api.anthropic.com"),
            (
                {
                    "LLM_MODEL_TASK": _CLAUDE,
                    "LLM_API_KEY": "k",
                    "LLM_API_BASE_TASK": "https://gateway.interno/anthropic",
                },
                "task",
                "gateway.interno",
            ),
            ({"LLM_MODEL_TASK": "bedrock/modelo", "LLM_API_KEY": "k"}, "task", None),
        ],
    )
    def test_endpoint_host(self, monkeypatch, env, role, host):
        _set_env(monkeypatch, env)

        assert LLMConfig.from_env(role, load_env=False).endpoint_host == host

    def test_connection_summary_is_role_provider_model_host_without_secrets(self, monkeypatch):
        _set_env(
            monkeypatch,
            {
                **_AZURE_TASK,
                "LLM_MODEL_REFLECTION": _CLAUDE,
                "LLM_API_KEY_REFLECTION": "key-secreta-claude",
                "LLM_API_BASE_REFLECTION": "https://gateway.interno/ruta/privada",
            },
        )

        summary = LLMConfig.from_env("reflection", load_env=False).connection_summary()

        assert summary.split(" | ") == ["reflection", "anthropic", _CLAUDE, "gateway.interno"]
        assert "key-secreta-claude" not in summary
        assert "/ruta/privada" not in summary


class TestModelWithoutDefault:
    """FR-001 (enmienda) y D12: `LLM_MODEL_<ROL>` ausente o vacio falla en validate()."""

    @pytest.mark.parametrize("role", ["task", "reflection"])
    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_missing_or_empty_model_fails_validation_without_network(
        self, monkeypatch, role, value
    ):
        env = {"LLM_API_KEY": "key-global", "LLM_API_BASE": "https://r.azure.com/"}
        if value is not None:
            env[f"LLM_MODEL_{role.upper()}"] = value
        if role == "reflection":
            env["LLM_MODEL_TASK"] = "azure/gpt-4.1-mini"
        _set_env(monkeypatch, env)
        calls = _forbid_network(monkeypatch)

        config = LLMConfig.from_env(role, load_env=False)
        with pytest.raises(LLMConnectionError) as exc_info:
            config.validate()

        error = exc_info.value
        assert error.role == role
        assert f"LLM_MODEL_{role.upper()}" in error.variable
        assert f"LLM_MODEL_{role.upper()}" in _error_text(exc_info)
        assert "LLM_MODEL_*" not in _error_text(exc_info)
        assert calls == []

    def test_empty_model_error_does_not_report_an_invented_provider(self, monkeypatch):
        _set_env(monkeypatch, {"LLM_MODEL_TASK": "", "LLM_API_KEY": "key-global"})

        with pytest.raises(LLMConnectionError) as exc_info:
            LLMConfig.from_env("task", load_env=False).validate()

        assert exc_info.value.provider not in ("openai", "azure", "anthropic")
        assert "Provider: openai" not in _error_text(exc_info)

    def test_without_task_model_there_is_no_anchor_and_globals_are_not_inherited(self, monkeypatch):
        _set_env(
            monkeypatch,
            {
                "LLM_API_KEY": "key-global",
                "LLM_API_BASE": "https://r.azure.com/",
                "LLM_MODEL_REFLECTION": "azure/gpt-4.1",
            },
        )

        reflection = LLMConfig.from_env("reflection", load_env=False)

        assert reflection.api_key is None
        assert reflection.api_base is None
        assert reflection.api_version is None
        assert "key-global" not in reflection.to_kwargs().values()

    def test_env_sources_model(self, monkeypatch):
        _set_env(monkeypatch, {"LLM_MODEL_TASK": "azure/gpt-4.1-mini"})

        assert LLMConfig.from_env("task", load_env=False).env_sources["model"] == "LLM_MODEL_TASK"
        reflection = LLMConfig.from_env("reflection", load_env=False)
        assert reflection.env_sources["model"] == "unset"
        assert reflection.model == ""

"""
SPEC-106 FR-002 / SC-004 (subfase 1a): regresion de parametros de llamada.

Un `.env` sin variables por rol y con todos los roles del mismo proveedor MUST
producir exactamente los mismos parametros de llamada que antes del cambio. Estos
tests son el golden de esa regla: se escriben y pasan ANTES de tocar
`LLMConfig.from_env` (SPEC-106 1b) y deben seguir verdes sin editarse. Los valores
esperados son literales (no se calculan con el codigo bajo prueba).

Cubren, por rol (`task`, `reflection` y el juez de hoy, que es la config del
profesor con rol `judge`), tres superficies de parametros:
- `to_kwargs()` (camino de `get_lm_function`, `call_llm` y el adapter RAG);
- los kwargs de la sonda de conexion (`_base_kwargs` con `max_tokens=5` y
  `apply_constraints`);
- los `params` del engine de DSPy (`get_dspy_lm().engine`).
"""

import os

import pytest

from shared.llm.config import LLMConfig

# Defaults del dataclass: temperature 0.7, max_tokens 1000, timeout 600.0.
_COMMON = {"temperature": 0.7, "timeout": 600.0}

_ENV_AZURE = {
    "LLM_MODEL_TASK": "azure/gpt-4.1-mini",
    "LLM_MODEL_REFLECTION": "azure/gpt-4.1",
    "LLM_API_KEY": "key-azure",
    "LLM_API_BASE": "https://recurso.openai.azure.com/",
    "LLM_API_VERSION": "2024-10-21",
}
_ENV_OPENAI_PROXY = {
    "LLM_MODEL_TASK": "openai/gpt-4o-mini",
    "LLM_MODEL_REFLECTION": "openai/gpt-4o",
    "LLM_API_KEY": "key-openai",
    "LLM_API_BASE": "https://proxy.interno/v1",
}
# Hoy `apply_constraints` quita `api_base` y `api_version` a todo `anthropic/`.
_ENV_ANTHROPIC = {
    "LLM_MODEL_TASK": "anthropic/claude-haiku-4-5",
    "LLM_MODEL_REFLECTION": "anthropic/claude-sonnet-4-6",
    "LLM_API_KEY": "key-anthropic",
    "LLM_API_BASE": "https://gateway.global",
}


def _set_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for name in list(os.environ):
        if name.startswith("LLM_"):
            monkeypatch.delenv(name)
    for name, value in env.items():
        monkeypatch.setenv(name, value)


def _config(role: str) -> LLMConfig:
    """Config de un rol; el juez de hoy es la del profesor con rol `judge`."""
    source = "reflection" if role == "judge" else role
    return LLMConfig.from_env(source, load_env=False, role=role)


def _probe_kwargs(config: LLMConfig) -> dict:
    base = config._base_kwargs()
    base["max_tokens"] = 5
    return config.apply_constraints(base)


def _engine_params(config: LLMConfig) -> dict:
    return config.get_dspy_lm().engine.params


# (rol) -> (to_kwargs, sonda, params del engine DSPy)
_AZURE_EXPECTED = {
    "task": {
        "model": "azure/gpt-4.1-mini",
        "max_tokens": 1000,
        "api_key": "key-azure",
        "api_base": "https://recurso.openai.azure.com/",
        "api_version": "2024-10-21",
        **_COMMON,
    },
    "reflection": {
        "model": "azure/gpt-4.1",
        "max_tokens": 1000,
        "api_key": "key-azure",
        "api_base": "https://recurso.openai.azure.com/",
        "api_version": "2024-10-21",
        **_COMMON,
    },
}
_AZURE_EXPECTED["judge"] = dict(_AZURE_EXPECTED["reflection"])

_OPENAI_EXPECTED = {
    "task": {
        "model": "openai/gpt-4o-mini",
        "max_tokens": 1000,
        "api_key": "key-openai",
        "api_base": "https://proxy.interno/v1",
        "api_version": "2024-02-15-preview",
        **_COMMON,
    },
    "reflection": {
        "model": "openai/gpt-4o",
        "max_tokens": 1000,
        "api_key": "key-openai",
        "api_base": "https://proxy.interno/v1",
        "api_version": "2024-02-15-preview",
        **_COMMON,
    },
}
_OPENAI_EXPECTED["judge"] = dict(_OPENAI_EXPECTED["reflection"])

# haiku-4-5: sin effort. sonnet-4-6: envia temperature y `output_config.effort`
# "medium" por defecto. Sin api_base ni api_version (los quita `apply_constraints`).
_ANTHROPIC_EXPECTED = {
    "task": {
        "model": "anthropic/claude-haiku-4-5",
        "max_tokens": 1000,
        "api_key": "key-anthropic",
        **_COMMON,
    },
    "reflection": {
        "model": "anthropic/claude-sonnet-4-6",
        "max_tokens": 1000,
        "api_key": "key-anthropic",
        "output_config": {"effort": "medium"},
        **_COMMON,
    },
}
_ANTHROPIC_EXPECTED["judge"] = dict(_ANTHROPIC_EXPECTED["reflection"])

_CASES = {
    "azure": (_ENV_AZURE, _AZURE_EXPECTED),
    "openai_proxy": (_ENV_OPENAI_PROXY, _OPENAI_EXPECTED),
    "anthropic_base_global": (_ENV_ANTHROPIC, _ANTHROPIC_EXPECTED),
}


@pytest.mark.parametrize("role", ["task", "reflection", "judge"])
@pytest.mark.parametrize("case", list(_CASES))
class TestEnvWithoutRoleVariables:
    def test_to_kwargs_are_unchanged(self, monkeypatch, case, role):
        env, expected = _CASES[case]
        _set_env(monkeypatch, env)

        assert _config(role).to_kwargs() == expected[role]

    def test_probe_kwargs_are_unchanged(self, monkeypatch, case, role):
        env, expected = _CASES[case]
        _set_env(monkeypatch, env)

        assert _probe_kwargs(_config(role)) == {**expected[role], "max_tokens": 5}

    def test_dspy_engine_params_are_unchanged(self, monkeypatch, case, role):
        env, expected = _CASES[case]
        _set_env(monkeypatch, env)

        params = dict(expected[role])
        params.pop("model")
        assert _engine_params(_config(role)) == params
        assert _config(role).get_dspy_lm().engine.model == expected[role]["model"]

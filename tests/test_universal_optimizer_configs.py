"""SPEC-103 FR-012: UniversalOptimizer arma una sola vez las configs LLM."""

from unittest.mock import patch

from gepa_standalone.universal_optimizer import UniversalOptimizer
from shared.llm import LLMConfig


def _cfg(role):
    return LLMConfig(
        model="anthropic/claude-haiku-4-5",
        api_key="x",
        temperature=0.5,
        max_tokens=1000,
        role=role,
    )


def _optimizer(models):
    opt = UniversalOptimizer()
    opt.config = {"models": models}
    with (
        patch(
            "gepa_standalone.universal_optimizer.get_task_config",
            side_effect=lambda: _cfg("task"),
        ),
        patch(
            "gepa_standalone.universal_optimizer.get_reflection_config",
            side_effect=lambda: _cfg("reflection"),
        ),
    ):
        opt.build_llm_configs()
    return opt


def test_yaml_overrides_applied_to_both_configs():
    opt = _optimizer({"temperature": 0.2, "max_tokens": 777, "cache": False})

    assert opt.active_temperature == 0.2
    assert opt.task_config.temperature == 0.2
    assert opt.reflection_config.temperature == 0.2
    assert opt.task_config.max_tokens == 777
    assert opt.reflection_config.max_tokens == 777
    assert opt.reflection_config.cache is False


def test_defaults_without_yaml_models():
    opt = _optimizer({})

    assert opt.active_temperature == 0.0
    assert opt.task_config.temperature == 0.0
    assert opt.reflection_config.temperature == 0.5
    assert opt.reflection_config.max_tokens == 2000
    assert opt.task_config.max_tokens == 1000


def test_configs_are_distinct_roles():
    opt = _optimizer({})

    assert opt.task_config is not opt.reflection_config
    assert opt.task_config.role == "task"
    assert opt.reflection_config.role == "reflection"


def test_reflection_lm_function_uses_given_config():
    from gepa_standalone.core.llm_factory import create_reflection_lm_function

    cfg = _cfg("reflection")
    with patch.object(LLMConfig, "get_lm_function", autospec=True) as get_fn:
        create_reflection_lm_function(config=cfg, temperature=0.9, max_tokens=5)

    assert get_fn.call_args.args[0] is cfg
    assert cfg.temperature == 0.5
    assert cfg.max_tokens == 1000

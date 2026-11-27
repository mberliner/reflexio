"""
SPEC-106 FR-008 y FR-005 (ultimo punto): `check_deployments` verifica cada rol contra
su propio endpoint y credencial; un rol no Azure es "no aplica"; `LLM_ENV_FILE` se
carga cuando no hay ninguna credencial (global ni por rol).

Sin red: `litellm.completion` se simula con `litellm.ModelResponse` reales.
"""

import os

import pytest

from shared.utils import check_deployments as cd
from tests.conftest import make_completion_response, patch_litellm_completion

AZURE_A = "https://alpha.openai.azure.com/"
AZURE_B = "https://beta.openai.azure.com/"


@pytest.fixture(autouse=True)
def isolated_env(tmp_path):
    """Sin .env del cwd ni variables LLM_* heredadas, y sin fuga al terminar.

    No usa monkeypatch a proposito: `load_dotenv` (via `--env-file`) escribe
    `os.environ` por fuera, y un `monkeypatch.delenv` posterior registraria esos
    valores y los restauraria en su teardown. Este fixture autouse se instancia
    antes que el `monkeypatch` del test, asi que su teardown corre despues y deja
    las `LLM_*` exactamente como estaban.
    """
    cwd = os.getcwd()
    saved = {name: value for name, value in os.environ.items() if name.startswith("LLM_")}
    for name in saved:
        del os.environ[name]
    os.chdir(tmp_path)
    yield
    os.chdir(cwd)
    for name in [n for n in os.environ if n.startswith("LLM_")]:
        del os.environ[name]
    os.environ.update(saved)


class TestRoleConfigs:
    def test_roles_without_judge(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL_TASK", "azure/gpt-4.1-mini")
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "azure/gpt-4o")
        assert [c.role for c in cd.role_configs()] == ["task", "reflection"]

    def test_judge_included_only_with_model_judge(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL_TASK", "azure/gpt-4.1-mini")
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "azure/gpt-4o")
        monkeypatch.setenv("LLM_MODEL_JUDGE", "azure/gpt-4o-mini")
        assert [c.role for c in cd.role_configs()] == ["task", "reflection", "judge"]


class TestEachRoleAgainstItsOwnEndpoint:
    def test_role_with_own_endpoint_is_probed_there(self, monkeypatch, capsys):
        monkeypatch.setenv("LLM_MODEL_TASK", "azure/gpt-4.1-mini")
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "azure/gpt-4o")
        monkeypatch.setenv("LLM_API_KEY", "key-task")
        monkeypatch.setenv("LLM_API_BASE", AZURE_A)
        monkeypatch.setenv("LLM_API_KEY_REFLECTION", "key-ref")
        monkeypatch.setenv("LLM_API_BASE_REFLECTION", AZURE_B)
        seen = []

        def fake(request, num_retries):
            seen.append((request["model"], request["api_base"], request["api_key"]))
            return make_completion_response()

        patch_litellm_completion(monkeypatch, fake)
        cd.check_config({})

        assert ("gpt-4.1-mini", AZURE_A, "key-task") in [
            (m.removeprefix("azure/"), b, k) for m, b, k in seen
        ]
        assert ("gpt-4o", AZURE_B, "key-ref") in [
            (m.removeprefix("azure/"), b, k) for m, b, k in seen
        ]
        out = capsys.readouterr().out
        assert "key-task" not in out and "key-ref" not in out
        assert "[X]" not in out

    def test_scanned_list_is_per_endpoint(self, monkeypatch):
        """Un deployment activo en el endpoint de la tarea no vale para el del profesor."""
        monkeypatch.setenv("LLM_MODEL_TASK", "azure/gpt-4.1-mini")
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "azure/gpt-4o")
        monkeypatch.setenv("LLM_API_KEY", "key-task")
        monkeypatch.setenv("LLM_API_BASE", AZURE_A)
        monkeypatch.setenv("LLM_API_KEY_REFLECTION", "key-ref")
        monkeypatch.setenv("LLM_API_BASE_REFLECTION", AZURE_B)
        confs = cd.role_configs()
        scanned = {cd._endpoint_key(confs[0]): ["gpt-4.1-mini", "gpt-4o"]}
        probed = []

        def fake(request, num_retries):
            probed.append(request["api_base"])
            return make_completion_response()

        patch_litellm_completion(monkeypatch, fake)
        cd.check_config(scanned, confs)

        assert probed == [AZURE_B]

    def test_judge_checked_when_configured(self, monkeypatch, capsys):
        monkeypatch.setenv("LLM_MODEL_TASK", "azure/gpt-4.1-mini")
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "azure/gpt-4.1-mini")
        monkeypatch.setenv("LLM_MODEL_JUDGE", "azure/gpt-4o-mini")
        monkeypatch.setenv("LLM_API_KEY", "k")
        monkeypatch.setenv("LLM_API_BASE", AZURE_A)
        models = []

        def fake(request, num_retries):
            models.append(request["model"])
            return make_completion_response()

        patch_litellm_completion(monkeypatch, fake)
        cd.check_config({})

        assert any(m.endswith("gpt-4o-mini") for m in models)
        assert "Judge Model" in capsys.readouterr().out


class TestNonAzureRole:
    def test_anthropic_role_is_not_applicable_not_an_error(self, monkeypatch, capsys):
        monkeypatch.setenv("LLM_MODEL_TASK", "azure/gpt-4.1-mini")
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "anthropic/claude-sonnet-5-5")
        monkeypatch.setenv("LLM_API_KEY", "key-az")
        monkeypatch.setenv("LLM_API_BASE", AZURE_A)
        monkeypatch.setenv("LLM_API_KEY_REFLECTION", "key-an")
        models = []

        def fake(request, num_retries):
            models.append(request["model"])
            return make_completion_response()

        patch_litellm_completion(monkeypatch, fake)
        cd.check_config({})

        out = capsys.readouterr().out
        assert "no aplica" in out
        assert "[X]" not in out
        assert not any("claude" in m for m in models)
        assert "key-an" not in out and "key-az" not in out


class TestEnvFileTrigger:
    def test_any_credential_detection(self, monkeypatch):
        assert cd._has_any_credential() is False
        monkeypatch.setenv("LLM_API_KEY_REFLECTION", "  ")
        assert cd._has_any_credential() is False
        monkeypatch.setenv("LLM_API_KEY_REFLECTION", "k")
        assert cd._has_any_credential() is True

    def test_main_does_not_set_env_file_with_only_role_credential(self, monkeypatch, tmp_path):
        env_file = tmp_path / "custom.env"
        env_file.write_text("LLM_API_KEY=from-file\n")
        monkeypatch.setenv("LLM_MODEL_TASK", "anthropic/claude-sonnet-5-5")
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "anthropic/claude-sonnet-5-5")
        monkeypatch.setenv("LLM_API_KEY_TASK", "only-task")
        monkeypatch.setattr(
            "sys.argv", ["check_deployments", "--quick", "--env-file", str(env_file)]
        )
        cd.main()
        assert "LLM_ENV_FILE" not in os.environ

    def test_main_loads_env_file_without_credentials(self, monkeypatch, tmp_path, capsys):
        env_file = tmp_path / "custom.env"
        env_file.write_text(
            "LLM_MODEL_TASK=azure/gpt-4.1-mini\n"
            "LLM_MODEL_REFLECTION=azure/gpt-4.1-mini\n"
            "LLM_API_KEY=from-file\n"
            f"LLM_API_BASE={AZURE_A}\n"
        )
        monkeypatch.setattr(
            "sys.argv", ["check_deployments", "--quick", "--env-file", str(env_file)]
        )
        patch_litellm_completion(
            monkeypatch, lambda request, num_retries: make_completion_response()
        )
        try:
            cd.main()
        finally:
            for name in [n for n in os.environ if n.startswith("LLM_")]:
                monkeypatch.delenv(name, raising=False)
        out = capsys.readouterr().out
        assert "alpha.openai.azure.com" in out
        assert "from-file" not in out

    def test_judge_defined_only_in_env_file_is_checked(self, monkeypatch, tmp_path, capsys):
        """R8: el juez del `.env` de `--env-file` se verifica aunque no este en el entorno."""
        env_file = tmp_path / "custom.env"
        env_file.write_text(
            "LLM_MODEL_TASK=azure/gpt-4.1-mini\n"
            "LLM_MODEL_REFLECTION=azure/gpt-4.1-mini\n"
            "LLM_MODEL_JUDGE=anthropic/claude-sonnet-5-5\n"
            "LLM_API_KEY_JUDGE=judge-key\n"
            "LLM_API_KEY=from-file\n"
            f"LLM_API_BASE={AZURE_A}\n"
        )
        monkeypatch.setattr(
            "sys.argv", ["check_deployments", "--quick", "--env-file", str(env_file)]
        )
        patch_litellm_completion(
            monkeypatch, lambda request, num_retries: make_completion_response()
        )
        cd.main()  # isolated_env limpia lo que load_dotenv deja en os.environ
        out = capsys.readouterr().out
        assert "judge | anthropic | anthropic/claude-sonnet-5-5 | api.anthropic.com" in out
        assert "judge-key" not in out

"""
SPEC-104 subfase 2a: punto unico de llamada a LiteLLM (D3, FR-001, FR-011, SC-009).

- AST: no hay otra llamada a `litellm.completion` en produccion fuera de
  `shared/llm/call.py` y de la herramienta de diagnostico
  `shared/utils/check_deployments.py`. La sonda de conexion
  (`LLMConfig.validate_connection`) pasa por el punto comun (SPEC-106 FR-005).
- Los tres caminos sin DSPy (`get_lm_function`, `call_llm`,
  `SimpleRAGAdapter._complete`) delegan en `checked_completion`.
- SC-009 por caso: a traves de `dspy.Predict` (con el fallback ChatAdapter ->
  JSONAdapter activo) un error persistente produce exactamente 1 llamada HTTP si
  no es `infraestructura` y 1 + reintentos si lo es, con la clase esperada.
- Con el contador abortado ningun camino llega al transporte HTTP.

Sin red: payloads de `tests/litellm_failure_payloads.py` inyectados en
`httpx.Client.send` (`intercept_httpx`).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import dspy
import litellm
import pytest

from gepa_standalone.adapters.simple_rag_adapter import SimpleRAGAdapter
from gepa_standalone.core.llm_factory import call_llm
from shared.llm import LLMCallFailure, LLMConfig, RunAborted, get_failure_tracker
from shared.llm.failures import DEFAULT_INFRA_RETRIES, FailureClass, LLMFailure
from tests.conftest import make_completion_response
from tests.litellm_failure_payloads import (
    ALL_FAILURE_CASES,
    PROVIDER_KWARGS,
    RETRY_CASES,
    FailurePayloadCase,
)
from tests.test_litellm_failure_mapping import intercept_httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PACKAGES = ("shared", "gepa_standalone", "dspy_gepa_poc")
COMPLETION_NAMES = frozenset({"completion", "acompletion"})

# (archivo, funcion que contiene la llamada): unicos lugares permitidos.
ALLOWED_CALL_SITES = {
    ("shared/llm/call.py", "_raw_completion"),
    # Herramienta de diagnostico, fuera de FR-005 de SPEC-106 (D5).
    ("shared/utils/check_deployments.py", None),
}

FAILING_CASES: tuple[FailurePayloadCase, ...] = tuple(
    c for c in ALL_FAILURE_CASES if c.spec104_class != "ok"
)


@pytest.fixture(autouse=True)
def _litellm_globals(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(litellm, "drop_params", False)
    monkeypatch.setattr(litellm, "num_retries", None)
    monkeypatch.setattr(litellm, "suppress_debug_info", True)
    yield


def _expected_calls(case: FailurePayloadCase, per_attempt: int = 1) -> int:
    attempts = 1 + DEFAULT_INFRA_RETRIES if case.spec104_class == "infraestructura" else 1
    return attempts * per_attempt


def _abort_tracker() -> None:
    get_failure_tracker().abort(
        LLMFailure(FailureClass.configuracion, "task", "AuthenticationError"), "test"
    )


# ==================== AST: punto unico de llamada ====================


def _completion_call_sites(path: Path) -> list[tuple[str, str | None]]:
    """Llamadas `litellm.completion(...)`/`acompletion` (o importadas por nombre) en `path`."""
    rel = path.relative_to(REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "litellm"
        for alias in node.names
        if alias.name in COMPLETION_NAMES
    }
    sites: list[tuple[str, str | None]] = []

    def visit(node: ast.AST, func: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            if isinstance(child, ast.Call):
                target = child.func
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr in COMPLETION_NAMES
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "litellm"
                ) or (isinstance(target, ast.Name) and target.id in imported):
                    sites.append((rel, func))
            visit(child, func)

    visit(tree, None)
    return sites


def _production_files() -> list[Path]:
    return sorted(p for pkg in PRODUCTION_PACKAGES for p in (REPO_ROOT / pkg).rglob("*.py"))


class TestSingleCallPoint:
    def test_no_other_litellm_completion_in_production(self) -> None:
        offending = []
        for path in _production_files():
            for rel, func in _completion_call_sites(path):
                allowed = (rel, func) in ALLOWED_CALL_SITES or (rel, None) in ALLOWED_CALL_SITES
                if not allowed:
                    offending.append(f"{rel}:{func}")
        assert offending == [], (
            "Llamada a litellm.completion fuera de shared/llm/call.py (SPEC-104 D3): "
            f"{offending}. Delegar en shared.llm.call.checked_completion."
        )

    def test_common_call_has_exactly_one_completion(self) -> None:
        sites = _completion_call_sites(REPO_ROOT / "shared/llm/call.py")
        assert sites == [("shared/llm/call.py", "_raw_completion")]

    def test_probe_has_no_own_completion(self) -> None:
        # SPEC-106 FR-005: la sonda de conexion pasa por el punto de llamada comun.
        assert _completion_call_sites(REPO_ROOT / "shared/llm/config.py") == []

    def test_detector_finds_known_probe(self) -> None:
        # Control del detector: la herramienta de diagnostico si llama a litellm.completion.
        sites = _completion_call_sites(REPO_ROOT / "shared/utils/check_deployments.py")
        assert sites
        assert all(rel == "shared/utils/check_deployments.py" for rel, _ in sites)


# ==================== Caminos sin DSPy delegan en checked_completion ====================


def _spy_checked_completion(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    import shared.llm.call as call_mod

    roles: list[str] = []
    original = call_mod.checked_completion

    def spy(kwargs, messages, role, **kw):
        roles.append(role)
        return original(kwargs, messages, role, **kw)

    monkeypatch.setattr(call_mod, "checked_completion", spy)
    return roles


class TestPathsDelegate:
    def test_get_lm_function(self, mock_env, monkeypatch: pytest.MonkeyPatch) -> None:
        roles = _spy_checked_completion(monkeypatch)
        completion = MagicMock(return_value=make_completion_response("ok"))
        monkeypatch.setattr("litellm.completion", completion)

        out = LLMConfig.from_env("task").get_lm_function(role="reflection")("hola")

        assert out == "ok"
        assert roles == ["reflection"]
        assert completion.call_args.kwargs["num_retries"] == 0

    def test_call_llm(self, mock_env, monkeypatch: pytest.MonkeyPatch) -> None:
        roles = _spy_checked_completion(monkeypatch)
        completion = MagicMock(return_value=make_completion_response("ok"))
        monkeypatch.setattr("litellm.completion", completion)

        assert call_llm("hola", model_name="task", max_tokens=20) == "ok"

        assert roles == ["task"]
        assert completion.call_args.kwargs["num_retries"] == 0
        assert completion.call_args.kwargs["max_tokens"] == 20

    def test_rag_adapter_task_and_judge(self, mock_env, monkeypatch: pytest.MonkeyPatch) -> None:
        roles = _spy_checked_completion(monkeypatch)
        completion = MagicMock(return_value=make_completion_response("ok"))
        monkeypatch.setattr("litellm.completion", completion)
        adapter = SimpleRAGAdapter()
        messages = [{"role": "user", "content": "hola"}]

        assert adapter._complete(messages) == "ok"
        assert adapter._complete(messages, is_judge=True) == "ok"

        assert roles == ["task", "judge"]
        assert all(c.kwargs["num_retries"] == 0 for c in completion.call_args_list)

    def test_rag_adapter_has_no_own_retry(self) -> None:
        # FR-011: el reintento por content_filter de SimpleRAGAdapter se elimino.
        assert not hasattr(SimpleRAGAdapter, "_call_llm_with_retry")

    @pytest.mark.parametrize("case", RETRY_CASES, ids=lambda c: c.id)
    def test_get_lm_function_http_calls(self, case: FailurePayloadCase) -> None:
        # get_lm_function activa litellm.drop_params (como hoy): el 422 de OpenAI
        # da 2 llamadas y None (limite conocido), clasificado `configuracion`.
        assert case.expected_http_calls is not None
        lm_func = LLMConfig(**PROVIDER_KWARGS[case.provider], role="task").get_lm_function()

        with intercept_httpx(case) as calls, pytest.raises(LLMCallFailure) as exc_info:
            lm_func("hola")

        assert len(calls) == _expected_calls(case, case.expected_http_calls["num_retries_0"])
        assert exc_info.value.failure.clase.value == case.spec104_class


# ==================== SC-009 por caso a traves de dspy.Predict ====================


def _predict_with_checked_lm(case: FailurePayloadCase) -> tuple[Exception | None, int]:
    cfg = LLMConfig(**PROVIDER_KWARGS[case.provider], role="task", cache=False)
    lm = cfg.get_dspy_lm()
    predict = dspy.Predict("question -> answer")
    with dspy.context(lm=lm), intercept_httpx(case) as calls:
        try:
            predict(question="hola")
        except Exception as exc:
            return exc, len(calls)
    return None, len(calls)


class TestDspyPredictOneCallPerCase:
    @pytest.mark.parametrize("case", FAILING_CASES, ids=lambda c: c.id)
    def test_http_calls_and_class_per_case(self, case: FailurePayloadCase) -> None:
        exc, calls = _predict_with_checked_lm(case)

        assert isinstance(exc, LLMCallFailure), f"{case.id}: {type(exc).__name__}: {exc}"
        assert calls == _expected_calls(case)
        assert exc.failure.clase.value == case.spec104_class
        assert exc.failure.rol == "task"

    def test_adapter_fallback_only_on_parse_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Contrato de dspy (SPEC-105 FR-007, SC-009 de SPEC-104): ChatAdapter cae a
        # JSONAdapter solo ante AdapterParseError. Un texto no parseable repite la
        # llamada una vez; una falla de capa 1 (test de arriba) no la repite. Si un
        # upgrade vuelve a reintentar ante cualquier excepcion, el test de arriba falla.
        calls: list[dict] = []

        def fake_completion(**kwargs):
            calls.append(kwargs)
            return make_completion_response("texto sin campos de salida")

        monkeypatch.setattr(litellm, "completion", fake_completion)
        lm = LLMConfig(**PROVIDER_KWARGS["openai"], role="task", cache=False).get_dspy_lm()
        with dspy.context(lm=lm), pytest.raises(dspy.utils.exceptions.AdapterParseError):
            dspy.Predict("question -> answer")(question="hola")
        assert len(calls) == 2
        assert "response_format" not in calls[0]
        assert "response_format" in calls[1]


# ==================== RunAborted sin HTTP ====================


class TestRunAbortedWithoutHttp:
    def _ok_case(self, provider: str) -> FailurePayloadCase:
        return next(
            c
            for c in ALL_FAILURE_CASES
            if c.provider == provider and c.case_type == "http_200" and c.spec104_class == "ok"
        )

    def test_dspy_predict(self) -> None:
        _abort_tracker()
        exc, calls = _predict_with_checked_lm(self._ok_case("openai"))

        assert isinstance(exc, RunAborted)
        assert calls == 0

    def test_get_lm_function(self) -> None:
        _abort_tracker()
        lm_func = LLMConfig(**PROVIDER_KWARGS["openai"], role="task").get_lm_function()

        with intercept_httpx(self._ok_case("openai")) as calls, pytest.raises(RunAborted):
            lm_func("hola")

        assert calls == []

    def test_call_llm(self, mock_env, monkeypatch: pytest.MonkeyPatch) -> None:
        _abort_tracker()
        completion = MagicMock(return_value=make_completion_response("ok"))
        monkeypatch.setattr("litellm.completion", completion)

        with pytest.raises(RunAborted):
            call_llm("hola", model_name="task")

        assert completion.call_count == 0

    def test_rag_adapter(self, mock_env, monkeypatch: pytest.MonkeyPatch) -> None:
        _abort_tracker()
        completion = MagicMock(return_value=make_completion_response("ok"))
        monkeypatch.setattr("litellm.completion", completion)

        with pytest.raises(RunAborted):
            SimpleRAGAdapter()._complete([{"role": "user", "content": "hola"}], is_judge=True)

        assert completion.call_count == 0

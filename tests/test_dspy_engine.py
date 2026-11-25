"""
SPEC-105 FR-002 / FR-006 / FR-007 / FR-012: engine propio de DSPy (`CheckedEngine`).

- Contrato de engine de dspy 3.5 (`dspy.LM(engine=...)`): una excepcion que no es
  `dspy.LMError` sale como `LMUnexpectedError` y una `dspy.LMError` pasa por
  identidad. Por eso `dspy_visible` (si dspy cambia esa regla, falla aca).
- `LLMCallFailure` y `RunAborted` llegan al codigo del repo con su clase, su
  `failure` y su causa, con una sola llamada HTTP.
- Traduccion `Request` -> Chat Completions propia y estricta (`request_to_chat`).
- Prompt de la tarea (FR-012): con `configure_dspy` (`ChatAdapter`) y con
  `JSONAdapter`, los mensajes que llegan a LiteLLM son byte a byte los de dspy
  3.4.1 (`tests/fixtures/task_prompt_dspy_3_4_1.json`, generado con el codigo
  real de dspy 3.4.1).
- Los entry points configuran dspy solo con `configure_dspy`.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Literal

import dspy
import litellm
import pytest
from dspy.lm15 import (
    Config,
    FunctionTool,
    ImagePart,
    Message,
    Reasoning,
    Request,
    Response,
    TextPart,
    UnsupportedFeatureError,
    Usage,
)

from shared.llm import LLMCallFailure, LLMConfig, RunAborted, get_failure_tracker
from shared.llm.dspy_lm import (
    CheckedEngine,
    checked_lm,
    configure_dspy,
    dspy_reflection_proposer,
    dspy_visible,
    request_to_chat,
)
from shared.llm.errors import EmptyResponseError
from shared.llm.failures import FailureClass, LLMFailure
from tests.conftest import make_completion_response, patch_litellm_completion

REPO = Path(__file__).resolve().parents[1]
GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "task_prompt_dspy_3_4_1.json").read_text(encoding="utf-8")
)
MODEL = "openai/gpt-4o-mini"


def _lm(role: str = "task", **kwargs: Any) -> dspy.LM:
    return LLMConfig(model=MODEL, api_key="key", role=role, cache=False, **kwargs).get_dspy_lm()


def _ok(content: str = "ok", finish_reason: str = "stop") -> Any:
    return make_completion_response(content, finish_reason)


def _record(monkeypatch: pytest.MonkeyPatch, answer: Any) -> list[dict[str, Any]]:
    """Simula `litellm.completion`; devuelve la lista de kwargs recibidos."""
    calls: list[dict[str, Any]] = []

    def fake(request: dict[str, Any], num_retries: int | None) -> Any:
        calls.append(request)
        return answer(request) if callable(answer) else answer

    patch_litellm_completion(monkeypatch, fake)
    return calls


# ==================== Contrato de engine de dspy ====================


class _RaisingEngine:
    def __init__(self, exc: BaseException):
        self.exc = exc

    def complete(self, request: Request) -> Response:
        raise self.exc


class TestDspyEngineContract:
    def test_engine_receives_request_and_returns_response(self) -> None:
        seen: list[Request] = []

        class Engine:
            def complete(self, request: Request) -> Response:
                seen.append(request)
                return Response(
                    id=None,
                    model=request.model,
                    message=Message.assistant("hola"),
                    finish_reason="stop",
                    usage=Usage(input_tokens=1, output_tokens=1),
                )

        lm = dspy.LM(MODEL, engine=Engine(), model_type="chat", cache=False, num_retries=0)
        assert lm("hi") == ["hola"]
        assert isinstance(seen[0], Request)
        assert seen[0].messages == (Message.user("hi"),)

    def test_non_lm_error_is_wrapped(self) -> None:
        """La regla que obliga a `dspy_visible`: dspy disfraza lo que no es suyo."""
        failure = LLMCallFailure(LLMFailure(clase=FailureClass.sin_texto, rol="task", causa="x"))
        lm = dspy.LM(MODEL, engine=_RaisingEngine(failure), cache=False, num_retries=0)
        with pytest.raises(dspy.utils.exceptions.LMUnexpectedError) as exc_info:
            lm("hi")
        assert exc_info.value.__cause__ is failure

    def test_lm_error_passes_by_identity(self) -> None:
        failure = LLMCallFailure(LLMFailure(clase=FailureClass.sin_texto, rol="task", causa="x"))
        visible = dspy_visible(failure, MODEL)
        lm = dspy.LM(MODEL, engine=_RaisingEngine(visible), cache=False, num_retries=0)
        with pytest.raises(LLMCallFailure) as exc_info:
            lm("hi")
        assert exc_info.value is visible

    def test_engine_hints_are_read_by_dspy(self) -> None:
        lm = _lm()
        assert lm.supports_response_schema is lm.engine.supports_response_schema
        assert lm.supported_params == lm.engine.supported_params


# ==================== dspy_visible ====================


class TestDspyVisible:
    def test_keeps_class_attributes_message_and_cause(self) -> None:
        cause = ValueError("origen")
        try:
            try:
                raise cause
            except ValueError as exc:
                raise EmptyResponseError("task", "length", FailureClass.presupuesto) from exc
        except EmptyResponseError as exc:
            original = exc
        visible = dspy_visible(original, MODEL)
        assert isinstance(visible, EmptyResponseError)
        assert isinstance(visible, dspy.LMError)
        assert type(visible).__name__ == "EmptyResponseError"
        assert visible.failure is original.failure
        assert visible.finish_reason == "length"
        assert str(visible) == str(original)
        assert visible.__cause__ is cause
        assert visible.model == MODEL

    def test_run_aborted_stays_run_aborted(self) -> None:
        failure = LLMFailure(clase=FailureClass.configuracion, rol="task", causa="x")
        visible = dspy_visible(RunAborted(failure, "motivo"), MODEL)
        assert isinstance(visible, RunAborted)
        assert not isinstance(visible, LLMCallFailure)
        assert visible.motivo == "motivo"

    def test_already_visible_is_returned_as_is(self) -> None:
        failure = LLMCallFailure(LLMFailure(clase=FailureClass.sin_texto, rol="task", causa="x"))
        visible = dspy_visible(failure, MODEL)
        assert dspy_visible(visible, MODEL) is visible


# ==================== Fallas a traves de dspy ====================


class TestFailuresThroughDspy:
    def test_call_failure_reaches_repo_with_litellm_cause(self, monkeypatch) -> None:
        def answer(request: dict[str, Any]) -> Any:
            raise litellm.AuthenticationError("bad key", llm_provider="openai", model="gpt-4o-mini")

        calls = _record(monkeypatch, answer)
        with pytest.raises(LLMCallFailure) as exc_info:
            _lm()("hi")
        assert exc_info.value.failure.clase == FailureClass.configuracion
        assert type(exc_info.value.__cause__).__name__ == "AuthenticationError"
        assert len(calls) == 1

    def test_run_aborted_reaches_repo(self, monkeypatch) -> None:
        calls = _record(monkeypatch, _ok())
        failure = LLMFailure(clase=FailureClass.configuracion, rol="task", causa="x")
        get_failure_tracker().abort(failure, "test")
        with pytest.raises(RunAborted):
            _lm()("hi")
        assert calls == []

    def test_empty_response_is_one_call_without_adapter_fallback(self, monkeypatch) -> None:
        calls = _record(monkeypatch, _ok(None, "length"))
        with dspy.context(lm=_lm()), pytest.raises(EmptyResponseError):
            dspy.Predict("question -> answer")(question="q")
        assert len(calls) == 1


# ==================== request_to_chat ====================


def _request(**kwargs: Any) -> Request:
    return Request(model=MODEL, **{"messages": (Message.user("hola"),), **kwargs})


class TestRequestToChat:
    def test_system_and_messages(self) -> None:
        messages, params = request_to_chat(
            _request(
                system="sis",
                messages=(Message.user("u"), Message.assistant("a"), Message.user("v")),
            )
        )
        assert messages == [
            {"role": "system", "content": "sis"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "v"},
        ]
        assert params == {}

    def test_several_text_parts_are_blocks(self) -> None:
        message = Message(role="user", parts=(TextPart("a"), TextPart("b")))
        messages, _ = request_to_chat(_request(messages=(message,)))
        assert messages[0]["content"] == [
            {"type": "text", "text": "a"},
            {"type": "text", "text": "b"},
        ]

    def test_config_fields(self) -> None:
        config = Config(
            max_tokens=50,
            temperature=0.2,
            stop=("X",),
            response_format={"type": "json_object"},
            extensions={"custom": 1},
        )
        _, params = request_to_chat(_request(config=config), "max_completion_tokens")
        assert params == {
            "max_completion_tokens": 50,
            "temperature": 0.2,
            "stop": ["X"],
            "response_format": {"type": "json_object"},
            "custom": 1,
        }

    @pytest.mark.parametrize(
        "request_kwargs",
        [
            {"tools": (FunctionTool(name="f"),)},
            {"messages": (Message(role="user", parts=(ImagePart(url="https://x/y.png"),)),)},
            {"config": Config(reasoning=Reasoning(effort="low"))},
            {"config": Config(top_k=3)},
        ],
        ids=["tools", "image", "reasoning", "top_k"],
    )
    def test_unsupported_is_refused(self, request_kwargs: dict[str, Any]) -> None:
        with pytest.raises(UnsupportedFeatureError):
            request_to_chat(_request(**request_kwargs))

    def test_unsupported_fails_before_calling(self, monkeypatch) -> None:
        calls = _record(monkeypatch, _ok())
        lm = _lm()
        with pytest.raises(dspy.utils.exceptions.LMUnsupportedFeatureError):
            lm(_request(config=Config(top_k=3)))
        assert calls == []


# ==================== Engine: kwargs y respuesta ====================


class TestCheckedEngine:
    def test_params_and_request_overrides(self, monkeypatch) -> None:
        calls = _record(monkeypatch, _ok())
        lm = _lm(temperature=0.3, max_tokens=300)
        # dspy no recibe parametros de generacion ni de conexion (FR-002).
        assert all(value is None for value in lm.kwargs.values())
        lm(_request(config=Config(response_format={"type": "json_object"})))
        sent = calls[0]
        assert sent["model"] == MODEL
        assert sent["temperature"] == 0.3
        assert sent["max_tokens"] == 300
        assert sent["api_key"] == "key"
        assert sent["response_format"] == {"type": "json_object"}
        assert sent["messages"] == [{"role": "user", "content": "hola"}]

    def test_reasoning_model_uses_max_completion_tokens(self, monkeypatch) -> None:
        calls = _record(monkeypatch, _ok())
        lm = LLMConfig(model="openai/gpt-5-mini", api_key="key", cache=False).get_dspy_lm()
        assert lm.engine.max_tokens_param == "max_completion_tokens"
        lm(
            Request(
                model="openai/gpt-5-mini",
                messages=(Message.user("hola"),),
                config=Config(max_tokens=20000),
            )
        )
        assert calls[0]["max_completion_tokens"] == 20000
        assert "max_tokens" not in calls[0]

    def test_response_text_and_usage(self, monkeypatch) -> None:
        _record(monkeypatch, make_completion_response("hola", prompt_tokens=7, completion_tokens=3))
        response = _lm()(_request())
        assert response.text == "hola"
        assert response.finish_reason == "stop"
        assert (response.usage.input_tokens, response.usage.output_tokens) == (7, 3)

    def test_reflection_prompt_is_one_user_message(self, monkeypatch) -> None:
        """NEEDS CLARIFICATION de SPEC-105 (dspy 3.5): la llamada del proposer al
        LM de reflexion (texto) pasa por el engine como un unico mensaje `user`."""
        calls = _record(monkeypatch, _ok("```\nNueva instruccion\n```"))
        proposer = dspy_reflection_proposer(_lm("reflection"))
        assert proposer({"p": "vieja"}, {"p": [{"Feedback": "x"}]}, ["p"]) == {
            "p": "Nueva instruccion"
        }
        assert len(calls) == 1
        assert [m["role"] for m in calls[0]["messages"]] == ["user"]

    def test_checked_lm_has_no_dspy_retries_nor_cache(self) -> None:
        lm = checked_lm(CheckedEngine(MODEL))
        assert lm.num_retries == 0
        assert lm.cache is False


# ==================== Prompt de la tarea (FR-012) ====================


class CVSig(dspy.Signature):
    """Extrae los datos del CV."""

    cv_text: str = dspy.InputField(desc="texto del CV")
    nombre: str = dspy.OutputField(desc="nombre completo")
    anios: int = dspy.OutputField(desc="anios de experiencia")
    nivel: Literal["junior", "senior"] = dspy.OutputField()
    skills: list[str] = dspy.OutputField()


def _cv_predict() -> dspy.Predict:
    predict = dspy.Predict(CVSig)
    predict.demos = [
        dspy.Example(
            cv_text="Ana, 3 anios", nombre="Ana", anios=3, nivel="junior", skills=["python"]
        )
    ]
    return predict


CHAT_ANSWER = (
    "[[ ## nombre ## ]]\nJuan\n\n[[ ## anios ## ]]\n10\n\n[[ ## nivel ## ]]\nsenior\n\n"
    '[[ ## skills ## ]]\n["go"]\n\n[[ ## completed ## ]]'
)
JSON_ANSWER = '{"nombre": "Juan", "anios": 10, "nivel": "senior", "skills": ["go"]}'


class TestTaskPromptUnchanged:
    def test_configure_dspy_pins_chat_adapter(self, monkeypatch) -> None:
        captured: dict[str, Any] = {}
        monkeypatch.setattr(dspy, "configure", lambda **kwargs: captured.update(kwargs))
        lm = _lm()
        configure_dspy(lm, track_usage=False)
        assert captured["lm"] is lm
        assert type(captured["adapter"]) is dspy.ChatAdapter
        assert captured["track_usage"] is False

    def test_chat_adapter_messages_match_dspy_3_4_1(self, monkeypatch) -> None:
        calls = _record(monkeypatch, _ok(CHAT_ANSWER))
        with dspy.context(lm=_lm(), adapter=dspy.ChatAdapter()):
            pred = _cv_predict()(cv_text="Juan, 10 anios")
        assert pred.anios == 10
        assert len(calls) == 1
        assert calls[0]["messages"] == GOLDEN["messages"]["ChatAdapter"]

    def test_json_adapter_messages_match_dspy_3_4_1(self, monkeypatch) -> None:
        calls = _record(monkeypatch, _ok(JSON_ANSWER))
        with dspy.context(lm=_lm(), adapter=dspy.JSONAdapter()):
            pred = _cv_predict()(cv_text="Juan, 10 anios")
        assert pred.nivel == "senior"
        assert len(calls) == 1
        assert calls[0]["messages"] == GOLDEN["messages"]["JSONAdapter"]
        assert "response_format" in calls[0]


# ==================== Entry points: solo configure_dspy ====================


def _bare_dspy_configure_calls(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "configure"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "dspy"
    ]


class TestEntryPointsUseConfigureDspy:
    def test_no_bare_dspy_configure_in_production(self) -> None:
        allowed = REPO / "shared" / "llm" / "dspy_lm.py"
        offenders = {
            str(f.relative_to(REPO)): lines
            for d in ("shared", "dspy_gepa_poc", "gepa_standalone")
            for f in sorted((REPO / d).rglob("*.py"))
            if f != allowed and (lines := _bare_dspy_configure_calls(f))
        }
        assert offenders == {}

    def test_detector_finds_bare_configure(self, tmp_path: Path) -> None:
        probe = tmp_path / "probe.py"
        probe.write_text("import dspy\ndspy.configure(lm=None)\n", encoding="utf-8")
        assert _bare_dspy_configure_calls(probe) == [2]

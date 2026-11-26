"""
SPEC-105 FR-005 / FR-007 / SC-005 / SC-006: el repo usa solo API publica de
`dspy`, `gepa` y `litellm`, y cada superficie publica que usa tiene un contrato
que falla en CI si un upgrade la cambia de forma incompatible.

- SC-005: ningun modulo de produccion importa simbolos privados (prefijo `_`) de
  esas librerias ni accede a atributos privados por la ruta del modulo.
- FR-007: `SURFACES` es el inventario de superficies publicas usadas; cada una
  tiene contratos (firma, tipo devuelto o comportamiento del que dependemos),
  aca o en el modulo de tests de su dominio (`test_dspy_engine`,
  `test_single_call_point`, `test_reflection_guard`, `test_litellm_failure_mapping`).
- SC-006: `MUTATIONS` simula con `monkeypatch` un cambio incompatible de cada
  superficie y verifica que su contrato se pone rojo
  (`TestContractsDetectIncompatibleChanges`). Toda superficie de `SURFACES`
  MUST tener al menos una mutacion. Las mutaciones tocan internos de las
  librerias solo en tests, para simular la version nueva; el codigo de
  produccion sigue sin usarlos (SC-005).
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import dspy
import dspy.clients.errors
import dspy.clients.execution
import dspy.lm15
import gepa
import gepa.core.adapter
import gepa.proposer.reflective_mutation.reflective_mutation as gepa_reflective_mutation
import litellm
import pytest
from dspy.teleprompt import LabeledFewShot
from dspy.teleprompt.gepa.gepa import DspyGEPAResult

from gepa_standalone.adapters.base_adapter import BaseAdapter
from tests import test_dspy_engine as engine_tests
from tests import test_litellm_failure_mapping as litellm_tests
from tests import test_reflection_guard as reflection_tests
from tests import test_single_call_point as call_point_tests
from tests.litellm_failure_payloads import ALL_HTTP_200_CASES

REPO = Path(__file__).resolve().parents[1]
PRODUCTION_DIRS = ("shared", "dspy_gepa_poc", "gepa_standalone")
LIBS = frozenset({"dspy", "gepa", "litellm"})


def _production_files() -> list[Path]:
    return sorted(
        f for d in PRODUCTION_DIRS for f in (REPO / d).rglob("*.py") if "__pycache__" not in f.parts
    )


def _private_lib_uses(tree: ast.AST) -> list[str]:
    """Usos de simbolos privados de `LIBS` en un modulo (imports y atributos)."""
    found: list[str] = []
    lib_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] in LIBS:
                    lib_aliases.add(alias.asname or parts[0])
                    if any(p.startswith("_") for p in parts):
                        found.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            parts = node.module.split(".")
            if parts[0] not in LIBS:
                continue
            if any(p.startswith("_") for p in parts):
                found.append(f"from {node.module} import ...")
            found.extend(
                f"from {node.module} import {a.name}" for a in node.names if a.name.startswith("_")
            )
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            base = node.value
            while isinstance(base, ast.Attribute):
                base = base.value
            if (
                isinstance(base, ast.Name)
                and base.id in lib_aliases
                and not node.attr.startswith("__")
            ):
                found.append(f"{ast.unparse(node)}")
    return found


class TestNoPrivateLibrarySymbols:
    def test_production_code_uses_only_public_symbols(self) -> None:
        offenders = {
            str(f.relative_to(REPO)): uses
            for f in _production_files()
            if (uses := _private_lib_uses(ast.parse(f.read_text(encoding="utf-8"))))
        }
        assert offenders == {}

    @pytest.mark.parametrize(
        "source",
        [
            "from dspy.adapters.json_adapter import _get_structured_outputs_response_format",
            "from litellm._logging import verbose_logger",
            "import dspy\ndspy.clients.lm._private()",
            "import gepa._internal",
        ],
    )
    def test_detector_flags_private_use(self, source: str) -> None:
        # SC-005: agregar un import privado hace fallar el test de arriba.
        assert _private_lib_uses(ast.parse(source))

    @pytest.mark.parametrize(
        "source",
        [
            "from dspy.utils.exceptions import AdapterParseError",
            "from dspy_gepa_poc.metrics import _score_field",
            "import dspy\ndspy.Predict.__init__",
        ],
    )
    def test_detector_ignores_public_and_repo_symbols(self, source: str) -> None:
        assert not _private_lib_uses(ast.parse(source))


def _params(fn) -> set[str]:
    return set(inspect.signature(fn).parameters)


class TestOptimizerConstructionContracts:
    def test_dspy_gepa_accepts_the_parameters_the_repo_passes(self) -> None:
        # `GEPAOptimizer` y `tests/conftest.py::repo_dspy_gepa`.
        assert {
            "metric",
            "reflection_lm",
            "instruction_proposer",
            "gepa_kwargs",
            "max_metric_calls",
            "auto",
            "track_stats",
            "reflection_minibatch_size",
            "skip_perfect_score",
            "candidate_selection_strategy",
            "use_merge",
            "max_merge_invocations",
        } <= _params(dspy.GEPA.__init__)

    def test_gepa_optimize_accepts_the_parameters_the_repo_passes(self) -> None:
        # `gepa_standalone/universal_optimizer.py`.
        assert {
            "seed_candidate",
            "trainset",
            "valset",
            "adapter",
            "task_lm",
            "custom_candidate_proposer",
            "max_metric_calls",
            "skip_perfect_score",
            "display_progress_bar",
            "callbacks",
        } <= _params(gepa.optimize)

    def test_proposal_fn_protocol_matches_the_repo_proposer(self) -> None:
        from gepa.core.adapter import ProposalFn

        from shared.llm.reflection import ReflectionProposer

        expected = ["candidate", "reflective_dataset", "components_to_update"]
        assert list(inspect.signature(ProposalFn.__call__).parameters)[1:] == expected
        assert list(inspect.signature(ReflectionProposer.__call__).parameters)[1:] == expected

    def test_dspy_gepa_rejects_unknown_parameters(self) -> None:
        # Sin filtro por firma en `GEPAOptimizer`: un parametro que desaparece falla.
        with pytest.raises(TypeError):
            dspy.GEPA(
                metric=lambda *a, **k: 0.0,
                reflection_lm=lambda prompt: "",
                auto="light",
                parametro_inexistente=1,
            )


# ==================== Inventario de superficies publicas (FR-007) ====================

SURFACES: dict[str, str] = {
    "dspy.LM(engine)": "`dspy.LM(model, engine=..., cache, num_retries)` (`checked_lm`)",
    "engine.complete": "contrato de engine: dspy llama `engine.complete(Request) -> Response`",
    "dspy.errors.identity": "`dspy.LMError` pasa por identidad; lo demas sale `LMUnexpectedError`",
    "engine.hints": "dspy lee del engine `supports_response_schema` / `supported_params`",
    "dspy.lm15.types": "`Request`, `Message`, `TextPart`, `Response`, `Usage` (`request_to_chat`)",
    "dspy.lm15.Config": "campos de `Config`: los traducidos y los rechazados son todos conocidos",
    "dspy.exceptions": "`dspy.LMError.default_code`, `AdapterParseError`, `LMUnexpectedError`",
    "dspy.GEPA.params": "`dspy.GEPA(instruction_proposer, gepa_kwargs, ...)`, sin `**kwargs`",
    "dspy.GEPA.proposer": "`dspy.GEPA` usa el `instruction_proposer` del repo",
    "dspy.GEPA.callbacks": "`gepa_kwargs` con `callbacks` llega a GEPA",
    "dspy.GEPA.result": "`compile(student, trainset, valset)` y `DspyGEPAResult`",
    "dspy.ChainOfThought": "`ChainOfThought(signature, rationale_field_type=str)`",
    "dspy.ChatAdapter": "mensajes de `ChatAdapter` (golden de dspy 3.4.1)",
    "dspy.JSONAdapter": "mensajes y `response_format` de `JSONAdapter` (golden de dspy 3.4.1)",
    "dspy.adapter.fallback": "`ChatAdapter` cae a `JSONAdapter` solo ante `AdapterParseError`",
    "dspy.context": "`dspy.context(lm=..., adapter=...)` / `dspy.configure` fijan el adapter",
    "dspy.Evaluate": "`Evaluate(devset, metric, ...)(program, metric=)` -> `.score` y `.results`",
    "dspy.Module.named_predictors": "`named_predictors()` y `signature.instructions`",
    "dspy.LabeledFewShot": "`LabeledFewShot(k).compile(student, trainset=)`",
    "gepa.optimize": "`gepa.optimize(custom_candidate_proposer, callbacks, ...)`",
    "gepa.ProposalFn": "protocolo `(candidate, reflective_dataset, components_to_update)`",
    "gepa.callbacks": "`on_proposal_start(event)` con la clave `iteration`",
    "gepa.EvaluationBatch": "`EvaluationBatch(outputs, scores, trajectories)`",
    "gepa.GEPAAdapter": "protocolo `evaluate` / `make_reflective_dataset` (`BaseAdapter`)",
    "gepa.GEPAResult": "`best_candidate`, `candidates`, `val_aggregate_scores`, `best_idx`, ...",
    "litellm.completion": "parametros que pasa el punto de llamada (`checked_response`)",
    "litellm.exceptions": "clase, `status_code` y `body` de las excepciones (SPEC-104 SC-009)",
    "litellm.response": "`finish_reason`, `content`, `refusal` de la respuesta 200 (SPEC-104)",
    "litellm.capabilities": "`supports_*` y `get_supported_openai_params` (pistas del engine)",
    "litellm.drop_params": "global `litellm.drop_params` (`get_lm_function`)",
}

MODEL = "openai/gpt-4o-mini"

# Campos de `dspy.lm15.Config` conocidos por `request_to_chat`: los traducidos
# y los que rechaza con `UnsupportedFeatureError`. Uno nuevo hace fallar el
# contrato en CI, antes de una corrida (D-027).
KNOWN_CONFIG_FIELDS = frozenset(
    {
        "max_tokens",
        "temperature",
        "top_p",
        "top_k",
        "stop",
        "response_format",
        "tool_choice",
        "reasoning",
        "cache",
        "seed",
        "frequency_penalty",
        "presence_penalty",
        "service_tier",
        "user_id",
        "store",
        "logprobs",
        "probabilities",
        "extensions",
    }
)


def _field_names(cls: type) -> set[str]:
    return {f.name for f in dataclasses.fields(cls)}


class _Echo(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.Predict("question -> answer")

    def forward(self, question: str) -> dspy.Prediction:
        return dspy.Prediction(answer=question)


def _exact(example: Any, pred: Any, trace: Any = None) -> float:
    return float(example.answer == pred.answer)


def _qa(question: str, answer: str) -> dspy.Example:
    return dspy.Example(question=question, answer=answer).with_inputs("question")


class TestDspyContracts:
    def test_lm15_types_keep_the_fields_the_engine_uses(self) -> None:
        lm15 = dspy.lm15
        assert {"model", "messages", "system", "tools", "config"} <= _field_names(lm15.Request)
        assert {"role", "parts", "continuation"} <= _field_names(lm15.Message)
        assert {"text", "continuation"} <= _field_names(lm15.TextPart)
        assert {"id", "model", "message", "finish_reason", "usage"} <= _field_names(lm15.Response)
        assert {"input_tokens", "output_tokens"} <= _field_names(lm15.Usage)
        message = lm15.Message.assistant("hola")
        assert message.role == "assistant"
        assert [part.text for part in message.parts] == ["hola"]
        assert issubclass(lm15.UnsupportedFeatureError, Exception)

    def test_lm15_config_fields_are_known(self) -> None:
        assert _field_names(dspy.lm15.Config) == KNOWN_CONFIG_FIELDS

    def test_exceptions_the_repo_uses(self) -> None:
        exceptions = dspy.utils.exceptions
        assert isinstance(dspy.LMError.default_code, str)
        assert issubclass(exceptions.LMUnexpectedError, dspy.LMError)
        assert issubclass(exceptions.AdapterParseError, Exception)
        assert not issubclass(exceptions.AdapterParseError, dspy.LMError)

    def test_gepa_compile_and_detailed_results(self) -> None:
        # `GEPAOptimizer.compile` y `reflexio_declarativa` (evolucion y estadisticas).
        assert {"student", "trainset", "valset"} <= _params(dspy.GEPA.compile)
        assert {
            "candidates",
            "val_aggregate_scores",
            "discovery_eval_counts",
            "total_metric_calls",
            "num_full_val_evals",
        } <= _field_names(DspyGEPAResult)
        assert isinstance(getattr(DspyGEPAResult, "best_idx", None), property)
        assert isinstance(getattr(DspyGEPAResult, "best_candidate", None), property)

    def test_evaluate_returns_score_and_results(self) -> None:
        # `run_evaluate` y `reflexio_declarativa._eval_repeated`: score en porcentaje.
        data = [_qa("a", "a"), _qa("b", "otra")]
        evaluator = dspy.evaluate.Evaluate(
            devset=data, metric=_exact, num_threads=1, display_progress=False
        )
        result = evaluator(_Echo(), metric=_exact)
        assert result.score == 50.0
        assert [(ex.question, pred.answer, score) for ex, pred, score in result.results] == [
            ("a", "a", 1.0),
            ("b", "b", 0.0),
        ]

    def test_named_predictors_and_instructions(self) -> None:
        # `call_failures.instructions_snapshot` y la lectura de candidatos.
        program = _Echo()
        program.predict.signature = program.predict.signature.with_instructions("Responder.")
        predictors = list(program.named_predictors())
        assert [name for name, _ in predictors] == ["predict"]
        assert predictors[0][1].signature.instructions == "Responder."

    def test_labeled_few_shot(self) -> None:
        data = [_qa(f"q{i}", f"a{i}") for i in range(3)]
        compiled = LabeledFewShot(k=2).compile(_Echo(), trainset=data)
        assert len(compiled.predict.demos) == 2


class TestGepaContracts:
    def test_evaluation_batch_fields(self) -> None:
        assert {"outputs", "scores", "trajectories"} <= _field_names(gepa.EvaluationBatch)
        batch = gepa.EvaluationBatch(outputs=["o"], scores=[1.0], trajectories=None)
        assert (batch.outputs, batch.scores, batch.trajectories) == (["o"], [1.0], None)

    def test_gepa_adapter_protocol_matches_base_adapter(self) -> None:
        for method in ("evaluate", "make_reflective_dataset"):
            expected = list(inspect.signature(getattr(gepa.GEPAAdapter, method)).parameters)
            assert list(inspect.signature(getattr(BaseAdapter, method)).parameters) == expected

    def test_gepa_result_attributes(self) -> None:
        # `universal_optimizer` (resultado de `gepa.optimize`).
        assert {"candidates", "val_aggregate_scores", "total_metric_calls"} <= _field_names(
            gepa.GEPAResult
        )
        assert isinstance(getattr(gepa.GEPAResult, "best_idx", None), property)
        assert isinstance(getattr(gepa.GEPAResult, "best_candidate", None), property)

    def test_proposal_start_event_has_iteration(self) -> None:
        from gepa.core.callbacks import GEPACallback, ProposalStartEvent

        assert "iteration" in ProposalStartEvent.__annotations__
        params = list(inspect.signature(GEPACallback.on_proposal_start).parameters)
        assert params == ["self", "event"]


class TestLitellmContracts:
    def test_completion_accepts_the_parameters_the_repo_passes(self) -> None:
        # `checked_response` / `LLMConfig.to_kwargs` / `CheckedEngine.request_kwargs`.
        params = inspect.signature(litellm.completion).parameters
        assert {
            "model",
            "messages",
            "temperature",
            "top_p",
            "seed",
            "stop",
            "max_tokens",
            "max_completion_tokens",
            "frequency_penalty",
            "presence_penalty",
            "response_format",
            "timeout",
            "api_key",
            "api_version",
            "thinking",
        } <= set(params)
        # `api_base`, `num_retries` y `output_config` viajan por **kwargs.
        assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())

    def test_capability_helpers(self) -> None:
        # Como los llama `CheckedEngine`.
        assert litellm.supports_function_calling(model=MODEL) is True
        assert litellm.supports_reasoning(MODEL) is False
        assert litellm.supports_response_schema(model=MODEL, custom_llm_provider="openai") is True
        supported = litellm.get_supported_openai_params(model=MODEL, custom_llm_provider="openai")
        assert "response_format" in supported

    def test_drop_params_global(self) -> None:
        assert isinstance(litellm.drop_params, bool)


# ==================== SC-006: el contrato se pone rojo ====================


@dataclass(frozen=True)
class Mutation:
    """Cambio incompatible simulado de una superficie y el contrato que lo detecta."""

    surface: str
    change: str
    apply: Callable[[pytest.MonkeyPatch], None]
    contract: Callable[[pytest.FixtureRequest], None]
    raises: type[BaseException] | tuple[type[BaseException], ...] = AssertionError


def _mp(request: pytest.FixtureRequest) -> pytest.MonkeyPatch:
    return request.getfixturevalue("monkeypatch")


def _litellm_isolated(request: pytest.FixtureRequest) -> pytest.MonkeyPatch:
    """Los globales que fijan los fixtures autouse de los modulos de LiteLLM."""
    mp = _mp(request)
    mp.setattr(litellm, "drop_params", False)
    mp.setattr(litellm, "num_retries", None)
    mp.setattr(litellm, "suppress_debug_info", True)
    return mp


# ---- dspy ----


def _lm_without_engine(mp: pytest.MonkeyPatch) -> None:
    class LM(dspy.LM):
        def __init__(self, model: str, *, engine: Any = None, **kwargs: Any) -> None:
            if engine is not None:
                raise TypeError("LM.__init__() got an unexpected keyword argument 'engine'")
            super().__init__(model, **kwargs)

    mp.setattr(dspy, "LM", LM)


def _engine_method_renamed(mp: pytest.MonkeyPatch) -> None:
    """dspy pasa a llamar `engine.generate(request)` en lugar de `complete`."""
    original = dspy.clients.execution._attempt

    class Renamed:
        def __init__(self, backend: Any) -> None:
            self._backend = backend

        def __getattr__(self, name: str) -> Any:
            return getattr(self._backend, name)

        def complete(self, request: Any) -> Any:
            return self._backend.generate(request)

    def attempt(lm: Any, call: Any, backend: Any, *args: Any, **kwargs: Any) -> Any:
        return original(lm, call, Renamed(backend), *args, **kwargs)

    mp.setattr(dspy.clients.execution, "_attempt", attempt)


def _lm_errors_wrapped_too(mp: pytest.MonkeyPatch) -> None:
    """dspy deja de preservar `dspy.LMError` por identidad."""
    unexpected = dspy.utils.exceptions.LMUnexpectedError

    def wrap_error(exc: Exception, *, model: str, provider: str | None = None) -> Exception:
        return unexpected(str(exc), model=model, provider=provider)

    mp.setattr(dspy.clients.errors, "wrap_error", wrap_error)


def _hints_not_read_from_engine(mp: pytest.MonkeyPatch) -> None:
    mp.setattr(dspy.LM, "supported_params", property(lambda self: set()))


def _usage_fields_renamed(mp: pytest.MonkeyPatch) -> None:
    usage = dataclasses.make_dataclass(
        "Usage",
        [
            ("prompt_tokens", int | None, dataclasses.field(default=None)),
            ("completion_tokens", int | None, dataclasses.field(default=None)),
        ],
    )
    mp.setattr(dspy.lm15, "Usage", usage)


def _config_new_field(mp: pytest.MonkeyPatch) -> None:
    config = dataclasses.make_dataclass(
        "Config",
        [("verbosity", str | None, dataclasses.field(default=None))],
        bases=(dspy.lm15.Config,),
        frozen=True,
    )
    mp.setattr(dspy.lm15, "Config", config)


def _lm_error_replaced(mp: pytest.MonkeyPatch) -> None:
    mp.setattr(dspy, "LMError", type("LMError", (Exception,), {}))


def _gepa_without_instruction_proposer_param(mp: pytest.MonkeyPatch) -> None:
    original = dspy.GEPA.__init__

    def init(self: Any, metric: Any, *, reflection_lm: Any = None, **kwargs: Any) -> None:
        original(self, metric, reflection_lm=reflection_lm, **kwargs)

    mp.setattr(dspy.GEPA, "__init__", init)


def _gepa_ignores_unknown_params(mp: pytest.MonkeyPatch) -> None:
    original = dspy.GEPA.__init__
    known = _params(original)

    def init(self: Any, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **{k: v for k, v in kwargs.items() if k in known})

    mp.setattr(dspy.GEPA, "__init__", init)


def _gepa_drops(param: str) -> Callable[[pytest.MonkeyPatch], None]:
    """`dspy.GEPA` acepta `param` pero ya no lo usa."""

    def apply(mp: pytest.MonkeyPatch) -> None:
        original = dspy.GEPA.__init__

        def init(self: Any, *args: Any, **kwargs: Any) -> None:
            kwargs.pop(param, None)
            original(self, *args, **kwargs)

        mp.setattr(dspy.GEPA, "__init__", init)

    return apply


def _gepa_result_without_best_idx(mp: pytest.MonkeyPatch) -> None:
    mp.delattr(DspyGEPAResult, "best_idx")


def _cot_ignores_rationale_type(mp: pytest.MonkeyPatch) -> None:
    original = dspy.ChainOfThought.__init__

    def init(self: Any, signature: Any, rationale_field: Any = None, **config: Any) -> None:
        config.pop("rationale_field_type", None)
        original(self, signature, rationale_field=rationale_field, **config)

    mp.setattr(dspy.ChainOfThought, "__init__", init)


def _adapter_format_changed(adapter: type) -> Callable[[pytest.MonkeyPatch], None]:
    """El adapter cambia el texto de la descripcion de la tarea del prompt."""

    def apply(mp: pytest.MonkeyPatch) -> None:
        original = adapter.format_task_description

        def format_task_description(self: Any, signature: Any) -> str:
            return original(self, signature) + " Responde con cuidado."

        mp.setattr(adapter, "format_task_description", format_task_description)

    return apply


def _fallback_on_any_error(mp: pytest.MonkeyPatch) -> None:
    """`ChatAdapter` vuelve a caer a `JSONAdapter` ante cualquier excepcion."""
    original = dspy.ChatAdapter.__call__

    def call(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return original(self, *args, **kwargs)
        except Exception:
            if type(self) is not dspy.ChatAdapter:
                raise
            return dspy.JSONAdapter()(*args, **kwargs)

    mp.setattr(dspy.ChatAdapter, "__call__", call)


def _context_ignores_adapter(mp: pytest.MonkeyPatch) -> None:
    original = dspy.context

    @contextmanager
    def context(**kwargs: Any) -> Iterator[None]:
        kwargs.pop("adapter", None)
        with original(**kwargs):
            yield

    mp.setattr(dspy, "context", context)


def _evaluate_returns_float(mp: pytest.MonkeyPatch) -> None:
    mp.setattr(dspy.evaluate.Evaluate, "__call__", lambda self, program, **kwargs: 50.0)


def _named_predictors_empty(mp: pytest.MonkeyPatch) -> None:
    mp.setattr(dspy.Module, "named_predictors", lambda self: [])


def _labeled_few_shot_renamed_k(mp: pytest.MonkeyPatch) -> None:
    original = LabeledFewShot.__init__

    def init(self: Any, max_demos: int = 16) -> None:
        original(self, k=max_demos)

    mp.setattr(LabeledFewShot, "__init__", init)


# ---- gepa ----


def _optimize_without_custom_proposer(mp: pytest.MonkeyPatch) -> None:
    def optimize(
        seed_candidate: Any,
        trainset: Any,
        valset: Any = None,
        adapter: Any = None,
        task_lm: Any = None,
        max_metric_calls: Any = None,
        skip_perfect_score: bool = True,
        display_progress_bar: bool = False,
        callbacks: Any = None,
    ) -> Any:
        raise NotImplementedError

    mp.setattr(gepa, "optimize", optimize)


def _proposal_fn_params_renamed(mp: pytest.MonkeyPatch) -> None:
    class ProposalFn(Protocol):
        def __call__(
            self, candidate: Any, reflective_dataset: Any, components: Any
        ) -> dict[str, str]: ...

    mp.setattr(gepa.core.adapter, "ProposalFn", ProposalFn)


def _proposal_event_key_renamed(mp: pytest.MonkeyPatch) -> None:
    """GEPA renombra la clave `iteration` del evento `on_proposal_start`."""
    original = gepa_reflective_mutation.notify_callbacks

    def notify(callbacks: Any, method_name: str, event: Any) -> None:
        if method_name == "on_proposal_start":
            event = {("iter" if k == "iteration" else k): v for k, v in event.items()}
        original(callbacks, method_name, event)

    mp.setattr(gepa_reflective_mutation, "notify_callbacks", notify)


def _evaluation_batch_without_trajectories(mp: pytest.MonkeyPatch) -> None:
    batch = dataclasses.make_dataclass("EvaluationBatch", ["outputs", "scores"])
    mp.setattr(gepa, "EvaluationBatch", batch)


def _adapter_protocol_renamed(mp: pytest.MonkeyPatch) -> None:
    class GEPAAdapter(Protocol):
        def evaluate(self, batch: Any, candidate: Any, capture_traces: bool = False) -> Any: ...

        def make_reflective_dataset(
            self, candidate: Any, eval_batch: Any, components: Any
        ) -> Any: ...

    mp.setattr(gepa, "GEPAAdapter", GEPAAdapter)


def _gepa_result_without_best_idx_property(mp: pytest.MonkeyPatch) -> None:
    mp.delattr(gepa.GEPAResult, "best_idx")


# ---- litellm ----


def _completion_without_params(mp: pytest.MonkeyPatch) -> None:
    def completion(model: str, messages: list, temperature: float | None = None) -> Any:
        raise NotImplementedError

    mp.setattr(litellm, "completion", completion)


def _errors_mapped_to_api_error(mp: pytest.MonkeyPatch) -> None:
    """LiteLLM deja de mapear los 400 a su subclase (todo `APIError` 500)."""
    original = litellm.completion

    def completion(*args: Any, **kwargs: Any) -> Any:
        try:
            return original(*args, **kwargs)
        except litellm.BadRequestError as exc:
            raise litellm.APIError(500, str(exc), "openai", kwargs.get("model")) from exc

    mp.setattr(litellm, "completion", completion)


def _finish_reason_normalized_to_stop(mp: pytest.MonkeyPatch) -> None:
    original = litellm.completion

    def completion(*args: Any, **kwargs: Any) -> Any:
        response = original(*args, **kwargs)
        response.choices[0].finish_reason = "stop"
        return response

    mp.setattr(litellm, "completion", completion)


def _capability_signature_changed(mp: pytest.MonkeyPatch) -> None:
    mp.setattr(litellm, "supports_response_schema", lambda model_name: True)


def _drop_params_removed(mp: pytest.MonkeyPatch) -> None:
    mp.delattr(litellm, "drop_params")


# ---- contratos que se ponen rojos ----

_FAILING_CALL = next(
    c
    for c in call_point_tests.FAILING_CASES
    if c.provider == "openai" and c.case_type == "http_error" and c.spec104_class == "entrada"
)
_HTTP_ERROR = litellm_tests._TABLE_1_AND_2_ERRORS[0]
_HTTP_200_NOT_STOP = next(c for c in ALL_HTTP_200_CASES if c.expected_finish_reason == "length")


def _engine_contract(name: str) -> Callable[[pytest.FixtureRequest], None]:
    return lambda request: getattr(engine_tests.TestDspyEngineContract(), name)()


def _prompt_contract(name: str, *args: Any) -> Callable[[pytest.FixtureRequest], None]:
    return lambda request: getattr(engine_tests.TestTaskPromptUnchanged(), name)(
        _mp(request), *args
    )


def _cot_contract(request: pytest.FixtureRequest) -> None:
    engine_tests.TestTaskPromptUnchanged().test_default_chain_of_thought_is_native_reasoning_in_dspy()


def _own(cls: type, name: str) -> Callable[[pytest.FixtureRequest], None]:
    return lambda request: getattr(cls(), name)()


def _dspy_gepa_valid_proposal(request: pytest.FixtureRequest) -> None:
    _litellm_isolated(request)
    reflection_tests.TestDspyGepaReflection().test_valid_proposal_creates_candidate(_mp(request))


def _dspy_gepa_callback(request: pytest.FixtureRequest) -> None:
    _litellm_isolated(request)
    reflection_tests.TestDspyGepaReflection().test_callback_sets_gepa_iteration_as_case_id(
        _mp(request), request.getfixturevalue("caplog")
    )


def _standalone_callback(request: pytest.FixtureRequest) -> None:
    _litellm_isolated(request)
    reflection_tests.TestStandaloneInGepaOptimize().test_callback_sets_gepa_iteration_as_case_id(
        _mp(request), request.getfixturevalue("caplog")
    )


def _one_call_per_failure(request: pytest.FixtureRequest) -> None:
    call_point_tests.TestDspyPredictOneCallPerCase().test_http_calls_and_class_per_case(
        _FAILING_CALL
    )


def _exception_mapping(request: pytest.FixtureRequest) -> None:
    _litellm_isolated(request)
    litellm_tests.TestExceptionMappingAndBodyPreservation().test_table_1_and_2_exception_and_body(
        _HTTP_ERROR
    )


def _response_normalization(request: pytest.FixtureRequest) -> None:
    _litellm_isolated(request)
    litellm_tests.TestHTTP200ResponseNormalization().test_http_200_normalized_fields(
        _HTTP_200_NOT_STOP
    )


_CONSTRUCTION = TestOptimizerConstructionContracts

MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        "dspy.LM(engine)",
        "dspy.LM deja de aceptar engine",
        _lm_without_engine,
        _engine_contract("test_engine_receives_request_and_returns_response"),
        TypeError,
    ),
    Mutation(
        "engine.complete",
        "dspy llama engine.generate en lugar de complete",
        _engine_method_renamed,
        _engine_contract("test_engine_receives_request_and_returns_response"),
        dspy.LMError,
    ),
    Mutation(
        "dspy.errors.identity",
        "dspy convierte tambien las dspy.LMError",
        _lm_errors_wrapped_too,
        _engine_contract("test_lm_error_passes_by_identity"),
        dspy.LMError,
    ),
    Mutation(
        "engine.hints",
        "dspy.LM deja de leer supported_params del engine",
        _hints_not_read_from_engine,
        _engine_contract("test_engine_hints_are_read_by_dspy"),
    ),
    Mutation(
        "dspy.lm15.types",
        "Usage renombra input_tokens y output_tokens",
        _usage_fields_renamed,
        _own(TestDspyContracts, "test_lm15_types_keep_the_fields_the_engine_uses"),
    ),
    Mutation(
        "dspy.lm15.Config",
        "Config agrega un campo",
        _config_new_field,
        _own(TestDspyContracts, "test_lm15_config_fields_are_known"),
    ),
    Mutation(
        "dspy.exceptions",
        "dspy.LMError pierde default_code y la jerarquia",
        _lm_error_replaced,
        _own(TestDspyContracts, "test_exceptions_the_repo_uses"),
        AttributeError,
    ),
    Mutation(
        "dspy.GEPA.params",
        "dspy.GEPA quita instruction_proposer",
        _gepa_without_instruction_proposer_param,
        _own(_CONSTRUCTION, "test_dspy_gepa_accepts_the_parameters_the_repo_passes"),
    ),
    Mutation(
        "dspy.GEPA.params",
        "dspy.GEPA ignora parametros desconocidos",
        _gepa_ignores_unknown_params,
        _own(_CONSTRUCTION, "test_dspy_gepa_rejects_unknown_parameters"),
        pytest.fail.Exception,
    ),
    Mutation(
        "dspy.GEPA.proposer",
        "dspy.GEPA acepta instruction_proposer pero usa el suyo",
        _gepa_drops("instruction_proposer"),
        _dspy_gepa_valid_proposal,
    ),
    Mutation(
        "dspy.GEPA.callbacks",
        "dspy.GEPA acepta gepa_kwargs pero no los pasa a GEPA",
        _gepa_drops("gepa_kwargs"),
        _dspy_gepa_callback,
    ),
    Mutation(
        "dspy.GEPA.result",
        "DspyGEPAResult pierde best_idx",
        _gepa_result_without_best_idx,
        _own(TestDspyContracts, "test_gepa_compile_and_detailed_results"),
    ),
    Mutation(
        "dspy.ChainOfThought",
        "ChainOfThought ignora rationale_field_type",
        _cot_ignores_rationale_type,
        _cot_contract,
    ),
    Mutation(
        "dspy.ChatAdapter",
        "ChatAdapter cambia el texto del prompt",
        _adapter_format_changed(dspy.ChatAdapter),
        _prompt_contract("test_chat_adapter_messages_match_dspy_3_4_1"),
    ),
    Mutation(
        "dspy.JSONAdapter",
        "JSONAdapter cambia el texto del prompt",
        _adapter_format_changed(dspy.JSONAdapter),
        _prompt_contract("test_json_adapter_messages_match_dspy_3_4_1", MODEL),
    ),
    Mutation(
        "dspy.adapter.fallback",
        "ChatAdapter cae a JSONAdapter ante cualquier excepcion",
        _fallback_on_any_error,
        _one_call_per_failure,
    ),
    Mutation(
        "dspy.context",
        "dspy.context ignora adapter",
        _context_ignores_adapter,
        _prompt_contract("test_json_adapter_messages_match_dspy_3_4_1", MODEL),
    ),
    Mutation(
        "dspy.Evaluate",
        "Evaluate devuelve un float",
        _evaluate_returns_float,
        _own(TestDspyContracts, "test_evaluate_returns_score_and_results"),
        AttributeError,
    ),
    Mutation(
        "dspy.Module.named_predictors",
        "named_predictors no devuelve los Predict",
        _named_predictors_empty,
        _own(TestDspyContracts, "test_named_predictors_and_instructions"),
    ),
    Mutation(
        "dspy.LabeledFewShot",
        "LabeledFewShot renombra k",
        _labeled_few_shot_renamed_k,
        _own(TestDspyContracts, "test_labeled_few_shot"),
        TypeError,
    ),
    Mutation(
        "gepa.optimize",
        "gepa.optimize quita custom_candidate_proposer",
        _optimize_without_custom_proposer,
        _own(_CONSTRUCTION, "test_gepa_optimize_accepts_the_parameters_the_repo_passes"),
    ),
    Mutation(
        "gepa.ProposalFn",
        "ProposalFn renombra components_to_update",
        _proposal_fn_params_renamed,
        _own(_CONSTRUCTION, "test_proposal_fn_protocol_matches_the_repo_proposer"),
    ),
    Mutation(
        "gepa.callbacks",
        "el evento on_proposal_start renombra iteration",
        _proposal_event_key_renamed,
        _standalone_callback,
    ),
    Mutation(
        "gepa.EvaluationBatch",
        "EvaluationBatch quita trajectories",
        _evaluation_batch_without_trajectories,
        _own(TestGepaContracts, "test_evaluation_batch_fields"),
    ),
    Mutation(
        "gepa.GEPAAdapter",
        "GEPAAdapter renombra components_to_update",
        _adapter_protocol_renamed,
        _own(TestGepaContracts, "test_gepa_adapter_protocol_matches_base_adapter"),
    ),
    Mutation(
        "gepa.GEPAResult",
        "GEPAResult pierde best_idx",
        _gepa_result_without_best_idx_property,
        _own(TestGepaContracts, "test_gepa_result_attributes"),
    ),
    Mutation(
        "litellm.completion",
        "litellm.completion pierde parametros y kwargs",
        _completion_without_params,
        _own(TestLitellmContracts, "test_completion_accepts_the_parameters_the_repo_passes"),
    ),
    Mutation(
        "litellm.exceptions",
        "LiteLLM mapea los 400 a APIError",
        _errors_mapped_to_api_error,
        _exception_mapping,
    ),
    Mutation(
        "litellm.response",
        "LiteLLM normaliza finish_reason a stop",
        _finish_reason_normalized_to_stop,
        _response_normalization,
    ),
    Mutation(
        "litellm.capabilities",
        "supports_response_schema cambia de firma",
        _capability_signature_changed,
        _own(TestLitellmContracts, "test_capability_helpers"),
        TypeError,
    ),
    Mutation(
        "litellm.drop_params",
        "LiteLLM quita el global drop_params",
        _drop_params_removed,
        _own(TestLitellmContracts, "test_drop_params_global"),
        AttributeError,
    ),
)


class TestContractsDetectIncompatibleChanges:
    def test_every_surface_has_a_mutation(self) -> None:
        assert {m.surface for m in MUTATIONS} == set(SURFACES)

    @pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: f"{m.surface}: {m.change}")
    def test_contract_turns_red(
        self, mutation: Mutation, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
    ) -> None:
        mutation.apply(monkeypatch)
        with pytest.raises(mutation.raises):
            mutation.contract(request)

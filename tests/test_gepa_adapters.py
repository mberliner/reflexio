"""
Unit tests for gepa_standalone adapters.

Tests for 4 adapters:
- SimpleClassifierAdapter (117 lines)
- SimpleExtractorAdapter (203 lines)
- SimpleSQLAdapter (105 lines)
- SimpleRAGAdapter (354 lines, PRIORITY)

Total coverage: 829 lines of critical logic.
"""

import json
from unittest.mock import MagicMock

import pytest
from gepa import EvaluationBatch

from gepa_standalone.adapters.simple_classifier_adapter import SimpleClassifierAdapter
from gepa_standalone.adapters.simple_extractor_adapter import SimpleExtractorAdapter
from gepa_standalone.adapters.simple_rag_adapter import SimpleRAGAdapter
from gepa_standalone.adapters.simple_sql_adapter import SimpleSQLAdapter
from shared.llm import (
    FailureClass,
    LLMCallFailure,
    LLMFailure,
    RunAborted,
    get_failure_tracker,
)
from tests.conftest import make_completion_response
from tests.litellm_failure_payloads import ALL_FAILURE_CASES, FailurePayloadCase
from tests.test_litellm_failure_mapping import intercept_httpx


def _payload(case_id: str) -> FailurePayloadCase:
    return next(c for c in ALL_FAILURE_CASES if c.id == case_id)


# ==================== Fixtures ====================


@pytest.fixture
def classifier_batch():
    """Batch for classifier tests."""
    return [
        {"case_id": "c0", "text": "Hello, how are you?", "label": "greeting"},
        {"case_id": "c1", "text": "Goodbye, see you later", "label": "farewell"},
        {"case_id": "c2", "text": "Hi there!", "label": "greeting"},
    ]


@pytest.fixture
def extractor_batch():
    """Batch for extractor tests."""
    return [
        {
            "case_id": "c0",
            "text": "John Doe, 35 years old, Python developer",
            "extracted": {"name": "John Doe", "age": "35", "role": "Python developer"},
        },
        {
            "case_id": "c1",
            "text": "Jane Smith, 28 years old, Designer",
            "extracted": {"name": "Jane Smith", "age": "28", "role": "Designer"},
        },
    ]


@pytest.fixture
def sql_batch():
    """Batch for SQL tests."""
    return [
        {
            "case_id": "c0",
            "question": "List all users",
            "extracted": {
                "schema": "users(id, name, email)",
                "expected_sql": "SELECT * FROM users",
            },
        },
        {
            "case_id": "c1",
            "question": "Count active users",
            "extracted": {
                "schema": "users(id, name, active)",
                "expected_sql": "SELECT COUNT(*) FROM users WHERE active = 1",
            },
        },
    ]


@pytest.fixture
def rag_batch():
    """Batch for RAG tests."""
    return [
        {
            "case_id": "c0",
            "question": "What is the capital of France?",
            "context": "France is a country in Europe. Its capital is Paris.",
            "answer": "Paris",
        },
        {
            "case_id": "c1",
            "question": "What is the population of Tokyo?",
            "context": "Tokyo is the capital of Japan with a population of 14 million.",
            "answer": "14 million",
        },
    ]


# ==================== SimpleClassifierAdapter Tests ====================


class TestSimpleClassifierAdapter:
    def test_classifier_evaluate_all_correct(self, mock_env, monkeypatch, classifier_batch):
        """All predictions correct → scores [1.0, 1.0, 1.0]."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            # Return label based on message content
            messages = kwargs.get("messages", [])
            user_msg = messages[-1]["content"] if messages else ""
            if "goodbye" in user_msg.lower():
                response.choices[0].message.content = "farewell"
            else:
                response.choices[0].message.content = "greeting"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleClassifierAdapter(valid_classes=["greeting", "farewell"])
        candidate = {"system_prompt": "Classify as greeting or farewell"}

        result = adapter.evaluate(classifier_batch, candidate)

        assert len(result.scores) == 3
        assert result.scores == [1.0, 1.0, 1.0]
        assert len(result.outputs) == 3
        assert result.trajectories is None

    def test_classifier_evaluate_mixed(self, mock_env, monkeypatch, classifier_batch):
        """Mixed correct/incorrect → scores [1.0, 0.0, 1.0]."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            # Intentionally wrong for the second example
            messages = kwargs.get("messages", [])
            user_msg = messages[-1]["content"] if messages else ""
            if "goodbye" in user_msg.lower():
                response.choices[0].message.content = "greeting"  # Wrong!
            else:
                response.choices[0].message.content = "greeting"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleClassifierAdapter(valid_classes=["greeting", "farewell"])
        candidate = {"system_prompt": "Classify..."}

        result = adapter.evaluate(classifier_batch, candidate)

        assert result.scores == [1.0, 0.0, 1.0]

    def test_classifier_unclassified_error_aborts_instead_of_dropping(
        self, mock_env, monkeypatch, classifier_batch
    ):
        """Excepcion no clasificada (regla 3) = `configuracion`: aborta la corrida (FR-006);
        el adapter no descarta ejemplos ni inventa un RuntimeError de "todos fallaron"."""

        def mock_completion(*args, **kwargs):
            raise Exception("API Error")

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleClassifierAdapter(valid_classes=["greeting", "farewell"])

        with pytest.raises(RunAborted):
            adapter.evaluate(classifier_batch, {"system_prompt": "Classify..."})

        assert get_failure_tracker().aborted

    def test_classifier_make_reflective_negatives(self, mock_env):
        """Only examples with score < 1.0 in reflective dataset."""
        adapter = SimpleClassifierAdapter(valid_classes=["greeting", "farewell"])
        eval_batch = EvaluationBatch(
            outputs=[
                {"predicted": "greeting", "expected": "greeting", "text": "hello"},
                {"predicted": "wrong", "expected": "farewell", "text": "bye"},
            ],
            scores=[1.0, 0.0],
            trajectories=None,
        )

        result = adapter.make_reflective_dataset(
            candidate={"system_prompt": "..."},
            eval_batch=eval_batch,
            components_to_update=["system_prompt"],
        )

        assert "system_prompt" in result
        assert len(result["system_prompt"]) == 1  # Only the incorrect one
        record = result["system_prompt"][0]
        assert "Inputs" in record
        assert "Feedback" in record
        assert "incorrecta" in record["Feedback"].lower()

    def test_classifier_text_truncation(self, mock_env, monkeypatch):
        """Texts > Config.CLASSIFIER_TEXT_MAX_LENGTH are truncated."""
        monkeypatch.setattr("gepa_standalone.config.Config.CLASSIFIER_TEXT_MAX_LENGTH", 10)

        adapter = SimpleClassifierAdapter(valid_classes=["greeting"])
        long_text = "a" * 50
        eval_batch = EvaluationBatch(
            outputs=[{"predicted": "wrong", "expected": "greeting", "text": long_text}],
            scores=[0.0],
            trajectories=None,
        )

        result = adapter.make_reflective_dataset(
            candidate={"system_prompt": "..."},
            eval_batch=eval_batch,
            components_to_update=["system_prompt"],
        )

        record = result["system_prompt"][0]
        truncated_text = record["Inputs"]["text"]
        assert len(truncated_text) <= 13  # 10 + "..."
        assert truncated_text.endswith("...")

    def test_classifier_label_key_detection(self):
        """_get_label_key searches for urgency/label/class/sentiment."""
        adapter = SimpleClassifierAdapter(valid_classes=["urgent", "normal"])

        assert adapter._get_label_key({"urgency": "urgent"}) == "urgency"
        assert adapter._get_label_key({"label": "normal"}) == "label"
        assert adapter._get_label_key({"class": "urgent"}) == "class"
        assert adapter._get_label_key({"sentiment": "positive"}) == "sentiment"
        assert adapter._get_label_key({"other": "value"}) == "label"  # Default

    def test_classifier_case_insensitive(self, mock_env, monkeypatch):
        """Comparison is lowercased."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            response.choices[0].message.content = "GREETING"  # Uppercase
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleClassifierAdapter(valid_classes=["greeting"])
        batch = [{"case_id": "c0", "text": "hello", "label": "greeting"}]  # Lowercase
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate)

        assert result.scores[0] == 1.0  # Should match despite case difference

    def test_classifier_with_trajectories(self, mock_env, monkeypatch, classifier_batch):
        """capture_traces=True returns trajectories."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            response.choices[0].message.content = "greeting"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleClassifierAdapter(valid_classes=["greeting", "farewell"])
        candidate = {"system_prompt": "Classify..."}

        result = adapter.evaluate(classifier_batch, candidate, capture_traces=True)

        assert result.trajectories is not None
        assert len(result.trajectories) == 3
        assert "system_prompt" in result.trajectories[0]
        assert "correct" in result.trajectories[0]


# ==================== SimpleExtractorAdapter Tests ====================


class TestSimpleExtractorAdapter:
    def test_extractor_evaluate_perfect_json(self, mock_env, monkeypatch, extractor_batch):
        """Perfect extraction → score 1.0."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            # Return perfect JSON based on input
            messages = kwargs.get("messages", [])
            user_msg = messages[-1]["content"] if messages else ""
            if "John Doe" in user_msg:
                response.choices[0].message.content = json.dumps(
                    {"name": "John Doe", "age": "35", "role": "Python developer"}
                )
            else:
                response.choices[0].message.content = json.dumps(
                    {"name": "Jane Smith", "age": "28", "role": "Designer"}
                )
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleExtractorAdapter(required_fields=["name", "age", "role"])
        candidate = {"system_prompt": "Extract fields..."}

        result = adapter.evaluate(extractor_batch, candidate)

        assert len(result.scores) == 2
        assert result.scores == [1.0, 1.0]

    def test_extractor_evaluate_partial_fields(self, mock_env, monkeypatch):
        """2/3 fields correct → score 0.666..."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            # Return partial match
            response.choices[0].message.content = json.dumps(
                {"name": "John Doe", "age": "35", "role": "WRONG"}  # 2/3 correct
            )
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleExtractorAdapter(required_fields=["name", "age", "role"])
        batch = [
            {
                "case_id": "c0",
                "text": "John Doe, 35 years old, Python developer",
                "extracted": {"name": "John Doe", "age": "35", "role": "Python developer"},
            }
        ]
        candidate = {"system_prompt": "Extract..."}

        result = adapter.evaluate(batch, candidate)

        assert result.scores[0] == pytest.approx(2 / 3, rel=0.01)

    def test_extractor_evaluate_invalid_json(self, mock_env, monkeypatch):
        """Invalid JSON → score 0.0 (fallback)."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            response.choices[0].message.content = "This is not JSON"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleExtractorAdapter(required_fields=["name"])
        batch = [{"case_id": "c0", "text": "John", "extracted": {"name": "John"}}]
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate)

        assert result.scores[0] == 0.0

    def test_extractor_extract_json_from_text(self):
        """Parses JSON embedded in markdown."""
        adapter = SimpleExtractorAdapter(required_fields=["name"])

        text = 'Here is the result: {"name": "John", "age": 30} and more text'
        extracted = adapter._extract_json_from_text(text)

        assert extracted == {"name": "John", "age": 30}

    def test_extractor_make_reflective_negatives(self, mock_env):
        """Only score < 1.0 in reflective dataset."""
        adapter = SimpleExtractorAdapter(required_fields=["name"], max_positive_examples=0)
        eval_batch = EvaluationBatch(
            outputs=[
                {
                    "extracted": {"name": "John"},
                    "expected": {"name": "John"},
                    "field_comparisons": {
                        "name": {"expected": "John", "extracted": "John", "correct": True}
                    },
                    "text": "John",
                },
                {
                    "extracted": {"name": "Wrong"},
                    "expected": {"name": "Jane"},
                    "field_comparisons": {
                        "name": {"expected": "Jane", "extracted": "Wrong", "correct": False}
                    },
                    "text": "Jane",
                },
            ],
            scores=[1.0, 0.0],
            trajectories=None,
        )

        result = adapter.make_reflective_dataset(
            candidate={"system_prompt": "..."},
            eval_batch=eval_batch,
            components_to_update=["system_prompt"],
        )

        assert len(result["system_prompt"]) == 1  # Only the incorrect one
        assert result["system_prompt"][0]["Type"] == "negative_example"

    def test_extractor_make_reflective_positives(self, mock_env):
        """Includes score == 1.0 if max_positive_examples > 0."""
        adapter = SimpleExtractorAdapter(required_fields=["name"], max_positive_examples=2)
        eval_batch = EvaluationBatch(
            outputs=[
                {
                    "extracted": {"name": "John"},
                    "expected": {"name": "John"},
                    "text": "John",
                },
                {
                    "extracted": {"name": "Jane"},
                    "expected": {"name": "Jane"},
                    "text": "Jane",
                },
            ],
            scores=[1.0, 1.0],
            trajectories=None,
        )

        result = adapter.make_reflective_dataset(
            candidate={"system_prompt": "..."},
            eval_batch=eval_batch,
            components_to_update=["system_prompt"],
        )

        assert len(result["system_prompt"]) == 2  # Both positive examples
        assert all(r["Type"] == "positive_example" for r in result["system_prompt"])

    def test_extractor_text_truncation(self, mock_env, monkeypatch):
        """Truncates according to Config.EXTRACTOR_TEXT_MAX_LENGTH."""
        monkeypatch.setattr("gepa_standalone.config.Config.EXTRACTOR_TEXT_MAX_LENGTH", 10)

        adapter = SimpleExtractorAdapter(required_fields=["name"], max_positive_examples=0)
        long_text = "a" * 50
        eval_batch = EvaluationBatch(
            outputs=[
                {
                    "extracted": {"name": "Wrong"},
                    "expected": {"name": "John"},
                    "field_comparisons": {
                        "name": {"expected": "John", "extracted": "Wrong", "correct": False}
                    },
                    "text": long_text,
                }
            ],
            scores=[0.0],
            trajectories=None,
        )

        result = adapter.make_reflective_dataset(
            candidate={"system_prompt": "..."},
            eval_batch=eval_batch,
            components_to_update=["system_prompt"],
        )

        truncated = result["system_prompt"][0]["Inputs"]["cv_text"]
        assert len(truncated) <= 13  # 10 + "..."

    def test_extractor_case_insensitive(self, mock_env, monkeypatch):
        """Field comparison is case-insensitive."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            response.choices[0].message.content = json.dumps({"name": "JOHN DOE"})  # Uppercase
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleExtractorAdapter(required_fields=["name"])
        # Lowercase
        batch = [{"case_id": "c0", "text": "john doe", "extracted": {"name": "john doe"}}]
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate)

        assert result.scores[0] == 1.0  # Should match despite case

    def test_extractor_missing_expected_field(self, mock_env, monkeypatch):
        """If expected field is missing → score 0.0 for that field."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            response.choices[0].message.content = json.dumps({"other": "value"})
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleExtractorAdapter(required_fields=["name"])
        batch = [{"case_id": "c0", "text": "test", "extracted": {"name": "John"}}]
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate)

        assert result.scores[0] == 0.0

    def test_extractor_with_trajectories(self, mock_env, monkeypatch):
        """capture_traces=True returns trajectories."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            response.choices[0].message.content = json.dumps({"name": "John"})
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleExtractorAdapter(required_fields=["name"])
        batch = [{"case_id": "c0", "text": "John", "extracted": {"name": "John"}}]
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate, capture_traces=True)

        assert result.trajectories is not None
        assert len(result.trajectories) == 1
        assert "field_comparisons" in result.trajectories[0]


# ==================== SimpleSQLAdapter Tests ====================


class TestSimpleSQLAdapter:
    def test_sql_evaluate_exact_match(self, mock_env, monkeypatch, sql_batch):
        """Identical SQL → score 1.0."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            messages = kwargs.get("messages", [])
            user_msg = messages[-1]["content"] if messages else ""
            if "List all users" in user_msg:
                response.choices[0].message.content = "SELECT * FROM users"
            else:
                response.choices[0].message.content = "SELECT COUNT(*) FROM users WHERE active = 1"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleSQLAdapter()
        candidate = {"system_prompt": "Generate SQL..."}

        result = adapter.evaluate(sql_batch, candidate)

        assert result.scores == [1.0, 1.0]

    def test_sql_evaluate_normalized_match(self, mock_env, monkeypatch):
        """SQL with different whitespace/case → score 1.0."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            # Different whitespace and case
            response.choices[0].message.content = "SELECT  *  FROM  users"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleSQLAdapter()
        batch = [
            {
                "case_id": "c0",
                "question": "List users",
                "extracted": {"schema": "users(id)", "expected_sql": "select * from users"},
            }
        ]
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate)

        assert result.scores[0] == 1.0

    def test_sql_evaluate_different_sql(self, mock_env, monkeypatch):
        """Different SQL → score 0.0."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            response.choices[0].message.content = "SELECT id FROM users"  # Different
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleSQLAdapter()
        batch = [
            {
                "case_id": "c0",
                "question": "List users",
                "extracted": {"schema": "users(id)", "expected_sql": "SELECT * FROM users"},
            }
        ]
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate)

        assert result.scores[0] == 0.0

    def test_sql_compare_removes_semicolon(self):
        """SELECT * FROM t; == SELECT * FROM t."""
        adapter = SimpleSQLAdapter()

        assert adapter._compare_sql("SELECT * FROM t;", "SELECT * FROM t")
        assert adapter._compare_sql("SELECT * FROM t", "SELECT * FROM t;")

    def test_sql_markdown_cleanup(self, mock_env, monkeypatch):
        """Extracts SQL from ```sql ... ```."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            response.choices[0].message.content = "```sql\nSELECT * FROM users\n```"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleSQLAdapter()
        batch = [
            {
                "case_id": "c0",
                "question": "List users",
                "extracted": {"schema": "users(id)", "expected_sql": "SELECT * FROM users"},
            }
        ]
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate)

        assert result.scores[0] == 1.0

    def test_sql_make_reflective_only_negatives(self, mock_env):
        """Only score < 1.0, no positives."""
        adapter = SimpleSQLAdapter()
        eval_batch = EvaluationBatch(
            outputs=[
                {"predicted": "SELECT *", "expected": "SELECT *", "question": "q1"},
                {"predicted": "WRONG", "expected": "SELECT *", "question": "q2"},
            ],
            scores=[1.0, 0.0],
            trajectories=None,
        )

        result = adapter.make_reflective_dataset(
            candidate={"system_prompt": "..."},
            eval_batch=eval_batch,
            components_to_update=["system_prompt"],
        )

        assert len(result["system_prompt"]) == 1  # Only incorrect
        assert "Feedback" in result["system_prompt"][0]

    def test_sql_whitespace_normalization(self):
        """Multiple spaces → single space."""
        adapter = SimpleSQLAdapter()

        assert adapter._compare_sql("SELECT  *  FROM   users", "SELECT * FROM users")

    def test_sql_with_trajectories(self, mock_env, monkeypatch):
        """capture_traces=True returns trajectories."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            response.choices[0].message.content = "SELECT * FROM users"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleSQLAdapter()
        batch = [
            {
                "case_id": "c0",
                "question": "List users",
                "extracted": {"schema": "users(id)", "expected_sql": "SELECT * FROM users"},
            }
        ]
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate, capture_traces=True)

        assert result.trajectories is not None
        assert len(result.trajectories) == 1
        assert "correct" in result.trajectories[0]


# ==================== SimpleRAGAdapter Tests ====================


class TestSimpleRAGAdapter:
    def test_rag_evaluate_successful_generation(self, mock_env, monkeypatch, rag_batch):
        """Generates answer and Judge gives score → score from Judge."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            messages = kwargs.get("messages", [])
            system_msg = messages[0]["content"] if messages else ""

            # Task model generates answer
            if "evaluador" not in system_msg.lower():
                response.choices[0].message.content = "Paris is the capital."
            # Judge model evaluates
            else:
                response.choices[0].message.content = '{"puntaje": 0.8, "razon": "Good answer"}'
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        candidate = {"system_prompt": "Answer the question..."}

        result = adapter.evaluate([rag_batch[0]], candidate)

        assert len(result.scores) == 1
        assert result.scores[0] == 0.8

    def test_rag_complete_returns_text_with_num_retries_0(self, mock_env, monkeypatch):
        """Respuesta sana → devuelve el texto; LiteLLM recibe num_retries=0 (FR-011)."""
        mock_completion = MagicMock(return_value=make_completion_response("Success"))
        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        messages = [{"role": "user", "content": "test"}]

        result = adapter._complete(messages)

        assert result == "Success"
        assert mock_completion.call_count == 1
        assert mock_completion.call_args.kwargs["num_retries"] == 0

    def test_rag_complete_input_filter_not_retried(self, mock_env):
        """Filtro de entrada (HTTP 400) → 1 llamada HTTP, `entrada`, sin reintento (FR-011)."""
        adapter = SimpleRAGAdapter()
        messages = [{"role": "user", "content": "test"}]

        with intercept_httpx(_payload("azure_400_content_filter_canonico")) as calls:
            with pytest.raises(LLMCallFailure) as exc_info:
                adapter._complete(messages)

        assert len(calls) == 1
        assert exc_info.value.failure.clase.value == "entrada"
        assert exc_info.value.failure.rol == "task"

    def test_rag_complete_output_filter_not_retried(self, mock_env):
        """Filtro de salida (HTTP 200 sin texto) → 1 llamada HTTP, `filtro_salida`."""
        adapter = SimpleRAGAdapter()
        messages = [{"role": "user", "content": "test"}]

        with intercept_httpx(_payload("azure_200_content_filter_vacio")) as calls:
            with pytest.raises(LLMCallFailure) as exc_info:
                adapter._complete(messages)

        assert len(calls) == 1
        assert exc_info.value.failure.clase.value == "filtro_salida"

    def test_rag_judge_uses_judge_role(self, mock_env, monkeypatch):
        """El juez llama con rol `judge` (D2), la tarea con rol `task`."""
        roles = []

        def fake_complete_text(kwargs, messages, role):
            roles.append(role)
            return '{"puntaje": 1.0, "razon": "ok"}' if role == "judge" else "Paris"

        monkeypatch.setattr(
            "gepa_standalone.adapters.simple_rag_adapter.complete_text", fake_complete_text
        )

        adapter = SimpleRAGAdapter()
        result = adapter.evaluate(
            [{"case_id": "c0", "question": "q", "context": "c", "answer": "Paris"}],
            {"system_prompt": "..."},
        )

        assert roles == ["task", "judge"]
        assert result.scores == [1.0]

    def test_rag_evaluate_run_aborted_propagates_without_http(self, mock_env, monkeypatch):
        """Contador abortado → `RunAborted` sale del adapter y no llama al LLM (FR-006)."""
        mock_completion = MagicMock(return_value=make_completion_response("x"))
        monkeypatch.setattr("litellm.completion", mock_completion)
        tracker = get_failure_tracker()
        tracker.abort(LLMFailure(FailureClass.configuracion, "task", "AuthenticationError"), "test")

        adapter = SimpleRAGAdapter()
        with pytest.raises(RunAborted):
            adapter.evaluate(
                [{"case_id": "c0", "question": "q", "context": "c", "answer": "a"}],
                {"system_prompt": "..."},
            )

        assert mock_completion.call_count == 0

    def test_rag_evaluate_with_judge_valid_score(self, mock_env, monkeypatch):
        """Judge returns 'Score: 0.8\nReason: ...' → 0.8."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            reply = '{"puntaje": 0.75, "razon": "Good but missing detail"}'
            response.choices[0].message.content = reply
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        score, reason = adapter._evaluate_with_judge("q", "gt", "gen")

        assert score == 0.75
        assert "Good but missing detail" in reason

    def test_rag_judge_content_filtered_is_ne_with_role_judge(self, mock_env, monkeypatch):
        """Juez bloqueado por filtro de entrada: 1 llamada del juez sin reintento y el caso
        queda NE con rol `judge` (tabla de la spec: `entrada` del juez es NE)."""
        # El juez usa la config de reflexion: mismo proveedor que el payload (Azure)
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "azure/gpt-4.1-mini")
        adapter = SimpleRAGAdapter()
        monkeypatch.setattr(adapter, "_task_call", lambda system_prompt, example: "Paris")
        batch = [{"case_id": "c0", "question": "q", "context": "c", "answer": "Paris"}]

        with intercept_httpx(_payload("azure_400_content_filter_canonico")) as calls:
            result = adapter.evaluate(batch, {"system_prompt": "p"})

        assert len(calls) == 1
        assert result.scores == [0.0]
        assert result.outputs[0]["evaluated"] is False
        assert result.outputs[0]["failure"]["rol"] == "judge"
        assert result.outputs[0]["failure"]["clave"] == "entrada"
        assert get_failure_tracker().snapshot()["counts"]["entrada"]["judge"] == 1

    def test_rag_sanitize_for_reflection(self):
        """Replaces problematic terms with [REDACTED] or safe alternatives."""
        adapter = SimpleRAGAdapter()

        text = "ERROR: This is an error with alucinacion and incorrecta response"
        sanitized = adapter._sanitize_for_reflection(text)

        assert "ERROR:" not in sanitized
        assert "Caso incorrecto:" in sanitized
        assert "alucinacion" not in sanitized
        assert "informacion no verificable" in sanitized
        assert "incorrecta" not in sanitized
        assert "no optima" in sanitized

    def test_rag_make_reflective_negatives(self, mock_env):
        """Only score < 1.0 in reflective dataset."""
        adapter = SimpleRAGAdapter(max_positive_examples=0)
        eval_batch = EvaluationBatch(
            outputs=[
                {
                    "generated_answer": "Paris",
                    "ground_truth": "Paris",
                    "judge_feedback": "Perfect",
                },
                {
                    "generated_answer": "Wrong",
                    "ground_truth": "Paris",
                    "judge_feedback": "Incorrect",
                },
            ],
            scores=[1.0, 0.5],
            trajectories=[
                {
                    "question": "Capital?",
                    "context": "France...",
                    "generated_answer": "Paris",
                    "ground_truth": "Paris",
                    "judge_feedback": "Perfect",
                },
                {
                    "question": "Capital?",
                    "context": "France...",
                    "generated_answer": "Wrong",
                    "ground_truth": "Paris",
                    "judge_feedback": "Incorrect",
                },
            ],
        )

        result = adapter.make_reflective_dataset(
            candidate={"system_prompt": "..."},
            eval_batch=eval_batch,
            components_to_update=["system_prompt"],
        )

        assert len(result["system_prompt"]) == 1  # Only score < 1.0
        assert result["system_prompt"][0]["Type"] == "negative_example"

    def test_rag_make_reflective_positives(self, mock_env):
        """Includes score == 1.0 if max_positive_examples > 0."""
        adapter = SimpleRAGAdapter(max_positive_examples=1)
        eval_batch = EvaluationBatch(
            outputs=[
                {
                    "generated_answer": "Paris",
                    "ground_truth": "Paris",
                    "judge_feedback": "Perfect",
                }
            ],
            scores=[1.0],
            trajectories=[
                {
                    "question": "Capital?",
                    "context": "France...",
                    "generated_answer": "Paris",
                    "ground_truth": "Paris",
                    "judge_feedback": "Perfect",
                }
            ],
        )

        result = adapter.make_reflective_dataset(
            candidate={"system_prompt": "..."},
            eval_batch=eval_batch,
            components_to_update=["system_prompt"],
        )

        assert len(result["system_prompt"]) == 1
        assert result["system_prompt"][0]["Type"] == "positive_example"
        assert "EJEMPLO EXITOSO" in result["system_prompt"][0]["Feedback (del Juez)"]

    def test_rag_context_truncation(self, mock_env, monkeypatch):
        """Context > Config.RAG_CONTEXT_MAX_LENGTH is truncated."""
        monkeypatch.setattr("gepa_standalone.config.Config.RAG_CONTEXT_MAX_LENGTH", 10)

        adapter = SimpleRAGAdapter(max_positive_examples=0)
        long_context = "a" * 50
        eval_batch = EvaluationBatch(
            outputs=[
                {
                    "generated_answer": "Wrong",
                    "ground_truth": "Right",
                    "judge_feedback": "Bad",
                }
            ],
            scores=[0.5],
            trajectories=[
                {
                    "question": "q",
                    "context": long_context,
                    "generated_answer": "Wrong",
                    "ground_truth": "Right",
                    "judge_feedback": "Bad",
                }
            ],
        )

        result = adapter.make_reflective_dataset(
            candidate={"system_prompt": "..."},
            eval_batch=eval_batch,
            components_to_update=["system_prompt"],
        )

        truncated_ctx = result["system_prompt"][0]["Inputs"]["contexto"]
        assert len(truncated_ctx) <= 13  # 10 + "..."

    def test_rag_with_trajectories(self, mock_env, monkeypatch):
        """capture_traces=True returns trajectories."""

        def mock_completion(*args, **kwargs):
            response = make_completion_response()
            messages = kwargs.get("messages", [])
            system_msg = messages[0]["content"] if messages else ""
            if "evaluador" not in system_msg.lower():
                response.choices[0].message.content = "Paris"
            else:
                response.choices[0].message.content = '{"puntaje": 1.0, "razon": "Perfect"}'
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        batch = [
            {
                "case_id": "c0",
                "question": "Capital?",
                "context": "France... Paris.",
                "answer": "Paris",
            }
        ]
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate, capture_traces=True)

        assert result.trajectories is not None
        assert len(result.trajectories) == 1
        assert "judge_feedback" in result.trajectories[0]

    def test_rag_input_filtered_with_baseline_also_filtered_is_ne_entrada_dato(self, mock_env):
        """Tarea bloqueada por filtro de entrada y el baseline tambien (mismo transporte):
        `entrada_dato`, NE, el ejemplo conserva su lugar y se hacen 2 llamadas HTTP (la del
        candidato y la unica del baseline; sin el reintento viejo por content_filter)."""
        adapter = SimpleRAGAdapter()
        adapter.set_baseline("baseline")
        batch = [{"case_id": "c0", "question": "q", "context": "c", "answer": "a"}]

        with intercept_httpx(_payload("azure_400_content_filter_canonico")) as calls:
            result = adapter.evaluate(batch, {"system_prompt": "candidato"})

        assert len(calls) == 2
        assert len(result.scores) == 1
        assert result.scores[0] == 0.0
        assert result.outputs[0]["evaluated"] is False
        assert result.outputs[0]["failure"]["clave"] == "entrada_dato"
        assert result.outputs[0]["failure"]["atribucion"] == "externa"
        assert get_failure_tracker().snapshot()["entrada_dato"] == ["c0"]

    def test_rag_task_failure_without_baseline_is_a_clear_error(self, mock_env):
        """Sin baseline fijado no se adivina la atribucion de `entrada`/`presupuesto`."""
        adapter = SimpleRAGAdapter()
        batch = [{"case_id": "c0", "question": "q", "context": "c", "answer": "a"}]

        with intercept_httpx(_payload("azure_400_content_filter_canonico")):
            with pytest.raises(RuntimeError, match="set_baseline"):
                adapter.evaluate(batch, {"system_prompt": "candidato"})


# ============ SimpleExtractorAdapter: scoring por campo (field_configs) ============


class TestExtractorFieldConfigs:
    """Verifica que el extractor aplica score_field por campo (set/fuzzy/normalized),
    igualando el contrato de las metricas DSPy."""

    def _adapter_returning(self, monkeypatch, payload, **kwargs):
        def mock_completion(*_a, **_k):
            response = make_completion_response()
            response.choices[0].message.content = json.dumps(payload)
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)
        return SimpleExtractorAdapter(required_fields=list(payload.keys()), **kwargs)

    def test_default_mode_exact_is_strict(self, mock_env, monkeypatch):
        """Sin field_configs el default es exact: variante de acentos no matchea."""
        adapter = self._adapter_returning(monkeypatch, {"educacion": "Ingenieria"})
        batch = [{"case_id": "c0", "text": "x", "extracted": {"educacion": "Ingeniería"}}]
        result = adapter.evaluate(batch, {"system_prompt": "..."})
        assert result.scores[0] == 0.0

    def test_set_mode_order_insensitive(self, mock_env, monkeypatch):
        """mode=set: skills en distinto orden puntua 1.0."""
        adapter = self._adapter_returning(
            monkeypatch,
            {"skills": "django, python, aws"},
            field_configs={"skills": {"mode": "set", "separators": ",;"}},
        )
        batch = [{"case_id": "c0", "text": "x", "extracted": {"skills": "python, aws, django"}}]
        result = adapter.evaluate(batch, {"system_prompt": "..."})
        assert result.scores[0] == pytest.approx(1.0)

    def test_set_mode_partial_coverage(self, mock_env, monkeypatch):
        """mode=set: cobertura parcial puntua fraccion del esperado."""
        adapter = self._adapter_returning(
            monkeypatch,
            {"skills": "python"},
            field_configs={"skills": {"mode": "set"}},
        )
        batch = [{"case_id": "c0", "text": "x", "extracted": {"skills": "python, aws, django"}}]
        result = adapter.evaluate(batch, {"system_prompt": "..."})
        assert result.scores[0] == pytest.approx(1 / 3, rel=0.01)

    def test_fuzzy_mode_tolerates_variants(self, mock_env, monkeypatch):
        """mode=fuzzy: variante cercana sobre el umbral puntua 1.0."""
        adapter = self._adapter_returning(
            monkeypatch,
            {"educacion": "Ingenieria en Sistemas, UBA"},
            field_configs={"educacion": {"mode": "fuzzy", "fuzzy_threshold": 0.85}},
        )
        batch = [
            {
                "case_id": "c0",
                "text": "x",
                "extracted": {"educacion": "Ingeniería en Sistemas, UBA"},
            }
        ]
        result = adapter.evaluate(batch, {"system_prompt": "..."})
        assert result.scores[0] == pytest.approx(1.0)

    def test_invalid_default_mode_raises(self, mock_env):
        with pytest.raises(ValueError, match="default_mode invalido"):
            SimpleExtractorAdapter(required_fields=["a"], default_mode="bogus")

    def test_invalid_field_mode_raises(self, mock_env):
        with pytest.raises(ValueError, match="Modo invalido"):
            SimpleExtractorAdapter(required_fields=["a"], field_configs={"a": {"mode": "bogus"}})

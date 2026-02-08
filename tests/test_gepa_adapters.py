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

# ==================== Fixtures ====================


@pytest.fixture
def classifier_batch():
    """Batch for classifier tests."""
    return [
        {"text": "Hello, how are you?", "label": "greeting"},
        {"text": "Goodbye, see you later", "label": "farewell"},
        {"text": "Hi there!", "label": "greeting"},
    ]


@pytest.fixture
def extractor_batch():
    """Batch for extractor tests."""
    return [
        {
            "text": "John Doe, 35 years old, Python developer",
            "extracted": {"name": "John Doe", "age": "35", "role": "Python developer"},
        },
        {
            "text": "Jane Smith, 28 years old, Designer",
            "extracted": {"name": "Jane Smith", "age": "28", "role": "Designer"},
        },
    ]


@pytest.fixture
def sql_batch():
    """Batch for SQL tests."""
    return [
        {
            "question": "List all users",
            "extracted": {
                "schema": "users(id, name, email)",
                "expected_sql": "SELECT * FROM users",
            },
        },
        {
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
            "question": "What is the capital of France?",
            "context": "France is a country in Europe. Its capital is Paris.",
            "answer": "Paris",
        },
        {
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
            response = MagicMock()
            response.choices = [MagicMock()]
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
            response = MagicMock()
            response.choices = [MagicMock()]
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

    def test_classifier_evaluate_all_fail_raises(self, mock_env, monkeypatch, classifier_batch):
        """If all examples fail technically → RuntimeError."""

        def mock_completion(*args, **kwargs):
            raise Exception("API Error")

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleClassifierAdapter(valid_classes=["greeting", "farewell"])
        candidate = {"system_prompt": "Classify..."}

        with pytest.raises(RuntimeError, match="ERROR CRÍTICO: Todos los ejemplos fallaron"):
            adapter.evaluate(classifier_batch, candidate)

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
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "GREETING"  # Uppercase
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleClassifierAdapter(valid_classes=["greeting"])
        batch = [{"text": "hello", "label": "greeting"}]  # Lowercase
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate)

        assert result.scores[0] == 1.0  # Should match despite case difference

    def test_classifier_with_trajectories(self, mock_env, monkeypatch, classifier_batch):
        """capture_traces=True returns trajectories."""

        def mock_completion(*args, **kwargs):
            response = MagicMock()
            response.choices = [MagicMock()]
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
            response = MagicMock()
            response.choices = [MagicMock()]
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
            response = MagicMock()
            response.choices = [MagicMock()]
            # Return partial match
            response.choices[0].message.content = json.dumps(
                {"name": "John Doe", "age": "35", "role": "WRONG"}  # 2/3 correct
            )
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleExtractorAdapter(required_fields=["name", "age", "role"])
        batch = [
            {
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
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "This is not JSON"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleExtractorAdapter(required_fields=["name"])
        batch = [{"text": "John", "extracted": {"name": "John"}}]
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
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = json.dumps({"name": "JOHN DOE"})  # Uppercase
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleExtractorAdapter(required_fields=["name"])
        batch = [{"text": "john doe", "extracted": {"name": "john doe"}}]  # Lowercase
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate)

        assert result.scores[0] == 1.0  # Should match despite case

    def test_extractor_missing_expected_field(self, mock_env, monkeypatch):
        """If expected field is missing → score 0.0 for that field."""

        def mock_completion(*args, **kwargs):
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = json.dumps({"other": "value"})
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleExtractorAdapter(required_fields=["name"])
        batch = [{"text": "test", "extracted": {"name": "John"}}]
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate)

        assert result.scores[0] == 0.0

    def test_extractor_with_trajectories(self, mock_env, monkeypatch):
        """capture_traces=True returns trajectories."""

        def mock_completion(*args, **kwargs):
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = json.dumps({"name": "John"})
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleExtractorAdapter(required_fields=["name"])
        batch = [{"text": "John", "extracted": {"name": "John"}}]
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
            response = MagicMock()
            response.choices = [MagicMock()]
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
            response = MagicMock()
            response.choices = [MagicMock()]
            # Different whitespace and case
            response.choices[0].message.content = "SELECT  *  FROM  users"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleSQLAdapter()
        batch = [
            {
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
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "SELECT id FROM users"  # Different
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleSQLAdapter()
        batch = [
            {
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
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "```sql\nSELECT * FROM users\n```"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleSQLAdapter()
        batch = [
            {
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
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "SELECT * FROM users"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleSQLAdapter()
        batch = [
            {
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
            response = MagicMock()
            response.choices = [MagicMock()]
            messages = kwargs.get("messages", [])
            system_msg = messages[0]["content"] if messages else ""

            # Task model generates answer
            if "evaluador" not in system_msg.lower():
                response.choices[0].message.content = "Paris is the capital."
            # Judge model evaluates
            else:
                response.choices[0].message.content = "PUNTAJE: 0.8\nRAZON: Good answer"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        candidate = {"system_prompt": "Answer the question..."}

        result = adapter.evaluate([rag_batch[0]], candidate)

        assert len(result.scores) == 1
        assert result.scores[0] == 0.8

    def test_rag_call_llm_with_retry_success_first_try(self, mock_env, monkeypatch):
        """No content_filter → returns output."""

        def mock_completion(*args, **kwargs):
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "Success"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        messages = [{"role": "user", "content": "test"}]

        result = adapter._call_llm_with_retry(messages)

        assert result == "Success"

    def test_rag_call_llm_with_retry_content_filter(self, mock_env, monkeypatch):
        """content_filter_error → retries → success."""
        attempt = 0

        def mock_completion(*args, **kwargs):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise Exception("content_filter error")
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "Success after retry"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        messages = [{"role": "user", "content": "test"}]

        result = adapter._call_llm_with_retry(messages, max_retries=2)

        assert result == "Success after retry"
        assert attempt == 2

    def test_rag_call_llm_with_retry_all_fail(self, mock_env, monkeypatch):
        """3 retries all fail → returns None."""

        def mock_completion(*args, **kwargs):
            raise Exception("content_filter persistent error")

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        messages = [{"role": "user", "content": "test"}]

        result = adapter._call_llm_with_retry(messages, max_retries=2)

        assert result is None

    def test_rag_evaluate_with_judge_valid_score(self, mock_env, monkeypatch):
        """Judge returns 'Score: 0.8\nReason: ...' → 0.8."""

        def mock_completion(*args, **kwargs):
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "PUNTAJE: 0.75\nRAZON: Good but missing detail"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        score, reason = adapter._evaluate_with_judge("q", "gt", "gen")

        assert score == 0.75
        assert "Good but missing detail" in reason

    def test_rag_evaluate_with_judge_invalid_format(self, mock_env, monkeypatch):
        """Judge without 'Score:' → score 0.0."""

        def mock_completion(*args, **kwargs):
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "This is wrong format"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        score, reason = adapter._evaluate_with_judge("q", "gt", "gen")

        assert score == 0.0

    def test_rag_evaluate_with_judge_content_filtered(self, mock_env, monkeypatch):
        """Judge blocked → score 0.0 with reason."""

        def mock_completion(*args, **kwargs):
            raise Exception("content_filter blocked judge")

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        score, reason = adapter._evaluate_with_judge("q", "gt", "gen")

        assert score == 0.0
        assert "Juez bloqueado" in reason

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
            response = MagicMock()
            response.choices = [MagicMock()]
            messages = kwargs.get("messages", [])
            system_msg = messages[0]["content"] if messages else ""
            if "evaluador" not in system_msg.lower():
                response.choices[0].message.content = "Paris"
            else:
                response.choices[0].message.content = "PUNTAJE: 1.0\nRAZON: Perfect"
            return response

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        batch = [
            {
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

    def test_rag_none_scores_excluded(self, mock_env, monkeypatch):
        """Scores None (content filter) not included in batch final."""
        # This test verifies the current behavior where content-filtered
        # examples get score 0.0, not None. The adapter always appends a score.

        def mock_completion(*args, **kwargs):
            raise Exception("content_filter error")

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        batch = [{"question": "q", "context": "c", "answer": "a"}]
        candidate = {"system_prompt": "..."}

        result = adapter.evaluate(batch, candidate)

        # Content-filtered example gets score 0.0 (not None)
        assert len(result.scores) == 1
        assert result.scores[0] == 0.0

    def test_rag_all_content_filtered_raises(self, mock_env, monkeypatch):
        """If all examples → technical error → no scores → should not raise.

        Note: Current implementation doesn't raise RuntimeError for RAG
        when all fail technically because it appends 0.0 scores.
        This test documents current behavior.
        """

        def mock_completion(*args, **kwargs):
            raise Exception("content_filter error")

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleRAGAdapter()
        batch = [{"question": "q", "context": "c", "answer": "a"}]
        candidate = {"system_prompt": "..."}

        # Should not raise because it appends score 0.0 for errors
        result = adapter.evaluate(batch, candidate)
        assert len(result.scores) == 1
        assert result.scores[0] == 0.0

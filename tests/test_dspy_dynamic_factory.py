"""
Unit tests for dspy_gepa_poc/dynamic_factory.py.

Tests exhaustivos para DynamicModuleFactory, cubriendo:
- Creacion de signatures con diversos configs
- Creacion de modules con distintos predictor types
- Casos de borde (configs vacios, campos faltantes, etc.)
- Validacion de estructura de signatures y modules
"""

import dspy
import pytest

from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def minimal_config():
    """Configuracion minima valida."""
    return {
        "instruction": "Perform task.",
        "inputs": [{"name": "input"}],
        "outputs": [{"name": "output"}],
    }


@pytest.fixture
def full_config():
    """Configuracion completa con descripciones."""
    return {
        "instruction": "Classify the sentiment of the text.",
        "inputs": [
            {"name": "text", "desc": "The input text to classify."},
            {"name": "context", "desc": "Additional context."},
        ],
        "outputs": [
            {"name": "sentiment", "desc": "The predicted sentiment."},
            {"name": "confidence", "desc": "Confidence score."},
        ],
    }


@pytest.fixture
def no_desc_config():
    """Config sin descripciones (desc)."""
    return {
        "instruction": "Process input.",
        "inputs": [{"name": "query"}],
        "outputs": [{"name": "answer"}],
    }


# =============================================================================
# CREATE_SIGNATURE: Basic Functionality
# =============================================================================


class TestCreateSignatureBasic:
    def test_signature_is_subclass_of_dspy_signature(self, minimal_config):
        """Signature generada hereda de dspy.Signature."""
        sig = DynamicModuleFactory.create_signature(minimal_config)

        assert issubclass(sig, dspy.Signature)

    def test_signature_has_correct_docstring(self, minimal_config):
        """Docstring de la signature es la instruction."""
        sig = DynamicModuleFactory.create_signature(minimal_config)

        assert sig.__doc__ == "Perform task."

    def test_signature_has_input_fields(self, minimal_config):
        """Campos de input se crean correctamente."""
        sig = DynamicModuleFactory.create_signature(minimal_config)

        assert "input" in sig.fields
        field_type = sig.fields["input"].json_schema_extra.get("__dspy_field_type")
        assert field_type == "input"

    def test_signature_has_output_fields(self, minimal_config):
        """Campos de output se crean correctamente."""
        sig = DynamicModuleFactory.create_signature(minimal_config)

        assert "output" in sig.fields
        field_type = sig.fields["output"].json_schema_extra.get("__dspy_field_type")
        assert field_type == "output"

    def test_signature_field_descriptions_default(self, no_desc_config):
        """Descripciones default se generan si no se proveen."""
        sig = DynamicModuleFactory.create_signature(no_desc_config)

        query_field = sig.fields["query"]
        answer_field = sig.fields["answer"]

        assert "Input field: query" in query_field.json_schema_extra["desc"]
        assert "Output field: answer" in answer_field.json_schema_extra["desc"]

    def test_signature_field_descriptions_explicit(self, full_config):
        """Descripciones explicitas se usan cuando se proveen."""
        sig = DynamicModuleFactory.create_signature(full_config)

        text_field = sig.fields["text"]
        sentiment_field = sig.fields["sentiment"]

        assert text_field.json_schema_extra["desc"] == "The input text to classify."
        assert sentiment_field.json_schema_extra["desc"] == "The predicted sentiment."

    def test_signature_multiple_inputs(self, full_config):
        """Multiple campos de input se manejan correctamente."""
        sig = DynamicModuleFactory.create_signature(full_config)

        field_names = list(sig.fields.keys())
        assert "text" in field_names
        assert "context" in field_names

    def test_signature_multiple_outputs(self, full_config):
        """Multiple campos de output se manejan correctamente."""
        sig = DynamicModuleFactory.create_signature(full_config)

        field_names = list(sig.fields.keys())
        assert "sentiment" in field_names
        assert "confidence" in field_names


# =============================================================================
# CREATE_SIGNATURE: Edge Cases
# =============================================================================


class TestCreateSignatureEdgeCases:
    def test_empty_inputs_list(self):
        """Config con inputs vacio crea signature sin inputs."""
        config = {
            "instruction": "Task.",
            "inputs": [],
            "outputs": [{"name": "output"}],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert "output" in sig.fields
        input_fields = [
            f
            for f in sig.fields.values()
            if f.json_schema_extra.get("__dspy_field_type") == "input"
        ]
        assert len(input_fields) == 0

    def test_empty_outputs_list(self):
        """Config con outputs vacio crea signature sin outputs."""
        config = {
            "instruction": "Task.",
            "inputs": [{"name": "input"}],
            "outputs": [],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert "input" in sig.fields
        output_fields = [
            f
            for f in sig.fields.values()
            if f.json_schema_extra.get("__dspy_field_type") == "output"
        ]
        assert len(output_fields) == 0

    def test_missing_instruction(self):
        """Instruction ausente usa default."""
        config = {
            "inputs": [{"name": "input"}],
            "outputs": [{"name": "output"}],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert sig.__doc__ == "Perform the task."

    def test_empty_instruction(self):
        """Instruction vacia se respeta."""
        config = {
            "instruction": "",
            "inputs": [{"name": "input"}],
            "outputs": [{"name": "output"}],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert sig.__doc__ == ""

    def test_missing_inputs_key(self):
        """Key 'inputs' ausente no causa error."""
        config = {
            "instruction": "Task.",
            "outputs": [{"name": "output"}],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert "output" in sig.fields

    def test_missing_outputs_key(self):
        """Key 'outputs' ausente no causa error."""
        config = {
            "instruction": "Task.",
            "inputs": [{"name": "input"}],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert "input" in sig.fields

    def test_field_name_with_underscores(self):
        """Nombres de campo con underscores funcionan."""
        config = {
            "instruction": "Task.",
            "inputs": [{"name": "user_query"}],
            "outputs": [{"name": "llm_response"}],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert "user_query" in sig.fields
        assert "llm_response" in sig.fields

    def test_many_fields(self):
        """Muchos campos se manejan correctamente."""
        config = {
            "instruction": "Multi-field task.",
            "inputs": [{"name": f"input_{i}"} for i in range(10)],
            "outputs": [{"name": f"output_{i}"} for i in range(5)],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert len(sig.fields) == 15


# =============================================================================
# CREATE_MODULE: Basic Functionality
# =============================================================================


class TestCreateModuleBasic:
    def test_module_is_dspy_module(self, minimal_config):
        """Module generado es instancia de dspy.Module."""
        module = DynamicModuleFactory.create_module(minimal_config, predictor_type="predict")

        assert isinstance(module, dspy.Module)

    def test_module_has_predictor_attribute(self, minimal_config):
        """Module tiene atributo predictor."""
        module = DynamicModuleFactory.create_module(minimal_config, predictor_type="predict")

        assert hasattr(module, "predictor")

    def test_module_cot_creates_chain_of_thought(self, minimal_config):
        """predictor_type='cot' crea ChainOfThought."""
        module = DynamicModuleFactory.create_module(minimal_config, predictor_type="cot")

        assert isinstance(module.predictor, dspy.ChainOfThought)

    def test_module_predict_creates_predict(self, minimal_config):
        """predictor_type='predict' crea Predict."""
        module = DynamicModuleFactory.create_module(minimal_config, predictor_type="predict")

        assert isinstance(module.predictor, dspy.Predict)

    def test_module_has_forward_method(self, minimal_config):
        """Module tiene metodo forward."""
        module = DynamicModuleFactory.create_module(minimal_config, predictor_type="predict")

        assert hasattr(module, "forward")
        assert callable(module.forward)

    def test_module_default_predictor_type(self, minimal_config):
        """Default predictor_type es 'cot'."""
        module = DynamicModuleFactory.create_module(minimal_config)

        assert isinstance(module.predictor, dspy.ChainOfThought)


# =============================================================================
# CREATE_MODULE: Edge Cases
# =============================================================================


class TestCreateModuleEdgeCases:
    def test_module_with_empty_config(self):
        """Config vacio crea module valido (sin campos)."""
        config = {"instruction": "Task."}
        module = DynamicModuleFactory.create_module(config, predictor_type="predict")

        assert isinstance(module, dspy.Module)
        assert hasattr(module, "predictor")

    def test_module_with_complex_signature(self, full_config):
        """Module con signature compleja se crea correctamente."""
        module = DynamicModuleFactory.create_module(full_config, predictor_type="cot")

        assert isinstance(module, dspy.Module)
        assert isinstance(module.predictor, dspy.ChainOfThought)

    def test_predictor_type_case_sensitive(self, minimal_config):
        """predictor_type es case-sensitive ('CoT' != 'cot')."""
        module = DynamicModuleFactory.create_module(minimal_config, predictor_type="CoT")

        # 'CoT' != 'cot', asi que deberia crear Predict (default del else)
        assert isinstance(module.predictor, dspy.Predict)

    def test_predictor_type_invalid_creates_predict(self, minimal_config):
        """predictor_type invalido crea Predict (fallback)."""
        module = DynamicModuleFactory.create_module(minimal_config, predictor_type="invalid")

        assert isinstance(module.predictor, dspy.Predict)


# =============================================================================
# INTEGRATION: Signature + Module
# =============================================================================


class TestSignatureModuleIntegration:
    def test_signature_can_be_used_directly(self, minimal_config):
        """Signature generada se puede instanciar directamente."""
        sig_class = DynamicModuleFactory.create_signature(minimal_config)

        # Crear predictor con la signature
        predictor = dspy.Predict(sig_class)

        assert predictor is not None

    def test_module_signature_matches_config(self, full_config):
        """Signature dentro del module coincide con config."""
        module = DynamicModuleFactory.create_module(full_config, predictor_type="predict")

        # Acceder a la signature del predictor
        sig = module.predictor.signature

        assert "text" in sig.fields
        assert "context" in sig.fields
        assert "sentiment" in sig.fields
        assert "confidence" in sig.fields

    def test_multiple_modules_from_same_config(self, minimal_config):
        """Multiples modules desde mismo config son independientes."""
        module1 = DynamicModuleFactory.create_module(minimal_config, predictor_type="cot")
        module2 = DynamicModuleFactory.create_module(minimal_config, predictor_type="predict")

        assert isinstance(module1.predictor, dspy.ChainOfThought)
        assert isinstance(module2.predictor, dspy.Predict)
        assert module1 is not module2

    def test_signature_reusability(self, minimal_config):
        """Signature generada se puede reutilizar multiples veces."""
        sig_class = DynamicModuleFactory.create_signature(minimal_config)

        pred1 = dspy.Predict(sig_class)
        pred2 = dspy.ChainOfThought(sig_class)

        assert pred1 is not pred2
        # ChainOfThought wraps signature, so we compare the base class
        assert pred1.signature.__name__ == "DynamicTask"
        assert pred2.predict.signature.__name__ != "DynamicTask"  # CoT adds reasoning field


# =============================================================================
# FIELD VALIDATION
# =============================================================================


class TestFieldValidation:
    def test_input_field_type_correct(self, minimal_config):
        """InputField tiene tipo correcto."""
        sig = DynamicModuleFactory.create_signature(minimal_config)

        input_field = sig.fields["input"]
        field_type = input_field.json_schema_extra.get("__dspy_field_type")
        assert field_type == "input"

    def test_output_field_type_correct(self, minimal_config):
        """OutputField tiene tipo correcto."""
        sig = DynamicModuleFactory.create_signature(minimal_config)

        output_field = sig.fields["output"]
        field_type = output_field.json_schema_extra.get("__dspy_field_type")
        assert field_type == "output"

    def test_all_inputs_are_input_fields(self, full_config):
        """Todos los inputs son InputField."""
        sig = DynamicModuleFactory.create_signature(full_config)

        for name in ["text", "context"]:
            field_type = sig.fields[name].json_schema_extra.get("__dspy_field_type")
            assert field_type == "input"

    def test_all_outputs_are_output_fields(self, full_config):
        """Todos los outputs son OutputField."""
        sig = DynamicModuleFactory.create_signature(full_config)

        for name in ["sentiment", "confidence"]:
            field_type = sig.fields[name].json_schema_extra.get("__dspy_field_type")
            assert field_type == "output"


# =============================================================================
# DYNAMIC CLASS GENERATION
# =============================================================================


class TestDynamicClassGeneration:
    def test_signature_class_name(self, minimal_config):
        """Signature generada tiene nombre 'DynamicTask'."""
        sig = DynamicModuleFactory.create_signature(minimal_config)

        assert sig.__name__ == "DynamicTask"

    def test_signature_is_new_class_each_time(self, minimal_config):
        """Cada llamada crea una clase nueva."""
        sig1 = DynamicModuleFactory.create_signature(minimal_config)
        sig2 = DynamicModuleFactory.create_signature(minimal_config)

        # Mismo nombre y estructura, pero clases diferentes
        assert sig1.__name__ == sig2.__name__
        assert sig1 is not sig2

    def test_signature_bases_include_dspy_signature(self, minimal_config):
        """Signature hereda de dspy.Signature."""
        sig = DynamicModuleFactory.create_signature(minimal_config)

        assert dspy.Signature in sig.__mro__


# =============================================================================
# SPECIAL CHARACTERS AND NAMING
# =============================================================================


class TestSpecialCharactersAndNaming:
    def test_field_name_with_numbers(self):
        """Nombres con numeros funcionan."""
        config = {
            "instruction": "Task.",
            "inputs": [{"name": "input1"}, {"name": "input2"}],
            "outputs": [{"name": "output1"}],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert "input1" in sig.fields
        assert "input2" in sig.fields
        assert "output1" in sig.fields

    def test_long_field_names(self):
        """Nombres largos funcionan."""
        config = {
            "instruction": "Task.",
            "inputs": [{"name": "very_long_input_field_name_that_is_descriptive"}],
            "outputs": [{"name": "very_long_output_field_name_that_is_also_descriptive"}],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert "very_long_input_field_name_that_is_descriptive" in sig.fields
        assert "very_long_output_field_name_that_is_also_descriptive" in sig.fields

    def test_instruction_with_special_characters(self):
        """Instruction con caracteres especiales se preserva."""
        config = {
            "instruction": "Classify: is this positive/negative? Use 50% threshold!",
            "inputs": [{"name": "text"}],
            "outputs": [{"name": "label"}],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert sig.__doc__ == "Classify: is this positive/negative? Use 50% threshold!"

    def test_multiline_instruction(self):
        """Instruction multilinea se preserva."""
        config = {
            "instruction": "Task description:\n1. Read input\n2. Process\n3. Return output",
            "inputs": [{"name": "input"}],
            "outputs": [{"name": "output"}],
        }
        sig = DynamicModuleFactory.create_signature(config)

        assert "\n" in sig.__doc__
        assert "1. Read input" in sig.__doc__

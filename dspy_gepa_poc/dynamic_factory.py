from typing import Any

import dspy


class DynamicModuleFactory:
    """
    Creates DSPy Signatures and Modules dynamically from configuration.
    Enables Zero-Code experiment definition via YAML.
    """

    @staticmethod
    def create_signature(signature_config: dict[str, Any]) -> type[dspy.Signature]:
        """
        Generates a dspy.Signature class based on YAML config.

        Args:
            signature_config: Dict containing 'instruction', 'inputs', 'outputs'.

        Returns:
            A new dspy.Signature subclass.
        """
        fields = {}

        # 1. Create Input Fields
        for inp in signature_config.get("inputs", []):
            name = inp["name"]
            desc = inp.get("desc", f"Input field: {name}")
            fields[name] = dspy.InputField(desc=desc)

        # 2. Create Output Fields
        for out in signature_config.get("outputs", []):
            name = out["name"]
            desc = out.get("desc", f"Output field: {name}")
            fields[name] = dspy.OutputField(desc=desc)

        # 3. Create the Signature Class dynamically using Python's type()
        # This is more robust than make_signature for explicit field definitions
        instruction = signature_config.get("instruction", "Perform the task.")

        # Add docstring to fields dict (which becomes class attributes)
        fields["__doc__"] = instruction

        # Create the class: name, bases, attributes
        DynamicSig = type("DynamicTask", (dspy.Signature,), fields)  # noqa: N806

        return DynamicSig

    @staticmethod
    def create_module(signature_config: dict[str, Any], predictor_type: str = "cot") -> dspy.Module:
        """
        Creates a ready-to-use DSPy Module (Predict or CoT) with the dynamic signature.

        Args:
            signature_config: YAML config for the signature.
            predictor_type: 'cot' (ChainOfThought) or 'predict'.

        Returns:
            Instantiated dspy.Module.
        """
        signature_class = DynamicModuleFactory.create_signature(signature_config)

        class DynamicWrapper(dspy.Module):
            def __init__(self):
                super().__init__()
                if predictor_type == "cot":
                    self.predictor = dspy.ChainOfThought(signature_class)
                else:
                    self.predictor = dspy.Predict(signature_class)

            def forward(self, **kwargs):
                return self.predictor(**kwargs)

        return DynamicWrapper()

    @staticmethod
    def create_pipeline_module(
        stages_config: list[dict[str, Any]],
        routing_config: dict[str, Any],
    ) -> dspy.Module:
        """
        Crea un dspy.Module compuesto por N etapas en serie con routing condicional.

        La primera etapa (gate_stage) decide si las posteriores se ejecutan.
        Si el campo de routing toma el valor de gate_value, se invocan las etapas
        siguientes. Si no, se inyectan los valores fijos de skip_outputs_when_gated.

        Args:
            stages_config: lista de etapas; cada una con keys:
                - name: str
                - predictor_type: 'cot' | 'predict' (opcional, default 'cot')
                - signature: dict con instruction/inputs/outputs
            routing_config: dict con:
                - gate_stage: nombre de la etapa que dispara el gate
                - gate_field: campo del output del gate_stage a evaluar
                - gate_value: valor que abre las etapas posteriores
                - skip_outputs_when_gated: dict {output_name: valor_fijo} a
                  inyectar cuando NO se cumple la condición

        Returns:
            Un dspy.Module cuyo forward(**kwargs) devuelve un dspy.Prediction con
            todos los campos de output de todas las etapas (los saltados llevan
            valor fijo).
        """
        if len(stages_config) < 2:
            raise ValueError("pipeline requires at least 2 stages")

        gate_stage_name = routing_config["gate_stage"]
        gate_field = routing_config["gate_field"]
        gate_value = routing_config["gate_value"]
        skip_outputs = routing_config.get("skip_outputs_when_gated", {})

        # Validar que gate_stage existe
        stage_names = [s["name"] for s in stages_config]
        if gate_stage_name not in stage_names:
            raise ValueError(f"routing.gate_stage='{gate_stage_name}' not in stages: {stage_names}")
        gate_idx = stage_names.index(gate_stage_name)

        # Pre-armar todas las signatures
        stage_specs = []
        for stage in stages_config:
            sig_cls = DynamicModuleFactory.create_signature(stage["signature"])
            inputs = [i["name"] for i in stage["signature"]["inputs"]]
            outputs = [o["name"] for o in stage["signature"]["outputs"]]
            predictor_type = stage.get("predictor_type", "cot")
            stage_specs.append(
                {
                    "name": stage["name"],
                    "sig_cls": sig_cls,
                    "inputs": inputs,
                    "outputs": outputs,
                    "predictor_type": predictor_type,
                }
            )

        class PipelineModule(dspy.Module):
            def __init__(self):
                super().__init__()
                self._gate_idx = gate_idx
                self._gate_field = gate_field
                self._gate_value = gate_value
                self._skip_outputs = dict(skip_outputs)
                self._stage_specs = stage_specs
                # Crear un predictor por etapa como atributo nombrado para
                # que dspy.Module.named_predictors() los detecte y GEPA pueda
                # reflexionar sobre cada uno por separado.
                for spec in stage_specs:
                    if spec["predictor_type"] == "cot":
                        predictor = dspy.ChainOfThought(spec["sig_cls"])
                    else:
                        predictor = dspy.Predict(spec["sig_cls"])
                    setattr(self, spec["name"], predictor)

            def forward(self, **kwargs):
                accumulated = {}

                # Etapas hasta el gate (incluido)
                for i in range(self._gate_idx + 1):
                    spec = self._stage_specs[i]
                    predictor = getattr(self, spec["name"])
                    stage_kwargs = {k: kwargs[k] for k in spec["inputs"] if k in kwargs}
                    result = predictor(**stage_kwargs)
                    for out_name in spec["outputs"]:
                        accumulated[out_name] = getattr(result, out_name, "")

                # Decidir routing
                gate_actual = str(accumulated.get(self._gate_field, "")).strip()
                proceed = gate_actual == self._gate_value

                # Etapas posteriores al gate
                for i in range(self._gate_idx + 1, len(self._stage_specs)):
                    spec = self._stage_specs[i]
                    if proceed:
                        predictor = getattr(self, spec["name"])
                        stage_kwargs = {k: kwargs[k] for k in spec["inputs"] if k in kwargs}
                        result = predictor(**stage_kwargs)
                        for out_name in spec["outputs"]:
                            accumulated[out_name] = getattr(result, out_name, "")
                    else:
                        # Inyectar valores fijos
                        for out_name in spec["outputs"]:
                            accumulated[out_name] = self._skip_outputs.get(out_name, "")

                return dspy.Prediction(**accumulated)

        return PipelineModule()

import dspy
from typing import Dict, Any, Type

class DynamicModuleFactory:
    """
    Creates DSPy Signatures and Modules dynamically from configuration.
    Enables Zero-Code experiment definition via YAML.
    """

    @staticmethod
    def create_signature(signature_config: Dict[str, Any]) -> Type[dspy.Signature]:
        """
        Generates a dspy.Signature class based on YAML config.
        
        Args:
            signature_config: Dict containing 'instruction', 'inputs', 'outputs'.
            
        Returns:
            A new dspy.Signature subclass.
        """
        fields = {}

        # 1. Create Input Fields
        for inp in signature_config.get('inputs', []):
            name = inp['name']
            desc = inp.get('desc', f"Input field: {name}")
            fields[name] = dspy.InputField(desc=desc)

        # 2. Create Output Fields
        for out in signature_config.get('outputs', []):
            name = out['name']
            desc = out.get('desc', f"Output field: {name}")
            fields[name] = dspy.OutputField(desc=desc)

        # 3. Create the Signature Class dynamically using Python's type()
        # This is more robust than make_signature for explicit field definitions
        instruction = signature_config.get('instruction', "Perform the task.")
        
        # Add docstring to fields dict (which becomes class attributes)
        fields['__doc__'] = instruction
        
        # Create the class: name, bases, attributes
        DynamicSig = type('DynamicTask', (dspy.Signature,), fields)
        
        return DynamicSig

    @staticmethod
    def create_module(signature_config: Dict[str, Any], predictor_type: str = "cot") -> dspy.Module:
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

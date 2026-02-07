"""
Simple Extractor Adapter for GEPA

Adaptador para usar GEPA en tareas de extraccion estructurada.
Hereda de BaseAdapter.
"""

import json
from typing import Dict, List, Any, Optional
from gepa import EvaluationBatch
from gepa_standalone.adapters.base_adapter import BaseAdapter
from gepa_standalone.config import Config


class SimpleExtractorAdapter(BaseAdapter):
    """
    Adaptador GEPA para extracción estructurada.
    """

    def __init__(self, required_fields: List[str], temperature: float = 0.0,
                 max_positive_examples: Optional[int] = None):
        super().__init__(temperature=temperature)
        self.required_fields = required_fields

        # Configuración de ejemplos positivos en dataset reflexivo
        # Prioridad: parámetro explícito > Config > default (2)
        if max_positive_examples is not None:
            self.max_positive_examples = max_positive_examples
        elif hasattr(Config, 'EXTRACTOR_MAX_POSITIVE_EXAMPLES'):
            self.max_positive_examples = Config.EXTRACTOR_MAX_POSITIVE_EXAMPLES
        else:
            self.max_positive_examples = 2

    def evaluate(
        self,
        batch: List[Dict[str, Any]],
        candidate: Dict[str, str],
        capture_traces: bool = False
    ) -> EvaluationBatch:
        outputs = []
        scores = []
        trajectories = [] if capture_traces else None
        
        system_prompt = candidate.get("system_prompt", "")

        for idx, example in enumerate(batch):
            user_text = example.get("text", "")
            expected_fields = example.get("extracted", {})

            try:
                extracted_text = self.call_model(
                    system_prompt=system_prompt,
                    user_content=user_text,
                    max_tokens=300
                )

                # Parsear JSON
                try:
                    extracted_fields = json.loads(extracted_text)
                except json.JSONDecodeError:
                    extracted_fields = self._extract_json_from_text(extracted_text)

                # Comparar campos
                correct_fields = 0
                total_fields = len(expected_fields)
                field_comparisons = {}

                for field_name, expected_value in expected_fields.items():
                    extracted_val = str(extracted_fields.get(field_name, "")).strip().lower()
                    expected_val = str(expected_value).strip().lower()
                    
                    is_correct = (extracted_val == expected_val) and (field_name in extracted_fields)
                    
                    if is_correct:
                        correct_fields += 1
                        
                    field_comparisons[field_name] = {
                        "expected": expected_value,
                        "extracted": extracted_fields.get(field_name),
                        "correct": is_correct
                    }

                score = correct_fields / total_fields if total_fields > 0 else 0.0

                outputs.append({
                    "extracted": extracted_fields,
                    "expected": expected_fields,
                    "field_comparisons": field_comparisons,
                    "text": user_text
                })
                scores.append(score)

                if capture_traces:
                    trajectories.append({
                        "input": user_text,
                        "expected_fields": expected_fields,
                        "extracted_fields": extracted_fields,
                        "field_comparisons": field_comparisons,
                        "system_prompt": system_prompt,
                        "score": score
                    })

            except Exception as e:
                print(f"[WARNING] Error técnico en ejemplo {idx}, descartando: {e}")

        if not scores:
             raise RuntimeError(f"ERROR CRÍTICO: Todos los ejemplos fallaron ({len(batch)} totales).")

        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

    def make_reflective_dataset(
        self,
        candidate: Dict[str, str],
        eval_batch: EvaluationBatch,
        components_to_update: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        reflective_datasets = {component: [] for component in components_to_update}

        if "system_prompt" not in components_to_update:
            return reflective_datasets

        source_data = eval_batch.trajectories if eval_batch.trajectories else eval_batch.outputs

        for i, (data, score) in enumerate(zip(source_data, eval_batch.scores)):
            if score < 1.0:
                field_comparisons = data.get("field_comparisons", {})
                errors = []
                for fname, comp in field_comparisons.items():
                    if not comp.get("correct"):
                        got = comp.get("extracted", "MISSING")
                        exp = comp.get("expected")
                        errors.append(f"'{fname}': exp='{exp}', got='{got}'")

                # Truncar texto según configuración
                cv_text = data.get("input", data.get("text", ""))
                max_len = Config.EXTRACTOR_TEXT_MAX_LENGTH
                if len(cv_text) > max_len:
                    cv_text_truncado = cv_text[:max_len] + "..."
                    print(f"[INFO] CV texto truncado de {len(cv_text)} a {max_len} caracteres para reflexión (Extractor)")
                else:
                    cv_text_truncado = cv_text

                reflective_record = {
                    "Inputs": {"cv_text": cv_text_truncado},
                    "Generated Outputs": {"extracted_fields": data.get("extracted_fields", data.get("extracted"))},
                    "Feedback": f"Errores: {'; '.join(errors)}. Revisa el formato JSON y la extracción exacta.",
                    "Type": "negative_example"
                }
                reflective_datasets["system_prompt"].append(reflective_record)

        # Agregar ejemplos positivos (éxitos) para refuerzo positivo
        if self.max_positive_examples > 0:
            positive_examples = [
                (data, score)
                for data, score in zip(source_data, eval_batch.scores)
                if score == 1.0
            ]

            for data, score in positive_examples[:self.max_positive_examples]:
                cv_text = data.get("input", data.get("text", ""))
                max_len = Config.EXTRACTOR_TEXT_MAX_LENGTH
                cv_text_truncado = cv_text[:max_len] + "..." if len(cv_text) > max_len else cv_text

                # Generar feedback positivo destacando qué funcionó bien
                extracted = data.get("extracted_fields", data.get("extracted", {}))
                expected = data.get("expected", {})

                # Identificar campos correctos
                correct_fields = []
                for field, value in extracted.items():
                    if field in expected and expected[field] == value:
                        correct_fields.append(f"'{field}': '{value}'")

                success_feedback = f"EJEMPLO EXITOSO: Extracción perfecta. Campos correctos: {', '.join(correct_fields)}."

                reflective_record = {
                    "Inputs": {"cv_text": cv_text_truncado},
                    "Generated Outputs": {"extracted_fields": extracted},
                    "Feedback": success_feedback,
                    "Type": "positive_example"
                }
                reflective_datasets["system_prompt"].append(reflective_record)

        # Log de estadísticas del dataset reflexivo
        num_negativos = len([r for r in reflective_datasets["system_prompt"] if r.get("Type") == "negative_example"])
        num_positivos = len([r for r in reflective_datasets["system_prompt"] if r.get("Type") == "positive_example"])
        if num_negativos > 0 or num_positivos > 0:
            print(f"[INFO] Dataset reflexivo (Extractor): {num_negativos} negativos, {num_positivos} positivos")

        return reflective_datasets

    def _extract_json_from_text(self, text: str) -> Dict[str, str]:
        import re
        start = text.find('{')
        if start == -1: return {}
        count = 0
        for i in range(start, len(text)):
            if text[i] == '{': count += 1
            elif text[i] == '}': 
                count -= 1
                if count == 0:
                    try: return json.loads(text[start:i+1])
                    except: pass
        return {}
"""
Simple Classifier Adapter for GEPA

Adaptador para usar GEPA en tareas de clasificacion simple.
Hereda de BaseAdapter para gestion centralizada de conexion.
"""

from typing import Any

from gepa import EvaluationBatch

from gepa_standalone.adapters.base_adapter import BaseAdapter
from gepa_standalone.config import Config


class SimpleClassifierAdapter(BaseAdapter):
    """
    Adaptador GEPA para clasificación simple.
    """

    def __init__(self, valid_classes: list[str], temperature: float = 0.0):
        # Inicializar clase base (configura cliente y deployment)
        super().__init__(temperature=temperature)
        self.valid_classes = valid_classes

    def evaluate(
        self, batch: list[dict[str, Any]], candidate: dict[str, str], capture_traces: bool = False
    ) -> EvaluationBatch:
        outputs = []
        scores = []
        trajectories = [] if capture_traces else None

        system_prompt = candidate.get("system_prompt", "")

        for idx, example in enumerate(batch):
            user_text = example.get("text", "")
            expected_class = example.get(self._get_label_key(example), "")

            try:
                # Usar método helper de la clase base
                predicted_class = self.call_model(
                    system_prompt=system_prompt, user_content=user_text, max_tokens=50
                ).lower()

                # Score
                is_correct = predicted_class == expected_class.lower()
                score = 1.0 if is_correct else 0.0

                outputs.append(
                    {"predicted": predicted_class, "expected": expected_class, "text": user_text}
                )
                scores.append(score)

                if capture_traces:
                    trajectories.append(
                        {
                            "input": user_text,
                            "expected": expected_class,
                            "predicted": predicted_class,
                            "system_prompt": system_prompt,
                            "correct": is_correct,
                        }
                    )

            except Exception as e:
                print(f"[WARNING] Error técnico en ejemplo {idx}, descartando: {e}")

        if not scores:
            raise RuntimeError(
                f"ERROR CRÍTICO: Todos los ejemplos fallaron ({len(batch)} totales)."
            )

        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch,
        components_to_update: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        reflective_datasets = {component: [] for component in components_to_update}

        if "system_prompt" not in components_to_update:
            return reflective_datasets

        # Usar trajectories si existen, sino outputs
        source_data = eval_batch.trajectories if eval_batch.trajectories else eval_batch.outputs

        for _i, (data, score) in enumerate(zip(source_data, eval_batch.scores, strict=False)):
            if score < 1.0:
                # Extraer datos dependiendo de si viene de trajectory o output
                text = data.get("input", data.get("text", ""))
                pred = data.get("predicted", "")
                exp = data.get("expected", "")

                # Truncar texto según configuración
                max_len = Config.CLASSIFIER_TEXT_MAX_LENGTH
                if len(text) > max_len:
                    text_truncado = text[:max_len] + "..."
                    print(
                        f"[INFO] Texto truncado de {len(text)} a {max_len} "
                        f"caracteres para reflexión (Classifier)"
                    )
                else:
                    text_truncado = text

                reflective_record = {
                    "Inputs": {"text": text_truncado},
                    "Generated Outputs": {"predicted_class": pred, "expected_class": exp},
                    "Feedback": (
                        f"Clasificación incorrecta. Se esperaba '{exp}' pero se obtuvo '{pred}'."
                    ),
                }
                reflective_datasets["system_prompt"].append(reflective_record)

        return reflective_datasets

    def _get_label_key(self, example: dict[str, Any]) -> str:
        possible_keys = ["urgency", "label", "class", "sentiment"]
        for key in possible_keys:
            if key in example:
                return key
        return "label"

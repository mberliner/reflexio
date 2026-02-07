"""
Simple SQL Adapter for GEPA

Adaptador para tareas de Text-to-SQL.
Hereda de BaseAdapter.
"""

import re
from typing import Dict, List, Any
from gepa import EvaluationBatch
from gepa_standalone.adapters.base_adapter import BaseAdapter


class SimpleSQLAdapter(BaseAdapter):
    """
    Adaptador GEPA para generación de SQL.
    """

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
            question = example.get("question", "")
            schema = example.get("extracted", {}).get("schema", "")
            expected_sql = example.get("extracted", {}).get("expected_sql", "")

            try:
                user_content = f"Esquema: {schema}\nPregunta: {question}"
                
                predicted_sql = self.call_model(
                    system_prompt=system_prompt,
                    user_content=user_content,
                    max_tokens=200
                )
                
                # Limpieza
                predicted_sql = re.sub(r'```sql|```', '', predicted_sql).strip()

                is_correct = self._compare_sql(predicted_sql, expected_sql)
                score = 1.0 if is_correct else 0.0

                outputs.append({
                    "predicted": predicted_sql,
                    "expected": expected_sql,
                    "question": question
                })
                scores.append(score)

                if capture_traces:
                    trajectories.append({
                        "input": user_content,
                        "expected": expected_sql,
                        "predicted": predicted_sql,
                        "correct": is_correct
                    })

            except Exception as e:
                print(f"[WARNING] Error técnico en ejemplo {idx}, descartando: {e}")

        if not scores:
             raise RuntimeError(f"ERROR CRÍTICO: Todos los ejemplos fallaron ({len(batch)} totales).")

        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

    def _compare_sql(self, sql1: str, sql2: str) -> bool:
        def normalize(s):
            s = s.strip().lower().rstrip(';')
            s = re.sub(r'\s+', ' ', s)
            return s
        return normalize(sql1) == normalize(sql2)

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
                reflective_record = {
                    "Inputs": {
                        "question": data.get("question", ""),
                        "expected_sql": data.get("expected", "")
                    },
                    "Generated Outputs": {"predicted_sql": data.get("predicted", "")},
                    "Feedback": "El SQL generado no coincide con el esperado. Sigue el esquema y sintaxis exacta."
                }
                reflective_datasets["system_prompt"].append(reflective_record)

        return reflective_datasets
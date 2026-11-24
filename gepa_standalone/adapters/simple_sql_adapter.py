"""
Simple SQL Adapter for GEPA

Adaptador para tareas de Text-to-SQL.
Hereda de BaseAdapter.
"""

import re
from typing import Any

from gepa import EvaluationBatch

from gepa_standalone.adapters.base_adapter import BaseAdapter


class SimpleSQLAdapter(BaseAdapter):
    """
    Adaptador GEPA para generación de SQL.
    """

    task_max_tokens = 200

    @staticmethod
    def _user_content(example: dict[str, Any]) -> str:
        extracted = example.get("extracted", {})
        return f"Esquema: {extracted.get('schema', '')}\nPregunta: {example.get('question', '')}"

    def _task_call(self, system_prompt: str, example: dict[str, Any]) -> str:
        return self.call_model(
            system_prompt=system_prompt,
            user_content=self._user_content(example),
            max_tokens=self.task_max_tokens,
        )

    def evaluate(
        self, batch: list[dict[str, Any]], candidate: dict[str, str], capture_traces: bool = False
    ) -> EvaluationBatch:
        outputs = []
        scores = []
        trajectories = [] if capture_traces else None

        system_prompt = candidate.get("system_prompt", "")

        for example in batch:
            case_id = self._case_id(example)
            question = example.get("question", "")
            expected_sql = example.get("extracted", {}).get("expected_sql", "")
            user_content = self._user_content(example)

            raw, failure = self._run_task_case(system_prompt, example, case_id)
            predicted_sql = ""
            if failure is None:
                # Limpieza
                predicted_sql = re.sub(r"```sql\s*|```", "", raw, flags=re.IGNORECASE).strip()

            is_correct = failure is None and self._compare_sql(predicted_sql, expected_sql)
            score = 1.0 if is_correct else 0.0
            meta = self._case_meta(case_id, failure)

            outputs.append(
                {
                    "predicted": predicted_sql,
                    "expected": expected_sql,
                    "question": question,
                    **meta,
                }
            )
            scores.append(score)

            if capture_traces:
                trajectories.append(
                    {
                        "input": user_content,
                        "expected": expected_sql,
                        "predicted": predicted_sql,
                        "correct": is_correct,
                        **meta,
                    }
                )

        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

    def _compare_sql(self, sql1: str, sql2: str) -> bool:
        def normalize(s):
            s = s.strip().lower().rstrip(";")
            s = re.sub(r"\s+", " ", s)
            return s

        return normalize(sql1) == normalize(sql2)

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch,
        components_to_update: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        reflective_datasets = {component: [] for component in components_to_update}

        if "system_prompt" not in components_to_update:
            return reflective_datasets

        source_data = eval_batch.trajectories if eval_batch.trajectories else eval_batch.outputs

        for i, (data, score) in enumerate(zip(source_data, eval_batch.scores, strict=False)):
            # Un caso NE nunca llega al Profesor (FR-012)
            if not self._case_evaluated(eval_batch, i, data):
                continue
            if score < 1.0:
                reflective_record = {
                    "Inputs": {
                        "question": data.get("question", ""),
                        "expected_sql": data.get("expected", ""),
                    },
                    "Generated Outputs": {"predicted_sql": data.get("predicted", "")},
                    "Feedback": self._failure_feedback(data)
                    or (
                        "El SQL generado no coincide con el esperado. "
                        "Sigue el esquema y sintaxis exacta."
                    ),
                }
                reflective_datasets["system_prompt"].append(reflective_record)

        return reflective_datasets

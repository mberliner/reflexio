"""
Simple RAG Adapter for GEPA

Adaptador para optimizar prompts de sistemas RAG (Retrieval-Augmented Generation).
Simula la fase de recuperacion leyendo el contexto directamente del dataset.
Usa un LLM como juez para evaluar la calidad de la respuesta generada.
"""

import json
import logging
import math
from dataclasses import replace
from typing import Any

import litellm
from gepa import EvaluationBatch

from gepa_standalone.adapters.base_adapter import BaseAdapter
from gepa_standalone.config import Config
from shared.llm import FailureClass, LLMCallFailure, LLMConfig, LLMFailure, get_failure_tracker
from shared.llm.config import complete_text

logger = logging.getLogger(__name__)

DEFAULT_JUDGE_RETRIES = 2


class SimpleRAGAdapter(BaseAdapter):
    """
    Adaptador GEPA para sistemas RAG.

    Flujo:
    1. Recibe (pregunta, contexto) del dataset.
    2. Genera respuesta usando el prompt candidato.
    3. Evalua la respuesta usando un LLM Juez (Model-Based Evaluation).
    """

    task_max_tokens = 400
    judge_max_tokens = 200

    def __init__(
        self,
        judge_config: LLMConfig,
        temperature: float = 0.0,
        max_positive_examples: int | None = None,
        judge_retries: int = DEFAULT_JUDGE_RETRIES,
    ):
        super().__init__(temperature=temperature)
        if (
            isinstance(judge_retries, bool)
            or not isinstance(judge_retries, int)
            or judge_retries < 0
        ):
            raise ValueError(f"judge_retries debe ser un entero >= 0: {judge_retries!r}")
        # Reintentos ante un puntaje ilegible o fuera de rango (SPEC-104 FR-009)
        self.judge_retries = judge_retries
        # Configuracion del juez inyectada por el orquestador (SPEC-106 D8): el adapter
        # no la reconstruye desde el entorno.
        self._judge_config = judge_config
        self.judge_model = self._judge_config.model

        # Configuracion de ejemplos positivos en dataset reflexivo
        # Prioridad: parametro explicito > Config > default (2)
        if max_positive_examples is not None:
            self.max_positive_examples = max_positive_examples
        elif hasattr(Config, "RAG_MAX_POSITIVE_EXAMPLES"):
            self.max_positive_examples = Config.RAG_MAX_POSITIVE_EXAMPLES
        else:
            self.max_positive_examples = 2

    @property
    def judge_config(self) -> LLMConfig:
        """Configuracion del juez (rol `judge`), de solo lectura para el orquestador."""
        return self._judge_config

    def _sanitize_for_reflection(self, text: str) -> str:
        """
        Sanitiza texto para evitar filtros de moderacion Azure en el modelo de reflexion.
        Reemplaza terminos que puedan activar content_filter/jailbreak detection.
        """
        if not text:
            return text

        sanitized = text.replace("ERROR:", "Caso incorrecto:")
        sanitized = sanitized.replace("alucinacion", "informacion no verificable")
        sanitized = sanitized.replace("incorrecta", "no optima")
        sanitized = sanitized.replace("error", "problema")

        # Truncar feedback muy largo que pueda contener patrones problematicos
        if len(sanitized) > 500:
            sanitized = sanitized[:497] + "..."

        return sanitized

    def _complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 300,
        is_judge: bool = False,
    ) -> str:
        """
        Llama al LLM por la llamada comun (SPEC-104, D3): sin reintento propio del
        adapter. Una falla sale como `LLMCallFailure` (o `RunAborted`).

        Args:
            messages: Lista de mensajes para el modelo.
            max_tokens: Maximo de tokens para la respuesta.
            is_judge: True para el juez (modelo y config de reflexion, rol `judge`).

        Returns:
            Contenido de la respuesta.
        """
        config = self._judge_config if is_judge else self._config

        litellm.drop_params = True
        call_kwargs = config.to_kwargs()
        call_kwargs["max_tokens"] = max_tokens
        if not is_judge:
            # Task generation uses the adapter temperature, like BaseAdapter.call_model.
            call_kwargs["temperature"] = self.temperature
        call_kwargs = config.apply_constraints(call_kwargs)

        return complete_text(call_kwargs, messages, "judge" if is_judge else "task")

    @staticmethod
    def _user_content(example: dict[str, Any]) -> str:
        return (
            f"Contexto:\n{example.get('context', '')}\n\nPregunta:\n{example.get('question', '')}"
        )

    def _task_call(self, system_prompt: str, example: dict[str, Any]) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._user_content(example)},
        ]
        return self._complete(messages, max_tokens=self.task_max_tokens)

    def evaluate(
        self, batch: list[dict[str, Any]], candidate: dict[str, str], capture_traces: bool = False
    ) -> EvaluationBatch:
        outputs = []
        scores = []
        trajectories = [] if capture_traces else None

        system_prompt = candidate.get("system_prompt", "")
        tracker = get_failure_tracker()

        for example in batch:
            case_id = self._case_id(example)
            question = example.get("question", "")
            context = example.get("context", "")
            ground_truth = example.get("answer", "")

            # 1. Generacion (Task Model)
            response_content, failure = self._run_task_case(system_prompt, example, case_id)
            generated_answer = ""
            score = 0.0
            feedback = ""

            # 2. Evaluacion (Judge Model): solo si la tarea respondio; una falla del
            # juez deja el caso NE con rol `judge` (tambien su `formato`, FR-009).
            if failure is None:
                generated_answer = response_content.strip()
                tracker.check_abort()
                tracker.record_attempt("judge", case_id)
                try:
                    score, feedback = self._evaluate_with_judge(
                        question=question,
                        ground_truth=ground_truth,
                        generated_answer=generated_answer,
                    )
                except LLMCallFailure as exc:
                    failure = replace(exc.failure, case_id=case_id)
                    tracker.record(failure)
                    tracker.check_abort()
                    score, feedback = 0.0, ""

            meta = self._case_meta(case_id, failure)
            outputs.append(
                {
                    "generated_answer": generated_answer,
                    "ground_truth": ground_truth,
                    "judge_feedback": feedback,
                    **meta,
                }
            )
            scores.append(score)

            if capture_traces:
                trajectories.append(
                    {
                        "question": question,
                        "context": context,
                        "ground_truth": ground_truth,
                        "generated_answer": generated_answer,
                        "score": score,
                        "judge_feedback": feedback,
                        "system_prompt": system_prompt,
                        **meta,
                    }
                )

        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

    def _evaluate_with_judge(
        self, question: str, ground_truth: str, generated_answer: str
    ) -> tuple[float, str]:
        """
        Usa un LLM para comparar la respuesta generada con la verdad base.
        Retorna (score 0.0-1.0, feedback_textual).
        """
        judge_prompt = (
            "Eres un evaluador experto de sistemas RAG en español.\n\n"
            "CRITERIOS DE EVALUACIÓN:\n"
            "1. PRECISIÓN FACTUAL: ¿Los hechos son correctos según el contexto?\n"
            "2. COMPLETITUD: ¿Incluye detalles críticos (números, condiciones, excepciones)?\n"
            "3. ALUCINACIÓN: ¿Inventa información no presente en el contexto?\n"
            "4. RELEVANCIA: ¿Responde exactamente lo preguntado?\n\n"
            "ESCALA:\n"
            "1.0 = Perfecta: todos los detalles críticos, sin alucinaciones\n"
            "0.75 = Buena: correcta pero omite detalle menor\n"
            "0.5 = Parcial: correcta en esencial pero falta info clave\n"
            "0.25 = Pobre: mayormente incorrecta o alucinaciones\n"
            "0.0 = Fallida: completamente incorrecta o no responde\n\n"
            "INSTRUCCIONES:\n"
            "- Ignora diferencias menores de redacción\n"
            "- Penaliza fuertemente alucinaciones\n"
            "- Números y límites son CRÍTICOS\n"
            "- Si contexto no tiene info, debe admitir desconocimiento\n\n"
            "FORMATO DE RESPUESTA: responde SOLO con un objeto JSON, sin texto adicional "
            "ni bloques de codigo, con las claves puntaje (numero entre 0.0 y 1.0) y "
            "razon (explicacion breve)."
        )

        user_content = (
            f"Pregunta: {question}\n"
            f"Respuesta Ideal: {ground_truth}\n"
            f"Respuesta Generada: {generated_answer}"
        )

        # Llamada al modelo Judge
        messages = [
            {"role": "system", "content": judge_prompt},
            {"role": "user", "content": user_content},
        ]

        # Un puntaje ilegible o fuera de rango se reintenta; agotados los reintentos
        # es `formato` del juez (NE). Las fallas de capa 1 salen sin reintento.
        attempts = self.judge_retries + 1
        problem = ""
        for attempt in range(1, attempts + 1):
            content = self._complete(
                messages, max_tokens=self.judge_max_tokens, is_judge=True
            ).strip()
            parsed = self._parse_judge_score(content)
            if isinstance(parsed, tuple):
                return parsed
            problem = parsed
            logger.debug(
                "Puntaje del juez invalido (intento %d/%d): %s", attempt, attempts, problem
            )

        raise LLMCallFailure(
            LLMFailure(
                clase=FailureClass.formato,
                rol="judge",
                causa=f"puntaje del juez invalido tras {attempts} intentos: {problem}",
            )
        )

    @staticmethod
    def _parse_judge_score(content: str) -> tuple[float, str] | str:
        """
        `(puntaje, razon)` si el JSON del juez es valido; si no, el motivo (str).

        El puntaje MUST ser un numero finito en [0.0, 1.0] (FR-009); un booleano no es
        un numero.
        """
        start, end = content.find(chr(123)), content.rfind(chr(125))
        if start == -1 or end <= start:
            return "sin objeto JSON"
        try:
            data = json.loads(content[start : end + 1])
        except ValueError:
            return "JSON no parseable"
        if not isinstance(data, dict) or "puntaje" not in data:
            return "falta el campo puntaje"
        raw = data["puntaje"]
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            return f"puntaje no numerico: {raw!r}"
        score = float(raw)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            return f"puntaje fuera de rango [0.0, 1.0]: {raw!r}"
        return score, str(data.get("razon", "")).strip()

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
            # Proporcionar feedback si el score no es perfecto
            if score < 1.0:
                q = data.get("question", "")
                ctx = data.get("context", "")
                gen = data.get("generated_answer", "")
                gt = data.get("ground_truth", "")
                fb = self._failure_feedback(data) or data.get(
                    "judge_feedback", "Respuesta incorrecta."
                )

                # Truncar contexto según configuración
                max_len = Config.RAG_CONTEXT_MAX_LENGTH
                if len(ctx) > max_len:
                    contexto_truncado = ctx[:max_len] + "..."
                    print(
                        f"[INFO] Contexto truncado de {len(ctx)} a {max_len} "
                        f"caracteres para reflexión"
                    )
                else:
                    contexto_truncado = ctx

                # Sanitizar todos los campos para evitar filtros de moderación
                reflective_record = {
                    "Inputs": {
                        "pregunta": self._sanitize_for_reflection(q),
                        "contexto": self._sanitize_for_reflection(contexto_truncado),
                    },
                    "Generated Outputs": {"respuesta_generada": self._sanitize_for_reflection(gen)},
                    "Ideal Output (Ground Truth)": self._sanitize_for_reflection(gt),
                    "Feedback (del Juez)": self._sanitize_for_reflection(fb),
                    "Type": "negative_example",
                }
                reflective_datasets["system_prompt"].append(reflective_record)

        # Agregar ejemplos positivos (éxitos) para refuerzo positivo
        if self.max_positive_examples > 0:
            positive_examples = [
                (data, score)
                for data, score in zip(source_data, eval_batch.scores, strict=False)
                if score == 1.0
            ]

            for data, _score in positive_examples[: self.max_positive_examples]:
                q = data.get("question", "")
                ctx = data.get("context", "")
                gen = data.get("generated_answer", "")
                gt = data.get("ground_truth", "")
                fb = data.get("judge_feedback", "Respuesta perfecta.")

                # Truncar contexto según configuración
                max_len = Config.RAG_CONTEXT_MAX_LENGTH
                contexto_truncado = ctx[:max_len] + "..." if len(ctx) > max_len else ctx

                # Sanitizar todos los campos para evitar filtros de moderación
                reflective_record = {
                    "Inputs": {
                        "pregunta": self._sanitize_for_reflection(q),
                        "contexto": self._sanitize_for_reflection(contexto_truncado),
                    },
                    "Generated Outputs": {"respuesta_generada": self._sanitize_for_reflection(gen)},
                    "Ideal Output (Ground Truth)": self._sanitize_for_reflection(gt),
                    "Feedback (del Juez)": f"EJEMPLO EXITOSO: {self._sanitize_for_reflection(fb)}",
                    "Type": "positive_example",
                }
                reflective_datasets["system_prompt"].append(reflective_record)

        # Log de estadísticas del dataset reflexivo
        num_negativos = len(
            [r for r in reflective_datasets["system_prompt"] if r.get("Type") == "negative_example"]
        )
        num_positivos = len(
            [r for r in reflective_datasets["system_prompt"] if r.get("Type") == "positive_example"]
        )
        if num_negativos > 0 or num_positivos > 0:
            print(f"[INFO] Dataset reflexivo: {num_negativos} negativos, {num_positivos} positivos")

        return reflective_datasets

"""
Simple RAG Adapter for GEPA

Adaptador para optimizar prompts de sistemas RAG (Retrieval-Augmented Generation).
Simula la fase de recuperacion leyendo el contexto directamente del dataset.
Usa un LLM como juez para evaluar la calidad de la respuesta generada.
"""

import time
from typing import Dict, List, Any, Optional
import litellm
from gepa import EvaluationBatch
from gepa_standalone.adapters.base_adapter import BaseAdapter
from gepa_standalone.config import Config
from gepa_standalone.core.llm_factory import get_reflection_config


class SimpleRAGAdapter(BaseAdapter):
    """
    Adaptador GEPA para sistemas RAG.

    Flujo:
    1. Recibe (pregunta, contexto) del dataset.
    2. Genera respuesta usando el prompt candidato.
    3. Evalua la respuesta usando un LLM Juez (Model-Based Evaluation).
    """

    def __init__(self, temperature: float = 0.0, max_positive_examples: Optional[int] = None):
        super().__init__(temperature=temperature)
        # Usamos el modelo "Profesor" (mas potente) para juzgar
        self._judge_config = get_reflection_config()
        self.judge_model = self._judge_config.model

        # Configuracion de ejemplos positivos en dataset reflexivo
        # Prioridad: parametro explicito > Config > default (2)
        if max_positive_examples is not None:
            self.max_positive_examples = max_positive_examples
        elif hasattr(Config, 'RAG_MAX_POSITIVE_EXAMPLES'):
            self.max_positive_examples = Config.RAG_MAX_POSITIVE_EXAMPLES
        else:
            self.max_positive_examples = 2

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

    def _call_llm_with_retry(
        self,
        messages: List[Dict[str, str]],
        max_retries: int = 2,
        is_reflection: bool = False,
        max_tokens: int = 300,
        model: Optional[str] = None
    ) -> Optional[str]:
        """
        Llama al LLM con manejo de errores y reintentos.

        Args:
            messages: Lista de mensajes para el modelo
            max_retries: Numero maximo de reintentos
            is_reflection: True si es llamada al modelo de reflexion GEPA
            max_tokens: Maximo de tokens para la respuesta
            model: Modelo a usar (si None, usa self.model)

        Returns:
            Contenido de la respuesta o None si fallo
        """
        target_model = model or self.model
        config = self._judge_config if model == self.judge_model else self._config

        for attempt in range(max_retries):
            try:
                response = litellm.completion(
                    model=target_model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=max_tokens,
                    api_key=config.api_key,
                    api_base=config.api_base,
                    api_version=config.api_version,
                )
                return response.choices[0].message.content
            except Exception as e:
                error_str = str(e)

                # Detectar errores de content_filter
                if "content_filter" in error_str or "jailbreak" in error_str:
                    role = "Reflection LM" if is_reflection else "Task/Judge LM"
                    print(f"[WARNING] {role} bloqueado por content filter (intento {attempt+1}/{max_retries})")

                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    else:
                        print(f"[ERROR] Fallo despues de {max_retries} intentos. Saltando esta iteracion.")
                        return None
                else:
                    # Error diferente, propagar
                    raise

        return None

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
            context = example.get("context", "")
            ground_truth = example.get("answer", "")

            # Construir input completo para el modelo de tarea
            user_content = f"Contexto:\n{context}\n\nPregunta:\n{question}"

            try:
                # 1. Generacion (Task Model) con retry
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
                response_content = self._call_llm_with_retry(messages, max_tokens=400, is_reflection=False)

                if response_content is None:
                    outputs.append({"error": "Content filter blocked request"})
                    scores.append(0.0)
                    if capture_traces:
                        trajectories.append({"error": "Content filter blocked request"})
                    continue

                generated_answer = response_content.strip()

                # 2. Evaluación (Judge Model)
                score, feedback = self._evaluate_with_judge(
                    question=question,
                    ground_truth=ground_truth,
                    generated_answer=generated_answer
                )

                outputs.append({
                    "generated_answer": generated_answer,
                    "ground_truth": ground_truth,
                    "judge_feedback": feedback
                })
                scores.append(score)

                if capture_traces:
                    trajectories.append({
                        "question": question,
                        "context": context,
                        "ground_truth": ground_truth,
                        "generated_answer": generated_answer,
                        "score": score,
                        "judge_feedback": feedback,
                        "system_prompt": system_prompt
                    })

            except Exception as e:
                print(f"[WARNING] Error en ejemplo {idx}: {e}")
                # Penalizar fallos técnicos
                outputs.append({"error": str(e)})
                scores.append(0.0)
                if capture_traces:
                    trajectories.append({"error": str(e)})

        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

    def _evaluate_with_judge(self, question: str, ground_truth: str, generated_answer: str) -> tuple[float, str]:
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

            "Formato:\n"
            "PUNTAJE: [0.0, 0.25, 0.5, 0.75, 1.0]\n"
            "RAZON: [Explicación detallada]"
        )
        
        user_content = (
            f"Pregunta: {question}\n"
            f"Respuesta Ideal: {ground_truth}\n"
            f"Respuesta Generada: {generated_answer}"
        )

        try:
            # Llamada al modelo Judge con retry
            messages = [
                {"role": "system", "content": judge_prompt},
                {"role": "user", "content": user_content}
            ]

            # Usar retry para manejar errores de content filter
            content = self._call_llm_with_retry(
                messages,
                max_tokens=200,
                is_reflection=False,
                model=self.judge_model
            )

            if content is None:
                return 0.0, "Juez bloqueado por content filter"

            content = content.strip()
            
            # Parsear respuesta
            score = 0.0
            reason = content
            
            lines = content.split('\n')
            for line in lines:
                if line.upper().startswith("PUNTAJE:") or line.upper().startswith("SCORE:"):
                    try:
                        score_str = line.split(":")[1].strip()
                        score = float(score_str)
                    except:
                        pass
                if line.upper().startswith("RAZON:") or line.upper().startswith("REASON:"):
                    reason = line.split(":", 1)[1].strip()
            
            return score, reason

        except Exception as e:
            return 0.0, f"Error del Juez: {str(e)}"

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
            # Proporcionar feedback si el score no es perfecto
            if score < 1.0:
                q = data.get("question", "")
                ctx = data.get("context", "")
                gen = data.get("generated_answer", "")
                gt = data.get("ground_truth", "")
                fb = data.get("judge_feedback", "Respuesta incorrecta.")

                # Truncar contexto según configuración
                max_len = Config.RAG_CONTEXT_MAX_LENGTH
                if len(ctx) > max_len:
                    contexto_truncado = ctx[:max_len] + "..."
                    print(f"[INFO] Contexto truncado de {len(ctx)} a {max_len} caracteres para reflexión")
                else:
                    contexto_truncado = ctx

                # Sanitizar todos los campos para evitar filtros de moderación
                reflective_record = {
                    "Inputs": {
                        "pregunta": self._sanitize_for_reflection(q),
                        "contexto": self._sanitize_for_reflection(contexto_truncado)
                    },
                    "Generated Outputs": {
                        "respuesta_generada": self._sanitize_for_reflection(gen)
                    },
                    "Ideal Output (Ground Truth)": self._sanitize_for_reflection(gt),
                    "Feedback (del Juez)": self._sanitize_for_reflection(fb),
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
                        "contexto": self._sanitize_for_reflection(contexto_truncado)
                    },
                    "Generated Outputs": {
                        "respuesta_generada": self._sanitize_for_reflection(gen)
                    },
                    "Ideal Output (Ground Truth)": self._sanitize_for_reflection(gt),
                    "Feedback (del Juez)": f"EJEMPLO EXITOSO: {self._sanitize_for_reflection(fb)}",
                    "Type": "positive_example"
                }
                reflective_datasets["system_prompt"].append(reflective_record)

        # Log de estadísticas del dataset reflexivo
        num_negativos = len([r for r in reflective_datasets["system_prompt"] if r.get("Type") == "negative_example"])
        num_positivos = len([r for r in reflective_datasets["system_prompt"] if r.get("Type") == "positive_example"])
        if num_negativos > 0 or num_positivos > 0:
            print(f"[INFO] Dataset reflexivo: {num_negativos} negativos, {num_positivos} positivos")

        return reflective_datasets

"""Agregacion de metricas sobre casos evaluados y delta pareado (SPEC-104 FR-003).

Sin dependencia de ningun framework ni llamada al modelo. La entrada es la forma
de resultado por caso fijada en D6: por repeticion de la evaluacion, una lista de
`(case_id, score, evaluated)`. Un caso no evaluado (NE) trae un score tecnico
0.0 que MUST NOT entrar a ninguna metrica reportada.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

SIN_CASOS_EVALUADOS = "sin casos evaluados"

# Misma convencion que los orquestadores: un score ya expresado en porcentaje
# (> 1) se muestra tal cual; uno normalizado se multiplica por 100.
_NORMALIZED_SCORE_MAX = 1.0

CaseResult = tuple[Any, float, bool]


def _format_percent(value: float) -> str:
    return f"{value:.2f}%" if value > _NORMALIZED_SCORE_MAX else f"{value:.2%}"


@dataclass(frozen=True)
class MetricSummary:
    """Metrica de un conjunto de casos, calculada solo sobre los evaluados."""

    score: float | None
    n_evaluados: int
    n_total: int
    repeats: int
    ne_repeats: int
    per_case: dict[Any, float] = field(default_factory=dict)

    @property
    def sin_casos_evaluados(self) -> bool:
        return self.n_evaluados == 0

    def ratio_label(self) -> str:
        return f"{self.n_evaluados}/{self.n_total}"

    def format_score(self) -> str:
        if self.score is None:
            return SIN_CASOS_EVALUADOS
        return _format_percent(self.score)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "n_evaluados": self.n_evaluados,
            "n_total": self.n_total,
            "repeats": self.repeats,
            "ne_repeats": self.ne_repeats,
            "sin_casos_evaluados": self.sin_casos_evaluados,
        }


@dataclass(frozen=True)
class PairedDelta:
    """Delta optimizado - baseline sobre los casos evaluados con ambos prompts."""

    delta: float | None
    baseline_score: float | None
    optimized_score: float | None
    n_pareados: int

    @property
    def sin_casos_evaluados(self) -> bool:
        return self.n_pareados == 0

    def format_delta(self) -> str:
        if self.delta is None:
            return SIN_CASOS_EVALUADOS
        sign = "+" if self.delta >= 0 else "-"
        return f"{sign}{_format_percent(abs(self.delta))}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "delta": self.delta,
            "baseline_score": self.baseline_score,
            "optimized_score": self.optimized_score,
            "n_pareados": self.n_pareados,
            "sin_casos_evaluados": self.sin_casos_evaluados,
        }


def _validate_repeat(repeat: Iterable[CaseResult]) -> list[CaseResult]:
    entries: list[CaseResult] = []
    seen: set[Any] = set()
    for entry in repeat:
        if not isinstance(entry, (tuple, list)) or len(entry) != 3:
            raise ValueError(f"se esperaba (case_id, score, evaluated), llego {entry!r}")
        case_id, score, evaluated = entry
        if case_id is None:
            raise ValueError("falta case_id en un resultado por caso (FR-013)")
        if case_id in seen:
            raise ValueError(f"case_id duplicado en una repeticion: {case_id!r}")
        seen.add(case_id)
        entries.append((case_id, float(score), bool(evaluated)))
    return entries


def summarize(repeats: Sequence[Iterable[CaseResult]]) -> MetricSummary:
    """Agrega las repeticiones de una evaluacion sobre sus casos evaluados.

    El score de un caso es el promedio de sus repeticiones evaluadas; un caso
    cuenta como evaluado si lo fue en al menos una. `ne_repeats` cuenta los pares
    (caso, repeticion) no evaluados. Sin casos evaluados el score es None.
    """
    validated = [_validate_repeat(r) for r in repeats]
    all_ids: dict[Any, None] = {}
    sums: dict[Any, float] = {}
    counts: dict[Any, int] = {}
    ne_repeats = 0
    for entries in validated:
        for case_id, score, evaluated in entries:
            all_ids.setdefault(case_id)
            if evaluated:
                sums[case_id] = sums.get(case_id, 0.0) + score
                counts[case_id] = counts.get(case_id, 0) + 1
            else:
                ne_repeats += 1
    per_case = {cid: sums[cid] / counts[cid] for cid in all_ids if cid in counts}
    score = sum(per_case.values()) / len(per_case) if per_case else None
    return MetricSummary(
        score=score,
        n_evaluados=len(per_case),
        n_total=len(all_ids),
        repeats=len(validated),
        ne_repeats=ne_repeats,
        per_case=per_case,
    )


def paired_delta(baseline: MetricSummary, optimized: MetricSummary) -> PairedDelta:
    """Delta optimizado - baseline sobre la interseccion de casos evaluados."""
    shared = [cid for cid in baseline.per_case if cid in optimized.per_case]
    if not shared:
        return PairedDelta(delta=None, baseline_score=None, optimized_score=None, n_pareados=0)
    base_score = sum(baseline.per_case[c] for c in shared) / len(shared)
    opt_score = sum(optimized.per_case[c] for c in shared) / len(shared)
    return PairedDelta(
        delta=opt_score - base_score,
        baseline_score=base_score,
        optimized_score=opt_score,
        n_pareados=len(shared),
    )

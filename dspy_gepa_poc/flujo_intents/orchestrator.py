"""Orquestador del flujo-intents: encadena las 5 etapas en inferencia.

Lee SOLO la config maestra (`flujo_intents.yaml`), carga los programas optimizados de
cada etapa LLM y los corre en serie con gates: si una etapa no emite su valor "pasa",
el flujo corta e inyecta `skip_value` aguas abajo. Si llega al Fast Gate, aplica el
mapeo determinista de `aprobacion` (§9.1).

La logica de encadenamiento (`run_flow`) esta desacoplada del LLM via un `stage_runner`
inyectable: se testea sin llamadas reales. El CLI arma el `stage_runner` real con DSPy.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import yaml

from .aprobacion import resolve_aprobacion

# Firma del runner por etapa: (nombre_etapa, ficha) -> valor del output de esa etapa.
StageRunner = Callable[[str, str], str]


def run_flow(
    ficha: str,
    stages: Sequence[Mapping[str, object]],
    skip_value: str,
    aprobacion_mapping: Mapping[str, Mapping[str, str]],
    stage_runner: StageRunner,
) -> dict[str, object]:
    """Corre el flujo completo sobre una ficha. Devuelve outputs por etapa + aprobacion.

    Encadenamiento: cada etapa con `gate_value` no nulo corta el flujo si su salida no
    coincide con ese valor. La etapa terminal queda con su decision; las posteriores con
    `skip_value`. Si todas las gated pasan, se aplica `aprobacion` sobre el color del
    Fast Gate.
    """
    result: dict[str, object] = {}
    proceed = True
    terminal_stage: str | None = None

    for stage in stages:
        name = str(stage["name"])
        gate_value = stage.get("gate_value")
        if proceed:
            value = str(stage_runner(name, ficha)).strip()
            result[name] = value
            if gate_value is not None and value != str(gate_value):
                proceed = False
                terminal_stage = name
        else:
            result[name] = skip_value

    if proceed:
        color = str(result[stages[-1]["name"]])
        aprobacion = resolve_aprobacion(color, aprobacion_mapping)
    else:
        aprobacion = {
            "decision": "detenido",
            "nivel_requerido": "-",
            "dictamen": f"Flujo cortado en la etapa '{terminal_stage}' antes del Fast Gate.",
        }
    result["aprobacion"] = aprobacion
    return result


def load_master_config(path: str | Path) -> dict[str, object]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return raw["flujo"]


def build_stage_modules(flujo_cfg: Mapping[str, object], repo_root: Path) -> dict[str, object]:
    """Construye un dspy.Module por etapa LLM y carga su programa optimizado si aplica.

    Importa DSPy de forma perezosa para que `run_flow` siga siendo testeable sin LLM.
    """
    from dspy_gepa_poc import AppConfig, DynamicModuleFactory

    modules: dict[str, object] = {}
    for stage in flujo_cfg["stages"]:  # type: ignore[index]
        name = str(stage["name"])
        stage_cfg = AppConfig(yaml_path=str(repo_root / str(stage["stage_config"])))
        sig = stage_cfg.raw_config["signature"]
        predictor_type = stage_cfg.raw_config.get("optimization", {}).get("predictor_type", "cot")
        module = DynamicModuleFactory.create_module(sig, predictor_type=predictor_type)
        program = str(stage.get("program", "baseline"))
        if program and program != "baseline":
            module.load(str(repo_root / program))
        modules[name] = module
    return modules


def make_stage_runner(
    flujo_cfg: Mapping[str, object], modules: Mapping[str, object]
) -> StageRunner:
    """Runner real: corre el modulo DSPy de la etapa y extrae su campo de output."""
    out_field_by_stage = {str(s["name"]): str(s["output"]) for s in flujo_cfg["stages"]}  # type: ignore[index]

    def runner(name: str, ficha: str) -> str:
        prediction = modules[name](ficha=ficha)
        return str(getattr(prediction, out_field_by_stage[name], "")).strip()

    return runner


def _format_result(ficha: str, result: Mapping[str, object]) -> str:
    lines = ["=" * 60, "FICHA:", ficha, "-" * 60]
    for key, value in result.items():
        if key == "aprobacion":
            ap = value  # type: ignore[assignment]
            lines.append(
                f"aprobacion: {ap['decision']} | nivel: {ap['nivel_requerido']}"  # type: ignore[index]
            )
            lines.append(f"  dictamen: {ap['dictamen']}")  # type: ignore[index]
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Orquestador end-to-end de flujo-intents")
    parser.add_argument(
        "--config",
        default="dspy_gepa_poc/flujo_intents/flujo_intents.yaml",
        help="Config maestra",
    )
    parser.add_argument("--ficha-file", help="Archivo de texto con una ficha serializada")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    flujo_cfg = load_master_config(repo_root / args.config)

    if not args.ficha_file:
        parser.error("Indicar --ficha-file con una ficha serializada (ver serialize_ficha).")

    import dspy

    from dspy_gepa_poc import LLMConfig

    task_config = LLMConfig.from_env("task")
    task_config.validate()
    dspy.configure(lm=task_config.get_dspy_lm())

    modules = build_stage_modules(flujo_cfg, repo_root)
    runner = make_stage_runner(flujo_cfg, modules)

    ficha = Path(args.ficha_file).read_text(encoding="utf-8")
    result = run_flow(
        ficha=ficha,
        stages=flujo_cfg["stages"],  # type: ignore[arg-type]
        skip_value=str(flujo_cfg.get("skip_value", "(no evaluada)")),
        aprobacion_mapping=flujo_cfg["aprobacion"]["mapping"],  # type: ignore[index]
        stage_runner=runner,
    )
    print(_format_result(ficha, result))


if __name__ == "__main__":
    main()

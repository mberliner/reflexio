import argparse
from pathlib import Path

import dspy
import yaml
from dotenv import load_dotenv

from dspy_gepa_poc import DynamicModuleFactory, LLMConfig
from shared.display import print_header


def build_inference_module(raw_config: dict) -> dspy.Module:
    """Reconstruye el modulo de inferencia respetando `module.type` del config.

    Para `rule_derived` (Fast Gate, D-013) usa `create_rule_derived_module`: el LLM
    emite p1..p5 + alto_impacto y `derive_color` calcula `clasificacion`. El modulo
    generico (`create_module`) NO deriva el color -> en produccion `clasificacion`
    saldria vacia/N/A y se perderia el determinismo del Marco (D-015b).
    """
    sig_config = raw_config["signature"]
    module_type = raw_config.get("module", {}).get("type", "dynamic")
    predictor_type = raw_config.get("optimization", {}).get("predictor_type", "cot")

    if module_type == "rule_derived":
        return DynamicModuleFactory.create_rule_derived_module(
            sig_config, predictor_type=predictor_type
        )
    return DynamicModuleFactory.create_module(sig_config, predictor_type=predictor_type)


def run_production_inference(run_dir_path: str):
    # 1. Cargar Variables de Entorno (API Keys)
    project_dir = Path(__file__).parent
    env_path = project_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()

    run_dir = Path(run_dir_path)
    if not run_dir.exists():
        print(f"Error: No se encontró el directorio {run_dir}")
        return

    print("--- Iniciando Entorno de Producción ---")
    print(f"Cargando artefactos desde: {run_dir}")

    # 2. Cargar la Configuración Snapshot (La "memoria" de cómo se construyó)
    config_path = run_dir / "config_snapshot.yaml"
    if not config_path.exists():
        print(f"Error: No se encontró config_snapshot.yaml en {run_dir}")
        return

    with open(config_path, encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    # 3. Configurar SOLO el Modelo Estudiante (Barato/Rapido)
    # Nota: No configuramos reflection_model ni usamos GEPA
    print("Configurando Modelo Estudiante (Inferencia)...")
    task_config = LLMConfig.from_env("task")
    lm = task_config.get_dspy_lm()
    dspy.configure(lm=lm)
    print(f"Modelo cargado: {task_config.model}")

    # 4. Reconstruir la Arquitectura del Módulo
    # Respetamos module.type: 'rule_derived' deriva el color con la regla del Marco;
    # 'dynamic' usa el predictor directo (D-015b).
    module_type = raw_config.get("module", {}).get("type", "dynamic")
    print(f"Reconstruyendo arquitectura del módulo (type: {module_type})...")
    module = build_inference_module(raw_config)

    # 5. CARGAR la "Inteligencia Congelada" (El JSON Optimizado)
    # Aquí es donde el modelo barato se vuelve inteligente
    model_path = run_dir / "optimized_program.json"
    if model_path.exists():
        module.load(str(model_path))
        print("Programa optimizado cargado exitosamente.")
    else:
        print(
            "Advertencia: No se encontró optimized_program.json, usando modelo base sin optimizar."
        )

    # 6. Ejecutar Inferencia (Loop Interactivo)
    print_header("LISTO PARA ANALISIS (Escribe 'salir' para terminar)")

    # Detectar nombre del campo de entrada (generalmente 'text')
    input_fields = raw_config["signature"]["inputs"]
    input_name = input_fields[0]["name"]

    while True:
        try:
            user_input = input(f"\nIngresa {input_name}: ")
            if user_input.lower() in ["salir", "exit", "quit"]:
                break

            # Ejecutar el módulo
            pred = module(**{input_name: user_input})

            # Mostrar resultados
            print("\n--- Resultado ---")
            for field in raw_config["signature"]["outputs"]:
                field_name = field["name"]
                val = getattr(pred, field_name, "N/A")
                print(f"{field_name.capitalize()}: {val}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error en inferencia: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run inference using an optimized DSPy module")
    parser.add_argument(
        "run_dir", help="Path to the run directory containing optimized_program.json"
    )
    args = parser.parse_args()

    run_production_inference(args.run_dir)

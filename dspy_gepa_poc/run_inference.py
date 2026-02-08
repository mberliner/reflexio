import sys
import dspy
import argparse
import yaml
from dotenv import load_dotenv
from pathlib import Path

# Agregar raíz al path si se ejecuta directamente
if __name__ == "__main__" and __package__ is None:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from dspy_gepa_poc import LLMConfig, DynamicModuleFactory
from shared.display import print_header

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

    print(f"--- Iniciando Entorno de Producción ---")
    print(f"Cargando artefactos desde: {run_dir}")

    # 2. Cargar la Configuración Snapshot (La "memoria" de cómo se construyó)
    config_path = run_dir / "config_snapshot.yaml"
    if not config_path.exists():
        print(f"Error: No se encontró config_snapshot.yaml en {run_dir}")
        return

    with open(config_path, 'r') as f:
        raw_config = yaml.safe_load(f)

    # 3. Configurar SOLO el Modelo Estudiante (Barato/Rapido)
    # Nota: No configuramos reflection_model ni usamos GEPA
    print("Configurando Modelo Estudiante (Inferencia)...")
    task_config = LLMConfig.from_env("task")
    lm = task_config.get_dspy_lm()
    dspy.configure(lm=lm)
    print(f"Modelo cargado: {task_config.model}")

    # 4. Reconstruir la Arquitectura del Módulo
    # Usamos la misma 'Signature' definida en el YAML
    print("Reconstruyendo arquitectura del módulo...")
    predictor_type = raw_config.get('optimization', {}).get('predictor_type', 'cot')
    module = DynamicModuleFactory.create_module(raw_config['signature'], predictor_type=predictor_type)

    # 5. CARGAR la "Inteligencia Congelada" (El JSON Optimizado)
    # Aquí es donde el modelo barato se vuelve inteligente
    model_path = run_dir / "optimized_program.json"
    if model_path.exists():
        module.load(str(model_path))
        print("Programa optimizado cargado exitosamente.")
    else:
        print("Advertencia: No se encontró optimized_program.json, usando modelo base sin optimizar.")

    # 6. Ejecutar Inferencia (Loop Interactivo)
    print_header("LISTO PARA ANALISIS (Escribe 'salir' para terminar)")
    
    # Detectar nombre del campo de entrada (generalmente 'text')
    input_fields = raw_config['signature']['inputs']
    input_name = input_fields[0]['name']

    while True:
        try:
            user_input = input(f"\nIngresa {input_name}: ")
            if user_input.lower() in ['salir', 'exit', 'quit']:
                break
            
            # Ejecutar el módulo
            pred = module(**{input_name: user_input})
            
            # Mostrar resultados
            print("\n--- Resultado ---")
            for field in raw_config['signature']['outputs']:
                field_name = field['name']
                val = getattr(pred, field_name, "N/A")
                print(f"{field_name.capitalize()}: {val}")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error en inferencia: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run inference using an optimized DSPy module")
    parser.add_argument("run_dir", help="Path to the run directory containing optimized_program.json")
    args = parser.parse_args()
    
    run_production_inference(args.run_dir)

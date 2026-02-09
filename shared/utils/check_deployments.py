#!/usr/bin/env python3
"""
Script para verificar deployments activos en Azure OpenAI

Uso:
    python check_deployments.py
    python check_deployments.py --quick  # Solo verifica config actual
"""

import argparse
import os
import sys

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

try:
    import litellm
    from shared.llm import LLMConfig
except ImportError:
    print("Error: Could not import required modules. Make sure you are running from the project root.")
    sys.exit(1)


def test_deployment(config, deployment_name, verbose=False):
    """
    Prueba si un deployment funciona. Retorna True si funciona.
    Asume que el deployment es en Azure.
    """
    # Construir el nombre del modelo para LiteLLM (agregando prefijo azure/)
    model_id = f"azure/{deployment_name}"
    
    # Create a temp config just for this deployment check
    test_config = LLMConfig(
        model=model_id,
        api_key=config.api_key,
        api_base=config.api_base,
        api_version=config.api_version
    )
    
    kwargs = test_config.to_kwargs()
    # Remove model from kwargs as we pass it explicitly
    model = kwargs.pop('model')
    
    # Manejo especial de temperatura para modelos de razonamiento (o1, o3, gpt-5)
    # Estos modelos solo aceptan temperatura = 1.0
    is_reasoning = any(x in deployment_name for x in ["o1", "o3", "o4", "gpt-5"])
    
    if is_reasoning:
        kwargs['temperature'] = 1.0
    
    # Remove max_tokens if present
    if 'max_tokens' in kwargs:
        del kwargs['max_tokens']
    
    try:
        # Intentar primero con max_completion_tokens (estándar nuevo para o1/gpt-5)
        # y luego fallback a max_tokens si falla por parámetro no soportado
        try:
            litellm.completion(
                model=model,
                messages=[{"role": "user", "content": "Hi"}],
                max_completion_tokens=20, 
                **kwargs
            )
            return True
        except Exception as e:
            # Si el error es explícitamente sobre el parámetro, intentamos la forma antigua
            if "unsupported_parameter" in str(e) or "max_completion_tokens" in str(e):
                litellm.completion(
                    model=model,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=1, 
                    **kwargs
                )
                return True
            raise e # Si no es error de parámetro, relanzar

    except Exception as e:
        if verbose:
            print(f"   [Error en {deployment_name}]: {e}")
        return False


def get_all_deployments():
    """Retorna lista exhaustiva de posibles deployments (nombres simples sin prefijo)"""
    return [
        # === GPT-5.x (más recientes) ===
        "gpt-5.2",
        "gpt-5.2-2025-12-11",
        "gpt-5.2-chat-2025-12-11",
        "gpt-5.1",
        "gpt-5.1-2025-11-13",
        "gpt-5.1-chat-2025-11-13",
        "gpt-5.1-codex",
        "gpt-5.1-codex-2025-11-13",
        "gpt-5.1-codex-mini-2025-11-13",
        "gpt-5.1-codex-max-2025-12-04",
        "gpt-5",
        "gpt-5-2025-08-07",
        "gpt-5-chat-2025-08-15",
        "gpt-5-chat-2025-10-03",
        "gpt-5-pro-2025-10-06",
        "gpt-5-mini-2025-08-07",
        "gpt-5-nano-2025-08-07",
        # === GPT-4.5 ===
        "gpt-4.5",
        "gpt-4.5-preview",
        "gpt-4.5-preview-2025-02-27",
        # === GPT-4.1 ===
        "gpt-4.1",
        "gpt-4.1-2025-04-14",
        "gpt-4.1-mini",
        "gpt-4.1-mini-2025-04-14",
        "gpt-4.1-nano",
        "gpt-4.1-nano-2025-04-14",
        # === GPT-4o ===
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4o-2024-11-20",
        "gpt-4o-2024-08-06",
        "gpt-4o-2024-05-13",
        "gpt-4o-mini-2024-07-18",
        "gpt-4o-canvas-2024-09-25",
        # === GPT-4 clásico ===
        "gpt-4",
        "gpt-4-turbo",
        "gpt-4-turbo-2024-04-09",
        "gpt-4-0125-Preview",
        "gpt-4-1106-Preview",
        "gpt-4-0613",
        "gpt-4-32k",
        # === GPT-3.5 ===
        "gpt-35-turbo",
        "gpt-35-turbo-16k",
        "gpt-35-turbo-0125",
        "gpt-35-turbo-1106",
        "gpt-35-turbo-0613",
        # === O-series (razonamiento) ===
        "o3",
        "o3-2025-04-16",
        "o3-mini",
        "o3-mini-2025-01-31",
        "o3-mini-alpha",
        "o3-pro",
        "o1",
        "o1-2024-12-17",
        "o1-preview",
        "o1-preview-2024-09-12",
        "o1-mini",
        "o1-mini-2024-09-12",
    ]


def scan_deployments(base_config, verbose=False):
    """Escanea y retorna lista de deployments activos (nombres simples)."""
    all_deployments = get_all_deployments()
    available = []

    print(f"\nEscaneando {len(all_deployments)} posibles deployments...")

    for i, deployment in enumerate(all_deployments, 1):
        if verbose:
            print(f"[{i}/{len(all_deployments)}] {deployment:<40}", end=" ")
            sys.stdout.flush()

        if test_deployment(base_config, deployment, verbose=verbose):
            available.append(deployment)
            if verbose:
                print("✓")
        elif verbose:
            print("✗")

    return available


def print_deployments_list(deployments):
    """Imprime lista de deployments en formato limpio."""
    if not deployments:
        print("\n❌ No se encontraron deployments activos.\n")
        return

    print(f"\n{'=' * 70}")
    print(f"DEPLOYMENTS ACTIVOS ({len(deployments)} encontrados)")
    print(f"{'=' * 70}\n")

    # Agrupar por familia
    groups = {
        "GPT-5.x": [],
        "GPT-4.5": [],
        "GPT-4.1": [],
        "GPT-4o": [],
        "GPT-4": [],
        "GPT-3.5": [],
        "O-series": [],
        "Otros": [],
    }

    for dep in deployments:
        # dep ya es el nombre simple
        if dep.startswith("gpt-5"):
            groups["GPT-5.x"].append(dep)
        elif dep.startswith("gpt-4.5"):
            groups["GPT-4.5"].append(dep)
        elif dep.startswith("gpt-4.1"):
            groups["GPT-4.1"].append(dep)
        elif "gpt-4o" in dep:
            groups["GPT-4o"].append(dep)
        elif dep.startswith("gpt-4"):
            groups["GPT-4"].append(dep)
        elif dep.startswith("gpt-35") or dep.startswith("gpt-3"):
            groups["GPT-3.5"].append(dep)
        elif dep.startswith("o1") or dep.startswith("o3") or dep.startswith("o4"):
            groups["O-series"].append(dep)
        else:
            groups["Otros"].append(dep)

    # Imprimir grupos con deployments
    for group_name, deps in groups.items():
        if deps:
            print(f"{group_name}:")
            for dep in sorted(deps):
                print(f"  • {dep}")
            print()

    print(f"{'=' * 70}\n")


def check_config(available_deployments, base_config):
    """Verifica la configuración actual."""
    print(f"{'=' * 70}")
    print("CONFIGURACIÓN ACTUAL (dspy_gepa_poc)")
    print(f"{'=' * 70}\n")

    # Load configs from env
    task_conf = LLMConfig.from_env("task")
    ref_conf = LLMConfig.from_env("reflection")
    
    # Extract plain names (removing azure/ prefix if present)
    task_raw = task_conf.model
    ref_raw = ref_conf.model
    
    task_name = task_raw.replace("azure/", "") if task_raw.startswith("azure/") else task_raw
    ref_name = ref_raw.replace("azure/", "") if ref_raw.startswith("azure/") else ref_raw

    task_ok = task_name in available_deployments
    ref_ok = ref_name in available_deployments
    
    # Check individually if not found in scan list
    if not task_ok:
        print(f"Verificando Task Model '{task_name}' manualmente...")
        if test_deployment(base_config, task_name, verbose=True):
            task_ok = True
            available_deployments.append(task_name)
    
    if not ref_ok and ref_name != task_name:
        print(f"Verificando Reflection Model '{ref_name}' manualmente...")
        if test_deployment(base_config, ref_name, verbose=True):
            ref_ok = True
            available_deployments.append(ref_name)

    print(f"\nTask Model (estudiante):      {task_raw}")
    print(f"  → Deployment Name:        {task_name}")
    print(f"  → Estado:                 {'✓ Activo' if task_ok else '✗ NO ENCONTRADO'}\n")

    print(f"Reflection Model (Prof):  {ref_raw}")
    print(f"  → Deployment Name:        {ref_name}")
    print(f"  → Estado:                 {'✓ Activo' if ref_ok else '✗ NO ENCONTRADO'}\n")

    if not task_ok or not ref_ok:
        print(f"{'=' * 70}")
        print("RECOMENDACIONES")
        print(f"{'=' * 70}\n")

        # Sugerir replacements
        if not task_ok:
            suggestions = [
                d for d in available_deployments if "mini" in d or "3.5" in d or "4.1" in d
            ]
            if suggestions:
                print("Para Task Model, considera usar uno de estos deployments detectados:")
                for s in suggestions[:3]:
                    print(f"  • azure/{s}")
                print()

        if not ref_ok:
            suggestions = [
                d
                for d in available_deployments
                if any(x in d for x in ["gpt-5", "gpt-4o", "gpt-4.5", "o3", "o1"])
            ]
            if suggestions:
                print("Para Reflection Model, considera usar uno de estos deployments detectados:")
                for s in suggestions[:5]:
                    print(f"  • azure/{s}")
                print()

        print("Actualiza tu archivo .env con el prefijo azure/ + el nombre del deployment.\n")
    else:
        print("✓ Todos los deployments configurados están activos.\n")


def main():
    parser = argparse.ArgumentParser(description="Verifica deployments activos en Azure OpenAI")
    parser.add_argument(
        "--quick",
        "-q",
        action="store_true",
        help="Solo verifica la configuración actual sin escanear todos los deployments",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Muestra progreso detallado del escaneo y errores"
    )

    args = parser.parse_args()
    
    # Load base config to get credentials (using 'task' as default source)
    try:
        base_config = LLMConfig.from_env("task")
    except Exception as e:
        print(f"Error loading configuration: {e}")
        print("Check your .env file.")
        sys.exit(1)

    print(f"\n{'=' * 70}")
    print("VERIFICADOR DE DEPLOYMENTS AZURE OPENAI")
    print(f"{'=' * 70}")
    print(f"\nEndpoint: {base_config.api_base}\n")

    try:
        if args.quick:
            # Solo verificar config actual
            check_config([], base_config)
        else:
            # Escaneo completo
            available = scan_deployments(base_config, verbose=args.verbose)
            print_deployments_list(available)
            check_config(available, base_config)

    except KeyboardInterrupt:
        print("\n\n⚠️  Verificación cancelada.\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

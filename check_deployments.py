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

# Añadir el directorio padre al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gepa_standalone.config import Config
from gepa_standalone.core.llm_factory import get_azure_client


def test_deployment(client, deployment_name):
    """Prueba si un deployment funciona. Retorna True si funciona."""
    try:
        # Intentar con max_completion_tokens primero
        client.chat.completions.create(
            model=deployment_name,
            messages=[{"role": "user", "content": "Hi"}],
            max_completion_tokens=1,
        )
        return True
    except Exception as e:
        error_msg = str(e)
        # Si falla por parámetro, intentar con max_tokens
        if "max_completion_tokens" in error_msg or "unsupported" in error_msg.lower():
            try:
                client.chat.completions.create(
                    model=deployment_name,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=1,
                )
                return True
            except Exception:
                return False
        return False


def get_all_deployments():
    """Retorna lista exhaustiva de posibles deployments incluyendo GPT-5.x"""
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


def scan_deployments(client, verbose=False):
    """Escanea y retorna lista de deployments activos."""
    all_deployments = get_all_deployments()
    available = []

    print(f"\nEscaneando {len(all_deployments)} posibles deployments...")

    for i, deployment in enumerate(all_deployments, 1):
        if verbose:
            print(f"[{i}/{len(all_deployments)}] {deployment:<40}", end=" ")
            sys.stdout.flush()

        if test_deployment(client, deployment):
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


def check_config(available_deployments):
    """Verifica la configuración actual."""
    print(f"{'=' * 70}")
    print("CONFIGURACIÓN ACTUAL")
    print(f"{'=' * 70}\n")

    task = Config.TASK_DEPLOYMENT
    reflection = Config.REFLECTION_DEPLOYMENT

    task_ok = task in available_deployments
    reflection_ok = reflection in available_deployments

    print(f"Task Model (estudiante):      {task}")
    print(f"  Estado: {'✓ Activo' if task_ok else '✗ NO ENCONTRADO'}\n")

    print(f"Reflection Model (Prof):  {reflection}")
    print(f"  Estado: {'✓ Activo' if reflection_ok else '✗ NO ENCONTRADO'}\n")

    if not task_ok or not reflection_ok:
        print(f"{'=' * 70}")
        print("RECOMENDACIONES")
        print(f"{'=' * 70}\n")

        # Sugerir replacements
        if not task_ok:
            suggestions = [
                d for d in available_deployments if "mini" in d or "3.5" in d or "4.1" in d
            ]
            if suggestions:
                print("Para Task Model, considera usar:")
                for s in suggestions[:3]:
                    print(f"  • {s}")
                print()

        if not reflection_ok:
            suggestions = [
                d
                for d in available_deployments
                if any(x in d for x in ["gpt-5", "gpt-4o", "gpt-4.5", "o3", "o1"])
            ]
            if suggestions:
                print("Para Reflection Model, considera usar:")
                for s in suggestions[:5]:
                    print(f"  • {s}")
                print()

        print("Actualiza tu archivo .env con:\n")
        if not task_ok and suggestions:
            print(f"AZURE_OPENAI_DEPLOYMENT={suggestions[0]}")
        if not reflection_ok and suggestions:
            ref_suggestions = [
                d
                for d in available_deployments
                if any(x in d for x in ["gpt-5", "gpt-4o", "gpt-4.5", "o3", "o1"])
            ]
            if ref_suggestions:
                print(f"AZURE_OPENAI_REFLECTION_DEPLOYMENT={ref_suggestions[0]}")
        print()
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
        "--verbose", "-v", action="store_true", help="Muestra progreso detallado del escaneo"
    )

    args = parser.parse_args()

    print(f"\n{'=' * 70}")
    print("VERIFICADOR DE DEPLOYMENTS AZURE OPENAI")
    print(f"{'=' * 70}")
    print(f"\nEndpoint: {Config.AZURE_ENDPOINT}\n")

    try:
        client = get_azure_client()

        if args.quick:
            # Solo verificar config actual
            deployments = [Config.TASK_DEPLOYMENT, Config.REFLECTION_DEPLOYMENT]
            available = [d for d in deployments if test_deployment(client, d)]
            check_config(available)
        else:
            # Escaneo completo
            available = scan_deployments(client, verbose=args.verbose)
            print_deployments_list(available)
            check_config(available)

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

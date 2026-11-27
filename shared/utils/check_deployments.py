#!/usr/bin/env python3
"""
Script para verificar deployments activos en Azure OpenAI

Uso (desde la raiz del repo):
    python -m shared.utils.check_deployments
    python -m shared.utils.check_deployments --quick  # Solo verifica config actual
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import litellm

    from shared.llm import LLMConfig, provider_of
except ImportError:
    print(
        "Error: Could not import required modules. Make sure you are running from the project root."
    )
    sys.exit(1)


def test_deployment(config, deployment_name, verbose=False):
    """
    Prueba si un deployment funciona. Retorna True si funciona.
    Asume que el deployment es en Azure.
    """
    if not config.api_base or not config.api_key:
        if verbose:
            print(f"   [Error en {deployment_name}]: Falta api_base o api_key")
        return False

    # Construir el nombre del modelo para LiteLLM (agregando prefijo azure/)
    model_id = f"azure/{deployment_name}"

    # Create a temp config just for this deployment check
    test_config = LLMConfig(
        model=model_id,
        api_key=config.api_key,
        api_base=config.api_base,
        api_version=config.api_version,
    )

    kwargs = test_config.to_kwargs()
    # Remove model from kwargs as we pass it explicitly
    model = kwargs.pop("model")

    # Manejo especial de temperatura para modelos de razonamiento (o1, o3, gpt-5)
    # Estos modelos solo aceptan temperatura = 1.0
    is_reasoning = any(x in deployment_name for x in ["o1", "o3", "o4", "gpt-5"])

    if is_reasoning:
        kwargs["temperature"] = 1.0

    # Remove max_tokens if present
    if "max_tokens" in kwargs:
        del kwargs["max_tokens"]

    try:
        # Intentar primero con max_completion_tokens (estándar nuevo para o1/gpt-5)
        # y luego fallback a max_tokens si falla por parámetro no soportado
        try:
            litellm.completion(
                model=model,
                messages=[{"role": "user", "content": "Hi"}],
                max_completion_tokens=20,
                **kwargs,
            )
            return True
        except Exception as e:
            # Si el error es explícitamente sobre el parámetro, intentamos la forma antigua
            if "unsupported_parameter" in str(e) or "max_completion_tokens" in str(e):
                litellm.completion(
                    model=model,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=1,
                    **kwargs,
                )
                return True
            raise e  # Si no es error de parámetro, relanzar

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
                print("[OK]")
        elif verbose:
            print("[X]")

    return available


def print_deployments_list(deployments):
    """Imprime lista de deployments en formato limpio."""
    if not deployments:
        print("\n[X] No se encontraron deployments activos.\n")
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
                print(f"  - {dep}")
            print()

    print(f"{'=' * 70}\n")


def _has_any_credential() -> bool:
    """True si hay `LLM_API_KEY` o alguna `LLM_API_KEY_<ROL>` no vacia (D2)."""
    return any(
        name.startswith("LLM_API_KEY") and value.strip() for name, value in os.environ.items()
    )


_ROLE_LABELS = {
    "task": "Task Model (estudiante)",
    "reflection": "Reflection Model (Prof)",
    "judge": "Judge Model (juez)",
}


def role_configs() -> list[LLMConfig]:
    """
    Configuracion resuelta de cada rol a verificar (SPEC-106 FR-008, D2): `task`,
    `reflection` y `judge` solo si `LLM_MODEL_JUDGE` esta definido. Cada rol usa su
    propia conexion (variables por rol y proveedor ancla).

    `LLM_MODEL_JUDGE` se lee despues de resolver `task` y `reflection`: `from_env`
    carga `LLM_ENV_FILE`, y el juez puede estar definido solo en ese `.env`.
    """
    confs = [LLMConfig.from_env(role) for role in ("task", "reflection")]
    if (os.getenv("LLM_MODEL_JUDGE") or "").strip():
        confs.append(LLMConfig.from_env("judge"))
    return confs


def _deployment_name(config: LLMConfig) -> str:
    model = config.model
    return model[len("azure/") :] if model.startswith("azure/") else model


def _endpoint_key(config: LLMConfig) -> tuple:
    """Identifica el endpoint de un rol (los deployments escaneados valen por endpoint)."""
    return (config.api_base, config.api_key, config.api_version)


def check_config(available_by_endpoint, role_confs=None):
    """
    Verifica la configuracion actual, cada rol contra su propio endpoint y credencial
    (SPEC-106 FR-008). Un rol que no es Azure se informa "no aplica", no como error.

    `available_by_endpoint` mapea la clave de endpoint (`_endpoint_key`) a los
    deployments activos ya escaneados en ese endpoint; se completa con las
    verificaciones manuales.
    """
    print(f"{'=' * 70}")
    print("CONFIGURACIÓN ACTUAL (por rol)")
    print(f"{'=' * 70}\n")

    if role_confs is None:
        role_confs = role_configs()

    failed = []
    for conf in role_confs:
        label = _ROLE_LABELS.get(conf.role, conf.role)
        print(f"{label}:  {conf.model or '(sin modelo)'}")
        print(f"  -> Conexion:               {conf.connection_summary()}")

        if not conf.model or provider_of(conf.model) != "azure":
            print("  -> Estado:                 no aplica (no es un deployment Azure)\n")
            continue

        name = _deployment_name(conf)
        available = available_by_endpoint.setdefault(_endpoint_key(conf), [])
        ok = name in available
        if not ok:
            print(f"  Verificando '{name}' manualmente...")
            if test_deployment(conf, name, verbose=True):
                ok = True
                available.append(name)
        print(f"  -> Deployment Name:        {name}")
        print(f"  -> Estado:                 {'[OK] Activo' if ok else '[X] NO ENCONTRADO'}\n")
        if not ok:
            failed.append((conf, available))

    if failed:
        print(f"{'=' * 70}")
        print("RECOMENDACIONES")
        print(f"{'=' * 70}\n")

        for conf, available in failed:
            if conf.role == "task":
                suggestions = [d for d in available if "mini" in d or "3.5" in d or "4.1" in d]
                limit = 3
            else:
                suggestions = [
                    d
                    for d in available
                    if any(x in d for x in ["gpt-5", "gpt-4o", "gpt-4.5", "o3", "o1"])
                ]
                limit = 5
            if suggestions:
                print(
                    f"Para {_ROLE_LABELS.get(conf.role, conf.role)}, considera usar uno de "
                    "estos deployments detectados:"
                )
                for s in suggestions[:limit]:
                    print(f"  - azure/{s}")
                print()

        print("Actualiza tu archivo .env con el prefijo azure/ + el nombre del deployment.\n")
    else:
        print("[OK] Todos los deployments configurados estan activos o no aplican.\n")


def main():
    parser = argparse.ArgumentParser(description="Verifica deployments activos en Azure OpenAI")
    parser.add_argument(
        "--quick",
        "-q",
        action="store_true",
        help="Solo verifica la configuración actual sin escanear todos los deployments",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Muestra progreso detallado del escaneo y errores",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Ruta a un .env especifico (default: el de dspy_gepa_poc, que es la "
        "config que esta herramienta verifica).",
    )

    args = parser.parse_args()

    # Resolver que .env usar. shared/llm ya no adivina el subproyecto (se quito el
    # fallback hardcodeado); esta herramienta declara su default (dspy_gepa_poc) y lo
    # expone via LLM_ENV_FILE, respetando lo que ya este en el entorno.
    # Precedencia: entorno actual > --env-file > LLM_ENV_FILE > .env de dspy_gepa_poc.
    # La carga se dispara sin ninguna credencial (global ni por rol), SPEC-106 FR-005.
    if not _has_any_credential():
        env_file = args.env_file or os.getenv("LLM_ENV_FILE")
        if not env_file:
            default_env = Path(__file__).resolve().parents[2] / "dspy_gepa_poc" / ".env"
            env_file = str(default_env) if default_env.exists() else None
        if env_file:
            os.environ["LLM_ENV_FILE"] = env_file

    # Configuracion de cada rol, cada uno con su propia conexion (FR-008)
    try:
        confs = role_configs()
    except Exception as e:
        print(f"Error loading configuration: {e}")
        print("Check your .env file.")
        sys.exit(1)

    print(f"\n{'=' * 70}")
    print("VERIFICADOR DE DEPLOYMENTS AZURE OPENAI")
    print(f"{'=' * 70}\n")
    for conf in confs:
        print(f"  {conf.connection_summary()}")
    print()

    try:
        available_by_endpoint: dict = {}
        if not args.quick:
            # Escaneo completo: una vez por endpoint Azure distinto
            for conf in confs:
                if not conf.model or provider_of(conf.model) != "azure":
                    continue
                key = _endpoint_key(conf)
                if key in available_by_endpoint:
                    continue
                print(f"\nEndpoint ({conf.role}): {conf.endpoint_host}")
                available = scan_deployments(conf, verbose=args.verbose)
                print_deployments_list(available)
                available_by_endpoint[key] = available
        check_config(available_by_endpoint, confs)

    except KeyboardInterrupt:
        print("\n\n[WARN] Verificacion cancelada.\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}\n")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

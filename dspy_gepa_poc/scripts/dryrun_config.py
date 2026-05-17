"""Dry-run para validar un YAML de DSPy: config + dataset + signature + metric, sin LLM.

Uso (desde la raiz del repo):
    python -m dspy_gepa_poc.scripts.dryrun_config --config <ruta_yaml>

Ejemplo:
    python -m dspy_gepa_poc.scripts.dryrun_config \\
        --config dspy_gepa_poc/configs/dynamic_cv_profile.yaml
"""

import argparse
import sys
from pathlib import Path

from dspy_gepa_poc import AppConfig, CSVDataLoader
from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory
from dspy_gepa_poc.metrics import create_dynamic_metric


def dryrun(config_path: Path) -> int:
    print("=" * 70)
    print(f"DRY-RUN: {config_path.name}")
    print("=" * 70)

    # 1. Load config
    print("\n[1] Cargando config YAML...")
    cfg = AppConfig(yaml_path=str(config_path))
    case_name = cfg.raw_config["case"]["name"]
    csv_name = cfg.raw_config["data"]["csv_filename"]
    print(f"    Case: {case_name}")
    print(f"    CSV: {csv_name}")

    # 2. Load dataset
    print("\n[2] Cargando dataset...")
    loader = CSVDataLoader()
    data_cfg = cfg.raw_config["data"]
    if "input_columns" in data_cfg:
        input_keys = data_cfg["input_columns"]
        if not isinstance(input_keys, list):
            input_keys = [input_keys]
    else:
        input_keys = [data_cfg["input_column"]]
    train, val, test = loader.load_dataset(filename=csv_name, input_keys=input_keys)
    print(f"    Train: {len(train)} | Val: {len(val)} | Test: {len(test)}")

    if not train:
        print("    [ERROR] Train set vacio.")
        return 1

    # 3. Inspect first example
    print("\n[3] Inspeccionando primer ejemplo de train...")
    ex0 = train[0]
    for k, v in ex0.toDict().items():
        sample = str(v)[:60] + ("..." if len(str(v)) > 60 else "")
        print(f"    {k:25s} = {sample!r}")

    # 4. Build signature + module
    print("\n[4] Construyendo signature DSPy dinamica...")
    sig_cfg = cfg.raw_config.get("signature")
    if not sig_cfg:
        print("    [WARN] No hay seccion 'signature' (modulo no-dynamic). Salteando.")
        output_fields = []
    else:
        output_fields = [out["name"] for out in sig_cfg["outputs"]]
        print(f"    Inputs:  {[i['name'] for i in sig_cfg['inputs']]}")
        print(f"    Outputs ({len(output_fields)}): {output_fields}")
        predictor_type = cfg.raw_config.get("optimization", {}).get("predictor_type", "cot")
        module = DynamicModuleFactory.create_module(sig_cfg, predictor_type=predictor_type)
        print(f"    Module: {type(module).__name__} (predictor={predictor_type})")

    # 5. Build metric
    if output_fields:
        print("\n[5] Construyendo metrica dinamica...")
        opt_cfg = cfg.raw_config.get("optimization", {})
        ignored = opt_cfg.get("ignore_in_metric", [])
        eval_fields = [f for f in output_fields if f not in ignored]
        match_mode = opt_cfg.get("match_mode", "exact")
        metric = create_dynamic_metric(eval_fields, match_mode=match_mode)
        print(f"    Eval fields ({len(eval_fields)}): {eval_fields}")
        print(f"    Match mode: {match_mode}")
        print(f"    Ignored: {ignored or 'ninguno'}")

        # 6. Sanity check: perfect prediction debe dar True/1.0
        print("\n[6] Sanity check (prediccion = ground truth)...")

        class FakePred:
            pass

        fake = FakePred()
        for f in output_fields:
            setattr(fake, f, getattr(ex0, f, ""))
        score = metric(ex0, fake)
        print(f"    Score: {score}")
        if score is not True and score < 1.0:
            print(f"    [WARN] Match perfecto NO da 1.0 (score={score}). Revisar metrica.")

    # 7. Cobertura de campos en el dataset completo
    if output_fields:
        print("\n[7] Cobertura de campos (no-vacios sobre total):")
        all_examples = train + val + test
        for f in output_fields:
            non_empty = sum(1 for e in all_examples if str(getattr(e, f, "")).strip())
            pct = 100 * non_empty / len(all_examples) if all_examples else 0
            print(f"    {f:25s}: {non_empty}/{len(all_examples)} ({pct:.0f}%)")

    print("\n" + "=" * 70)
    print("DRY-RUN OK - configuracion valida, lista para correr con LLM")
    print("=" * 70)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Dry-run de validacion para YAML de DSPy.")
    parser.add_argument("--config", required=True, help="Ruta al YAML de configuracion")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"Error: config no existe: {config_path}", file=sys.stderr)
        sys.exit(1)

    sys.exit(dryrun(config_path))


if __name__ == "__main__":
    main()

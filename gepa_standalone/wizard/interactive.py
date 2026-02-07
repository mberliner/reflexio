"""
Interactive Wizard for GEPA Universal Optimizer

Guides users through creating YAML configuration files via interactive questions.
"""

import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

import yaml

from gepa_standalone.utils.paths import get_paths


class InteractiveWizard:
    """Interactive wizard for generating GEPA config YAML."""

    def run(self) -> Dict[str, Any]:
        """
        Execute wizard and return config dict.

        Returns:
            Complete config dictionary
        """
        self._print_banner()

        config = {}

        # 1. Case metadata
        config["case"] = self._ask_case_metadata()

        # 2. Adapter type
        adapter_type = self._ask_adapter_type()
        config["adapter"] = self._ask_adapter_config(adapter_type)

        # 3. Data
        config["data"] = self._ask_data_config(adapter_type)

        # 4. Prompt
        config["prompt"] = self._ask_prompt_config()

        # 5. Optimization params
        config["optimization"] = self._ask_optimization_params()

        # 6. Summary and confirmation
        self._display_config_summary(config)

        if self._confirm_save():
            self._save_config_yaml(config)

        return config

    def _print_banner(self):
        """Print welcome banner."""
        print("\n" + "=" * 70)
        print("        GEPA Universal Optimizer - Configuracion Interactiva")
        print("=" * 70)
        print("\nEste wizard te guiara para crear una configuracion YAML que podras")
        print("reutilizar en futuras ejecuciones.\n")

    def _ask_case_metadata(self) -> Dict[str, str]:
        """Ask for case name and title."""
        print("-" * 70)
        print("1. METADATA DEL CASO")
        print("-" * 70 + "\n")

        while True:
            name = input(">> Nombre del caso (snake_case, sin espacios): ").strip()

            # Validate: only alphanumeric and underscores
            if not re.match(r'^[a-z0-9_]+$', name):
                print("   [ERROR] Solo letras minusculas, numeros y guiones bajos (_)")
                continue

            break

        title = input(">> Titulo descriptivo: ").strip()

        description = input(">> Descripcion (opcional, Enter para omitir): ").strip()

        metadata = {"name": name, "title": title}
        if description:
            metadata["description"] = description

        return metadata

    def _ask_adapter_type(self) -> str:
        """Ask for adapter type."""
        print("\n" + "-" * 70)
        print("2. TIPO DE ADAPTADOR")
        print("-" * 70 + "\n")

        print("Selecciona el tipo de adaptador para tu tarea:")
        print("  1) classifier - Clasificacion simple (ej: urgencia, sentiment)")
        print("  2) extractor  - Extraccion estructurada JSON (ej: campos de CV)")
        print("  3) sql        - Generacion de consultas SQL\n")

        while True:
            choice = input(">> Opcion (1-3): ").strip()

            if choice == "1":
                return "classifier"
            elif choice == "2":
                return "extractor"
            elif choice == "3":
                return "sql"
            else:
                print("   [ERROR] Opcion invalida. Ingresa 1, 2 o 3.")

    def _ask_adapter_config(self, adapter_type: str) -> Dict[str, Any]:
        """Ask for adapter-specific parameters."""
        print("\n" + "-" * 70)
        print(f"3. PARAMETROS DEL ADAPTADOR ({adapter_type.upper()})")
        print("-" * 70 + "\n")

        adapter_config = {"type": adapter_type}

        if adapter_type == "classifier":
            print(">> Clases validas (separadas por coma): ", end="")
            classes_str = input().strip()
            valid_classes = [c.strip() for c in classes_str.split(",") if c.strip()]

            if not valid_classes:
                print("   [ERROR] Debes especificar al menos una clase")
                return self._ask_adapter_config(adapter_type)

            adapter_config["valid_classes"] = valid_classes

        elif adapter_type == "extractor":
            print(">> Campos requeridos (separados por coma): ", end="")
            fields_str = input().strip()
            required_fields = [f.strip() for f in fields_str.split(",") if f.strip()]

            if not required_fields:
                print("   [ERROR] Debes especificar al menos un campo")
                return self._ask_adapter_config(adapter_type)

            adapter_config["required_fields"] = required_fields

            print(">> Ejemplos positivos en reflexion (0-3, default: 0): ", end="")
            max_pos_str = input().strip()
            if max_pos_str:
                try:
                    max_pos = int(max_pos_str)
                    adapter_config["max_positive_examples"] = max_pos
                except ValueError:
                    print("   [WARNING] Valor invalido, usando default: 0")
                    adapter_config["max_positive_examples"] = 0
            else:
                adapter_config["max_positive_examples"] = 0

        # SQL has no additional params

        return adapter_config

    def _ask_data_config(self, adapter_type: str) -> Dict[str, Any]:
        """Ask for CSV filename and columns."""
        print("\n" + "-" * 70)
        print("4. DATOS")
        print("-" * 70 + "\n")

        # List available CSVs
        datasets_dir = get_paths().datasets
        csv_files = list(datasets_dir.glob("*.csv"))

        if csv_files:
            print("Archivos CSV disponibles en experiments/datasets/:")
            for csv_file in csv_files:
                print(f"  - {csv_file.name}")
        else:
            print("No se encontraron CSVs en experiments/datasets/")

        print()

        while True:
            csv_filename = input(">> Archivo CSV: ").strip()
            csv_path = get_paths().dataset(csv_filename)

            if not csv_path.exists():
                print(f"   [ERROR] Archivo no encontrado: {csv_filename}")
                print(f"   Coloca tu CSV en: {datasets_dir}")
                continue

            # Preview CSV structure
            print("\nLeyendo estructura del CSV...")
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames

            print(f"Columnas encontradas: {', '.join(headers)}\n")

            # Ask for input column
            input_col = input(">> Columna de entrada (default: text): ").strip()
            if not input_col:
                input_col = "text"

            if input_col not in headers:
                print(f"   [ERROR] Columna '{input_col}' no existe en el CSV")
                continue

            # Ask for output columns
            print(">> Columnas de salida (separadas por coma): ", end="")
            output_cols_str = input().strip()
            output_columns = [c.strip() for c in output_cols_str.split(",") if c.strip()]

            # Validate output columns
            invalid_cols = [c for c in output_columns if c not in headers]
            if invalid_cols:
                print(f"   [ERROR] Columnas no encontradas: {', '.join(invalid_cols)}")
                continue

            # Preview data
            print("\nValidando estructura... OK")
            self._preview_data(csv_path)

            break

        return {
            "csv_filename": csv_filename,
            "input_column": input_col,
            "output_columns": output_columns
        }

    def _preview_data(self, csv_path: Path):
        """Preview dataset split counts."""
        counts = {"train": 0, "val": 0, "test": 0}

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                split = row.get("split", "").lower()
                if split in counts:
                    counts[split] += 1

        print("\nVista previa de datos:")
        print(f"  Train: {counts['train']} ejemplos")
        print(f"  Val:   {counts['val']} ejemplos")
        print(f"  Test:  {counts['test']} ejemplos")

    def _ask_prompt_config(self) -> Dict[str, str]:
        """Ask for prompt JSON filename."""
        print("\n" + "-" * 70)
        print("5. PROMPT INICIAL")
        print("-" * 70 + "\n")

        # List available prompts
        prompts_dir = get_paths().prompts
        json_files = list(prompts_dir.glob("*.json"))

        if json_files:
            print("Archivos JSON disponibles en experiments/prompts/:")
            for json_file in json_files:
                print(f"  - {json_file.name}")
        else:
            print("No se encontraron prompts en experiments/prompts/")

        print()

        while True:
            prompt_filename = input(">> Archivo de prompt: ").strip()
            prompt_path = get_paths().prompt(prompt_filename)

            if not prompt_path.exists():
                print(f"   [ERROR] Archivo no encontrado: {prompt_filename}")
                print(f"   Coloca tu JSON en: {prompts_dir}")
                continue

            # Validate JSON and preview
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt_data = json.load(f)

                if "system_prompt" in prompt_data:
                    print(f"\nPrompt cargado:")
                    preview = prompt_data["system_prompt"][:150]
                    if len(prompt_data["system_prompt"]) > 150:
                        preview += "..."
                    print(f'  "{preview}"\n')
                else:
                    print("   [WARNING] JSON no tiene campo 'system_prompt'")

            except json.JSONDecodeError as e:
                print(f"   [ERROR] JSON invalido: {e}")
                continue

            break

        return {"filename": prompt_filename}

    def _ask_optimization_params(self) -> Dict[str, Any]:
        """Ask for GEPA optimization parameters."""
        print("\n" + "-" * 70)
        print("6. PARAMETROS DE OPTIMIZACION")
        print("-" * 70 + "\n")

        # max_metric_calls
        while True:
            max_calls_str = input(">> Maximo de llamadas a metrica (40-150, recomendado 50): ").strip()

            try:
                max_calls = int(max_calls_str)
                if max_calls < 10 or max_calls > 500:
                    print("   [ERROR] Valor debe estar entre 10 y 500")
                    continue
                break
            except ValueError:
                print("   [ERROR] Ingresa un numero entero")

        # skip_perfect_score
        skip_str = input(">> Detener si se alcanza score perfecto? (s/n, default: s): ").strip().lower()
        skip_perfect = skip_str != "n"

        # display_progress_bar
        progress_str = input(">> Mostrar barra de progreso? (s/n, default: s): ").strip().lower()
        display_progress = progress_str != "n"

        return {
            "max_metric_calls": max_calls,
            "skip_perfect_score": skip_perfect,
            "display_progress_bar": display_progress
        }

    def _display_config_summary(self, config: Dict[str, Any]):
        """Display config summary for review."""
        print("\n" + "=" * 70)
        print("RESUMEN DE CONFIGURACION")
        print("=" * 70 + "\n")

        print(f"Caso: {config['case']['name']} ({config['case'].get('title', 'N/A')})")
        print(f"Adaptador: {config['adapter']['type']}")

        if config['adapter']['type'] == "classifier":
            print(f"  - Clases: {', '.join(config['adapter']['valid_classes'])}")
        elif config['adapter']['type'] == "extractor":
            print(f"  - Campos: {', '.join(config['adapter']['required_fields'])}")
            print(f"  - Ejemplos positivos: {config['adapter'].get('max_positive_examples', 0)}")

        print(f"Datos: {config['data']['csv_filename']}")
        print(f"  - Entrada: {config['data']['input_column']}")
        print(f"  - Salida: {', '.join(config['data']['output_columns'])}")

        print(f"Prompt: {config['prompt']['filename']}")

        print(f"Optimizacion:")
        print(f"  - Max calls: {config['optimization']['max_metric_calls']}")
        print(f"  - Skip perfect: {config['optimization']['skip_perfect_score']}")
        print(f"  - Progress bar: {config['optimization']['display_progress_bar']}")

        print("\n" + "=" * 70 + "\n")

    def _confirm_save(self) -> bool:
        """Ask user to confirm saving config."""
        save_str = input(">> Guardar esta configuracion? (s/n): ").strip().lower()
        return save_str == "s"

    def _save_config_yaml(self, config: Dict[str, Any]):
        """Save config to YAML file."""
        configs_dir = get_paths().experiments / "configs"
        configs_dir.mkdir(parents=True, exist_ok=True)

        output_path = configs_dir / f"{config['case']['name']}.yaml"

        # Add header comment
        yaml_content = f"""# GEPA Universal Optimizer Configuration
# Generado: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
# Caso: {config['case']['name']}

"""
        yaml_content += yaml.dump(config, sort_keys=False, allow_unicode=True, default_flow_style=False)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        print(f"\nConfig guardado en: {output_path}")
        print("\nPara ejecutar esta optimizacion en el futuro, usa:")
        print(f"  python universal_optimizer.py --config {output_path.relative_to(get_paths().root)}")

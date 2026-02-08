"""
Universal GEPA Optimizer

Interfaz universal para optimizar prompts con GEPA en cualquier caso de uso.
Soporta configuración mediante archivo YAML o wizard interactivo.

Usage:
    # Con config YAML existente
    python universal_optimizer.py --config experiments/configs/mi_caso.yaml

    # Sin config (activa wizard interactivo)
    python universal_optimizer.py
"""

import sys
import os
import json
import argparse
import traceback
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# Ensure parent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import yaml
from gepa import optimize

from gepa_standalone.config_schema import ConfigValidator
from gepa_standalone.wizard.interactive import InteractiveWizard
from gepa_standalone.adapters.simple_classifier_adapter import SimpleClassifierAdapter
from gepa_standalone.adapters.simple_extractor_adapter import SimpleExtractorAdapter
from gepa_standalone.adapters.simple_sql_adapter import SimpleSQLAdapter
from gepa_standalone.adapters.simple_rag_adapter import SimpleRAGAdapter
from gepa_standalone.data.data_loader import load_gepa_data
from gepa_standalone.core.llm_factory import create_reflection_lm_function, get_reflection_config, get_task_config
from shared.display import print_header, print_section, print_summary, print_detailed_results
from gepa_standalone.utils.results_logger import save_run_details, log_experiment_result
from shared.paths import get_paths
from gepa_standalone.config import Config


class UniversalOptimizer:
    """Orquestador universal de optimización GEPA."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize optimizer.

        Args:
            config_path: Path to YAML config. If None or doesn't exist, activates wizard.
        """
        self.config_path = config_path
        self.config = None
        self.adapter = None
        self.train_data = None
        self.val_data = None
        self.test_data = None
        self.results = None

    def run(self, verbose: bool = False):
        """Execute complete optimization workflow."""
        # 1. Load or generate config
        config_path = None
        if self.config_path:
            p = Path(self.config_path)
            if p.exists():
                config_path = p
            else:
                # Try relative to script directory
                script_dir = Path(__file__).parent
                fallback_path = script_dir / self.config_path
                if fallback_path.exists():
                    config_path = fallback_path
                
        if config_path:
            self.config_path = str(config_path)
            print(f"\n[INFO] Loading config from: {self.config_path}")
            self.config = self.load_config()
        else:
            if self.config_path:
                print(f"\n[WARNING] Config file not found: {self.config_path}")
            print("\n[INFO] Activating interactive wizard...\n")
            self.config = self.run_wizard()

        # Apply YAML overrides to global Config
        Config.apply_yaml_config(self.config)

        # 2. Validate config
        self.validate_config()

        # 3. Load data
        self.load_data()

        # 4. Initialize adapter
        self.initialize_adapter()

        # 5. Load initial prompt
        initial_prompt = self.load_prompt()

        # 6. Execute GEPA pipeline
        self.execute_gepa_pipeline(initial_prompt, verbose=verbose)

        # 7. Save results
        run_dir = self.save_results()

        # Save a snapshot of the YAML config used
        if self.config:
            import shutil
            snapshot_path = run_dir / "config_snapshot.yaml"
            if self.config_path and Path(self.config_path).exists():
                shutil.copy2(self.config_path, snapshot_path)
            else:
                # If from wizard, write the dict to yaml
                with open(snapshot_path, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            print(f">> [LOG] Config snapshot saved: {snapshot_path}")

        print("\n[SUCCESS] Optimization completed!")

    def load_config(self) -> Dict[str, Any]:
        """
        Load and parse YAML config file.

        Returns:
            Config dictionary

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If config is malformed
        """
        config_path = Path(self.config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            print(f"[INFO] Config loaded successfully: {config['case']['name']}")
            return config

        except yaml.YAMLError as e:
            print(f"\n[ERROR] Invalid YAML format in config file:")
            print(f"  {e}")
            raise

    def run_wizard(self) -> Dict[str, Any]:
        """
        Run interactive wizard to generate config.

        Returns:
            Config dictionary generated by wizard
        """
        wizard = InteractiveWizard()
        config = wizard.run()
        return config

    def validate_config(self):
        """
        Validate config structure and parameters.

        Raises:
            ValueError: If config has validation errors
        """
        errors = ConfigValidator.validate(self.config)

        if errors:
            error_msg = ConfigValidator.display_errors(errors)
            print(error_msg)
            raise ValueError(f"Config validation failed with {len(errors)} error(s)")

        print("[INFO] Config validation passed")

    def load_data(self):
        """Load dataset using universal data loader."""
        csv_filename = self.config['data']['csv_filename']
        input_column = self.config['data'].get('input_column', 'text')
        output_columns = self.config['data'].get('output_columns')

        print(f"\n[INFO] Loading data from: {csv_filename}")

        # If output_columns not specified, infer from CSV
        if not output_columns:
            csv_path = get_paths().dataset(csv_filename)
            with open(csv_path, 'r', encoding='utf-8') as f:
                import csv
                reader = csv.DictReader(f)
                all_cols = reader.fieldnames
                output_columns = [c for c in all_cols if c not in ['split', input_column]]

        # Load using universal function
        self.train_data, self.val_data, self.test_data = load_gepa_data(
            csv_filename=csv_filename,
            input_column=input_column,
            output_columns=output_columns
        )

        print(f"[INFO] Loaded: {len(self.train_data)} train, {len(self.val_data)} val, {len(self.test_data)} test")

    def initialize_adapter(self):
        """Initialize adapter based on config type."""
        adapter_type = self.config['adapter']['type']
        # Capture actual temperature used for reporting consistency
        self.active_temperature = self.config.get('models', {}).get('temperature', 0.0)

        print(f"[INFO] Initializing {adapter_type} adapter...")

        if adapter_type == "classifier":
            valid_classes = self.config['adapter']['valid_classes']
            self.adapter = SimpleClassifierAdapter(
                valid_classes=valid_classes,
                temperature=self.active_temperature
            )

        elif adapter_type == "extractor":
            required_fields = self.config['adapter']['required_fields']
            max_pos = self.config['adapter'].get('max_positive_examples')

            self.adapter = SimpleExtractorAdapter(
                required_fields=required_fields,
                temperature=self.active_temperature,
                max_positive_examples=max_pos
            )

        elif adapter_type == "sql":
            self.adapter = SimpleSQLAdapter(temperature=self.active_temperature)

        elif adapter_type == "rag":
            max_pos = self.config['adapter'].get('max_positive_examples')
            self.adapter = SimpleRAGAdapter(
                temperature=self.active_temperature,
                max_positive_examples=max_pos
            )

        else:
            raise ValueError(f"Unsupported adapter type: {adapter_type}")

        print(f"[INFO] Adapter initialized: {adapter_type}")

    def _has_positive_reflection(self) -> bool:
        """Determine if this run uses positive reflection."""
        adapter_type = self.config['adapter']['type']
        if adapter_type in ["extractor", "rag"]:
            max_pos = self.config['adapter'].get('max_positive_examples', 0)
            return max_pos > 0
        return False

    def load_prompt(self) -> Dict[str, str]:
        """
        Load initial prompt from JSON file.

        Returns:
            Prompt dictionary with 'system_prompt' key
        """
        prompt_filename = self.config['prompt']['filename']
        prompt_path = get_paths().prompt(prompt_filename)

        print(f"[INFO] Loading prompt from: {prompt_filename}")

        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt = json.load(f)

        return prompt

    def execute_gepa_pipeline(self, initial_prompt: Dict[str, str], verbose: bool = False):
        """
        Execute complete GEPA optimization pipeline.

        Args:
            initial_prompt: Initial prompt dictionary
            verbose: If True, show reflection analysis in console
        """
        case_title = self.config['case'].get('title', self.config['case']['name'])

        # Header
        print_header(f"GEPA Optimization: {case_title}")

        # Dataset info
        from gepa_standalone.data.data_loader import print_dataset_info
        print_dataset_info(self.config['data']['csv_filename'])

        print(f"\nPROMPT INICIAL:\n{initial_prompt['system_prompt']}")

        # 1. BASELINE
        print_section("BASELINE PERFORMANCE")
        print(">> Evaluando prompt inicial en conjunto de validacion...")
        eval_baseline = self.adapter.evaluate(self.val_data, initial_prompt)
        baseline_avg = sum(eval_baseline.scores) / len(eval_baseline.scores) if eval_baseline.scores else 0.0
        print(f"Precision Baseline: {baseline_avg*100:.1f}%")

        # 2. OPTIMIZATION
        print_section("GEPA OPTIMIZATION")
        reflection_lm = create_reflection_lm_function(verbose=verbose)

        # Snapshot parameters for consistency
        self.active_max_metric_calls = self.config['optimization']['max_metric_calls']
        self.active_skip_perfect_score = self.config['optimization'].get('skip_perfect_score', True)

        result = optimize(
            seed_candidate=initial_prompt,
            trainset=self.train_data,
            valset=self.val_data,
            adapter=self.adapter,
            task_lm=None,
            reflection_lm=reflection_lm,
            max_metric_calls=self.active_max_metric_calls,
            skip_perfect_score=self.active_skip_perfect_score,
            display_progress_bar=self.config['optimization'].get('display_progress_bar', True)
        )

        optimized_prompt = result.best_candidate

        # 3. OPTIMIZED PERFORMANCE
        print_section("OPTIMIZED PERFORMANCE")
        print(">> Midiendo desempeno del mejor prompt encontrado...")
        eval_opt = self.adapter.evaluate(self.val_data, optimized_prompt)
        opt_avg = sum(eval_opt.scores) / len(eval_opt.scores) if eval_opt.scores else 0.0

        # 4. ROBUSTNESS TEST
        print_section("ROBUSTNESS TEST")
        print(">> Verificando generalizacion en conjunto de prueba...")
        eval_test = self.adapter.evaluate(self.test_data, optimized_prompt)
        test_avg = sum(eval_test.scores) / len(eval_test.scores) if eval_test.scores else 0.0

        print_detailed_results(eval_test)

        # 5. SUMMARY
        print_summary(
            baseline_avg=baseline_avg,
            optimized_avg=opt_avg,
            test_avg=test_avg,
            task_model=self.adapter.model,
            reflection_model=get_reflection_config().model,
            budget_used=result.total_metric_calls
        )

        print(f"\nPROMPT ORIGINAL:\n{initial_prompt['system_prompt']}")
        print(f"\nPROMPT OPTIMIZADO:\n{optimized_prompt['system_prompt']}")

        # Store results for logging
        self.results = {
            "initial_prompt": initial_prompt['system_prompt'],
            "final_prompt": optimized_prompt['system_prompt'],
            "baseline_score": baseline_avg,
            "optimized_score": opt_avg,
            "test_score": test_avg,
            "total_metric_calls": result.total_metric_calls
        }

    def save_results(self) -> Path:
        """
        Save final results and log to master CSV.

        Returns:
            Path to the run directory
        """
        run_id = str(uuid.uuid4())[:8]
        
        # Determine model names
        task_config = get_task_config()
        reflect_config = get_reflection_config()
        
        # Prepare metadata
        metadata = {
            "case": self.config['case']['name'],
            "task_model": task_config.model,
            "reflection_model": reflect_config.model,
            "max_metric_calls": self.config['optimization']['max_metric_calls'],
            "timestamp": datetime.now().isoformat()
        }
        
        # Save detailed results
        run_dir = save_run_details(
            case_name=self.config['case']['name'],
            run_id=run_id,
            initial_prompt=self.results['initial_prompt'],
            final_prompt=self.results['final_prompt'],
            metadata=metadata,
            results=self.results
        )
        
        # Log to master CSV
        log_experiment_result(
            case_title=self.config['case']['title'],
            task_model=task_config.model,
            reflection_model=reflect_config.model,
            baseline_score=self.results['baseline_score'],
            optimized_score=self.results['optimized_score'],
            robustness_score=self.results['test_score'],
            run_directory=str(run_dir),
            budget=metadata['max_metric_calls'],
        )

        return run_dir


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Universal GEPA Optimizer - Interfaz unica para todos los casos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with existing config
  python universal_optimizer.py --config experiments/configs/email_urgency.yaml

  # Run without config (activates wizard)
  python universal_optimizer.py

For more info, see: gepa_standalone/experiments/configs/
        """
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to YAML config file. If not provided or doesn't exist, wizard mode activates."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show real-time reflection analysis from the Teacher model."
    )

    args = parser.parse_args()

    # Initialize and run optimizer
    optimizer = UniversalOptimizer(config_path=args.config)

    try:
        optimizer.run(verbose=args.verbose)
    except Exception as e:
        print(f"\n[ERROR] Optimization failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

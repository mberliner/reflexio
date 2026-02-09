import csv
import os
import shutil


def get_runs_from_csv(csv_path):
    runs = set()
    if not os.path.exists(csv_path):
        print(f"Warning: CSV not found at {csv_path}")
        return runs

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        try:
            headers = next(reader)
            # Find column index for 'Run Directory'
            try:
                idx = headers.index("Run Directory")
            except ValueError:
                print(f"Error: 'Run Directory' column not found in {csv_path}")
                return runs

            for row in reader:
                if len(row) > idx:
                    path = row[idx].strip()
                    # Filter out non-path entries like "Sin datos... (Archivado)"
                    if path and path.startswith("runs/"):
                        # Normalize path separators
                        path = path.replace("\\", "/")
                        runs.add(path)
        except StopIteration:
            pass
    return runs


def get_actual_runs(base_dir, runs_dir_rel, is_nested=False):
    actual_runs = set()
    runs_root = os.path.join(base_dir, runs_dir_rel)

    if not os.path.exists(runs_root):
        return actual_runs

    if not is_nested:
        # For DSPy: runs are direct children
        for item in os.listdir(runs_root):
            if item == "latest":
                continue
            full_path = os.path.join(runs_root, item)
            if os.path.isdir(full_path):
                rel_path = os.path.join(runs_dir_rel, item).replace("\\", "/")
                actual_runs.add(rel_path)
    else:
        # For GEPA: runs are nested like runs/category/timestamp_id
        if os.path.isdir(runs_root):
            for category in os.listdir(runs_root):
                cat_path = os.path.join(runs_root, category)
                if os.path.isdir(cat_path):
                    for item in os.listdir(cat_path):
                        if item == "latest":
                            continue
                        full_path = os.path.join(cat_path, item)
                        # We include it if it's a directory (real or symlink to dir)
                        if os.path.isdir(full_path):
                            rel_path = os.path.join(runs_dir_rel, category, item).replace("\\", "/")
                            actual_runs.add(rel_path)
    return actual_runs


def process_project(project_name, project_results_dir, is_nested):
    print(f"\nProcessing {project_name}...")
    csv_path = os.path.join(project_results_dir, "experiments", "metricas_optimizacion.csv")

    # 1. Get expected runs from CSV
    expected_runs = get_runs_from_csv(csv_path)
    print(f"Found {len(expected_runs)} valid referenced runs in CSV.")

    # 2. Get actual runs from disk (excluding 'latest')
    actual_runs = get_actual_runs(project_results_dir, "runs", is_nested)
    print(f"Found {len(actual_runs)} actual run directories on disk (excluding 'latest').")

    # 3. Compare
    missing = expected_runs - actual_runs
    extra = actual_runs - expected_runs

    # 4. Report Missing
    if missing:
        print("\nMISSING RUNS (Referenced in CSV but not found on disk):")
        for m in sorted(missing):
            print(f" - {m}")
    else:
        print("\nNo missing runs.")

    # 5. Delete Extra
    if extra:
        print(f"\nEXTRA RUNS (Found on disk but not in CSV). Deleting {len(extra)} folders...")
        for e in sorted(extra):
            full_path = os.path.join(project_results_dir, e)
            print(f" - Deleting: {full_path}")
            try:
                if os.path.islink(full_path):
                    os.unlink(full_path)
                else:
                    shutil.rmtree(full_path)
            except OSError as err:
                print(f"   Error deleting {full_path}: {err}")
    else:
        print("\nNo extra runs to delete.")


# DSPy Project
process_project("dspy_gepa_poc", "dspy_gepa_poc/results", is_nested=False)

# GEPA Standalone Project
process_project("gepa_standalone", "gepa_standalone/results", is_nested=True)

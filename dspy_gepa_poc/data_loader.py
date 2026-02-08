import csv
import logging
import os
import sys
import dspy
from pathlib import Path
from typing import List, Tuple, Dict, Any

# Add project root to path for shared module access
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.paths import get_dspy_paths

logger = logging.getLogger(__name__)


class CSVDataLoader:
    """
    Handles loading datasets from CSV files into DSPy Examples.
    Separates data (CSV) from logic (Python), enabling the GEPA V1 architecture.
    """

    def __init__(self, datasets_dir: str = None):
        """
        Initialize the loader.

        Args:
            datasets_dir: Path to directory containing CSVs.
                          Defaults to DSPyPaths.datasets via shared paths.
        """
        if datasets_dir:
            self.datasets_dir = datasets_dir
        else:
            self.datasets_dir = str(get_dspy_paths().datasets)

    def load_dataset(
        self, 
        filename: str, 
        input_keys: List[str]
    ) -> Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]]:
        """
        Generic loader for any CSV dataset.
        
        Args:
            filename: Name of the CSV file (e.g., 'sentiment.csv')
            input_keys: List of column names to be treated as inputs (e.g., ['text'])
            
        Returns:
            Tuple (trainset, valset, testset) containing lists of dspy.Examples
        """
        filepath = os.path.join(self.datasets_dir, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Dataset not found at: {filepath}")

        trainset = []
        valset = []
        testset = []

        with open(filepath, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # 1. Identify and remove split from fields
                split = row.pop('split', None)
                if not split:
                    logger.warning("Skipping row without 'split' field: %s", row)
                    continue 

                # 2. Ensure all keys are strings and values are stripped of whitespace
                clean_row = {str(k).strip(): (v or "").strip() for k, v in row.items() if k is not None}

                # 3. Create dspy.Example
                try:
                    example = dspy.Example(**clean_row)
                except Exception as e:
                    logger.error(f"Error creating example from row: {clean_row}")
                    raise
                
                # 4. Define inputs explicitly
                example = example.with_inputs(*input_keys)

                # 5. Add to appropriate list
                if split == 'train':
                    trainset.append(example)
                elif split == 'val':
                    valset.append(example)
                elif split == 'test':
                    testset.append(example)
        
        return trainset, valset, testset

# Convenience functions to replicate old API but using CSVs
def load_sentiment_dataset() -> Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]]:
    loader = CSVDataLoader()
    return loader.load_dataset("sentiment.csv", input_keys=["text"])

def load_extraction_dataset() -> Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]]:
    loader = CSVDataLoader()
    # For extraction, we might need to reconstruct the nested dictionary if the
    # module expects 'extracted_info' as a single dict field.
    # HOWEVER, standard DSPy Signatures usually work with flat fields better.
    # Let's see how modules.py is defined.
    # If modules.py expects flat fields (customer_name, product, etc.), this works.
    # If it expects a dict, we need a custom processor here.
    return loader.load_dataset("extraction.csv", input_keys=["text"])

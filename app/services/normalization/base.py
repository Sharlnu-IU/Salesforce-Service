import re
import os
import pandas as pd
from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class BaseNormalizer(ABC):
    """
    Base class for normalizing Salesforce object data.
    Subclasses must implement normalize() to turn a raw DataFrame
    into one or more clean relational DataFrames.
    """

    @abstractmethod
    def normalize(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Takes a raw pandas DataFrame (extracted from Bulk API CSV)
        and returns a dictionary mapping target table names to their respective DataFrames.
        """
        pass

    @staticmethod
    def to_snake_case(name: str) -> str:
        """Converts PascalCase or camelCase string to snake_case."""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    @staticmethod
    def safe_get(row: Any, col: str, default: Any = None) -> Any:
        """Safely gets a value from a Series or dict, returning default if null/missing."""
        val = row.get(col, default) if hasattr(row, 'get') else getattr(row, col, default)
        if pd.isna(val) or val == '':
            return default
        return val

    @staticmethod
    def get_statistics(tables: Dict[str, pd.DataFrame]) -> Dict[str, int]:
        """Returns row count per normalized table."""
        return {table_name: len(df) for table_name, df in tables.items()}

    def save_to_files(
        self,
        tables: Dict[str, pd.DataFrame],
        output_dir: str,
        output_format: str = "parquet"
    ) -> List[str]:
        """
        Saves normalized DataFrames to files (Parquet or JSON) in output_dir.
        Returns the list of created file paths.
        """
        os.makedirs(output_dir, exist_ok=True)
        created_paths = []

        for table_name, table_df in tables.items():
            if table_df.empty:
                logger.info(f"Table {table_name} is empty, creating empty schema file.")

            if output_format.lower() == "json":
                out_path = os.path.join(output_dir, f"{table_name}.json")
                table_df.to_json(out_path, orient="records", date_format="iso")
            else:
                out_path = os.path.join(output_dir, f"{table_name}.parquet")
                table_df.to_parquet(out_path, engine="pyarrow", index=False)

            created_paths.append(out_path)
            logger.info(f"Saved normalized table {table_name} to {out_path} ({len(table_df)} rows)")

        return created_paths

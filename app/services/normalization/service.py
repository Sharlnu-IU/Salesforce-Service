import os
import pandas as pd
from typing import Dict, List
import logging
from app.services.normalization.base import BaseNormalizer
from app.services.normalization.account import AccountNormalizer

logger = logging.getLogger(__name__)

class NormalizationService:
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Registry of supported normalizers
        self._normalizers: Dict[str, BaseNormalizer] = {
            "Account": AccountNormalizer()
        }

    def _get_normalizer(self, object_name: str) -> BaseNormalizer:
        normalizer = self._normalizers.get(object_name)
        if not normalizer:
            raise ValueError(f"No normalizer registered for object type: {object_name}")
        return normalizer

    def normalize_csv(self, object_name: str, csv_filepath: str) -> List[str]:
        """
        Reads a raw Salesforce CSV, normalizes it into one or more relational DataFrames,
        and saves each as a Parquet file.
        Returns a list of output Parquet file paths.
        """
        logger.info(f"Normalizing {object_name} from {csv_filepath}")
        
        # 1. Read CSV
        try:
            df = pd.read_csv(csv_filepath)
        except Exception as e:
            logger.error(f"Failed to read CSV {csv_filepath}: {str(e)}")
            raise
            
        # 2. Get the correct normalizer
        normalizer = self._get_normalizer(object_name)
        
        # 3. Normalize
        tables = normalizer.normalize(df)
        
        # 4. Save to Parquet
        output_files = []
        for table_name, table_df in tables.items():
            if table_df.empty:
                logger.warning(f"Table {table_name} is empty after normalization. Skipping.")
                continue
                
            parquet_path = os.path.join(self.output_dir, f"{table_name}.parquet")
            try:
                # We use pyarrow engine by default
                table_df.to_parquet(parquet_path, engine='pyarrow', index=False)
                output_files.append(parquet_path)
                logger.info(f"Saved normalized table {table_name} to {parquet_path}")
            except Exception as e:
                logger.error(f"Failed to save Parquet {parquet_path}: {str(e)}")
                raise
                
        return output_files

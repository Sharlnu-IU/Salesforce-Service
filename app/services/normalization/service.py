import os
import glob
import logging
from typing import Dict, List, Tuple, Any
import pandas as pd
from app.services.normalization.base import BaseNormalizer
from app.services.normalization.account import AccountNormalizer
from app.services.normalization.contact import ContactNormalizer
from app.services.normalization.opportunity import OpportunityNormalizer
from app.services.normalization.lead import LeadNormalizer
from app.services.normalization.case import CaseNormalizer
from app.services.normalization.task_event import TaskEventNormalizer
from app.services.normalization.campaign import CampaignNormalizer
from app.services.normalization.user import UserNormalizer

logger = logging.getLogger(__name__)

SUPPORTED_CATALOG: Dict[str, List[str]] = {
    "Account": ["accounts", "account_addresses", "account_teams"],
    "Contact": ["contacts", "contact_roles"],
    "Opportunity": ["opportunities", "opportunity_line_items", "opportunity_contact_roles"],
    "Lead": ["leads"],
    "Case": ["cases", "case_comments"],
    "Task": ["tasks", "events"],
    "Event": ["tasks", "events"],
    "Campaign": ["campaigns", "campaign_members"],
    "User": ["users"],
}

class NormalizationService:
    def __init__(self, output_dir: str = "data/normalized"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Registry of supported normalizers
        self._normalizers: Dict[str, BaseNormalizer] = {
            "Account": AccountNormalizer(),
            "Contact": ContactNormalizer(),
            "Opportunity": OpportunityNormalizer(),
            "Lead": LeadNormalizer(),
            "Case": CaseNormalizer(),
            "Task": TaskEventNormalizer(),
            "Event": TaskEventNormalizer(),
            "Campaign": CampaignNormalizer(),
            "User": UserNormalizer(),
        }

    @staticmethod
    def get_supported_catalog() -> Dict[str, List[str]]:
        """Returns the static mapping of supported Salesforce objects to their relational output tables."""
        return SUPPORTED_CATALOG

    def _get_normalizer(self, object_name: str) -> BaseNormalizer:
        # Case-insensitive lookup
        for key, norm in self._normalizers.items():
            if key.lower() == object_name.lower():
                return norm
        raise ValueError(f"No normalizer registered for object type: {object_name}")

    def normalize_csv(
        self,
        object_name: str,
        csv_filepath: str,
        output_format: str = "parquet",
        target_dir: str = None
    ) -> Tuple[List[str], Dict[str, int]]:
        """
        Reads a raw Salesforce CSV, normalizes it into relational DataFrames,
        and saves each to Parquet (or JSON) in target_dir.
        Returns:
            created_files: list of saved file paths
            table_counts: dictionary of table name -> record count
        """
        dest_dir = target_dir or self.output_dir
        os.makedirs(dest_dir, exist_ok=True)
        
        logger.info(f"Normalizing {object_name} from {csv_filepath}")
        
        try:
            df = pd.read_csv(csv_filepath)
        except Exception as e:
            logger.error(f"Failed to read CSV {csv_filepath}: {str(e)}")
            raise
            
        normalizer = self._get_normalizer(object_name)
        tables = normalizer.normalize(df)
        
        created_files = normalizer.save_to_files(
            tables=tables,
            output_dir=dest_dir,
            output_format=output_format
        )
        
        stats = BaseNormalizer.get_statistics(tables)
        return created_files, stats

    def list_normalized_files(self, scan_id: str) -> List[str]:
        """Lists normalized files generated for a specific scan."""
        scan_dir = os.path.join(self.output_dir, scan_id)
        if not os.path.exists(scan_dir):
            return []
        return glob.glob(os.path.join(scan_dir, "*.*"))

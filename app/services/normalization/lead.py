import pandas as pd
from typing import Dict
from app.services.normalization.base import BaseNormalizer

class LeadNormalizer(BaseNormalizer):
    def normalize(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Normalizes Lead DataFrame into `leads` table.
        """
        if df.empty or 'Id' not in df.columns:
            return {
                "leads": pd.DataFrame(columns=['id', 'first_name', 'last_name', 'company', 'email', 'status', 'lead_source'])
            }

        cols = ['Id', 'FirstName', 'LastName', 'Company', 'Email', 'Phone', 'Status', 'LeadSource', 'IsConverted', 'OwnerId']
        actual_cols = [c for c in cols if c in df.columns]
        leads_df = df[actual_cols].copy()
        leads_df.columns = [self.to_snake_case(c) for c in leads_df.columns]

        return {
            "leads": leads_df
        }

import pandas as pd
from typing import Dict
from app.services.normalization.base import BaseNormalizer

class ContactNormalizer(BaseNormalizer):
    def normalize(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Normalizes Contact DataFrame into `contacts` and `contact_roles` tables.
        """
        if df.empty or 'Id' not in df.columns:
            return {
                "contacts": pd.DataFrame(columns=['id', 'account_id', 'first_name', 'last_name', 'email', 'phone', 'title']),
                "contact_roles": pd.DataFrame(columns=['contact_id', 'account_id', 'role'])
            }

        # 1. Contacts Table
        cols = ['Id', 'AccountId', 'FirstName', 'LastName', 'Email', 'Phone', 'Title', 'Department', 'OwnerId']
        actual_cols = [c for c in cols if c in df.columns]
        contacts_df = df[actual_cols].copy()
        contacts_df.columns = [self.to_snake_case(c) for c in contacts_df.columns]

        # 2. Contact Roles Table
        role_rows = []
        for _, row in df.iterrows():
            cid = row['Id']
            acc_id = self.safe_get(row, 'AccountId')
            title = self.safe_get(row, 'Title')
            if acc_id:
                role_rows.append({
                    'contact_id': cid,
                    'account_id': acc_id,
                    'role': title or 'Contact'
                })

        roles_df = pd.DataFrame(role_rows) if role_rows else pd.DataFrame(
            columns=['contact_id', 'account_id', 'role']
        )

        return {
            "contacts": contacts_df,
            "contact_roles": roles_df
        }

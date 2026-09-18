import pandas as pd
from typing import Dict
from app.services.normalization.base import BaseNormalizer

class OpportunityNormalizer(BaseNormalizer):
    def normalize(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Normalizes Opportunity DataFrame into `opportunities`, `opportunity_line_items`,
        and `opportunity_contact_roles` tables.
        """
        if df.empty or 'Id' not in df.columns:
            return {
                "opportunities": pd.DataFrame(columns=['id', 'account_id', 'name', 'stage_name', 'amount', 'close_date', 'probability']),
                "opportunity_line_items": pd.DataFrame(columns=['opportunity_id', 'product_name', 'quantity', 'unit_price', 'total_price']),
                "opportunity_contact_roles": pd.DataFrame(columns=['opportunity_id', 'contact_id', 'role', 'is_primary'])
            }

        # 1. Opportunities Table
        cols = ['Id', 'AccountId', 'Name', 'StageName', 'Amount', 'CloseDate', 'Probability', 'Type', 'LeadSource', 'OwnerId']
        actual_cols = [c for c in cols if c in df.columns]
        opps_df = df[actual_cols].copy()
        opps_df.columns = [self.to_snake_case(c) for c in opps_df.columns]

        # 2. Opportunity Line Items (if nested or present)
        line_item_rows = []
        if 'LineItems' in df.columns or 'Product2Id' in df.columns:
            for _, row in df.iterrows():
                if self.safe_get(row, 'Product2Id'):
                    line_item_rows.append({
                        'opportunity_id': row['Id'],
                        'product_name': self.safe_get(row, 'Product2Id'),
                        'quantity': self.safe_get(row, 'Quantity', 1),
                        'unit_price': self.safe_get(row, 'UnitPrice', 0.0),
                        'total_price': self.safe_get(row, 'TotalPrice', 0.0),
                    })
        line_items_df = pd.DataFrame(line_item_rows) if line_item_rows else pd.DataFrame(
            columns=['opportunity_id', 'product_name', 'quantity', 'unit_price', 'total_price']
        )

        # 3. Opportunity Contact Roles
        contact_role_rows = []
        if 'ContactId' in df.columns:
            for _, row in df.iterrows():
                cid = self.safe_get(row, 'ContactId')
                if cid:
                    contact_role_rows.append({
                        'opportunity_id': row['Id'],
                        'contact_id': cid,
                        'role': self.safe_get(row, 'Role', 'Decision Maker'),
                        'is_primary': self.safe_get(row, 'IsPrimary', True)
                    })
        contact_roles_df = pd.DataFrame(contact_role_rows) if contact_role_rows else pd.DataFrame(
            columns=['opportunity_id', 'contact_id', 'role', 'is_primary']
        )

        return {
            "opportunities": opps_df,
            "opportunity_line_items": line_items_df,
            "opportunity_contact_roles": contact_roles_df
        }

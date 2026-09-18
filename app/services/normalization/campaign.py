import pandas as pd
from typing import Dict
from app.services.normalization.base import BaseNormalizer

class CampaignNormalizer(BaseNormalizer):
    def normalize(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Normalizes Campaign DataFrame into `campaigns` and `campaign_members` tables.
        """
        if df.empty or 'Id' not in df.columns:
            return {
                "campaigns": pd.DataFrame(columns=['id', 'name', 'status', 'start_date', 'end_date', 'expected_revenue']),
                "campaign_members": pd.DataFrame(columns=['campaign_id', 'lead_id', 'contact_id', 'status'])
            }

        # 1. Campaigns Table
        cols = ['Id', 'Name', 'Status', 'StartDate', 'EndDate', 'ExpectedRevenue', 'ActualCost', 'Type', 'IsActive', 'OwnerId']
        actual = [c for c in cols if c in df.columns]
        campaigns_df = df[actual].copy()
        campaigns_df.columns = [self.to_snake_case(c) for c in campaigns_df.columns]

        # 2. Campaign Members Table (if member fields embedded)
        member_rows = []
        if 'LeadId' in df.columns or 'ContactId' in df.columns:
            for _, row in df.iterrows():
                lid = self.safe_get(row, 'LeadId')
                cid = self.safe_get(row, 'ContactId')
                if lid or cid:
                    member_rows.append({
                        'campaign_id': row['Id'],
                        'lead_id': lid,
                        'contact_id': cid,
                        'status': self.safe_get(row, 'MemberStatus', 'Sent')
                    })
        members_df = pd.DataFrame(member_rows) if member_rows else pd.DataFrame(
            columns=['campaign_id', 'lead_id', 'contact_id', 'status']
        )

        return {
            "campaigns": campaigns_df,
            "campaign_members": members_df
        }

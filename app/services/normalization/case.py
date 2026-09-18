import pandas as pd
from typing import Dict
from app.services.normalization.base import BaseNormalizer

class CaseNormalizer(BaseNormalizer):
    def normalize(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Normalizes Case DataFrame into `cases` and `case_comments` tables.
        """
        if df.empty or 'Id' not in df.columns:
            return {
                "cases": pd.DataFrame(columns=['id', 'account_id', 'contact_id', 'case_number', 'subject', 'status', 'priority']),
                "case_comments": pd.DataFrame(columns=['case_id', 'comment_body', 'is_published'])
            }

        # 1. Cases Table
        cols = ['Id', 'AccountId', 'ContactId', 'CaseNumber', 'Subject', 'Status', 'Priority', 'Origin', 'Description', 'CreatedDate', 'ClosedDate', 'OwnerId']
        actual_cols = [c for c in cols if c in df.columns]
        cases_df = df[actual_cols].copy()
        cases_df.columns = [self.to_snake_case(c) for c in cases_df.columns]

        # 2. Case Comments Table
        comment_rows = []
        if 'Comments' in df.columns or 'Description' in df.columns:
            for _, row in df.iterrows():
                desc = self.safe_get(row, 'Description')
                if desc:
                    comment_rows.append({
                        'case_id': row['Id'],
                        'comment_body': str(desc)[:1000],
                        'is_published': False
                    })
        comments_df = pd.DataFrame(comment_rows) if comment_rows else pd.DataFrame(
            columns=['case_id', 'comment_body', 'is_published']
        )

        return {
            "cases": cases_df,
            "case_comments": comments_df
        }

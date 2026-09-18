import pandas as pd
from typing import Dict
from app.services.normalization.base import BaseNormalizer

class UserNormalizer(BaseNormalizer):
    def normalize(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Normalizes User DataFrame into `users` table.
        """
        if df.empty or 'Id' not in df.columns:
            return {
                "users": pd.DataFrame(columns=['id', 'username', 'email', 'is_active', 'department', 'title'])
            }

        cols = ['Id', 'Username', 'LastName', 'FirstName', 'Email', 'IsActive', 'Department', 'Title', 'UserRoleId', 'ProfileId']
        actual = [c for c in cols if c in df.columns]
        users_df = df[actual].copy()
        users_df.columns = [self.to_snake_case(c) for c in users_df.columns]

        return {
            "users": users_df
        }

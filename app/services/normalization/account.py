import pandas as pd
from typing import Dict
from app.services.normalization.base import BaseNormalizer

class AccountNormalizer(BaseNormalizer):
    def normalize(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Splits a raw Account DataFrame into `accounts`, `account_addresses`, and `account_teams` tables.
        """
        if df.empty or 'Id' not in df.columns:
            return {
                "accounts": pd.DataFrame(columns=['id', 'name', 'type']),
                "account_addresses": pd.DataFrame(columns=['account_id', 'address_type', 'city', 'state', 'street', 'postal_code', 'country']),
                "account_teams": pd.DataFrame(columns=['account_id', 'user_id', 'team_role'])
            }

        # 1. Accounts Table
        core_cols = ['Id', 'Name', 'Type', 'Industry', 'AnnualRevenue', 'Phone', 'Website', 'OwnerId']
        actual_cols = [c for c in core_cols if c in df.columns]
        accounts_df = df[actual_cols].copy()
        accounts_df.columns = [self.to_snake_case(c) for c in accounts_df.columns]

        # 2. Account Addresses Table (Billing and Shipping)
        address_rows = []
        for _, row in df.iterrows():
            acc_id = row['Id']
            # Billing
            if any(pd.notna(row.get(f'Billing{f}')) for f in ['City', 'State', 'Street', 'PostalCode', 'Country']):
                address_rows.append({
                    'account_id': acc_id,
                    'address_type': 'Billing',
                    'city': self.safe_get(row, 'BillingCity'),
                    'state': self.safe_get(row, 'BillingState'),
                    'street': self.safe_get(row, 'BillingStreet'),
                    'postal_code': self.safe_get(row, 'BillingPostalCode'),
                    'country': self.safe_get(row, 'BillingCountry')
                })
            # Shipping
            if any(pd.notna(row.get(f'Shipping{f}')) for f in ['City', 'State', 'Street', 'PostalCode', 'Country']):
                address_rows.append({
                    'account_id': acc_id,
                    'address_type': 'Shipping',
                    'city': self.safe_get(row, 'ShippingCity'),
                    'state': self.safe_get(row, 'ShippingState'),
                    'street': self.safe_get(row, 'ShippingStreet'),
                    'postal_code': self.safe_get(row, 'ShippingPostalCode'),
                    'country': self.safe_get(row, 'ShippingCountry')
                })

        addresses_df = pd.DataFrame(address_rows) if address_rows else pd.DataFrame(
            columns=['account_id', 'address_type', 'city', 'state', 'street', 'postal_code', 'country']
        )

        # 3. Account Teams Table (derived from OwnerId or TeamMember fields)
        team_rows = []
        for _, row in df.iterrows():
            owner_id = self.safe_get(row, 'OwnerId')
            if owner_id:
                team_rows.append({
                    'account_id': row['Id'],
                    'user_id': owner_id,
                    'team_role': 'Account Owner'
                })

        teams_df = pd.DataFrame(team_rows) if team_rows else pd.DataFrame(
            columns=['account_id', 'user_id', 'team_role']
        )

        return {
            "accounts": accounts_df,
            "account_addresses": addresses_df,
            "account_teams": teams_df
        }

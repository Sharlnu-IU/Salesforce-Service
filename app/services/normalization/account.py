import pandas as pd
from typing import Dict
from app.services.normalization.base import BaseNormalizer

class AccountNormalizer(BaseNormalizer):
    def normalize(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Splits a raw Account DataFrame into `accounts` and `account_addresses` tables.
        """
        # Ensure we have the minimum columns
        if 'Id' not in df.columns:
            raise ValueError("Account normalizer requires 'Id' column.")
            
        # 1. Accounts Table
        # We take Id, Name, Type, and any other non-address fields.
        account_cols = ['Id', 'Name', 'Type']
        # Filter only columns that actually exist in the df
        actual_account_cols = [col for col in account_cols if col in df.columns]
        
        accounts_df = df[actual_account_cols].copy()
        # Rename to snake_case
        accounts_df.rename(columns={
            'Id': 'id',
            'Name': 'name',
            'Type': 'type'
        }, inplace=True)
        
        # 2. Account Addresses Table
        # We will extract Billing address fields if they exist
        billing_cols = ['BillingCity', 'BillingState', 'BillingStreet', 'BillingPostalCode', 'BillingCountry']
        address_rows = []
        
        # Check if any billing columns exist
        has_billing = any(col in df.columns for col in billing_cols)
        
        if has_billing:
            for _, row in df.iterrows():
                # Only create an address row if at least one address field is non-null
                has_address_data = False
                for b_col in billing_cols:
                    if b_col in row and pd.notna(row[b_col]) and row[b_col] != '':
                        has_address_data = True
                        break
                        
                if has_address_data:
                    address_rows.append({
                        'account_id': row['Id'],
                        'address_type': 'Billing',
                        'city': row.get('BillingCity'),
                        'state': row.get('BillingState'),
                        'street': row.get('BillingStreet'),
                        'postal_code': row.get('BillingPostalCode'),
                        'country': row.get('BillingCountry')
                    })
                    
        account_addresses_df = pd.DataFrame(address_rows)
        if account_addresses_df.empty:
            # Create empty dataframe with correct columns if no addresses found
            account_addresses_df = pd.DataFrame(columns=[
                'account_id', 'address_type', 'city', 'state', 'street', 'postal_code', 'country'
            ])
            
        return {
            "accounts": accounts_df,
            "account_addresses": account_addresses_df
        }

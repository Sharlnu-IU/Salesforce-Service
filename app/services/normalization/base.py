import pandas as pd
from typing import Dict
from abc import ABC, abstractmethod

class BaseNormalizer(ABC):
    """
    Base class for normalizing Salesforce object data.
    Subclasses should implement normalize() to turn a raw DataFrame
    into one or more clean relational DataFrames.
    """
    
    @abstractmethod
    def normalize(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Takes a raw pandas DataFrame (e.g., extracted from Salesforce Bulk CSV)
        and returns a dictionary mapping target table names to their respective DataFrames.
        
        Example:
        return {
            "accounts": accounts_df,
            "account_addresses": addresses_df
        }
        """
        pass

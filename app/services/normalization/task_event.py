import pandas as pd
from typing import Dict
from app.services.normalization.base import BaseNormalizer

class TaskEventNormalizer(BaseNormalizer):
    def normalize(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Normalizes Task or Event DataFrames into `tasks` and/or `events` tables.
        """
        if df.empty or 'Id' not in df.columns:
            return {
                "tasks": pd.DataFrame(columns=['id', 'who_id', 'what_id', 'subject', 'status', 'priority']),
                "events": pd.DataFrame(columns=['id', 'who_id', 'what_id', 'subject', 'start_date_time', 'end_date_time'])
            }

        # Check whether input represents Task, Event, or both
        is_event = 'StartDateTime' in df.columns or 'EndDateTime' in df.columns
        is_task = 'Status' in df.columns or 'ActivityDate' in df.columns

        tasks_df = pd.DataFrame(columns=['id', 'who_id', 'what_id', 'subject', 'status', 'priority'])
        events_df = pd.DataFrame(columns=['id', 'who_id', 'what_id', 'subject', 'start_date_time', 'end_date_time'])

        if is_event and not is_task:
            cols = ['Id', 'WhoId', 'WhatId', 'Subject', 'StartDateTime', 'EndDateTime', 'Description', 'OwnerId']
            actual = [c for c in cols if c in df.columns]
            events_df = df[actual].copy()
            events_df.columns = [self.to_snake_case(c) for c in events_df.columns]
        else:
            cols = ['Id', 'WhoId', 'WhatId', 'Subject', 'Status', 'Priority', 'ActivityDate', 'Description', 'OwnerId']
            actual = [c for c in cols if c in df.columns]
            tasks_df = df[actual].copy()
            tasks_df.columns = [self.to_snake_case(c) for c in tasks_df.columns]

        return {
            "tasks": tasks_df,
            "events": events_df
        }

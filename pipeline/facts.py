"""Fact-table construction and configurable duplicate handling."""
from __future__ import annotations
import pandas as pd
from .exceptions import DuplicateBusinessKeyError
from .utils import composite_key

def build_fact_table(resolved: pd.DataFrame, master: pd.DataFrame, spec: dict,
                     source_file: str, load_id: str, load_date: pd.Timestamp,
                     duplicate_strategy: str):
    """Build traceable facts and skip/update/error on configured business keys."""
    fact = resolved[spec["columns"]].copy()
    fact["Source_File"] = source_file
    fact["Source_Row_Number"] = resolved["Source_Row_Number"].values
    fact["Load_Date"] = load_date
    fact["Load_ID"] = load_id
    key = spec["business_key"]
    within_duplicate = fact.duplicated(key, keep="last")
    duplicate_count = int(within_duplicate.sum())
    fact = fact.loc[~within_duplicate].copy()
    existing_keys = set(composite_key(master, key)) if not master.empty else set()
    exists = composite_key(fact, key).isin(existing_keys)
    duplicate_count += int(exists.sum())
    if duplicate_strategy == "error" and duplicate_count:
        raise DuplicateBusinessKeyError(f"Found {duplicate_count} duplicate fact business keys")
    if duplicate_strategy == "update" and exists.any():
        incoming_updates = fact.loc[exists].set_index(key)
        indexed_master = master.set_index(key)
        indexed_master.loc[incoming_updates.index, incoming_updates.columns] = incoming_updates.values
        master = indexed_master.reset_index()
    new_rows = fact.loc[~exists].copy()
    sk = spec["surrogate_key"]
    start = int(master[sk].max()) + 1 if not master.empty else 1
    new_rows.insert(0, sk, range(start, start + len(new_rows)))
    combined = (new_rows.reset_index(drop=True) if master.empty else
                pd.concat([master, new_rows], ignore_index=True))
    columns = [sk, *spec["columns"], "Source_File", "Source_Row_Number", "Load_Date", "Load_ID"]
    return combined[columns], {"new": len(new_rows), "duplicates": duplicate_count}

def create_date_dimension(start: str, end: str) -> pd.DataFrame:
    """Create a Power BI-friendly Gregorian date dimension."""
    dates = pd.date_range(start, end, freq="D")
    iso = dates.isocalendar()
    return pd.DataFrame({
        "Date_Key": dates.strftime("%Y%m%d").astype(int), "Date": dates,
        "Year": dates.year, "Quarter": "Q" + dates.quarter.astype(str),
        "Quarter_Number": dates.quarter, "Month_Number": dates.month,
        "Month_Name": dates.month_name(), "Year_Month": dates.strftime("%Y-%m"),
        "Week_Number": iso.week.to_numpy(), "Day": dates.day,
        "Day_Name": dates.day_name(), "Is_Weekend": dates.dayofweek >= 5,
    })

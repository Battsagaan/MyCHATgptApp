"""Dimension processing independent from persistence technology."""
from __future__ import annotations
import pandas as pd
from .exceptions import DuplicateBusinessKeyError
from .utils import composite_key

def process_dimension(source_df: pd.DataFrame, master_df: pd.DataFrame, spec: dict, now: pd.Timestamp):
    """Apply SCD Type 1, preserving keys and returning master, lookup and metrics."""
    key_cols, columns, sk = spec["business_key"], spec["columns"], spec["surrogate_key"]
    incoming = source_df[columns].drop_duplicates(key_cols, keep="last").copy()
    if master_df.duplicated(key_cols).any():
        raise DuplicateBusinessKeyError(f"Master dimension has duplicate key: {key_cols}")
    master = master_df.copy()
    existing_keys = set(composite_key(master, key_cols)) if not master.empty else set()
    incoming_keys = composite_key(incoming, key_cols)
    is_new = ~incoming_keys.isin(existing_keys)
    new_rows = incoming.loc[is_new].copy()
    start = int(master[sk].max()) + 1 if not master.empty else 1
    new_rows.insert(0, sk, range(start, start + len(new_rows)))
    new_rows["Created_Date"] = now
    new_rows["Updated_Date"] = now

    updated = 0
    if not master.empty:
        attrs = [c for c in columns if c not in key_cols]
        incoming_existing = incoming.loc[~is_new]
        if attrs and not incoming_existing.empty:
            indexed = master.set_index(key_cols)
            latest = incoming_existing.set_index(key_cols)
            common = indexed.index.intersection(latest.index)
            old = indexed.loc[common, attrs].astype("string").fillna("<NULL>")
            new = latest.loc[common, attrs].astype("string").fillna("<NULL>")
            changed = old.ne(new).any(axis=1)
            changed_keys = common[changed]
            if len(changed_keys):
                indexed.loc[changed_keys, attrs] = latest.loc[changed_keys, attrs].values
                indexed.loc[changed_keys, "Updated_Date"] = now
                updated = len(changed_keys)
            master = indexed.reset_index()
    master = (new_rows.reset_index(drop=True) if master.empty else
              pd.concat([master, new_rows], ignore_index=True))
    master = master[[sk, *columns, "Created_Date", "Updated_Date"]]
    lookup = master[[*key_cols, sk]].copy()
    metrics = {"new": len(new_rows), "updated": updated, "existing": len(incoming) - len(new_rows) - updated}
    return master, lookup, metrics

def resolve_dimension_keys(source_df: pd.DataFrame, lookups: dict, dimension_config: dict, fact_spec: dict):
    """Resolve every configured dimension using vectorized many-to-one merges."""
    result = source_df.copy()
    for dim_name, reference in fact_spec["dimension_references"].items():
        source_keys = reference["source_key"]
        sk = reference["foreign_key"]
        lookup_sk = dimension_config[dim_name]["surrogate_key"]
        lookup = lookups[dim_name].rename(columns={lookup_sk: sk})
        result = result.merge(lookup, on=source_keys, how="left", validate="many_to_one")
    return result

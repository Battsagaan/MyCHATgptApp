"""Vectorized source cleaning with conversion-error tracking."""
from __future__ import annotations
import re
import pandas as pd

def clean_text(series: pd.Series) -> pd.Series:
    """Trim and collapse Unicode-safe whitespace, preserving character case."""
    result = series.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    return result.mask(result.eq(""), pd.NA)

def clean_identifier(series: pd.Series) -> pd.Series:
    """Keep identifiers as strings and remove Excel's accidental integer '.0'."""
    result = clean_text(series)
    return result.str.replace(r"^(\d+)\.0$", r"\1", regex=True)

def parse_dates(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Parse ISO, day/month, month/day and Excel serial dates.

    Ambiguous slash dates are interpreted day-first. Explicit month-first values
    where the first component is <= 12 are retried month-first if needed.
    """
    output = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    numeric = pd.to_numeric(series, errors="coerce")
    serial_mask = numeric.notna() & numeric.between(1, 2958465)
    output.loc[serial_mask] = pd.to_datetime(
        numeric.loc[serial_mask], unit="D", origin="1899-12-30", errors="coerce"
    )
    remaining = series.notna() & ~serial_mask
    if remaining.any():
        text = clean_text(series.loc[remaining])
        parsed = pd.to_datetime(text, format="mixed", errors="coerce", dayfirst=True)
        retry = parsed.isna()
        if retry.any():
            parsed.loc[retry] = pd.to_datetime(
                text.loc[retry], format="mixed", errors="coerce", dayfirst=False
            )
        output.loc[remaining] = parsed
    invalid = series.notna() & output.isna()
    return output.dt.normalize(), invalid

def clean_dataframe(df: pd.DataFrame, cfg) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Clean configured columns and return per-field invalid conversion masks."""
    result = df.copy()
    errors: dict[str, pd.Series] = {}
    for column in cfg.TEXT_COLUMNS:
        result[column] = clean_identifier(result[column]) if column in cfg.ID_COLUMNS else clean_text(result[column])
    for column in cfg.DATE_COLUMNS:
        result[column], errors[column] = parse_dates(result[column])
    for column in cfg.NUMERIC_COLUMNS:
        original = result[column]
        result[column] = pd.to_numeric(original, errors="coerce")
        errors[column] = original.notna() & result[column].isna()
    return result, errors

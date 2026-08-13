"""Source-schema, row-level, and final-model validation."""
from __future__ import annotations
from collections import Counter
import pandas as pd
from .exceptions import DataValidationError, MissingColumnError

def validate_schema(headers: list[str], cfg) -> dict[str, list[str]]:
    """Validate exact source headers and report all structural differences."""
    duplicates = sorted(k for k, count in Counter(headers).items() if count > 1)
    missing = sorted(set(cfg.EXPECTED_COLUMNS) - set(headers))
    unexpected = sorted(set(headers) - set(cfg.EXPECTED_COLUMNS))
    problems = {"missing": missing, "unexpected": unexpected, "duplicated": duplicates}
    fatal = missing or duplicates or (unexpected and not cfg.ALLOW_UNEXPECTED_COLUMNS)
    if fatal:
        parts = ["PROCESS FAILED: invalid source structure."]
        for label, values in problems.items():
            if values:
                parts.append(f"{label.title()} columns:\n- " + "\n- ".join(values))
        raise MissingColumnError("\n\n".join(parts))
    return problems

def validate_rows(df: pd.DataFrame, conversion_errors: dict[str, pd.Series], cfg):
    """Split source rows into valid and rejected groups with all reasons."""
    reasons = pd.Series("", index=df.index, dtype="string")
    def add(mask: pd.Series, message: str) -> None:
        nonlocal reasons
        reasons.loc[mask] = reasons.loc[mask].where(reasons.loc[mask].eq(""), reasons.loc[mask] + "; ") + message
    for column in cfg.REQUIRED_COLUMNS:
        add(df[column].isna(), f"Missing {column}")
    for column, mask in conversion_errors.items():
        add(mask, f"Invalid {column}")
    # Every configured business key is mandatory, even if omitted from REQUIRED_COLUMNS.
    key_columns = set()
    for table in (*getattr(cfg, "DIMENSION_CONFIG", {}).values(), *getattr(cfg, "FACT_CONFIG", {}).values()):
        key_columns.update(c for c in table["business_key"] if c in df.columns)
    for column in key_columns:
        add(df[column].isna(), f"Blank business key {column}")
    rejected = df.loc[reasons.ne("")].copy()
    rejected["Validation_Status"] = "REJECTED"
    rejected["Error_Reason"] = reasons.loc[rejected.index]
    return df.loc[reasons.eq("")].copy(), rejected

def validate_integrity(tables: dict[str, pd.DataFrame], cfg) -> None:
    """Verify dimension uniqueness, fact uniqueness, required values and FKs."""
    errors: list[str] = []
    for name, spec in cfg.DIMENSION_CONFIG.items():
        table = tables[name]
        if table[spec["surrogate_key"]].isna().any() or table[spec["surrogate_key"]].duplicated().any():
            errors.append(f"{name}: surrogate keys are blank or duplicated")
        if table.duplicated(spec["business_key"]).any():
            errors.append(f"{name}: business keys are duplicated")
    for name, spec in cfg.FACT_CONFIG.items():
        fact = tables[name]
        if fact.duplicated(spec["business_key"]).any():
            errors.append(f"{name}: fact business keys are duplicated")
        required = spec["business_key"] + list(r["foreign_key"] for r in spec["dimension_references"].values())
        if fact[required].isna().any().any():
            errors.append(f"{name}: required fields contain blanks")
        for dim_name, ref in spec["dimension_references"].items():
            fk = ref["foreign_key"]
            dim_key = cfg.DIMENSION_CONFIG[dim_name]["surrogate_key"]
            if not fact[fk].isin(tables[dim_name][dim_key]).all():
                errors.append(f"{name}.{fk}: orphan foreign keys")
    if errors:
        raise DataValidationError("Final integrity checks failed:\n- " + "\n- ".join(errors))

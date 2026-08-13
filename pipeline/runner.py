"""Orchestration layer for one or many source workbooks."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import pandas as pd
import config
from .cleaning import clean_dataframe
from .dimensions import process_dimension, resolve_dimension_keys
from .facts import build_fact_table, create_date_dimension
from .logging_setup import configure_logging, generate_processing_log
from .storage import (backup_master_files, inspect_source, load_master_table, load_source_file,
                      save_master_tables, save_rejected_rows)
from .utils import ensure_folders, file_sha256, load_id as make_load_id
from .validation import validate_integrity, validate_rows, validate_schema

def table_columns(cfg=config) -> dict[str, list[str]]:
    """Derive stable persisted schemas solely from configuration."""
    schemas = {}
    for name, spec in cfg.DIMENSION_CONFIG.items():
        schemas[name] = [spec["surrogate_key"], *spec["columns"], "Created_Date", "Updated_Date"]
    for name, spec in cfg.FACT_CONFIG.items():
        schemas[name] = [spec["surrogate_key"], *spec["columns"], *cfg.AUDIT_COLUMNS]
    schemas["Load_History"] = cfg.LOAD_HISTORY_COLUMNS
    return schemas

def run_file(source_path: Path, cfg=config) -> dict:
    """Process one workbook in memory and commit only after integrity checks."""
    precise_now = pd.Timestamp.now()
    now = precise_now.floor("s")
    identifier = make_load_id(precise_now.to_pydatetime())
    stamp = now.strftime("%Y-%m-%d_%H%M%S") + "_" + identifier[-6:]
    logger = configure_logging(cfg.LOG_FOLDER, identifier)
    schemas = table_columns(cfg)
    try:
        logger.info("Source detected: %s", source_path.name)
        headers = inspect_source(source_path, cfg.SOURCE_SHEET)
        validate_schema(headers, cfg)
        file_hash = file_sha256(source_path)
        history = load_master_table(cfg.MASTER_FOLDER / cfg.LOAD_HISTORY_FILE, schemas["Load_History"])
        if cfg.SKIP_PREVIOUSLY_SUCCESSFUL_HASHES and not history.empty:
            already = history["File_Hash"].eq(file_hash) & history["Status"].eq("SUCCESS")
            if already.any():
                logger.info("Skipped already-successful file hash: %s", source_path.name)
                return {"status": "SKIPPED", "load_id": identifier, "source": source_path.name}
        raw = load_source_file(source_path, cfg.SOURCE_SHEET)
        raw["Source_File"] = source_path.name
        cleaned, conversion_errors = clean_dataframe(raw, cfg)
        valid, rejected = validate_rows(cleaned, conversion_errors, cfg)
        rejected["Source_File"] = source_path.name

        tables: dict[str, pd.DataFrame] = {}
        lookups, dim_metrics = {}, {}
        for name, spec in cfg.DIMENSION_CONFIG.items():
            master = load_master_table(cfg.MASTER_FOLDER / f"{name}.xlsx", schemas[name])
            tables[name], lookups[name], dim_metrics[name] = process_dimension(valid, master, spec, now)
        resolved = resolve_dimension_keys(valid, lookups, cfg.DIMENSION_CONFIG, next(iter(cfg.FACT_CONFIG.values())))
        resolved["Date_Key"] = resolved[cfg.DATE_COLUMNS[0]].dt.strftime("%Y%m%d").astype("Int64")
        fact_metrics = {}
        for name, spec in cfg.FACT_CONFIG.items():
            master = load_master_table(cfg.MASTER_FOLDER / f"{name}.xlsx", schemas[name])
            # Excel round-trips dates as Python datetime objects while freshly
            # cleaned sources use pandas datetime64. Normalize before keying so
            # their textual composite-key representations are identical.
            for date_column in cfg.DATE_COLUMNS:
                if date_column in master.columns and not master.empty:
                    master[date_column] = pd.to_datetime(master[date_column], errors="raise").dt.normalize()
            tables[name], fact_metrics[name] = build_fact_table(
                resolved, master, spec, source_path.name, identifier, now, cfg.DUPLICATE_STRATEGY
            )
        if cfg.ENABLE_DATE_DIMENSION:
            tables["Dim_Date"] = create_date_dimension(cfg.DATE_START, cfg.DATE_END)

        stat = source_path.stat()
        history_row = pd.DataFrame([{
            "Load_ID": identifier, "File_Name": source_path.name, "File_Size": stat.st_size,
            "File_Modified_Date": pd.Timestamp(stat.st_mtime, unit="s"), "File_Hash": file_hash,
            "Load_Date": now, "Rows_Processed": len(raw), "Rows_Accepted": len(valid),
            "Rows_Rejected": len(rejected), "Status": "SUCCESS",
        }])
        tables["Load_History"] = pd.concat([history, history_row], ignore_index=True)[schemas["Load_History"]]
        validate_integrity(tables, cfg)
        # Load history itself changes for every non-hash-skipped successful load,
        # even when every incoming fact is a duplicate.
        backup_master_files(cfg.MASTER_FOLDER, cfg.ARCHIVE_FOLDER, stamp, list(tables))
        save_master_tables(tables, cfg.MASTER_FOLDER)
        rejected_path = save_rejected_rows(rejected, cfg.REJECTED_FOLDER, stamp)
        summary = generate_processing_log(identifier, source_path.name, len(raw), len(valid), len(rejected), dim_metrics, fact_metrics)
        logger.info("\n%s", summary)
        return {"status": "SUCCESS", "load_id": identifier, "dimensions": dim_metrics,
                "facts": fact_metrics, "rejected": len(rejected), "rejected_path": rejected_path}
    except Exception:
        logger.exception("PROCESS FAILED for %s", source_path)
        raise

def run_all(cfg=config) -> list[dict]:
    """Process all input workbooks in deterministic filename order."""
    ensure_folders([cfg.INPUT_FOLDER, cfg.MASTER_FOLDER, cfg.ARCHIVE_FOLDER,
                    cfg.REJECTED_FOLDER, cfg.LOG_FOLDER])
    files = sorted(cfg.INPUT_FOLDER.glob("*.xlsx"))
    if not files:
        raise FileNotFoundError(f"No .xlsx source files found in {cfg.INPUT_FOLDER}")
    if not cfg.PROCESS_ALL_FILES:
        files = files[:1]
    return [run_file(path, cfg) for path in files]

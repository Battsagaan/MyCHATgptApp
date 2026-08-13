"""Application logging and human-readable summary generation."""
from __future__ import annotations
import logging
from pathlib import Path

def configure_logging(folder: Path, load_id: str) -> logging.Logger:
    folder.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("excel_data_pipeline")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(folder / f"{load_id}.log", encoding="utf-8")
    stream_handler = logging.StreamHandler()
    for handler in (file_handler, stream_handler):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

def generate_processing_log(load_id: str, source: str, source_rows: int, valid: int,
                            rejected: int, dimensions: dict, facts: dict, status="SUCCESS") -> str:
    lines = ["=" * 50, "ETL PROCESS SUMMARY", "=" * 50, f"Load ID: {load_id}",
             f"Source file: {source}", "", f"Source rows: {source_rows:,}",
             f"Valid rows: {valid:,}", f"Rejected rows: {rejected:,}", "", "DIMENSIONS"]
    lines.extend(f"{name}: +{m['new']} new / {m['updated']} updated / {m['existing']} unchanged"
                 for name, m in dimensions.items())
    lines.extend(["", "FACT TABLE"])
    lines.extend(f"{name}: +{m['new']} new / {m['duplicates']} duplicates skipped" for name, m in facts.items())
    lines.extend(["", f"Processing status: {status}", "=" * 50])
    return "\n".join(lines)


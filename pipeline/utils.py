"""Small reusable utilities."""
from __future__ import annotations
import hashlib
from datetime import datetime
from pathlib import Path

def ensure_folders(paths: list[Path]) -> None:
    """Create application directories when missing."""
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)

def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return a streaming SHA-256 digest without loading the entire file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_id(now: datetime | None = None) -> str:
    """Create a readable, collision-resistant load identifier."""
    return (now or datetime.now()).strftime("LOAD_%Y%m%d_%H%M%S_%f")

def composite_key(frame, columns: list[str]):
    """Create stable tuple keys; suitable for vectorized membership operations."""
    return frame[columns].astype("string").fillna("<NULL>").agg("\x1f".join, axis=1)


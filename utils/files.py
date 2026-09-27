from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(
    destination: str | Path,
    content: str,
    *,
    mode: int = 0o600,
    overwrite: bool = False,
) -> Path:
    destination = Path(destination)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, destination)
        return destination
    finally:
        if temporary and temporary.exists():
            temporary.unlink()

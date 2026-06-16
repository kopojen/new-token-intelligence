from __future__ import annotations

from pathlib import Path
import os


def load_dotenv(path: str | Path = ".env.local") -> None:
    dotenv_path = Path(path)
    if not dotenv_path.exists():
        return
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Local workspace secrets should override stale inherited env vars.
        os.environ[key] = value

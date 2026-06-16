from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_STATE: dict[str, Any] = {
    "updated_at": "",
    "cycle": {},
    "signals": [],
    "top_gainers": [],
    "announcements": [],
    "errors": [],
}


def load_runtime_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return deepcopy(DEFAULT_RUNTIME_STATE)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return deepcopy(DEFAULT_RUNTIME_STATE)
    state = deepcopy(DEFAULT_RUNTIME_STATE)
    state.update(payload)
    return state


def write_runtime_state(state: dict[str, Any], path: str | Path) -> Path:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state_path

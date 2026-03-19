r"""
fp_soother_util.presets
========================
Persists saved "preset" slots per device -- a snapshot of SootherState field
values a user can save and later re-send in one shot via
SootherClient.send_preset().

Stored in an OS-appropriate user data directory by default (e.g.
~/Library/Application Support/fp-soother on macOS, %LOCALAPPDATA%\fp-soother
on Windows, ~/.local/share/fp-soother on Linux), keyed by device address then
slot number.
"""

from __future__ import annotations

import json
from pathlib import Path

from platformdirs import user_data_dir

DEFAULT_PRESETS_STORE_PATH = Path(user_data_dir("fp-soother")) / "presets.json"


def _load_all(store_path: Path) -> dict:
    if not store_path.exists():
        return {}
    try:
        return json.loads(store_path.read_text())
    except json.JSONDecodeError, OSError:
        return {}


def save_preset(
    address: str,
    slot: int,
    values: dict[str, int],
    store_path: Path = DEFAULT_PRESETS_STORE_PATH,
) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    devices = _load_all(store_path)
    devices.setdefault(address, {})[str(slot)] = values
    store_path.write_text(json.dumps(devices, indent=2))


def load_preset(
    address: str, slot: int, store_path: Path = DEFAULT_PRESETS_STORE_PATH
) -> dict[str, int] | None:
    devices = _load_all(store_path)
    return devices.get(address, {}).get(str(slot))


def list_presets(
    address: str, store_path: Path = DEFAULT_PRESETS_STORE_PATH
) -> dict[int, dict[str, int]]:
    """Return all saved preset slots for *address* as {slot: values}."""
    devices = _load_all(store_path)
    return {int(slot): values for slot, values in devices.get(address, {}).items()}

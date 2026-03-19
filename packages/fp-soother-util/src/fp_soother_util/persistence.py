r"""
fp_soother_util.persistence
============================
Persists session keys for paired devices so callers can reconnect without
re-pairing each time.

Stored in an OS-appropriate user data directory by default (e.g.
~/Library/Application Support/fp-soother on macOS, %LOCALAPPDATA%\fp-soother
on Windows, ~/.local/share/fp-soother on Linux).
"""

from __future__ import annotations

import json
from pathlib import Path

from platformdirs import user_data_dir

DEFAULT_STORE_PATH = Path(user_data_dir("fp-soother")) / "paired_devices.json"


def _load_all(store_path: Path) -> dict:
    if not store_path.exists():
        return {}
    try:
        return json.loads(store_path.read_text())
    except json.JSONDecodeError, OSError:
        return {}


def save_paired_device(
    address: str,
    peripheral_type: int,
    session_key: bytes,
    store_path: Path = DEFAULT_STORE_PATH,
) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    devices = _load_all(store_path)
    devices[address] = {
        "peripheral_type": peripheral_type,
        "session_key": session_key.hex(),
    }
    store_path.write_text(json.dumps(devices, indent=2))


def load_paired_device(
    address: str, store_path: Path = DEFAULT_STORE_PATH
) -> tuple[int, bytes] | None:
    devices = _load_all(store_path)
    entry = devices.get(address)
    if entry is None:
        return None
    return entry["peripheral_type"], bytes.fromhex(entry["session_key"])


def list_paired_devices(
    store_path: Path = DEFAULT_STORE_PATH,
) -> dict[str, tuple[int, bytes]]:
    """Return all paired devices as {address: (peripheral_type, session_key)}."""
    devices = _load_all(store_path)
    return {
        address: (entry["peripheral_type"], bytes.fromhex(entry["session_key"]))
        for address, entry in devices.items()
    }


def forget_paired_device(address: str, store_path: Path = DEFAULT_STORE_PATH) -> None:
    devices = _load_all(store_path)
    if address in devices:
        devices.pop(address, None)
        store_path.write_text(json.dumps(devices, indent=2))

"""Shared utilities for fp-soother packages."""

from importlib.metadata import version

from .persistence import (
    DEFAULT_STORE_PATH,
    forget_paired_device,
    list_paired_devices,
    load_paired_device,
    save_paired_device,
)
from .presets import (
    DEFAULT_PRESETS_STORE_PATH,
    list_presets,
    load_preset,
    save_preset,
)

__all__ = [
    "DEFAULT_PRESETS_STORE_PATH",
    "DEFAULT_STORE_PATH",
    "forget_paired_device",
    "list_paired_devices",
    "list_presets",
    "load_paired_device",
    "load_preset",
    "save_paired_device",
    "save_preset",
]

__version__ = version("fp-soother-util")

"""
fp_soother_lib.exceptions
==========================
Library-specific exception hierarchy.
"""


class SootherError(Exception):
    """Base class for all fp_soother_lib errors."""


class SootherNotFoundError(SootherError):
    """Raised when the soother cannot be found during a BLE scan."""


class SootherConnectionError(SootherError):
    """Raised when a BLE connection attempt fails or is dropped."""


class SootherCommandError(SootherError):
    """Raised when a command cannot be sent (e.g. characteristic not writable,
    or unknown UUID because protocol has not yet been fully reverse-engineered)."""

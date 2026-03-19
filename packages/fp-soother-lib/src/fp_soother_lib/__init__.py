"""
Fisher-Price Smart Connect Deluxe Soother — Python BLE Library
==============================================================

Pairs and controls the device over raw BLE -- no official app or cloud
account needed.

Quick start
-----------
import asyncio
from fp_soother_lib import SootherClient

async def main():
    async with SootherClient.connect("AA:BB:CC:DD:EE:FF") as soother:
        if not soother.is_paired:
            await soother.pair()  # device must already be in pairing mode
        await soother.set_nightlight(True)
        print(soother.state)

asyncio.run(main())

Package layout
--------------
fp_soother_lib/
  constants.py    ← UUIDs, command IDs, state bit-layout tables
  encryption.py   ← real AES-128-CBC crypto + key derivation
  protocol.py     ← SootherState + command-frame construction
  pairing.py      ← the from-scratch pairing handshake
  client.py       ← high-level async client (the main entry point)
  scanner.py      ← BLE discovery & GATT-dump helpers
  exceptions.py   ← library-specific exceptions
"""

from importlib.metadata import version

from bleak.backends.device import BLEDevice

from .client import SootherClient
from .exceptions import (
    SootherCommandError,
    SootherConnectionError,
    SootherError,
    SootherNotFoundError,
)
from .protocol import SootherState
from .scanner import dump_gatt, find_soother, scan

__all__ = [
    "BLEDevice",
    "SootherClient",
    "SootherCommandError",
    "SootherConnectionError",
    "SootherError",
    "SootherNotFoundError",
    "SootherState",
    "dump_gatt",
    "find_soother",
    "scan",
]

__version__ = version("fp-soother-lib")

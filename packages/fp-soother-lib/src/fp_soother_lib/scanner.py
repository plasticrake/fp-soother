"""
fp_soother_lib.scanner
=======================
BLE discovery and GATT enumeration helpers. See fp-soother-cli's ``scan`` and
``dump-gatt`` commands for a command-line wrapper around these.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError

from .constants import SERVICE_UUID
from .exceptions import SootherNotFoundError


def _is_soother(device: BLEDevice, adv: AdvertisementData) -> bool:
    """A Deluxe Soother advertises its real SmartConnect service UUID
    directly in the advertisement's service UUID list."""
    uuids = [u.lower() for u in (adv.service_uuids or [])]
    return SERVICE_UUID.lower() in uuids


async def scan(
    timeout: float = 10.0,
    *,
    all_devices: bool = False,
    callback: Callable[[BLEDevice, AdvertisementData], None] | None = None,
) -> list[tuple[BLEDevice, AdvertisementData]]:
    """Scan for BLE devices and return matches.

    If provided, ``callback`` is called for each matching advertisement.
    """
    results: list[tuple[BLEDevice, AdvertisementData]] = []

    def on_advertisement(device: BLEDevice, adv: AdvertisementData) -> None:
        if all_devices or _is_soother(device, adv):
            results.append((device, adv))
            if callback is not None:
                callback(device, adv)

    scanner = BleakScanner(on_advertisement)
    print(f"[scanner] Scanning for {timeout}s …")
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()

    return results


def _write_dump_file(output_file: str, dump: str) -> None:
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(dump)


async def dump_gatt(address: str, *, output_file: str | None = None) -> str:
    """Connect to a BLE device and return a formatted GATT service/characteristic dump."""
    lines: list[str] = []
    lines.extend((f"GATT dump — {address}", "=" * 60))

    async with BleakClient(address) as client:
        lines.extend((f"Connected:  {client.is_connected}", ""))

        for service in client.services:
            lines.append(f"SERVICE  {service.uuid}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                lines.append(f"  CHAR   {char.uuid}  [{props}]")
                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char.uuid)
                        lines.append(f"         value: {value.hex()}")
                    except (BleakError, TimeoutError, OSError) as exc:
                        lines.append(f"         read failed: {exc}")
            lines.append("")

    dump = "\n".join(lines)
    if output_file:
        await asyncio.to_thread(_write_dump_file, output_file, dump)
        print(f"[scanner] GATT dump saved to {output_file}")
    return dump


async def find_soother(timeout: float = 10.0) -> tuple[BLEDevice, AdvertisementData]:
    """Scan and return the first soother found."""
    results = await scan(timeout=timeout)
    if not results:
        raise SootherNotFoundError(
            f"No soother found after {timeout}s scan. It may need to be in "
            "pairing mode to advertise, or try all_devices=True to see everything nearby."
        )
    return results[0]

"""
examples/basic_usage.py
=======================
Example usage of fp_soother_lib against a real Fisher-Price Deluxe Soother.

Put the device in its own pairing mode (hold its pairing button) before the
very first connection to derive a session key, which can be passed to future
SootherClient connections.
"""

import argparse
import asyncio
import logging

from fp_soother_lib import SootherClient

logging.basicConfig(level=logging.INFO)


async def demo_pair_and_control(device_address, session_key: bytes | None = None):
    """First-time pairing, then basic control. Safe to run again later --
    if a session_key is passed, pairing is skipped.
    """

    async with SootherClient.connect(
        device_address, session_key=session_key
    ) as soother:
        if not soother.is_paired:
            print(
                "Not paired yet -- put the device in pairing mode now, then press Enter."
            )
            await asyncio.to_thread(input)
            print("Pairing...")
            await soother.pair()
            print("Paired! (the device's pairing chime should have just stopped)")
            print(
                f"Derived session key: {soother.session_key.hex() if soother.session_key else 'None'}"
            )
        else:
            print("Already paired -- using the provided session key.")

        state = await soother.refresh_state()
        print("Current state:", state)

        print("Turning the nightlight on...")
        await soother.set_nightlight(True)
        await asyncio.sleep(2)

        print("Setting volume to 8 (of 0-15)...")
        await soother.set_volume(8)
        await asyncio.sleep(1)

        print("Turning the nightlight back off...")
        await soother.set_nightlight(False)

        print("Final state:", soother.state)


async def demo_auto_discover():
    """Let the library scan (by the device's real BLE service UUID) and
    auto-connect to the first soother found, instead of a hardcoded address."""
    async with SootherClient.connect() as soother:
        print("Auto-connected to soother at", soother.address)
        if soother.is_paired:
            await soother.set_nightlight(True)


async def demo_state_watch(device_address):
    """Register a callback that fires on every refreshed state read."""

    def on_state(state):
        print(
            "  STATE UPDATE: nightlight =",
            state.nightlight_mode,
            " volume =",
            state.volume_level,
        )

    async with SootherClient.connect(device_address) as soother:
        soother.on_state_change(on_state)
        for _ in range(3):
            await soother.refresh_state()
            await asyncio.sleep(2)


async def demo_raw_exploration(device_address):
    """
    Escape hatches for anything not covered by the named set_*() methods --
    e.g. an attribute this library doesn't expose a dedicated method for yet.
    See fp_soother_lib/constants.py for the full list of command IDs and its
    STATE_ATTRS table for their value ranges.
    """
    from fp_soother_lib.constants import (
        CHAR_AUX_STATE,
        CMD_ANIMAL_PROJECTION_SPEED,
    )

    async with SootherClient.connect(device_address) as soother:
        raw = await soother.read_raw(CHAR_AUX_STATE)
        print("Raw auxState bytes:", raw.hex())

        # send_raw_command still goes through the real encrypt/rolling-token
        # pipeline -- it's just not wrapped in a named method.
        await soother.send_raw_command(CMD_ANIMAL_PROJECTION_SPEED, 2)
        print("State after raw command:", soother.state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Control a Fisher-Price Deluxe Soother"
    )
    parser.add_argument(
        "device_address",
        nargs="?",
        help="Bluetooth address or macOS device UUID; omit to auto-discover",
    )
    args = parser.parse_args()
    if args.device_address:
        asyncio.run(demo_pair_and_control(args.device_address))
    else:
        asyncio.run(demo_auto_discover())

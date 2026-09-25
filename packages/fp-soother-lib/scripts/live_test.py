"""
scripts/live_test.py
====================
Live hardware check for fp_soother_lib: connects to one or more real soothers
and exercises every safe setter over a single connection per device.

For each setting it changes the value, confirms the device reports the new
value, notes any other field that changed alongside it, then restores every
field to where it was. It also checks custom star colors, CMD_PRESET,
rtcUpdate and CHAR_STATE notifications, and finally compares the end state
to the start.

Firmware 9+ (unique-key) devices need a session key. Pass --pair (with the
device in its own pairing mode) to pair and save the key to the .env file;
later runs load it from there. Firmware 8 and older (shared-key) devices need
no key.

Usage (from the repository root):

    uv run --package fp-soother-lib python packages/fp-soother-lib/scripts/live_test.py ADDRESS [ADDRESS ...]
    uv run --package fp-soother-lib python packages/fp-soother-lib/scripts/live_test.py ADDRESS --pair

Settings that make sound (volume, sound mode and sleep stages) are only
tested with --audible.

Addresses can be real MAC addresses (e.g. 00:22:AE:0A:51:78) even on macOS,
where they are resolved with a scan; otherwise use bleak's per-host UUIDs.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from bleak import BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from fp_soother_lib import SootherClient, SootherError, SootherState
from fp_soother_lib.constants import (
    ANIMAL_PROJECTION_MODES,
    ANIMAL_PROJECTION_SPEEDS,
    SLEEP_STAGE_TIMER_DURATIONS,
    SLEEP_STAGES_MODES,
    SLEEP_TIMER_DURATIONS,
    SOUND_MODES,
    STAR_PROJECTION_SEQUENCES,
    STAR_PROJECTION_SPEEDS,
    TIMER_DURATIONS,
)

DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Fields that change on their own or follow other fields, so they are left
# out of side-effect reports and end-state comparisons.
VOLATILE_FIELDS = {
    # The device raises play_mode whenever an output comes on; the real app
    # only reads it, so the script neither tests nor restores it.
    "play_mode",
    "transmission_mode",
    "sound_mode_expiring",
    "led_expiring",
    "firmware_upgrade_status",
    "previous_animal_projection_mode",
    "previous_star_projection_sequence_mode",
}
AUX_FIELDS = (
    "captive_sleep_stage_timer",
    "soothe_sleep_stage_timer",
    "sleep_stage_timer",
)
STATE_FIELDS = tuple(SootherState._ATTR_MAP.values()) + AUX_FIELDS


# ── .env key storage ─────────────────────────────────────────────────────────


def _env_name(address: str) -> str:
    return "SOOTHER_KEY_" + re.sub(r"[^A-Z0-9]", "_", address.upper())


def load_key(env_file: Path, address: str) -> bytes | None:
    if not env_file.exists():
        return None
    name = _env_name(address)
    for line in env_file.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == name:
            return bytes.fromhex(value.strip().strip("\"'"))
    return None


def save_key(env_file: Path, address: str, session_key: bytes) -> None:
    name = _env_name(address)
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    lines = [line for line in lines if line.partition("=")[0].strip() != name]
    lines.append(f"{name}={session_key.hex()}")
    env_file.write_text("\n".join(lines) + "\n")


# ── Checks ───────────────────────────────────────────────────────────────────


@dataclass
class Result:
    name: str
    status: str  # PASS, FAIL, SKIP
    detail: str = ""


class CountingClient(SootherClient):
    """Counts real CHAR_STATE notifications (refresh_state() also fires
    on_state_change callbacks, so those can't be used to count them)."""

    notifications = 0

    def _on_state_notification(
        self, _char: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        self.notifications += 1
        super()._on_state_notification(_char, data)


@dataclass
class Setting:
    field: str
    apply: Callable[[SootherClient, int], Awaitable[None]]
    values: list[int]
    # Restore order: plain settings (1) before the output toggles they can
    # switch on (2). The device turns an output on when its brightness/volume
    # changes, so the toggle must be restored after.
    order: int = 1
    audible: bool = False


def _setter(name: str) -> Callable[[SootherClient, int], Awaitable[None]]:
    return lambda client, value: getattr(client, name)(value)


# Value ranges come from App.md (the real app's controls). The raw bit widths
# allow larger values that the device doesn't use.
SETTINGS = [
    Setting("nightlight_mode", lambda c, v: c.set_nightlight(bool(v)), [0, 1], order=2),
    Setting("nightlight_brightness", _setter("set_nightlight_brightness"), list(range(1, 8))),
    Setting("animal_projection_mode", _setter("set_animal_projection_mode"), [0, *ANIMAL_PROJECTION_MODES.values()], order=2),
    Setting("animal_projection_brightness", _setter("set_animal_projection_brightness"), list(range(1, 11))),
    Setting("animal_projection_speed", _setter("set_animal_projection_speed"), list(ANIMAL_PROJECTION_SPEEDS.values())),
    Setting("star_projection_sequence_mode", _setter("set_star_projection_sequence_mode"), [0, *STAR_PROJECTION_SEQUENCES.values()], order=2),
    Setting("star_projection_brightness", _setter("set_star_projection_brightness"), list(range(1, 7))),
    Setting("star_projection_speed", _setter("set_star_projection_speed"), list(STAR_PROJECTION_SPEEDS.values())),
    Setting("sound_timer_setting", _setter("set_sound_timer"), list(TIMER_DURATIONS.values())),
    Setting("light_timer", _setter("set_light_timer"), list(TIMER_DURATIONS.values())),
    Setting("captive_playlist_selection", _setter("set_captive_playlist_selection"), list(range(1, 32))),
    Setting("soothe_playlist_selection", _setter("set_soothe_playlist_selection"), list(range(1, 32))),
    Setting("captive_sleep_stage_timer", _setter("set_captive_sleep_stage_timer"), list(SLEEP_STAGE_TIMER_DURATIONS.values())),
    Setting("soothe_sleep_stage_timer", _setter("set_soothe_sleep_stage_timer"), list(SLEEP_STAGE_TIMER_DURATIONS.values())),
    Setting("sleep_stage_timer", _setter("set_sleep_stage_timer"), list(SLEEP_TIMER_DURATIONS.values())),
    Setting("volume_level", _setter("set_volume"), list(range(1, 10)), audible=True),
    Setting("sound_mode", _setter("set_sound_mode"), [0, *SOUND_MODES.values()], order=2, audible=True),
    Setting("sleep_stages_mode", _setter("set_sleep_stages_mode"), list(SLEEP_STAGES_MODES.values()), order=2, audible=True),
]  # fmt: skip
COLOR_FIELDS = (
    "star_projection_custom_color0",
    "star_projection_custom_color1",
    "star_projection_custom_color2",
)


def _snapshot(state: SootherState) -> dict[str, int | None]:
    return {f: getattr(state, f) for f in STATE_FIELDS}


def _next_value(values: list[int], current: int | None) -> int:
    ordered = sorted(set(values))
    if current not in ordered:
        return ordered[0]
    return ordered[(ordered.index(current) + 1) % len(ordered)]


def _diff(before: Mapping, after: Mapping, ignore: set[str]) -> list[str]:
    return [
        f"{f} {before[f]}->{after[f]}"
        for f in STATE_FIELDS
        if f not in ignore and f not in VOLATILE_FIELDS and before[f] != after[f]
    ]


async def _await_values(
    client: SootherClient, expected: Mapping[str, int | None]
) -> bool:
    """Poll state until every field in *expected* matches (the write itself
    already re-reads state once; the device can lag a little behind)."""
    for _ in range(4):
        if all(getattr(client.state, f) == v for f, v in expected.items()):
            return True
        await asyncio.sleep(0.4)
        await client.refresh_state()
    return all(getattr(client.state, f) == v for f, v in expected.items())


async def restore_to(client: SootherClient, snapshot: Mapping) -> list[str]:
    """Put every drifted field back to *snapshot*, in dependency order:
    custom colors first (setting them switches the star projector to its
    custom sequence), then plain settings, then output toggles.
    Returns whatever still differs afterwards."""
    await client.refresh_state()
    colors = tuple(snapshot[f] for f in COLOR_FIELDS)
    if tuple(getattr(client.state, f) for f in COLOR_FIELDS) != colors:
        await client.set_star_projection_custom_colors(*colors)
    for order in (1, 2):
        for setting in SETTINGS:
            target = snapshot[setting.field]
            if setting.order != order or target is None:
                continue
            if getattr(client.state, setting.field) != target:
                await setting.apply(client, target)
    await _await_values(
        client, {f: v for f, v in snapshot.items() if f not in VOLATILE_FIELDS}
    )
    return _diff(snapshot, _snapshot(client.state), set())


async def check_change(
    client: SootherClient,
    name: str,
    expected: dict[str, int],
    change: Callable[[], Awaitable[None]],
) -> Result:
    """Apply *change*, confirm *expected* reads back, note any side effects,
    then restore every field to its value before the change."""
    before = _snapshot(client.state)
    original = {f: before[f] for f in expected}
    try:
        await change()
        ok = await _await_values(client, expected)
        after = _snapshot(client.state)
    finally:
        drift = await restore_to(client, before)
    detail = f"{original} -> {expected}"
    if not ok:
        got = {f: after[f] for f in expected}
        return Result(name, "FAIL", f"{detail}, device reported {got}")
    if drift:
        return Result(name, "FAIL", f"{detail}, restore failed: {', '.join(drift)}")
    side = _diff(before, after, set(expected))
    if side:
        detail += f" (side effects: {', '.join(side)})"
    return Result(name, "PASS", detail)


async def _guarded(name: str, check: Awaitable[Result]) -> Result:
    try:
        return await check
    except SootherError as exc:
        return Result(name, "FAIL", f"{type(exc).__name__}: {exc}")


async def run_checks(client: SootherClient, audible: bool) -> list[Result]:
    results: list[Result] = []
    state = await client.refresh_state()
    baseline = _snapshot(state)

    missing = [f for f in AUX_FIELDS if getattr(state, f) is None]
    results.append(
        Result("read state + aux", "FAIL" if missing else "PASS",
               f"aux missing: {missing}" if missing else "")
    )  # fmt: skip

    for setting in SETTINGS:
        if setting.audible and not audible:
            results.append(Result(setting.field, "SKIP", "needs --audible"))
            continue
        target = _next_value(setting.values, getattr(client.state, setting.field))
        results.append(
            await _guarded(
                setting.field,
                check_change(
                    client,
                    setting.field,
                    {setting.field: target},
                    lambda s=setting, t=target: s.apply(client, t),
                ),
            )
        )

    # Custom colors: blue (5) / purple (6) as color2 exercise the 9th bit.
    current = tuple(getattr(client.state, f) for f in COLOR_FIELDS)
    new_colors = (2, 3, 5) if current != (2, 3, 5) else (4, 1, 6)
    results.append(
        await _guarded(
            "custom colors",
            check_change(
                client,
                "custom colors",
                dict(zip(COLOR_FIELDS, new_colors, strict=True)),
                lambda: client.set_star_projection_custom_colors(*new_colors),
            ),
        )
    )

    # CMD_PRESET: one silent override, everything else resent as-is.
    new_timer = _next_value(list(TIMER_DURATIONS.values()), client.state.light_timer)
    results.append(
        await _guarded(
            "preset (light_timer override)",
            check_change(
                client,
                "preset (light_timer override)",
                {"light_timer": new_timer},
                lambda: client.send_preset(light_timer=new_timer),
            ),
        )
    )

    try:
        await client.send_rtc_update()
        results.append(Result("rtcUpdate", "PASS"))
    except SootherError as exc:
        results.append(Result("rtcUpdate", "FAIL", f"{type(exc).__name__}: {exc}"))

    await asyncio.sleep(1)
    notifications = client.notifications if isinstance(client, CountingClient) else 0
    results.append(
        Result("state notifications", "PASS" if notifications else "FAIL",
               f"{notifications} received")
    )  # fmt: skip

    leftover = await restore_to(client, baseline)
    results.append(
        Result("end state matches start", "FAIL" if leftover else "PASS",
               ", ".join(leftover))
    )  # fmt: skip
    return results


# ── Driver ───────────────────────────────────────────────────────────────────


MAC_ADDRESS = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")


async def _resolve_mac_on_macos(address: str) -> BLEDevice | None:
    """CoreBluetooth hides real MAC addresses behind per-host UUIDs, so a MAC
    can't be passed to SootherClient directly on macOS. Scan with bleak's
    use_bdaddr option (which reports real MACs) and hand SootherClient the
    resulting BLEDevice instead."""
    if sys.platform != "darwin" or not MAC_ADDRESS.match(address):
        return None
    device = await BleakScanner.find_device_by_address(
        address, timeout=20, cb={"use_bdaddr": True}
    )
    if device is None:
        raise SootherError(f"Could not find a BLE device advertising at {address}")
    return device


async def connect_with_retry(address: str, session_key: bytes | None) -> CountingClient:
    """Some firmware stops advertising for a while after a disconnect, so a
    single scan can miss it."""
    last: Exception | None = None
    for attempt in range(1, 6):
        try:
            client = CountingClient(
                address,
                session_key=session_key,
                ble_device=await _resolve_mac_on_macos(address),
                scan_timeout=20,
            )
            await client.open()
            return client
        except (SootherError, BleakError) as exc:
            last = exc
            print(f"  connect attempt {attempt} failed: {exc}")
            await asyncio.sleep(5)
    raise SootherError(f"could not connect to {address}: {last}")


async def test_device(address: str, args: argparse.Namespace) -> list[Result]:
    print(f"\n== {address}")
    client = await connect_with_retry(address, load_key(args.env_file, address))
    try:
        s = client.state
        mode = "shared-key" if client.uses_shared_key else "unique-key"
        print(f"  firmware {s.firmware_version} (api {s.firmware_api_level}), {mode}")
        if not client.is_paired:
            if not args.pair:
                return [Result("session key", "SKIP",
                               f"none in {args.env_file}; rerun with --pair")]  # fmt: skip
            await asyncio.to_thread(
                input, "  Put the device in pairing mode, then press Enter... "
            )
            await client.pair()
        elif args.pair and client.uses_shared_key:
            await client.pair()  # no handshake; exercises the clock-sync path
        if not client.uses_shared_key and client.session_key is not None:
            save_key(args.env_file, address, client.session_key)
        return await run_checks(client, args.audible)
    finally:
        await client.close()


def print_results(address: str, results: list[Result]) -> None:
    print(f"\n-- {address}")
    for r in results:
        print(f"  {r.status:4}  {r.name}" + (f": {r.detail}" if r.detail else ""))
    counts = {k: sum(r.status == k for r in results) for k in ("PASS", "FAIL", "SKIP")}
    print("  " + ", ".join(f"{v} {k.lower()}" for k, v in counts.items()))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("addresses", nargs="+", help="BLE address(es) to test")
    parser.add_argument(
        "--pair", action="store_true", help="pair devices that have no saved key"
    )
    parser.add_argument(
        "--audible", action="store_true", help="also test settings that make sound"
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"session key store (default {DEFAULT_ENV_FILE})",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args()  # fmt: skip
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    all_results: dict[str, list[Result]] = {}
    for address in args.addresses:
        try:
            all_results[address] = await test_device(address, args)
        except SootherError as exc:
            all_results[address] = [Result("connect", "FAIL", str(exc))]
        # Give the device time to advertise again before the next one.
        await asyncio.sleep(2)

    for address, results in all_results.items():
        print_results(address, results)
    failed = any(r.status == "FAIL" for rs in all_results.values() for r in rs)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

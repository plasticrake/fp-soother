"""
fp_soother_cli.cli
===================
Command-line interface for fp-soother-lib.

Usage
-----
fp-soother-cli scan
fp-soother-cli dump-gatt AA:BB:CC:DD:EE:FF
fp-soother-cli pair AA:BB:CC:DD:EE:FF
fp-soother-cli status AA:BB:CC:DD:EE:FF
fp-soother-cli set nightlight AA:BB:CC:DD:EE:FF on
fp-soother-cli set volume AA:BB:CC:DD:EE:FF 8
"""
# spellchecker:words coro

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

import click
from fp_soother_lib import (
    SootherClient,
    SootherCommandError,
    SootherConnectionError,
    SootherNotFoundError,
    dump_gatt,
    find_soother,
    scan,
)
from fp_soother_util import (
    forget_paired_device,
    load_paired_device,
    save_paired_device,
)

ADDRESS_ARG = click.argument("address", required=False, default=None)


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        return asyncio.run(coro)
    except (SootherConnectionError, SootherCommandError, SootherNotFoundError) as exc:
        raise click.ClickException(str(exc)) from exc


async def _with_client(
    address: str | None, fn: Callable[[SootherClient], Awaitable[None]]
) -> None:
    if address is None:
        device, _ = await find_soother()
        address = device.address
    saved = load_paired_device(address)
    session_key = saved[1] if saved is not None else None
    async with SootherClient.connect(address, session_key=session_key) as client:
        await fn(client)


def _print_state(client: SootherClient) -> None:
    state = client.state
    for field in dataclasses.fields(state):
        if field.name.startswith("_"):
            continue
        click.echo(f"{field.name}: {getattr(state, field.name)}")


@click.group()
def main() -> None:
    """Control a Fisher-Price Smart Connect Deluxe Soother over BLE."""


@main.command(name="scan")
@click.option("--timeout", type=float, default=10.0, help="Scan duration in seconds.")
@click.option("--all", "all_devices", is_flag=True, help="Show all BLE devices.")
def scan_cmd(timeout: float, all_devices: bool) -> None:
    """Scan for nearby soothers."""

    async def run() -> list:
        return await scan(timeout=timeout, all_devices=all_devices)

    results = _run(run())
    if not results:
        click.echo("No devices found.")
        return
    for device, adv in results:
        click.echo(f"Name:    {device.name or '(unknown)'}")
        click.echo(f"Address: {device.address}")
        click.echo(f"RSSI:    {adv.rssi} dBm")
        for uuid in adv.service_uuids or []:
            click.echo(f"SvcUUID: {uuid}")
        click.echo()


@main.command("dump-gatt")
@click.argument("address")
@click.option(
    "--output", "output_file", type=click.Path(), help="Write dump to this file."
)
def dump_gatt_cmd(address: str, output_file: str | None) -> None:
    """Connect to ADDRESS and print its full GATT table."""
    dump = _run(dump_gatt(address, output_file=output_file))
    click.echo(dump)


@main.command()
@ADDRESS_ARG
def pair(address: str | None) -> None:
    """Pair with a device already in its own pairing mode."""

    async def run() -> None:
        async def do_pair(client: SootherClient) -> None:
            await client.pair()
            if client.session_key is not None:
                save_paired_device(
                    client.address, client.peripheral_type, client.session_key
                )
            click.echo(f"Paired with {client.address}.")

        await _with_client(address, do_pair)

    _run(run())


@main.command()
@click.argument("address")
def forget(address: str) -> None:
    """Remove a device's saved session key."""
    forget_paired_device(address)
    click.echo(f"Forgot {address}.")


@main.command()
@ADDRESS_ARG
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def status(address: str | None, as_json: bool) -> None:
    """Read and print the device's current state."""

    async def run() -> None:
        async def do_status(client: SootherClient) -> None:
            await client.refresh_state()
            if as_json:
                data = {
                    f.name: getattr(client.state, f.name)
                    for f in dataclasses.fields(client.state)
                    if not f.name.startswith("_") and f.name != "raw_state"
                }
                click.echo(json.dumps(data, indent=2))
            else:
                _print_state(client)

        await _with_client(address, do_status)

    _run(run())


@main.group()
def set() -> None:
    """Change a setting on the device."""


def _set_command(
    name: str, apply: Callable[[SootherClient, int], Awaitable[None]], help_text: str
) -> None:
    @click.argument("address")
    @click.argument("value", type=int)
    def cmd(address: str, value: int) -> None:
        async def run() -> None:
            async def do_set(client: SootherClient) -> None:
                await apply(client, value)
                click.echo("OK.")

            await _with_client(address, do_set)

        _run(run())

    cmd.__doc__ = help_text
    set.command(name=name)(cmd)


def _set_bool_command(
    name: str, apply: Callable[[SootherClient, bool], Awaitable[None]], help_text: str
) -> None:
    @click.argument("address")
    @click.argument("state_value", type=click.Choice(["on", "off"]))
    def cmd(address: str, state_value: str) -> None:
        async def run() -> None:
            async def do_set(client: SootherClient) -> None:
                await apply(client, state_value == "on")
                click.echo("OK.")

            await _with_client(address, do_set)

        _run(run())

    cmd.__doc__ = help_text
    set.command(name=name)(cmd)


_set_bool_command("play", SootherClient.set_play, "Start/stop playback.")
_set_bool_command(
    "nightlight", SootherClient.set_nightlight, "Turn the nightlight on/off."
)
_set_command("sound-mode", SootherClient.set_sound_mode, "Set sound preset (0-31).")
_set_command("volume", SootherClient.set_volume, "Set volume level (0-15).")
_set_command(
    "nightlight-brightness",
    SootherClient.set_nightlight_brightness,
    "Set nightlight brightness (0-7).",
)
_set_command(
    "animal-mode",
    SootherClient.set_animal_projection_mode,
    "Set animal projection mode (0-3).",
)
_set_command(
    "animal-brightness",
    SootherClient.set_animal_projection_brightness,
    "Set animal projection brightness (0-15).",
)
_set_command(
    "animal-speed",
    SootherClient.set_animal_projection_speed,
    "Set animal projection speed (0-3).",
)
_set_command(
    "star-mode",
    SootherClient.set_star_projection_sequence_mode,
    "Set star projection sequence mode (0-7).",
)
_set_command(
    "star-brightness",
    SootherClient.set_star_projection_brightness,
    "Set star projection brightness (0-7).",
)
_set_command(
    "star-speed",
    SootherClient.set_star_projection_speed,
    "Set star projection speed (0-3).",
)
_set_command(
    "sound-timer", SootherClient.set_sound_timer, "Set sound timer setting (0-15)."
)
_set_command(
    "light-timer", SootherClient.set_light_timer, "Set light timer setting (0-15)."
)


if __name__ == "__main__":
    main()

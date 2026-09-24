"""
fp_soother_lib.pairing
=======================
Pairing handshake: derives a session key for a new device over BLE alone.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from . import encryption as enc
from .constants import (
    CHAR_INFRA_STATE,
    CHAR_INFRA_UPDATE,
    CHAR_STATE,
    CHAR_STATE_UPDATE,
    NOTIFY_CHARACTERISTICS,
    PERIPHERAL_TYPE,
)
from .exceptions import SootherCommandError, SootherConnectionError
from .protocol import build_rtc_update_command

log = logging.getLogger(__name__)


async def _subscribe_all(client: BleakClient, on_state_notify) -> asyncio.Future:
    """Subscribe to every characteristic the real app subscribes to before
    doing anything else, and return a future that resolves with the
    device's key-request reply notification."""
    loop = asyncio.get_running_loop()
    reply_future: asyncio.Future = loop.create_future()

    def on_infra_update(_sender, data: bytearray):
        if not reply_future.done():
            reply_future.set_result(bytes(data))

    for uuid in NOTIFY_CHARACTERISTICS:
        callback = (
            on_state_notify
            if uuid == CHAR_STATE
            else (on_infra_update if uuid == CHAR_INFRA_UPDATE else (lambda *_: None))
        )
        try:
            await client.start_notify(uuid, callback)
        except BleakError, TimeoutError, OSError:
            pass  # some of these may not support notify on every firmware; best-effort, matches the real app's own tolerance
    return reply_future


async def _read_char(client: BleakClient, uuid: str, timeout: float = 8.0) -> bytes:
    """read_gatt_char wrapped in a timeout -- a single hung BLE read should
    fail fast and clearly rather than silently stalling the whole flow. Any
    BLE-level failure is raised as SootherConnectionError."""
    try:
        return bytes(
            await asyncio.wait_for(client.read_gatt_char(uuid), timeout=timeout)
        )
    except TimeoutError as exc:
        raise SootherConnectionError(
            f"Read of {uuid} timed out after {timeout}s"
        ) from exc
    except (BleakError, OSError) as exc:
        raise SootherConnectionError(f"Read of {uuid} failed: {exc}") from exc


async def _read_and_decrypt_state(
    client: BleakClient, key: bytes, max_attempts: int = 10
) -> bytes:
    """Read + decrypt CHAR_STATE, retrying until the device's own checksum
    passes. Required: the device briefly returns stale ciphertext right
    after a key exchange, and the real app itself retries the same way."""
    for _ in range(max_attempts):
        ct = await _read_char(client, CHAR_STATE)
        raw = enc.decrypt_state(ct, key)
        if enc.is_valid_state_decrypt(raw):
            return raw
        await asyncio.sleep(0.3)
    raise SootherConnectionError(
        f"CHAR_STATE decrypt never passed checksum after {max_attempts} attempts"
    )


async def pair(
    device: BLEDevice,
    peripheral_type: int = PERIPHERAL_TYPE,
    timeout: float = 15.0,
    *,
    ble_device_callback: Callable[[], BLEDevice] | None = None,
) -> bytes:
    """
    Pair a device: derive its real session key and complete the handshake that
    makes the firmware leave pairing mode.

    The device must already be in pairing mode (its own pairing button/
    procedure) before calling this -- this function does not trigger that.
    *device* must already be resolved by the caller (SootherClient resolves
    it once via _resolve_ble_device() rather than this function scanning for
    it separately).

    *timeout* only bounds the key-exchange reply wait below; connection
    establishment's own retry/timeout behavior is owned by
    bleak_retry_connector.establish_connection().

    Returns the 16-byte session key. Callers should persist it so future
    connections can skip pairing entirely.

    Raises SootherConnectionError if the connection or a characteristic read
    fails, SootherCommandError if the device rejects the key-request or
    rtcUpdate write (a rejected key request usually means the device is not
    in pairing mode), and TimeoutError if the device never sends its
    key-request reply within *timeout*.
    """
    try:
        # establish_connection() owns its own retry/timeout lifecycle --
        # don't wrap this in an external asyncio.wait_for/timeout on top of
        # it (cancelling a BLE connect mid-flight can leave some backends,
        # e.g. CoreBluetooth, hung instead of erroring).
        client = await establish_connection(
            BleakClient, device, device.address, ble_device_callback=ble_device_callback
        )
    except (BleakError, TimeoutError, OSError) as exc:
        raise SootherConnectionError(
            f"Failed to connect to {device.address}: {exc}"
        ) from exc

    try:
        latest_notification: dict = {}

        def on_state_notify(_sender, data: bytearray):
            latest_notification["ct"] = bytes(data)

        reply_future = await _subscribe_all(client, on_state_notify)

        # The real app always reads infrastructureState before state.
        await _read_char(client, CHAR_INFRA_STATE)

        # Shared/pairing-key decrypt of CHAR_STATE (changeCmdAuthKey=0) gives
        # us the bytes we need to derive the real changeCmdAuthKey for the
        # key-request.
        shared_key = enc.derive_pairing_key(peripheral_type)
        state_ct = await _read_char(client, CHAR_STATE)
        raw_state = enc.decrypt_state(state_ct, shared_key)
        cak = enc.change_cmd_auth_key_from_raw_state(raw_state)

        key_request = enc.build_key_request_message(cak, peripheral_type)
        try:
            await client.write_gatt_char(CHAR_INFRA_UPDATE, key_request, response=True)
        except (BleakError, TimeoutError, OSError) as exc:
            raise SootherCommandError(
                f"Device rejected the key request ({exc}); it is probably not "
                "in pairing mode"
            ) from exc

        reply = await asyncio.wait_for(reply_future, timeout=timeout)
        session_key, _key_request_key = enc.decrypt_key_request_reply(
            reply, peripheral_type
        )

        # Confirm the key actually works and get a fresh, valid raw state to
        # build the rtcUpdate command from.
        raw_state = await _read_and_decrypt_state(client, session_key)

        # The rtcUpdate command is REQUIRED here -- the device's firmware
        # specifically waits for it (not just any accepted write) before
        # leaving pairing mode. Confirmed live: substituting a different
        # command in its place leaves the pairing chime playing.
        rtc_cmd = build_rtc_update_command(raw_state)
        encrypted_rtc = enc.encrypt_command(rtc_cmd, session_key)
        try:
            await client.write_gatt_char(
                CHAR_STATE_UPDATE, encrypted_rtc, response=True
            )
        except (BleakError, TimeoutError, OSError) as exc:
            raise SootherCommandError(f"rtcUpdate write failed: {exc}") from exc

        return session_key
    finally:
        if client.is_connected:
            # Don't let a failed teardown mask the handshake's own result or
            # exception.
            try:
                await client.disconnect()
            except (BleakError, TimeoutError, OSError) as exc:
                log.debug("Error disconnecting after pairing: %s", exc)

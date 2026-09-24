"""
fp_soother_lib.client
======================
High-level async client for the Fisher-Price Smart Connect Deluxe Soother.

Example
-------
import asyncio
from fp_soother_lib import SootherClient

async def main():
    # Pass session_key if previously paired, or call .pair() on first connect.
    async with SootherClient.connect("AA:BB:CC:DD:EE:FF", session_key=key) as soother:
        if not soother.is_paired:
            await soother.pair()
        await soother.set_nightlight(True)
        print(soother.state)

asyncio.run(main())

Host-managed discovery (e.g. Home Assistant)
---------------------------------------------
A host that owns its own BLE scanner should resolve BLEDevice objects
itself and hand them to us, instead of letting us run our own scan (see
AGENTS.md for the full rationale):

client = SootherClient(address, session_key=key, ble_device_callback=my_resolver)
await client.open()
...
await client.close()

Here ``my_resolver`` is a zero-arg callable returning the host's current
best BLEDevice for *address* (e.g. Home Assistant's
``bluetooth.async_ble_device_from_address``), called fresh on every
(re)connect.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from . import encryption as enc
from .constants import (
    CHAR_AUX_STATE,
    CHAR_INFRA_STATE,
    CHAR_STATE,
    CHAR_STATE_UPDATE,
    CMD_ANIMAL_PROJECTION_BRIGHTNESS,
    CMD_ANIMAL_PROJECTION_MODE,
    CMD_ANIMAL_PROJECTION_SPEED,
    CMD_CAPTIVE_PLAYLIST_SELECTION,
    CMD_CAPTIVE_SLEEP_STAGE_TIMER,
    CMD_LIGHT_TIMER,
    CMD_NIGHTLIGHT_BRIGHTNESS,
    CMD_NIGHTLIGHT_MODE,
    CMD_PLAY_MODE,
    CMD_SLEEP_STAGE_TIMER,
    CMD_SLEEP_STAGES_MODE,
    CMD_SOOTHE_PLAYLIST_SELECTION,
    CMD_SOOTHE_SLEEP_STAGE_TIMER,
    CMD_SOUND_MODE,
    CMD_SOUND_TIMER_SETTING,
    CMD_STAR_PROJECTION_BRIGHTNESS,
    CMD_STAR_PROJECTION_SEQUENCE_MODE,
    CMD_STAR_PROJECTION_SPEED,
    CMD_VOLUME_LEVEL,
    NOTIFY_CHARACTERISTICS,
    PERIPHERAL_TYPE,
)
from .exceptions import SootherCommandError, SootherConnectionError
from .pairing import pair as pair_device
from .protocol import (
    SootherState,
    build_custom_color_sequence_command,
    build_preset_command,
    build_rtc_update_command,
    build_state_command,
    decode_aux_state,
    decode_infra_state,
    decode_state,
)
from .scanner import find_soother

log = logging.getLogger(__name__)


class SootherClient:
    """Async BLE client for the Fisher-Price Smart Connect Deluxe Soother."""

    def __init__(
        self,
        address: str,
        session_key: bytes | None = None,
        peripheral_type: int = PERIPHERAL_TYPE,
        *,
        ble_device: BLEDevice | None = None,
        ble_device_callback: Callable[[], BLEDevice] | None = None,
        scan_timeout: float = 10.0,
    ) -> None:
        self._address = address
        self._peripheral_type = peripheral_type
        self._client: BleakClient | None = None
        self._session_key: bytes | None = session_key
        # A caller that already knows how to reach the device (e.g. a Home
        # Assistant integration resolving via its own BleakScanner) can pass
        # ble_device/ble_device_callback to skip our own scan-by-address --
        # see _resolve_ble_device().
        self._ble_device = ble_device
        self._ble_device_callback = ble_device_callback
        self._scan_timeout = scan_timeout
        self._state = SootherState()
        # Serializes all BLE reads/writes for this device. Every command is a
        # read-modify-write (rolling anti-replay tokens are drawn from the
        # most recent raw state, then a fresh state is re-read afterward) --
        # without this, two concurrent commands (e.g. two UI controls changed
        # in quick succession) can interleave their reads/writes and corrupt
        # each other's rolling tokens or read a mid-transition state.
        self._io_lock = asyncio.Lock()
        self._state_callbacks: list[Callable[[SootherState], None]] = []
        self._disconnect_callbacks: list[Callable[[], None]] = []
        self._latest_notification_ct: bytes | None = None

    # ─── Connection management ────────────────────────────────────────────────

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        address: str | None = None,
        session_key: bytes | None = None,
        *,
        peripheral_type: int = PERIPHERAL_TYPE,
        scan_timeout: float = 10.0,
        ble_device: BLEDevice | None = None,
        ble_device_callback: Callable[[], BLEDevice] | None = None,
    ) -> AsyncGenerator[SootherClient]:
        """Connect to a device. If *address* is None, scans for the first
        soother found. Pass *session_key* if already paired -- call .pair()
        explicitly for a device that's never been paired (must already be in
        its own pairing mode).

        For a host that already owns BLE discovery (e.g. Home Assistant),
        pass *ble_device*/*ble_device_callback* instead of relying on our own
        scan -- see SootherClient.__init__."""
        if address is None:
            try:
                device, _ = await find_soother(timeout=scan_timeout)
            except (BleakError, OSError) as exc:
                raise SootherConnectionError(f"BLE scan failed: {exc}") from exc
            address = device.address
            ble_device = device

        instance = cls(
            address,
            session_key=session_key,
            peripheral_type=peripheral_type,
            scan_timeout=scan_timeout,
            ble_device=ble_device,
            ble_device_callback=ble_device_callback,
        )
        await instance._connect()
        try:
            yield instance
        finally:
            await instance._disconnect()

    async def _resolve_ble_device(self) -> BLEDevice:
        """Resolve the BLEDevice to connect to, for handoff to
        bleak_retry_connector.establish_connection() (which requires an
        already-resolved device, not a bare address).

        Precedence: a caller-supplied resolver callback (re-invoked on every
        call, so a host like Home Assistant can hand us its currently-best
        route to the device on each reconnect) > a caller-supplied fixed
        BLEDevice > our own scan-by-address, for plain standalone use."""
        if self._ble_device_callback is not None:
            return self._ble_device_callback()
        if self._ble_device is not None:
            return self._ble_device
        try:
            device = await BleakScanner.find_device_by_address(
                self._address, timeout=self._scan_timeout
            )
        except (BleakError, OSError) as exc:
            raise SootherConnectionError(
                f"BLE scan for {self._address} failed: {exc}"
            ) from exc
        if device is None:
            raise SootherConnectionError(
                f"Could not find a BLE device advertising at {self._address}"
            )
        return device

    async def _establish(
        self, disconnected_callback: Callable[[BleakClient], None]
    ) -> BleakClient:
        device = await self._resolve_ble_device()
        try:
            return await establish_connection(
                BleakClient,
                device,
                self._address,
                disconnected_callback=disconnected_callback,
                ble_device_callback=self._ble_device_callback,
            )
        except (BleakError, TimeoutError, OSError) as exc:
            # Covers establish_connection()'s own terminal exceptions too --
            # BleakNotFoundError/BleakOutOfConnectionSlotsError/
            # BleakAbortedError/BleakConnectionError are all BleakError
            # subclasses (verified against bleak_retry_connector).
            raise SootherConnectionError(
                f"Failed to connect to {self._address}: {exc}"
            ) from exc

    async def _connect(self) -> None:
        self._client = await self._establish(self._on_disconnected)
        await self._subscribe_notifications()

    async def _disconnect(self) -> None:
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except (BleakError, TimeoutError, OSError) as exc:
                log.debug("Error disconnecting from %s: %s", self._address, exc)
        self._client = None

    async def open(self) -> None:
        """Open the BLE connection without the ``connect()`` context-manager
        lifecycle, for callers that manage the connection's lifetime
        themselves (e.g. a long-running server). Pair with close()."""
        await self._connect()

    async def close(self) -> None:
        """Close a connection opened via open() or the connect() context
        manager."""
        await self._disconnect()

    def _on_disconnected(self, client: BleakClient) -> None:
        log.warning("Device disconnected unexpectedly.")
        for cb in self._disconnect_callbacks:
            try:
                cb()
            except Exception as exc:  # noqa: BLE001 - isolate user callbacks
                log.warning("Disconnect callback raised: %s", exc)

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        """Register a callback invoked when the device disconnects
        unexpectedly (not via close()/the connect() context manager)."""
        self._disconnect_callbacks.append(callback)

    @property
    def address(self) -> str:
        return self._address

    @property
    def peripheral_type(self) -> int:
        return self._peripheral_type

    @property
    def session_key(self) -> bytes | None:
        """Return the active session key, if set or paired."""
        return self._session_key

    @property
    def is_connected(self) -> bool:
        return bool(self._client and self._client.is_connected)

    @property
    def is_paired(self) -> bool:
        """True if this client has a session key (from a prior pair() call
        or passed on init)."""
        return self._session_key is not None

    # ─── Pairing ──────────────────────────────────────────────────────────────

    async def pair(self) -> None:
        """
        Perform the real from-scratch pairing handshake. The device must
        already be in its own pairing mode.

        This disconnects and reconnects internally (the handshake owns its
        own connection lifecycle).
        """
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None
        device = await self._resolve_ble_device()
        self._session_key = await pair_device(
            device, self._peripheral_type, ble_device_callback=self._ble_device_callback
        )
        # Reconnect for subsequent use.
        self._client = await self._establish(self._on_disconnected)
        await self._subscribe_notifications()

    # ─── Notification handling ────────────────────────────────────────────────

    async def _subscribe_notifications(self) -> None:
        client = self._require_client()
        for uuid in NOTIFY_CHARACTERISTICS:
            callback = (
                self._on_state_notification if uuid == CHAR_STATE else (lambda *_: None)
            )
            try:
                await client.start_notify(uuid, callback)
            except (BleakError, TimeoutError, OSError) as exc:
                log.debug("Could not subscribe to %s: %s", uuid, exc)

    def _on_state_notification(
        self, _char: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        self._latest_notification_ct = bytes(data)
        if self._session_key is None:
            return
        # The device also sends a CHAR_STATE notification whenever its state
        # changes on its own (e.g. its physical buttons) -- decode it so
        # .state (and on_state_change subscribers) reflect changes we didn't
        # make ourselves, not just the ones from our own commands.
        try:
            raw = enc.decrypt_state(self._latest_notification_ct, self._session_key)
            if not enc.is_valid_state_decrypt(raw):
                return
            descrambled, _cak = enc.descramble_decrypted_state(raw)
            new_state = decode_state(descrambled, raw_state=raw)
        except Exception as exc:  # noqa: BLE001 - bleak's notification dispatch must not blow up on bad data
            log.debug("Could not decode state notification: %s", exc)
            return
        self._merge_core_state(new_state)
        log.debug("State notification: %s", self._state_for_logging())
        self._notify_state_callbacks()

    def _merge_core_state(self, new_state: SootherState) -> None:
        """Copy the CHAR_STATE-derived fields from *new_state* onto
        self._state, preserving fields only available from separate reads
        (aux/infra state) that a bare notification doesn't carry."""
        for field_name in self._state._ATTR_MAP.values():
            setattr(self._state, field_name, getattr(new_state, field_name))
        self._state.raw_state = new_state.raw_state

    def on_state_change(self, callback: Callable[[SootherState], None]) -> None:
        self._state_callbacks.append(callback)

    def _notify_state_callbacks(self) -> None:
        for cb in self._state_callbacks:
            try:
                cb(self._state)
            except Exception as exc:  # noqa: BLE001 - user callbacks are intentionally isolated from the library state machine
                log.warning("State callback raised: %s", exc)

    # ─── State reading ────────────────────────────────────────────────────────

    def _require_session_key(self) -> bytes:
        if self._session_key is None:
            raise SootherCommandError(
                "No session key -- call pair() first (device must be in pairing mode), "
                "or connect a device that was already paired before."
            )
        return self._session_key

    def _require_client(self) -> BleakClient:
        if self._client is None or not self._client.is_connected:
            raise SootherConnectionError("Not connected.")
        return self._client

    async def _read_char(self, uuid: str) -> bytes:
        """read_gatt_char on the current connection, raising any BLE-level
        failure as SootherConnectionError."""
        client = self._require_client()
        try:
            return bytes(await client.read_gatt_char(uuid))
        except (BleakError, TimeoutError, OSError) as exc:
            raise SootherConnectionError(f"Read of {uuid} failed: {exc}") from exc

    async def _read_raw_state(self, max_attempts: int = 10) -> bytes:
        """Read + decrypt CHAR_STATE, retrying until the device's own
        checksum passes (see encryption.is_valid_state_decrypt)."""
        key = self._require_session_key()
        for _ in range(max_attempts):
            ct = await self._read_char(CHAR_STATE)
            raw = enc.decrypt_state(ct, key)
            if enc.is_valid_state_decrypt(raw):
                return raw
            await asyncio.sleep(0.3)
        raise SootherConnectionError(
            f"CHAR_STATE decrypt never passed checksum after {max_attempts} attempts"
        )

    async def _read_raw_aux_state(self, max_attempts: int = 10) -> bytes:
        """Read + decrypt CHAR_AUX_STATE, retrying until the device's own
        checksum passes. Despite its own bit-layout table (AUX_ATTRS),
        auxState turns out to be framed identically to CHAR_STATE on the
        wire: a 16-byte AES-128-CBC block (same session key) that must pass
        the same raw[10] == raw[15] ^ raw[4] checksum and go through the
        same descramble_decrypted_state() byte permutation before AUX_ATTRS'
        byte/bit offsets apply -- confirmed live: decoding a freshly-set
        soothe_sleep_stage_timer through this pipeline reproduces the exact
        value just written."""
        key = self._require_session_key()
        for _ in range(max_attempts):
            ct = await self._read_char(CHAR_AUX_STATE)
            raw = enc.decrypt_state(ct, key)
            if enc.is_valid_state_decrypt(raw):
                descrambled, _cak = enc.descramble_decrypted_state(raw)
                return descrambled
            await asyncio.sleep(0.3)
        raise SootherConnectionError(
            f"CHAR_AUX_STATE decrypt never passed checksum after {max_attempts} attempts"
        )

    async def refresh_state(self) -> SootherState:
        """Read the device's current state (with retry) and update .state."""
        async with self._io_lock:
            return await self._refresh_state_locked()

    async def _refresh_state_locked(self) -> SootherState:
        """refresh_state()'s body, for callers that already hold _io_lock."""
        raw = await self._read_raw_state()
        descrambled, _cak = enc.descramble_decrypted_state(raw)
        # Merge (not replace) so aux/infra-only fields (e.g. the sleep-stage
        # timers) aren't reset to their None defaults while the reads below
        # are in flight -- a concurrent CHAR_STATE notification (the device
        # sends one for every state change, including ones from our own
        # commands) merges into self._state and fires state callbacks via
        # _merge_core_state()/_notify_state_callbacks() at any point during
        # this coroutine's awaits. Replacing self._state outright let that
        # race observe a state with the timers wiped to None.
        self._merge_core_state(decode_state(descrambled, raw_state=raw))
        try:
            aux_descrambled = await self._read_raw_aux_state()
            decode_aux_state(aux_descrambled, self._state)
        except (
            BleakError,
            TimeoutError,
            OSError,
            ValueError,
            SootherConnectionError,
        ) as exc:
            log.debug("aux state read failed: %s", exc)
        client = self._require_client()
        try:
            infra_ct = bytes(await client.read_gatt_char(CHAR_INFRA_STATE))
            decode_infra_state(infra_ct, self._state)
        except (BleakError, TimeoutError, OSError, ValueError) as exc:
            log.debug("infra state read failed: %s", exc)
        log.debug("Decrypted state: %s", self._state_for_logging())
        self._notify_state_callbacks()
        return self._state

    @property
    def state(self) -> SootherState:
        """Last known device state (populated by refresh_state())."""
        return self._state

    def _state_for_logging(self) -> dict[str, object]:
        """Decrypted state as a dict, omitting the raw pre-descramble bytes."""
        return {
            f.name: getattr(self._state, f.name)
            for f in dataclasses.fields(self._state)
            if f.name not in ("raw_state", "_ATTR_MAP")
        }

    # ─── Command sending ──────────────────────────────────────────────────────

    async def _send_state_command(
        self, command_id: int, value: int, name: str = "command"
    ) -> None:
        log.debug("Sending %s -> %s", name, value)
        async with self._io_lock:
            raw_state = await self._ensure_raw_state_locked()
            raw_cmd = build_state_command(command_id, value, raw_state)
            await self._write_command_locked(raw_cmd, "write failed")

    async def send_rtc_update(self) -> None:
        """Sync the device's clock. Required once right after a fresh pair()
        (pair() already does this); harmless to call any other time."""
        log.debug("Sending clock sync (rtcUpdate)")
        async with self._io_lock:
            raw_state = await self._ensure_raw_state_locked()
            raw_cmd = build_rtc_update_command(raw_state)
            await self._write_command_locked(raw_cmd, "rtcUpdate write failed")

    async def _send_custom_color_command(
        self, color0: int, color1: int, color2: int
    ) -> None:
        log.debug(
            "Sending set_star_projection_custom_colors -> (%s, %s, %s)",
            color0,
            color1,
            color2,
        )
        async with self._io_lock:
            raw_state = await self._ensure_raw_state_locked()
            raw_cmd = build_custom_color_sequence_command(
                color0, color1, color2, raw_state
            )
            await self._write_command_locked(raw_cmd, "write failed")

    async def _ensure_raw_state_locked(self) -> bytes:
        """Return the most recent raw (pre-descramble) CHAR_STATE bytes,
        reading them first if none have been read yet. Caller must hold
        _io_lock."""
        if self._state.raw_state is None:
            await self._refresh_state_locked()
        raw_state = self._state.raw_state
        if raw_state is None:
            raise SootherConnectionError("Device state is unavailable.")
        return raw_state

    async def _write_command_locked(self, raw_cmd: bytes, error_prefix: str) -> None:
        """Encrypt and write a fully-built 16-byte command frame, then
        refresh state. Caller must hold _io_lock."""
        key = self._require_session_key()
        client = self._require_client()
        encrypted = enc.encrypt_command(raw_cmd, key)
        try:
            await client.write_gatt_char(CHAR_STATE_UPDATE, encrypted, response=True)
        except (BleakError, TimeoutError, OSError) as exc:
            raise SootherCommandError(f"{error_prefix}: {exc}") from exc
        await self._refresh_state_locked()

    # ─── Public control API ───────────────────────────────────────────────────
    # Values reflect the real, confirmed bit widths (see protocol.SootherState).

    async def set_play(self, playing: bool) -> None:
        await self._send_state_command(CMD_PLAY_MODE, int(playing), "set_play")

    async def set_sound_mode(self, mode: int) -> None:
        """mode: 0-31, a preset index. Semantic meaning per-index is unknown."""
        await self._send_state_command(CMD_SOUND_MODE, mode & 0x1F, "set_sound_mode")

    async def set_volume(self, level: int) -> None:
        """level: 0-15."""
        await self._send_state_command(CMD_VOLUME_LEVEL, level & 0x0F, "set_volume")

    async def set_nightlight(self, on: bool) -> None:
        await self._send_state_command(CMD_NIGHTLIGHT_MODE, int(on), "set_nightlight")

    async def set_nightlight_brightness(self, level: int) -> None:
        """level: 0-7."""
        await self._send_state_command(
            CMD_NIGHTLIGHT_BRIGHTNESS, level & 0x07, "set_nightlight_brightness"
        )

    async def set_animal_projection_mode(self, mode: int) -> None:
        await self._send_state_command(
            CMD_ANIMAL_PROJECTION_MODE, mode & 0x03, "set_animal_projection_mode"
        )

    async def set_animal_projection_brightness(self, level: int) -> None:
        """level: 0-15."""
        await self._send_state_command(
            CMD_ANIMAL_PROJECTION_BRIGHTNESS,
            level & 0x0F,
            "set_animal_projection_brightness",
        )

    async def set_animal_projection_speed(self, speed: int) -> None:
        """speed: 0-3."""
        await self._send_state_command(
            CMD_ANIMAL_PROJECTION_SPEED, speed & 0x03, "set_animal_projection_speed"
        )

    async def set_star_projection_sequence_mode(self, mode: int) -> None:
        """mode: 0-7."""
        await self._send_state_command(
            CMD_STAR_PROJECTION_SEQUENCE_MODE,
            mode & 0x07,
            "set_star_projection_sequence_mode",
        )

    async def set_star_projection_brightness(self, level: int) -> None:
        """level: 0-7."""
        await self._send_state_command(
            CMD_STAR_PROJECTION_BRIGHTNESS,
            level & 0x07,
            "set_star_projection_brightness",
        )

    async def set_star_projection_speed(self, speed: int) -> None:
        """speed: 0-3."""
        await self._send_state_command(
            CMD_STAR_PROJECTION_SPEED, speed & 0x03, "set_star_projection_speed"
        )

    async def set_star_projection_custom_colors(
        self, color0: int, color1: int, color2: int
    ) -> None:
        """Set the up to 3 custom sequence colors (each 0-7; see App.md's
        palette: Red, Orange, Yellow, Green, Blue, Purple)."""
        await self._send_custom_color_command(
            color0 & 0x07, color1 & 0x07, color2 & 0x07
        )

    async def set_sound_timer(self, setting: int) -> None:
        """setting: 0-15 (device-defined timer durations, not raw minutes)."""
        await self._send_state_command(
            CMD_SOUND_TIMER_SETTING, setting & 0x0F, "set_sound_timer"
        )

    async def set_light_timer(self, setting: int) -> None:
        """setting: 0-15 (device-defined timer durations, not raw minutes)."""
        await self._send_state_command(
            CMD_LIGHT_TIMER, setting & 0x0F, "set_light_timer"
        )

    async def set_sleep_stages_mode(self, mode: int) -> None:
        """mode: 0=Off, 1=Settle, 2=Soothe, 3=Sleep."""
        await self._send_state_command(
            CMD_SLEEP_STAGES_MODE, mode & 0x03, "set_sleep_stages_mode"
        )

    async def set_captive_sleep_stage_timer(self, setting: int) -> None:
        """setting: device-defined timer duration for the Settle stage."""
        await self._send_state_command(
            CMD_CAPTIVE_SLEEP_STAGE_TIMER,
            setting & 0x0F,
            "set_captive_sleep_stage_timer",
        )

    async def set_soothe_sleep_stage_timer(self, setting: int) -> None:
        """setting: device-defined timer duration for the Soothe stage."""
        await self._send_state_command(
            CMD_SOOTHE_SLEEP_STAGE_TIMER,
            setting & 0x0F,
            "set_soothe_sleep_stage_timer",
        )

    async def set_sleep_stage_timer(self, setting: int) -> None:
        """setting: device-defined timer duration for the Sleep stage."""
        await self._send_state_command(
            CMD_SLEEP_STAGE_TIMER, setting & 0x0F, "set_sleep_stage_timer"
        )

    async def set_captive_playlist_selection(self, mask: int) -> None:
        """mask: 5-bit bitmask selecting which tracks play during Settle."""
        await self._send_state_command(
            CMD_CAPTIVE_PLAYLIST_SELECTION,
            mask & 0x1F,
            "set_captive_playlist_selection",
        )

    async def set_soothe_playlist_selection(self, mask: int) -> None:
        """mask: 5-bit bitmask selecting which tracks play during Soothe."""
        await self._send_state_command(
            CMD_SOOTHE_PLAYLIST_SELECTION,
            mask & 0x1F,
            "set_soothe_playlist_selection",
        )

    async def send_preset(self, **overrides: int) -> None:
        """
        Apply a bundle of settings in a single BLE write (command_id=22),
        mirroring the real app's "preset"/"favorite" apply -- instead of one
        command per attribute, every settable attribute is bundled into one
        composite command.

        Starts from the current known state (.state) and applies any keyword
        overrides using the same field names as SootherState (e.g.
        nightlight_mode=1, sound_mode=3, volume_level=8); any attribute you
        don't override is sent as its current live value, not left unset --
        the device command this maps to (dyw47.json's "preset" command,
        id 22) always bundles all ~21 settable attributes in one shot, just
        like the real app's own preset-apply.
        """
        log.debug("Sending preset -> %s", overrides)
        async with self._io_lock:
            raw_state = await self._ensure_raw_state_locked()
            new_state = dataclasses.replace(self._state, **overrides)
            raw_cmd = build_preset_command(new_state, raw_state)
            await self._write_command_locked(raw_cmd, "preset write failed")

    # ─── Escape hatches for further exploration ──────────────────────────────

    async def send_raw_command(self, command_id: int, value: int) -> None:
        """Send an arbitrary attribute-set command by raw command_id/value."""
        await self._send_state_command(command_id, value, f"raw command {command_id}")

    async def read_raw(self, char_uuid: str) -> bytes:
        return await self._read_char(char_uuid)

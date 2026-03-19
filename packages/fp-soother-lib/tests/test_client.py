import dataclasses
import os
from types import SimpleNamespace
from typing import cast

import pytest
from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from fp_soother_lib import encryption as enc
from fp_soother_lib.client import SootherClient
from fp_soother_lib.exceptions import SootherCommandError, SootherConnectionError
from fp_soother_lib.protocol import SootherState, build_preset_command

ADDRESS = "AA:BB:CC:DD:EE:FF"

# _on_state_notification()'s first parameter is unused, so a stand-in cast to
# BleakGATTCharacteristic is enough to satisfy its signature in tests.
_NO_CHAR = cast(BleakGATTCharacteristic, None)


def _fake_client(is_connected: bool) -> BleakClient:
    return cast(BleakClient, SimpleNamespace(is_connected=is_connected))


def make_valid_raw_state(fill: int = 0x11) -> bytearray:
    raw = bytearray([fill] * 16)
    raw[4] = 0x03
    raw[15] = 0xAB
    raw[10] = raw[15] ^ raw[4]  # satisfies is_valid_state_decrypt()
    return raw


def test_is_paired_reflects_session_key():
    assert SootherClient(ADDRESS).is_paired is False
    assert SootherClient(ADDRESS, session_key=os.urandom(16)).is_paired is True


def test_is_connected_false_without_client():
    client = SootherClient(ADDRESS)
    assert client.is_connected is False


def test_is_connected_reflects_underlying_bleak_client():
    client = SootherClient(ADDRESS)
    client._client = _fake_client(is_connected=True)
    assert client.is_connected is True
    client._client = _fake_client(is_connected=False)
    assert client.is_connected is False


def test_require_session_key_raises_when_unpaired():
    client = SootherClient(ADDRESS)
    with pytest.raises(SootherCommandError):
        client._require_session_key()


def test_require_session_key_returns_key_when_present():
    key = os.urandom(16)
    client = SootherClient(ADDRESS, session_key=key)
    assert client._require_session_key() == key


def test_require_client_raises_when_not_connected():
    client = SootherClient(ADDRESS)
    with pytest.raises(SootherConnectionError):
        client._require_client()

    client._client = _fake_client(is_connected=False)
    with pytest.raises(SootherConnectionError):
        client._require_client()


def test_require_client_returns_client_when_connected():
    client = SootherClient(ADDRESS)
    fake_client = _fake_client(is_connected=True)
    client._client = fake_client
    assert client._require_client() is fake_client


def test_state_for_logging_excludes_raw_state_and_attr_map():
    client = SootherClient(ADDRESS)
    client._state = SootherState(raw_state=b"\x00" * 16)
    logged = client._state_for_logging()
    assert "raw_state" not in logged
    assert "_ATTR_MAP" not in logged
    assert logged["volume_level"] == client._state.volume_level


def test_merge_core_state_copies_mapped_fields_and_raw_state():
    client = SootherClient(ADDRESS)
    client._state.captive_sleep_stage_timer = 5  # only from a separate aux read

    new_state = SootherState(raw_state=b"\x01" * 16)
    new_state.volume_level = 9
    new_state.nightlight_mode = 1

    client._merge_core_state(new_state)

    assert client._state.volume_level == 9
    assert client._state.nightlight_mode == 1
    assert client._state.raw_state == b"\x01" * 16
    # Aux-only field must survive a CHAR_STATE-only notification merge.
    assert client._state.captive_sleep_stage_timer == 5


def test_on_state_notification_noop_without_session_key():
    client = SootherClient(ADDRESS)
    before = client._state
    client._on_state_notification(_NO_CHAR, bytearray(b"\x00" * 16))
    assert client._latest_notification_ct == b"\x00" * 16
    assert client._state is before


def test_on_state_notification_updates_state_on_valid_checksum():
    session_key = os.urandom(16)
    raw = make_valid_raw_state()
    ciphertext = enc.encrypt_command(bytes(raw), session_key)

    client = SootherClient(ADDRESS, session_key=session_key)
    seen = []
    client.on_state_change(seen.append)

    client._on_state_notification(_NO_CHAR, bytearray(ciphertext))

    assert client.state.raw_state == bytes(raw)
    assert seen == [client.state]


def test_on_state_notification_ignored_on_invalid_checksum():
    session_key = os.urandom(16)
    raw = make_valid_raw_state()
    raw[10] ^= 0xFF  # break the checksum
    ciphertext = enc.encrypt_command(bytes(raw), session_key)

    client = SootherClient(ADDRESS, session_key=session_key)
    seen = []
    client.on_state_change(seen.append)

    client._on_state_notification(_NO_CHAR, bytearray(ciphertext))

    assert client.state.raw_state is None
    assert seen == []


def test_on_state_notification_ignores_malformed_ciphertext():
    session_key = os.urandom(16)
    client = SootherClient(ADDRESS, session_key=session_key)

    # Not a multiple of the AES block size -- must be swallowed, not raised.
    client._on_state_notification(_NO_CHAR, bytearray(b"\x00" * 5))

    assert client.state.raw_state is None


async def test_ensure_raw_state_locked_returns_cached_state_without_refresh(
    monkeypatch,
):
    client = SootherClient(ADDRESS)
    raw = bytes(make_valid_raw_state())
    client._state.raw_state = raw

    async def fail_refresh():
        raise AssertionError(
            "_refresh_state_locked must not run when raw_state is already cached"
        )

    monkeypatch.setattr(client, "_refresh_state_locked", fail_refresh)

    result = await client._ensure_raw_state_locked()

    assert result == raw


async def test_ensure_raw_state_locked_refreshes_when_state_missing(monkeypatch):
    client = SootherClient(ADDRESS)
    raw = bytes(make_valid_raw_state())

    async def fake_refresh():
        client._state.raw_state = raw

    monkeypatch.setattr(client, "_refresh_state_locked", fake_refresh)

    result = await client._ensure_raw_state_locked()

    assert result == raw


async def test_ensure_raw_state_locked_raises_when_still_unavailable(monkeypatch):
    client = SootherClient(ADDRESS)

    async def fake_refresh():
        pass  # doesn't populate raw_state

    monkeypatch.setattr(client, "_refresh_state_locked", fake_refresh)

    with pytest.raises(SootherConnectionError):
        await client._ensure_raw_state_locked()


async def test_send_preset_merges_overrides_onto_current_live_state(monkeypatch):
    """send_preset() must send every unoverridden attribute at its current
    live value (not zero/default) -- only the passed overrides should change
    relative to the live state."""
    raw_state = bytes(make_valid_raw_state())
    client = SootherClient(ADDRESS, session_key=os.urandom(16))
    client._state = SootherState(raw_state=raw_state, volume_level=5, nightlight_mode=0)

    async def fake_ensure_raw_state_locked():
        return raw_state

    captured = {}

    async def fake_write_command_locked(raw_cmd, error_prefix):
        captured["raw_cmd"] = raw_cmd
        captured["error_prefix"] = error_prefix

    monkeypatch.setattr(
        client, "_ensure_raw_state_locked", fake_ensure_raw_state_locked
    )
    monkeypatch.setattr(client, "_write_command_locked", fake_write_command_locked)

    await client.send_preset(nightlight_mode=1)

    expected_state = dataclasses.replace(client._state, nightlight_mode=1)
    assert captured["raw_cmd"] == build_preset_command(expected_state, raw_state)
    assert captured["error_prefix"] == "preset write failed"
    # send_preset() must not mutate the live state itself -- only the frame
    # it builds from a copy of it.
    assert client._state.volume_level == 5
    assert client._state.nightlight_mode == 0

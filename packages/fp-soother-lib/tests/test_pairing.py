import os
from types import SimpleNamespace
from typing import cast

import pytest
from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError, BleakGATTProtocolError, BleakGATTProtocolErrorCode

from fp_soother_lib import pairing
from fp_soother_lib.constants import CHAR_INFRA_UPDATE, CHAR_STATE
from fp_soother_lib.exceptions import SootherCommandError, SootherConnectionError

ADDRESS = "AA:BB:CC:DD:EE:FF"
_DEVICE = cast(BLEDevice, SimpleNamespace(address=ADDRESS))


class _FakePairingClient:
    """Stand-in BleakClient for pairing.pair(): every read returns random
    16-byte ciphertext unless *read_error* is set, and writes to
    CHAR_INFRA_UPDATE raise *key_request_error* if set."""

    def __init__(
        self,
        *,
        read_error: BaseException | None = None,
        key_request_error: BaseException | None = None,
    ) -> None:
        self.is_connected = True
        self.read_error = read_error
        self.key_request_error = key_request_error
        self.disconnect_calls = 0

    async def start_notify(self, _uuid, _callback) -> None:
        pass

    async def read_gatt_char(self, _uuid) -> bytearray:
        if self.read_error is not None:
            raise self.read_error
        return bytearray(os.urandom(16))

    async def write_gatt_char(self, uuid, _data, response) -> None:
        if uuid == CHAR_INFRA_UPDATE and self.key_request_error is not None:
            raise self.key_request_error

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.is_connected = False


def _use_fake_client(monkeypatch, fake: _FakePairingClient) -> None:
    async def fake_establish_connection(*_args, **_kwargs):
        return fake

    monkeypatch.setattr(pairing, "establish_connection", fake_establish_connection)


async def test_pair_wraps_rejected_key_request_as_command_error(monkeypatch):
    error = BleakGATTProtocolError(BleakGATTProtocolErrorCode.UNLIKELY_ERROR)
    fake = _FakePairingClient(key_request_error=error)
    _use_fake_client(monkeypatch, fake)

    with pytest.raises(SootherCommandError, match="pairing mode") as info:
        await pairing.pair(_DEVICE)

    assert info.value.__cause__ is error
    assert fake.disconnect_calls == 1


async def test_pair_wraps_read_bleak_error_as_connection_error(monkeypatch):
    error = BleakError("read failed")
    fake = _FakePairingClient(read_error=error)
    _use_fake_client(monkeypatch, fake)

    with pytest.raises(SootherConnectionError) as info:
        await pairing.pair(_DEVICE)

    assert info.value.__cause__ is error
    assert fake.disconnect_calls == 1


async def test_pair_keeps_timeout_error_when_device_never_replies(monkeypatch):
    fake = _FakePairingClient()
    _use_fake_client(monkeypatch, fake)

    with pytest.raises(TimeoutError):
        await pairing.pair(_DEVICE, timeout=0.01)

    assert fake.disconnect_calls == 1


async def test_read_char_wraps_bleak_error():
    error = BleakError("read failed")
    fake = _FakePairingClient(read_error=error)

    with pytest.raises(SootherConnectionError) as info:
        await pairing._read_char(cast(BleakClient, fake), CHAR_STATE)

    assert info.value.__cause__ is error

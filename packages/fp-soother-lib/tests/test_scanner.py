from types import SimpleNamespace
from typing import cast

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from fp_soother_lib.constants import SERVICE_UUID
from fp_soother_lib.scanner import _is_soother

# _is_soother() only inspects adv.service_uuids and never touches `device`,
# so a bare stand-in cast to BLEDevice is enough here.
_DEVICE = cast(BLEDevice, SimpleNamespace())


def _adv(service_uuids):
    return cast(AdvertisementData, SimpleNamespace(service_uuids=service_uuids))


def test_is_soother_matches_exact_uuid():
    assert _is_soother(_DEVICE, _adv([SERVICE_UUID])) is True


def test_is_soother_matches_case_insensitively():
    assert _is_soother(_DEVICE, _adv([SERVICE_UUID.lower()])) is True
    assert _is_soother(_DEVICE, _adv([SERVICE_UUID.upper()])) is True


def test_is_soother_false_when_uuid_absent():
    other_uuid = "0000180f-0000-1000-8000-00805f9b34fb"
    assert _is_soother(_DEVICE, _adv([other_uuid])) is False


def test_is_soother_false_when_no_service_uuids():
    assert _is_soother(_DEVICE, _adv(None)) is False
    assert _is_soother(_DEVICE, _adv([])) is False

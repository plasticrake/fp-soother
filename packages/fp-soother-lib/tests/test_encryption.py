import os

import pytest

from fp_soother_lib import encryption as enc
from fp_soother_lib.constants import RAW_TO_STATE_MAP, SHARED_KEY_RAW_TO_STATE_MAP
from fp_soother_lib.key_tables import (
    KEY_REQUEST_KEYS,
    PAIRING_KEYS,
    SHARED_ENCRYPTION_KEY,
)
from fp_soother_lib.protocol import decode_state

PERIPHERAL_TYPE = 11


def test_derive_pairing_key():
    assert enc.derive_pairing_key(PERIPHERAL_TYPE) == PAIRING_KEYS[PERIPHERAL_TYPE]


def test_derive_key_request_key():
    assert (
        enc.derive_key_request_key(PERIPHERAL_TYPE) == KEY_REQUEST_KEYS[PERIPHERAL_TYPE]
    )


def test_encrypt_command_decrypt_state_roundtrip():
    session_key = os.urandom(16)
    plaintext = os.urandom(16)
    ciphertext = enc.encrypt_command(plaintext, session_key)
    assert ciphertext != plaintext
    assert enc.decrypt_state(ciphertext, session_key) == plaintext


def test_build_key_request_plaintext_rejects_wrong_length_key():
    with pytest.raises(ValueError):
        enc.build_key_request_plaintext(b"\x00" * 15, PERIPHERAL_TYPE)


def test_build_key_request_plaintext_layout():
    cak = bytes(range(16))
    tb = enc.KEY_REQUEST_TABLES[PERIPHERAL_TYPE]
    plaintext = enc.build_key_request_plaintext(cak, PERIPHERAL_TYPE)

    assert len(plaintext) == 16
    assert plaintext[0] == tb[1]
    assert plaintext[1] == cak[2]
    assert plaintext[2] == tb[6]
    assert plaintext[3] == tb[9]
    assert plaintext[4] == cak[1]
    assert plaintext[5] == cak[0]
    assert plaintext[6] == tb[5]
    assert plaintext[7] == tb[2]
    assert plaintext[8] == 0x00
    assert plaintext[9] == (tb[5] ^ cak[1])
    assert plaintext[10] == tb[3]
    assert plaintext[11] == tb[0]
    assert plaintext[12] == tb[7]
    assert plaintext[13] == 0x0D
    assert plaintext[14] == tb[4]
    assert plaintext[15] == tb[8]


def test_build_key_request_message_is_encrypted_plaintext():
    cak = bytes(range(16))
    plaintext = enc.build_key_request_plaintext(cak, PERIPHERAL_TYPE)
    message = enc.build_key_request_message(cak, PERIPHERAL_TYPE)

    key = enc.derive_pairing_key(PERIPHERAL_TYPE)
    assert enc.decrypt_state(message, key) == plaintext


def test_decrypt_key_request_reply_rejects_wrong_length():
    with pytest.raises(ValueError):
        enc.decrypt_key_request_reply(b"\x00" * 16, PERIPHERAL_TYPE)


def test_decrypt_key_request_reply_roundtrip():
    session_key_material = os.urandom(16)
    key_request_key = enc.derive_key_request_key(PERIPHERAL_TYPE)
    ciphertext = enc._aes_cbc(key_request_key, session_key_material, encrypt=True)
    reply = b"\x00" + ciphertext  # 1-byte prefix + 16-byte ciphertext

    session_key, used_key = enc.decrypt_key_request_reply(reply, PERIPHERAL_TYPE)
    assert session_key == session_key_material
    assert used_key == key_request_key


def test_is_valid_state_decrypt_true_when_checksum_matches():
    raw = bytearray(16)
    raw[4] = 0x03
    raw[15] = 0xAB
    raw[10] = raw[15] ^ raw[4]
    assert enc.is_valid_state_decrypt(bytes(raw)) is True


def test_is_valid_state_decrypt_false_when_checksum_mismatches():
    raw = bytearray(16)
    raw[4] = 0x03
    raw[15] = 0xAB
    raw[10] = (raw[15] ^ raw[4]) ^ 0x01
    assert enc.is_valid_state_decrypt(bytes(raw)) is False


def test_is_valid_state_decrypt_false_for_wrong_length():
    assert enc.is_valid_state_decrypt(bytes(15)) is False
    assert enc.is_valid_state_decrypt(bytes(17)) is False


def test_descramble_decrypted_state_rejects_wrong_length():
    with pytest.raises(ValueError):
        enc.descramble_decrypted_state(bytes(15))


def test_descramble_decrypted_state_matches_raw_to_state_map():
    raw = bytes(range(16))
    state, _cak = enc.descramble_decrypted_state(raw)
    assert len(state) == len(RAW_TO_STATE_MAP) == 12
    assert list(state) == [raw[i] for i in RAW_TO_STATE_MAP]


def test_descramble_decrypted_state_change_cmd_auth_key():
    raw = bytes(range(16))
    _state, cak = enc.descramble_decrypted_state(raw)
    assert len(cak) == 16
    assert cak[0] == raw[6]
    assert cak[1] == raw[15]
    assert cak[2] == raw[4]
    assert cak[3:] == bytes(13)


def test_descramble_cak_matches_change_cmd_auth_key_from_raw_state():
    raw = os.urandom(16)
    _state, cak_from_descramble = enc.descramble_decrypted_state(raw)
    assert enc.change_cmd_auth_key_from_raw_state(raw) == cak_from_descramble


def test_change_cmd_auth_key_from_raw_state_rejects_wrong_length():
    with pytest.raises(ValueError):
        enc.change_cmd_auth_key_from_raw_state(bytes(10))


# ── Shared-key (firmware < 9) layout ─────────────────────────────────────────

# A real CHAR_STATE read from a firmware-8 dyw47 (volume 5, nightlight off,
# nightlight brightness 4, both playlists 31, both timers continuous).
FW8_STATE_CIPHERTEXT = bytes.fromhex("b4d2ba40abfd24891db56cd92aa858e6")


def test_is_valid_state_decrypt_shared_key_checksum():
    raw = bytearray(os.urandom(16))
    raw[3] = raw[5] ^ raw[6]
    assert enc.is_valid_state_decrypt(bytes(raw), shared_key=True) is True
    raw[3] ^= 0xFF
    assert enc.is_valid_state_decrypt(bytes(raw), shared_key=True) is False


def test_descramble_decrypted_state_shared_key_layout():
    raw = bytes(range(16))
    state, cak = enc.descramble_decrypted_state(raw, shared_key=True)
    assert list(state) == [raw[i] for i in SHARED_KEY_RAW_TO_STATE_MAP]
    assert cak == bytes([raw[0], raw[6], raw[5]]) + bytes(13)
    assert enc.change_cmd_auth_key_from_raw_state(raw, shared_key=True) == cak


def test_shared_encryption_key_is_ramped_native_constant():
    """libogg.so's slot-17 constant plus the same +i ramp salt as the
    other key tables; the old memory dump filed it as PAIRING_KEYS[19]."""
    native = bytes.fromhex("398109103560f0d5294cb0b22d99326c")
    assert SHARED_ENCRYPTION_KEY == bytes((b + i) & 0xFF for i, b in enumerate(native))
    assert SHARED_ENCRYPTION_KEY == PAIRING_KEYS[19]


def test_real_firmware_8_state_decodes_with_shared_key():
    raw = enc.decrypt_state(FW8_STATE_CIPHERTEXT, SHARED_ENCRYPTION_KEY)
    assert enc.is_valid_state_decrypt(raw, shared_key=True)
    assert not enc.is_valid_state_decrypt(raw)
    state_bytes, _cak = enc.descramble_decrypted_state(raw, shared_key=True)
    state = decode_state(state_bytes)
    assert state.volume_level == 5
    assert state.nightlight_mode == 0
    assert state.nightlight_brightness == 4
    assert state.captive_playlist_selection == 31
    assert state.soothe_playlist_selection == 31
    assert state.sound_timer_setting == 15
    assert state.light_timer == 15

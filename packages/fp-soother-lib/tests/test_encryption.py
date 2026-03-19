import os

import pytest

from fp_soother_lib import encryption as enc
from fp_soother_lib.constants import RAW_TO_STATE_MAP
from fp_soother_lib.key_tables import KEY_REQUEST_KEYS, PAIRING_KEYS

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

"""
fp_soother_lib.encryption
==========================
The SmartConnect crypto: AES-128-CBC (zero IV, no padding -- every message
is exactly one 16-byte block).

  - The pairing-key / key-request-key/table values come from a live-memory
    dump of the native library, extracted once and frozen in key_tables.py
    (see that module's docstring), and were confirmed exact against real
    device replies.
  - is_valid_state_decrypt() / descramble_decrypted_state() implement a real
    checksum+descramble step the device's own firmware performs, in one of
    two byte layouts: unique-key (firmware >= 9) or shared-key (older).
  - encrypt_command() intentionally does NOT re-scramble its input: the
    build_*_command() functions in protocol.py already produce a final,
    fully-positioned frame.
"""

from __future__ import annotations

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .constants import RAW_TO_STATE_MAP, SHARED_KEY_RAW_TO_STATE_MAP
from .key_tables import KEY_REQUEST_KEYS, KEY_REQUEST_TABLES, PAIRING_KEYS


def _aes_cbc(key: bytes, data: bytes, *, encrypt: bool) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CBC(bytes(16)))
    ctx = cipher.encryptor() if encrypt else cipher.decryptor()
    return ctx.update(data)


def derive_pairing_key(peripheral_type: int) -> bytes:
    """
    The shared "pairing key" used to decrypt CHAR_STATE before a device has
    ever been paired (changeCmdAuthKey=0, verifyPivot=false).
    """
    return PAIRING_KEYS[peripheral_type]


def derive_key_request_key(peripheral_type: int) -> bytes:
    """
    Decrypts the device's raw CHAR_INFRA_UPDATE reply (to our key-request)
    into the genuine new session key.
    """
    return KEY_REQUEST_KEYS[peripheral_type]


def build_key_request_plaintext(
    change_cmd_auth_key: bytes, peripheral_type: int
) -> bytes:
    """
    The plaintext of the key-request message written to CHAR_INFRA_UPDATE to
    trigger the device's unique-key exchange. Byte 8 is genuine uninitialized
    stack memory in the real app (confirmed varying between identical real
    captures) -- the device does not validate this message's content beyond
    the outer AES layer, so its value here doesn't matter.
    """
    if len(change_cmd_auth_key) != 16:
        raise ValueError("change_cmd_auth_key must be 16 bytes")
    tb = KEY_REQUEST_TABLES[peripheral_type]
    cak = change_cmd_auth_key

    p = bytearray(16)
    p[0] = tb[1]
    p[1] = cak[2]
    p[2] = tb[6]
    p[3] = tb[9]
    p[4] = cak[1]
    p[5] = cak[0]
    p[6] = tb[5]
    p[7] = tb[2]
    p[8] = 0x00
    p[9] = tb[5] ^ cak[1]
    p[10] = tb[3]
    p[11] = tb[0]
    p[12] = tb[7]
    p[13] = 0x0D
    p[14] = tb[4]
    p[15] = tb[8]
    return bytes(p)


def build_key_request_message(
    change_cmd_auth_key: bytes, peripheral_type: int = 11
) -> bytes:
    """The full encrypted key-request message to write to CHAR_INFRA_UPDATE."""
    key = derive_pairing_key(peripheral_type)
    plaintext = build_key_request_plaintext(change_cmd_auth_key, peripheral_type)
    return _aes_cbc(key, plaintext, encrypt=True)


def decrypt_key_request_reply(
    reply: bytes, peripheral_type: int = 11
) -> tuple[bytes, bytes]:
    """
    Decrypts the device's real notification reply on CHAR_INFRA_UPDATE to our
    key-request write. `reply` is the raw notification value as received
    over BLE (a 1-byte prefix + 16-byte AES-128-CBC ciphertext).

    Returns (session_key, key_request_key).
    """
    if len(reply) != 17:
        raise ValueError(
            "expected a 17-byte reply (1-byte prefix + 16-byte ciphertext)"
        )
    key = derive_key_request_key(peripheral_type)
    session_key = _aes_cbc(key, reply[1:], encrypt=False)
    return session_key, key


# The native decrypt core (SmartCrypto's FUN_00007900, verifyPivot=true) has
# two byte layouts for a 16-byte-key CHAR_STATE block, chosen by a per-key
# mode flag: unique-key (session key from pairing.pair(), firmware >= 9) and
# shared-key (key_tables.SHARED_ENCRYPTION_KEY, older firmware). Each layout
# is (checksum index, xor index a, xor index b, state positions, cak positions).
_UNIQUE_KEY_LAYOUT = (10, 15, 4, RAW_TO_STATE_MAP, (6, 15, 4))
_SHARED_KEY_LAYOUT = (3, 5, 6, SHARED_KEY_RAW_TO_STATE_MAP, (0, 6, 5))


def _layout(shared_key: bool):
    return _SHARED_KEY_LAYOUT if shared_key else _UNIQUE_KEY_LAYOUT


def is_valid_state_decrypt(raw: bytes, *, shared_key: bool = False) -> bool:
    """
    The device's own firmware only treats a decrypted CHAR_STATE block as
    genuine if a self-consistency checksum on the raw AES-CBC-decrypted bytes
    (BEFORE descrambling) holds: raw[10] == raw[15] ^ raw[4] for a unique-key
    device, raw[3] == raw[5] ^ raw[6] for a shared-key (*shared_key*) one.
    Immediately after a fresh pairing the device can briefly return
    stale/invalid ciphertext; the real app retries CHAR_STATE reads until
    this checksum passes (this project has observed 3 failures before a 4th
    succeeds) -- always retry rather than trusting the first read, or
    changeCmdAuthKey/rolling-token bytes derived from it will be wrong.
    """
    check, a, b, _state_map, _cak_map = _layout(shared_key)
    return len(raw) == 16 and raw[check] == (raw[a] ^ raw[b])


def descramble_decrypted_state(
    raw: bytes, *, shared_key: bool = False
) -> tuple[bytes, bytes]:
    """
    Split a raw (already checksum-validated) AES-CBC-decrypted CHAR_STATE
    block into (state, next_change_cmd_auth_key). state is 9 meaningful
    bytes (padded to 12); next_change_cmd_auth_key is 16 bytes with only
    [0:3] populated (matching change_cmd_auth_key_from_raw_state()).
    *shared_key* selects the shared-key (firmware < 9) byte layout.
    """
    if len(raw) != 16:
        raise ValueError("raw must be 16 bytes")
    _check, _a, _b, state_map, _cak_map = _layout(shared_key)
    state = bytes(raw[i] for i in state_map)
    return state, change_cmd_auth_key_from_raw_state(raw, shared_key=shared_key)


def change_cmd_auth_key_from_raw_state(
    raw_state: bytes, *, shared_key: bool = False
) -> bytes:
    """
    Derive changeCmdAuthKey directly from a raw (pre-descramble) decrypted
    CHAR_STATE block -- this is also exactly next_change_cmd_auth_key from
    descramble_decrypted_state(), provided as its own function since callers
    building a command frame need it before/without calling descramble.
    """
    if len(raw_state) != 16:
        raise ValueError("raw_state must be 16 bytes")
    _check, _a, _b, _state_map, cak_map = _layout(shared_key)
    cak = bytearray(16)
    for i, pos in enumerate(cak_map):
        cak[i] = raw_state[pos]
    return bytes(cak)


def encrypt_command(raw_command: bytes, session_key: bytes) -> bytes:
    """
    Encrypt a control-command write. `raw_command` must already be a final,
    fully-positioned 16-byte frame (rolling tokens/command_id/value already
    placed -- see protocol.py's build_state_command()/build_rtc_update_command()).
    Do NOT scramble it again here: those builder functions already produce
    the final frame shape.
    """
    return _aes_cbc(session_key, raw_command, encrypt=True)


def decrypt_state(ciphertext: bytes, session_key: bytes) -> bytes:
    """Plain AES-CBC decrypt of a CHAR_STATE read -- returns the RAW
    (pre-descramble) 16-byte block. Always check is_valid_state_decrypt()
    before trusting it, and use descramble_decrypted_state() to interpret it."""
    return _aes_cbc(session_key, ciphertext, encrypt=False)

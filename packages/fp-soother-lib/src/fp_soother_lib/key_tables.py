"""
fp_soother_lib.key_tables
==========================
Per-peripheral-type key material for the SmartConnect pairing handshake.

These are the final, already-combined values previously computed at runtime
from a raw memory dump of the native SmartCrypto library.

  PAIRING_KEYS[pt]       = table_a[pt] + ramp_salt        (mod 256, byte-wise)
  KEY_REQUEST_KEYS[pt]   = key_request_table[pt] + ramp_salt (mod 256, byte-wise)
  KEY_REQUEST_TABLES[pt] = table_b[pt][i] + i              (mod 256, per byte)

Only peripheral type 11 (dyw47 Deluxe Soother) has been validated against real
hardware. The others were transcribed/extracted for completeness but are
unverified.
"""

from __future__ import annotations

PAIRING_KEYS: dict[int, bytes] = {
    0: bytes.fromhex("b76488640ebf69c5a59dfe0d6716e989"),
    1: bytes.fromhex("0b2e6c4711de4b45e7e66756d44a5f56"),
    2: bytes.fromhex("ba71bc76c14bb1190da3d8122c58fba1"),
    3: bytes.fromhex("b62c15a208b0de35c4f13e556180c8c3"),
    4: bytes.fromhex("f395722801c3086bc787e84267f51c90"),
    5: bytes.fromhex("883ccf77042988d2f2ea086929c63348"),
    6: bytes.fromhex("7bd63b4da103b37a0ce6b6ef8e27e787"),
    7: bytes.fromhex("72b3d9059027b6e6edb47c1e556fb71a"),
    8: bytes.fromhex("0bdbc998b1880c6851198026bdd14c9c"),
    9: bytes.fromhex("3b10a2678645089aaed47cbb66e4fdb3"),
    10: bytes.fromhex("9466f9c0ace2edec7f4153c2e394f443"),
    11: bytes.fromhex("39bc2a4afe78b6b0435a10868f8d2e21"),
    12: bytes.fromhex("7739b9c0afec0d101a60ee899356c546"),
    13: bytes.fromhex("d650d92cd63bffb96da7a99eef829e6c"),
    14: bytes.fromhex("3fa40b6ee27b57c1e6821cf8f7d9431b"),
    15: bytes.fromhex("cb8aed4d9831dcc6fe0de357cee88b4a"),
    18: bytes.fromhex("4c9d63410b738c5d0a96bcc348ba5083"),
    19: bytes.fromhex("39820b133965f6dc3155babd39a6407b"),
}

KEY_REQUEST_KEYS: dict[int, bytes] = {
    0: bytes.fromhex("12bc5ed76048e60decba4b9f80f800b3"),
    1: bytes.fromhex("9365bdfc3f88c49cde85aeaafb7d6b3c"),
    2: bytes.fromhex("12bc5ed76048e60decba4b9f80f800b3"),
    3: bytes.fromhex("8493397963f479bcc66356af96a4e5a5"),
    4: bytes.fromhex("c671e17d5240339f50aaf1c1817988b1"),
    5: bytes.fromhex("720cf5eedd407809c5ea2bbf0d8d577b"),
    6: bytes.fromhex("4d9ca4882cb09f3bc5f9d2dd2ce8bc2f"),
    7: bytes.fromhex("c7cd5f01dc8a0b3c5d9aa290c6e2faad"),
    8: bytes.fromhex("da724db069252b5d990ce7c541c7e673"),
    9: bytes.fromhex("92375445a1d8c0da36c4ad8317bc681c"),
    10: bytes.fromhex("459eb9daf61fefb18f7c8de20b177409"),
    11: bytes.fromhex("df76f2b089af9a7cab0d2a98dd1795df"),
    12: bytes.fromhex("b73ed9aa6d3efdc17c4263e6e3b370c7"),
    13: bytes.fromhex("d307266be1e4f1107e1ca8ec3e18fb08"),
    14: bytes.fromhex("22bda93b11ebd3aaa31b0e37b47dcafa"),
    15: bytes.fromhex("d15d885d34a3b822ebe66eef18f06bdb"),
    18: bytes.fromhex("00020406080a0c0e10121416181a1c1e"),
    19: bytes.fromhex("62eb804fcd9097fba80dc745bc17bb0e"),
}

KEY_REQUEST_TABLES: dict[int, bytes] = {
    0: bytes.fromhex("62eb804fcd9097fba80d"),
    1: bytes.fromhex("bd3bb20db1042daa78f2"),
    2: bytes.fromhex("3b9d4aba8303ada2c12e"),
    3: bytes.fromhex("e39cd085a83abb9c8db3"),
    4: bytes.fromhex("ca733d2ba37940dd8437"),
    5: bytes.fromhex("dba7926dc52e07c6e26f"),
    6: bytes.fromhex("340a6d44e257a58b134a"),
    7: bytes.fromhex("6f5cc46a4854b812490b"),
    8: bytes.fromhex("0bcb2b5ea766a1b4c4f0"),
    9: bytes.fromhex("6cd2e238b5b2785b9de1"),
    10: bytes.fromhex("94b8a93cad5ce040a48c"),
    11: bytes.fromhex("3daabfeb4fde3c207e14"),
    12: bytes.fromhex("2998f94abedc05efdfd6"),
    13: bytes.fromhex("632c974567870f91705c"),
    14: bytes.fromhex("0ce715fd93ee61cd2c64"),
    15: bytes.fromhex("9266bfa82dc7367b9159"),
    18: bytes.fromhex("7b3ae09a4a5193aad457"),
    19: bytes.fromhex("e82a4386dfa1f48be26a"),
}

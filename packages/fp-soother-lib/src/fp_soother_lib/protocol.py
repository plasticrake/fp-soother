"""
fp_soother_lib.protocol
========================
State encoding/decoding and command-frame construction for the SmartConnect
BLE protocol used by the Fisher-Price Deluxe Soother (dyw47). See
constants.py for UUIDs and bit-layout tables.

The 16-byte plaintext behind every CHAR_STATE read/CHAR_STATE_UPDATE write is
a single AES-128-CBC block (zero IV). A read's raw decrypted bytes are NOT
the state directly: the real firmware/native code checksums and descrambles
them first (see encryption.py's is_valid_state_decrypt()/
descramble_decrypted_state()) into a 9-byte logical state buffer, which
STATE_ATTRS below indexes with LSB-first bit packing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import fields as dc_fields
from datetime import datetime
from typing import ClassVar

from .constants import (
    AUX_ATTRS,
    CMD_PRESET,
    CMD_PROJECTOR_CUSTOM_SEQUENCE,
    DEFAULTS,
    INFRA_ATTRS,
    PRESET_ATTRS,
    PRESET_BYTE_LENGTH,
    RTC_UPDATE_COMMAND_ID,
    STATE_ATTRS,
    STATE_BYTE_LENGTH,
)

# ── Bit helpers ──────────────────────────────────────────────────────────────


def _get_bits(data: bytes | bytearray, byte_idx: int, bit_idx: int, length: int) -> int:
    if bit_idx + length > 8:
        word = data[byte_idx] | (data[byte_idx + 1] << 8)
    else:
        word = data[byte_idx]
    return (word >> bit_idx) & ((1 << length) - 1)


def _set_bits(
    data: bytearray, byte_idx: int, bit_idx: int, length: int, value: int
) -> None:
    mask = (1 << length) - 1
    v = value & mask
    if bit_idx + length > 8:
        word = data[byte_idx] | (data[byte_idx + 1] << 8)
        word = (word & ~(mask << bit_idx)) | (v << bit_idx)
        data[byte_idx] = word & 0xFF
        data[byte_idx + 1] = (word >> 8) & 0xFF
    else:
        data[byte_idx] = (data[byte_idx] & ~((mask << bit_idx) & 0xFF)) | (
            (v << bit_idx) & 0xFF
        )


# ── State dataclass ──────────────────────────────────────────────────────────


# fmt: off
@dataclass
class SootherState:
    """Decoded representation of the device's state.

    Field ranges reflect real, confirmed bit widths (e.g. volume_level is
    0-15, not 0-100) -- there is no known 0-100 abstraction in the real
    protocol, so this deliberately doesn't invent one.
    """

    play_mode:                              int = DEFAULTS["playMode"]
    sound_mode:                             int = DEFAULTS["soundMode"]          # 0-31, presets; semantic meaning per-index unknown
    volume_level:                           int = DEFAULTS["volumeLevel"]        # 0-15

    animal_projection_mode:                 int = DEFAULTS["animalProjectionMode"]
    animal_projection_brightness:           int = DEFAULTS["animalProjectionBrightness"]
    animal_projection_speed:                int = DEFAULTS["animalProjectionSpeed"]

    star_projection_sequence_mode:          int = DEFAULTS["starProjectionSequenceMode"]
    star_projection_custom_color0:          int = DEFAULTS["starProjectionCustomSequenceColor0"]
    star_projection_custom_color1:          int = DEFAULTS["starProjectionCustomSequenceColor1"]
    star_projection_custom_color2:          int = DEFAULTS["starProjectionCustomSequenceColor2"]
    star_projection_brightness:             int = DEFAULTS["starProjectionBrightness"]
    star_projection_speed:                  int = DEFAULTS["starProjectionSpeed"]

    nightlight_mode:                        int = DEFAULTS["nightlightMode"]      # 0/1
    nightlight_brightness:                  int = DEFAULTS["nightlightBrightness"]

    sleep_stages_mode:                      int = DEFAULTS["sleepStagesMode"]
    captive_playlist_selection:             int = DEFAULTS["captivePlaylistSelection"]
    soothe_playlist_selection:              int = DEFAULTS["soothePlaylistSelection"]

    sound_timer_setting:                    int = DEFAULTS["soundTimerSetting"]
    light_timer:                            int = DEFAULTS["lightTimer"]

    # Status / flags (read-only from device)
    transmission_mode:                      int = 0
    firmware_upgrade_status:                int = 0
    sound_mode_expiring:                    int = 0
    led_expiring:                           int = 0
    previous_animal_projection_mode:        int = DEFAULTS["previousAnimalProjectionMode"]
    previous_star_projection_sequence_mode: int = DEFAULTS["previousStarProjectionSequenceMode"]

    # From separate characteristics
    captive_sleep_stage_timer:              int | None = None
    soothe_sleep_stage_timer:               int | None = None
    sleep_stage_timer:                      int | None = None
    firmware_version:                       int | None = None
    firmware_bank:                          int | None = None
    firmware_api_level:                     int | None = None
    error:                                  int | None = None

    # Raw, pre-descramble 16-byte CHAR_STATE plaintext this was decoded from
    # -- needed by build_state_command()/build_rtc_update_command() for their
    # rolling-token/changeCmdAuthKey bytes. None for a freshly-constructed
    # SootherState that wasn't decoded from a real read. Excluded from repr()
    # since it's an implementation detail, not part of the logical state.
    raw_state: bytes | None = field(default=None, repr=False)

    # Maps the wire attribute name (as used in STATE_ATTRS) to this
    # dataclass's field name. A plain shared constant, not a dataclass field
    # (ClassVar keeps it out of dataclasses.fields()/__init__()/repr()/
    # compare(), so callers enumerating a SootherState's data fields don't
    # need to filter it out themselves).
    _ATTR_MAP: ClassVar[dict[str, str]] = {
        "transmissionMode":                     "transmission_mode",
        "playMode":                             "play_mode",
        "soundMode":                             "sound_mode",
        "volumeLevel":                           "volume_level",
        "animalProjectionMode":                  "animal_projection_mode",
        "animalProjectionBrightness":            "animal_projection_brightness",
        "animalProjectionSpeed":                 "animal_projection_speed",
        "starProjectionSequenceMode":            "star_projection_sequence_mode",
        "starProjectionCustomSequenceColor0":    "star_projection_custom_color0",
        "starProjectionCustomSequenceColor1":    "star_projection_custom_color1",
        "starProjectionCustomSequenceColor2":    "star_projection_custom_color2",
        "starProjectionBrightness":              "star_projection_brightness",
        "starProjectionSpeed":                   "star_projection_speed",
        "nightlightMode":                        "nightlight_mode",
        "nightlightBrightness":                  "nightlight_brightness",
        "sleepStagesMode":                       "sleep_stages_mode",
        "captivePlaylistSelection":              "captive_playlist_selection",
        "soothePlaylistSelection":               "soothe_playlist_selection",
        "firmwareUpgradeStatus":                 "firmware_upgrade_status",
        "soundModeExpiring":                     "sound_mode_expiring",
        "ledExpiring":                           "led_expiring",
        "soundTimerSetting":                     "sound_timer_setting",
        "lightTimer":                            "light_timer",
        "previousAnimalProjectionMode":          "previous_animal_projection_mode",
        "previousStarProjectionSequenceMode":    "previous_star_projection_sequence_mode",
    }

# fmt: on

# ── Encode / decode ──────────────────────────────────────────────────────────


def decode_state(
    raw_9byte: bytes | bytearray, raw_state: bytes | None = None
) -> SootherState:
    """Decode an already-descrambled 9(+)-byte state buffer into a SootherState.

    `raw_state`, if given, is stashed on the result for use by
    build_state_command()/build_rtc_update_command() later.
    """
    s = SootherState(raw_state=bytes(raw_state) if raw_state is not None else None)
    for attr_name, (bi, bit_i, length) in STATE_ATTRS.items():
        val = _get_bits(raw_9byte, bi, bit_i, length)
        field_name = s._ATTR_MAP.get(attr_name)
        if field_name:
            setattr(s, field_name, val)
    return s


def encode_state(state: SootherState) -> bytes:
    """Encode a SootherState back into its 9-byte descrambled form."""
    buf = bytearray(STATE_BYTE_LENGTH)
    attr_map_inv = {v: k for k, v in state._ATTR_MAP.items()}
    for field_obj in dc_fields(state):
        attr_name = attr_map_inv.get(field_obj.name)
        if attr_name and attr_name in STATE_ATTRS:
            bi, bit_i, length = STATE_ATTRS[attr_name]
            val = getattr(state, field_obj.name) or 0
            _set_bits(buf, bi, bit_i, length, val)
    return bytes(buf)


def decode_aux_state(raw: bytes | bytearray, state: SootherState) -> None:
    """Update *state* in place with values from the auxState characteristic."""
    field_map = {
        "captiveSleepStageTimer": "captive_sleep_stage_timer",
        "sootheSleepStageTimer": "soothe_sleep_stage_timer",
        "sleepStageTimer": "sleep_stage_timer",
    }
    for attr_name, (bi, bit_i, length) in AUX_ATTRS.items():
        fn = field_map.get(attr_name)
        if fn:
            setattr(state, fn, _get_bits(raw, bi, bit_i, length))


def decode_infra_state(raw: bytes | bytearray, state: SootherState) -> None:
    """Update *state* with firmware info from the infrastructureState characteristic."""
    field_map = {
        "error": "error",
        "firmwareVersion": "firmware_version",
        "firmwareBank": "firmware_bank",
        "firmwareApiLevel": "firmware_api_level",
        "crc": None,
    }
    for attr_name, info in INFRA_ATTRS.items():
        bi, length = info["byte_index"], info["length"]
        if bi + length > len(raw):
            continue
        fn = field_map.get(attr_name)
        if fn:
            setattr(state, fn, int.from_bytes(raw[bi : bi + length], "little"))


# ── Command frame construction ───────────────────────────────────────────────
#
# Every command is a 16-byte plaintext frame with three rolling-token bytes
# and, for simple attribute commands, a value + command-id byte. The FULL
# frame (not a short logical payload) is what encryption.encrypt_command()
# expects -- these functions produce it directly.


def build_state_command(command_id: int, value: int, prev_raw_state: bytes) -> bytes:
    """
    Build the 16-byte plaintext for a simple attribute-set command.

    Three bytes from the most recently read (raw, pre-descramble) CHAR_STATE
    are embedded as replay-protection rolling tokens:
      cmd[1] = prev_raw_state[4]
      cmd[4] = prev_raw_state[15]
      cmd[5] = prev_raw_state[6]
      cmd[9] = prev_raw_state[15]  (repeated)
      cmd[11] = value
      cmd[13] = command_id
    All other bytes are 0x00.
    """
    cmd = bytearray(16)
    cmd[1] = prev_raw_state[4]
    cmd[4] = prev_raw_state[15]
    cmd[5] = prev_raw_state[6]
    cmd[9] = prev_raw_state[15]
    cmd[11] = value & 0xFF
    cmd[13] = command_id & 0xFF
    return bytes(cmd)


def build_custom_color_sequence_command(
    color0: int, color1: int, color2: int, prev_raw_state: bytes
) -> bytes:
    """Pack 3 custom sequence colors (3 bits each) into command ID 9."""
    # 9-bit packed value: color0 | (color1 << 3) | (color2 << 6)
    value_low = (color0 & 0x7) | ((color1 & 0x7) << 3) | ((color2 & 0x3) << 6)
    value_high = (color2 >> 2) & 0x1

    cmd = bytearray(16)
    cmd[1] = prev_raw_state[4]
    cmd[4] = prev_raw_state[15]
    cmd[5] = prev_raw_state[6]
    cmd[9] = prev_raw_state[15]
    cmd[11] = value_low
    cmd[12] = value_high
    cmd[13] = CMD_PROJECTOR_CUSTOM_SEQUENCE
    return bytes(cmd)


def build_rtc_update_command(
    prev_raw_state: bytes,
    weekday: int | None = None,
    total_seconds: int | None = None,
) -> bytes:
    """
    Build the 16-byte plaintext for the rtcUpdate (clock-sync) command.

    This is a REQUIRED, one-time step right after a fresh pairing -- the
    device's firmware waits specifically for this command (not just any
    accepted write) before it leaves pairing mode. It's otherwise an
    ordinary command usable any time.

    weekday: 0=Monday..6=Sunday (defaults to the current local day).
    total_seconds: seconds since local midnight (defaults to now).
    """
    if weekday is None or total_seconds is None:
        local_tz = datetime.now().astimezone().tzinfo
        now = datetime.now(tz=local_tz)
        if weekday is None:
            weekday = now.weekday()
        if total_seconds is None:
            total_seconds = now.hour * 3600 + now.minute * 60 + now.second

    byte_mid = (total_seconds >> 16) & 0xFF
    byte_low = (total_seconds >> 8) & 0xFF

    cmd = bytearray(16)
    cmd[1] = prev_raw_state[4]
    cmd[4] = prev_raw_state[15]
    cmd[5] = prev_raw_state[6]
    cmd[9] = prev_raw_state[15]
    cmd[0] = (byte_mid & 0x1F) << 3
    cmd[7] = (byte_low & 0x1F) << 3
    cmd[10] = (byte_low >> 5) & 0x07
    cmd[11] = weekday & 0x07
    cmd[13] = RTC_UPDATE_COMMAND_ID
    # Bytes 3, 8, 12, 15: confirmed NOT to matter for firmware acceptance
    # (live-tested with these exact placeholder values and with the real
    # app's own differing values at the same positions -- both worked).
    cmd[3] = 0x94
    cmd[8] = 0x01
    cmd[12] = 0x88
    cmd[15] = 0x05
    return bytes(cmd)


def build_preset_command(state: SootherState, prev_raw_state: bytes) -> bytes:
    """
    Build the 16-byte plaintext CMD_PRESET (22) composite command, which
    applies EVERY settable attribute in *state* in a single write -- this is
    what the real app sends when applying a saved "favorite"/preset, instead
    of one command per attribute.

    Derived by reverse-engineering the
    real app's command-building pipeline (Blutter decompile of
    fw_processor.dart/smart_model.dart/smart_command.dart in the sibling
    soother_apk project), not from a live capture -- unlike build_state_command(),
    which every confirmed-working code path in this project (nightlight
    control, etc.) has exercised. Specifically:

    1. SmartCommand.append(value, length) is a plain LSB-first bit-packer: it
       accumulates bits into a running buffer and flushes full bytes as they
       fill. SmartModel.getPresetCommand() calls it once per entry of
       presetStructureWithValues() -- one call per attribute in PRESET_ATTRS,
       in that exact order -- which is why dyw47.json's "presets" section
       (PRESET_ATTRS here) already IS the resulting byte/bit layout.
    2. SmartCommand.getBytes() prepends the raw command_id (22) as a single
       byte before the packed attribute bytes: the real "logical command" is
       `[command_id] + <8 packed attribute bytes>` = 9 bytes.
    3. That 9-byte logical command is final-framed by the same
       scramble/positioning formula that produces build_state_command()'s
       and build_rtc_update_command()'s frames: a fixed mapping of logical
       payload bytes + the changeCmdAuthKey derived from prev_raw_state onto
       out[0..14] of the 16-byte output -- build_state_command() is provably
       that same formula's output on bytes 0-14 for the special case where
       only pt[0] (command_id) and pt[1] (value) are non-zero (it never
       touches byte 15 at all), so the positions below are that formula
       inlined, this time exercising pt[2]..pt[8] for the first time in this
       project. out[15] is NOT part of that proven mapping -- see below.

    Positions sourced from pt[9]/pt[10]/pt[11] (out-of-bounds for this
    9-byte logical command in the original native code, i.e. genuinely
    uninitialized stack memory there) are zero-filled here as the best
    available guess. out[15] is a separate, unconfirmed assumption layered
    on top of the proven out[0..14] mapping: build_state_command() leaves
    its own byte 15 at 0x00 always (it is real, live-tested, and never sets
    it), so nothing here establishes what byte 15 should be for a command
    frame. This function instead forces out[15] = out[10] ^ out[4] to
    satisfy the same self-consistency checksum encryption.
    is_valid_state_decrypt() checks on reads (raw[10] == raw[15] ^ raw[4]) --
    plausible if the device applies the same checksum symmetrically to
    writes, but not confirmed, and not what build_state_command() does.
    """
    packed = bytearray(PRESET_BYTE_LENGTH)
    attr_map_inv = {v: k for k, v in state._ATTR_MAP.items()}
    for field_obj in dc_fields(state):
        attr_name = attr_map_inv.get(field_obj.name)
        if attr_name and attr_name in PRESET_ATTRS:
            bi, bit_i, length = PRESET_ATTRS[attr_name]
            val = getattr(state, field_obj.name) or 0
            _set_bits(packed, bi, bit_i, length, val)

    pt = bytearray(16)
    pt[0] = CMD_PRESET
    pt[1 : 1 + PRESET_BYTE_LENGTH] = packed
    # pt[9:16] stay zero -- out-of-bounds positions for this 9-byte logical
    # command, see docstring.

    cak0 = prev_raw_state[6]
    cak1 = prev_raw_state[15]
    cak2 = prev_raw_state[4]

    out = bytearray(16)
    out[0] = pt[2]
    out[1] = cak2
    out[2] = pt[7]
    out[3] = pt[10]
    out[4] = cak1
    out[5] = cak0
    out[6] = pt[6]
    out[7] = pt[3]
    out[8] = pt[11]
    out[9] = pt[6] ^ cak1
    out[10] = pt[4]
    out[11] = pt[1]
    out[12] = pt[8]
    out[13] = pt[0]
    out[14] = pt[5]
    out[15] = out[10] ^ out[4]
    return bytes(out)

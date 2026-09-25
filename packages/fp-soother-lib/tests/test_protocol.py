import pytest

from fp_soother_lib import protocol
from fp_soother_lib.constants import (
    AUX_ATTRS,
    CMD_PRESET,
    CMD_PROJECTOR_CUSTOM_SEQUENCE,
    INFRA_ATTRS,
    PRESET_ATTRS,
    RTC_UPDATE_COMMAND_ID,
    STATE_ATTRS,
)
from fp_soother_lib.protocol import (
    SootherState,
    build_custom_color_sequence_command,
    build_preset_command,
    build_rtc_update_command,
    build_state_command,
    decode_aux_state,
    decode_infra_state,
    decode_state,
    encode_state,
    frame_command,
)

# Maps PRESET_ATTRS' packed-byte index (0-7) to the byte index it lands at in
# build_preset_command()'s final 16-byte frame -- the inverse of that
# function's pt[1..8] = packed[0..7] followed by its out[...] = pt[...]
# scramble.
PRESET_PACKED_BYTE_TO_OUT_INDEX = [11, 0, 7, 10, 14, 6, 2, 12]

# All logical fields the 9-byte state buffer actually carries (excludes
# "connectionState", which has no SootherState field).
ATTR_ITEMS = list(SootherState._ATTR_MAP.items())


@pytest.mark.parametrize(
    "attr_name,field_name", ATTR_ITEMS, ids=[a for a, _ in ATTR_ITEMS]
)
def test_bit_field_isolated_roundtrip(attr_name, field_name):
    """Setting a single field to its max value and round-tripping through
    encode_state/decode_state must affect only that field -- this pins down
    STATE_ATTRS' byte/bit offsets against any accidental overlap."""
    _bi, _bit_i, length = STATE_ATTRS[attr_name]
    max_val = (1 << length) - 1

    state = SootherState()
    for fn in SootherState._ATTR_MAP.values():
        setattr(state, fn, 0)
    setattr(state, field_name, max_val)

    decoded = decode_state(encode_state(state))

    for fn in SootherState._ATTR_MAP.values():
        expected = max_val if fn == field_name else 0
        assert getattr(decoded, fn) == expected, fn


def test_decode_state_stashes_raw_state():
    raw_state = bytes(range(16))
    state = decode_state(bytes(protocol.STATE_BYTE_LENGTH), raw_state=raw_state)
    assert state.raw_state == raw_state


def test_decode_state_raw_state_defaults_to_none():
    state = decode_state(bytes(protocol.STATE_BYTE_LENGTH))
    assert state.raw_state is None


def test_build_state_command_byte_placement():
    prev_raw_state = bytes(range(16))
    cmd = build_state_command(command_id=7, value=200, prev_raw_state=prev_raw_state)

    assert len(cmd) == 16
    assert cmd[1] == prev_raw_state[4]
    assert cmd[4] == prev_raw_state[15]
    assert cmd[5] == prev_raw_state[6]
    assert cmd[9] == prev_raw_state[15]
    assert cmd[11] == 200 & 0xFF
    assert cmd[13] == 7

    untouched = set(range(16)) - {1, 4, 5, 9, 11, 13}
    for i in untouched:
        assert cmd[i] == 0, i


def test_build_state_command_masks_value_and_command_id_to_a_byte():
    prev_raw_state = bytes(16)
    cmd = build_state_command(
        command_id=0x1FF, value=0x1FF, prev_raw_state=prev_raw_state
    )
    assert cmd[11] == 0xFF
    assert cmd[13] == 0xFF


def test_build_custom_color_sequence_command_packs_colors():
    prev_raw_state = bytes(16)
    color0, color1, color2 = 7, 5, 7
    cmd = build_custom_color_sequence_command(color0, color1, color2, prev_raw_state)

    expected_low = (color0 & 0x7) | ((color1 & 0x7) << 3) | ((color2 & 0x3) << 6)
    expected_high = (color2 >> 2) & 0x1

    assert cmd[11] == expected_low
    assert cmd[12] == expected_high
    assert cmd[13] == CMD_PROJECTOR_CUSTOM_SEQUENCE


def test_build_custom_color_sequence_command_shares_rolling_tokens():
    prev_raw_state = bytes(range(16))
    cmd = build_custom_color_sequence_command(1, 2, 3, prev_raw_state)
    assert cmd[1] == prev_raw_state[4]
    assert cmd[4] == prev_raw_state[15]
    assert cmd[5] == prev_raw_state[6]
    assert cmd[9] == prev_raw_state[15]


def test_build_rtc_update_command_explicit_time():
    prev_raw_state = bytes(range(16))
    weekday = 2
    total_seconds = 3661  # 01:01:01

    cmd = build_rtc_update_command(
        prev_raw_state, weekday=weekday, total_seconds=total_seconds
    )

    byte_mid = (total_seconds >> 16) & 0xFF
    byte_low = (total_seconds >> 8) & 0xFF

    assert cmd[1] == prev_raw_state[4]
    assert cmd[4] == prev_raw_state[15]
    assert cmd[5] == prev_raw_state[6]
    assert cmd[9] == prev_raw_state[15]
    assert cmd[0] == (byte_mid & 0x1F) << 3
    assert cmd[7] == (byte_low & 0x1F) << 3
    assert cmd[10] == (byte_low >> 5) & 0x07
    assert cmd[11] == weekday & 0x07
    assert cmd[13] == RTC_UPDATE_COMMAND_ID
    assert cmd[3] == 0x94
    assert cmd[8] == 0x01
    assert cmd[12] == 0x88
    assert cmd[15] == 0x05


def test_build_rtc_update_command_masks_weekday():
    cmd = build_rtc_update_command(bytes(16), weekday=15, total_seconds=0)
    assert cmd[11] == 15 & 0x07


def test_build_rtc_update_command_defaults_to_now():
    """With no explicit weekday/total_seconds, the command must still be a
    well-formed 16-byte frame with a plausible weekday/time encoded."""
    prev_raw_state = bytes(range(16))
    cmd = build_rtc_update_command(prev_raw_state)

    assert len(cmd) == 16
    assert cmd[13] == RTC_UPDATE_COMMAND_ID
    assert 0 <= (cmd[11] & 0x07) <= 6
    assert cmd[1] == prev_raw_state[4]
    assert cmd[4] == prev_raw_state[15]


def test_build_preset_command_frame_fixed_positions():
    """Structural invariants that hold regardless of *state*'s content:
    command id, rolling tokens, and the forced checksum byte."""
    prev_raw_state = bytes(range(16))
    cmd = build_preset_command(SootherState(), prev_raw_state)

    assert len(cmd) == 16
    assert cmd[13] == CMD_PRESET
    assert cmd[1] == prev_raw_state[4]
    assert cmd[4] == prev_raw_state[15]
    assert cmd[5] == prev_raw_state[6]
    assert cmd[9] == cmd[6] ^ prev_raw_state[15]
    assert cmd[15] == cmd[10] ^ cmd[4]


@pytest.mark.parametrize(
    "attr_name", list(PRESET_ATTRS.keys()), ids=list(PRESET_ATTRS.keys())
)
def test_build_preset_command_bit_field_isolated(attr_name):
    """Setting a single preset-eligible field to its max value must affect
    only that field's bits in the packed preset payload -- pins down
    PRESET_ATTRS' byte/bit offsets (and build_preset_command()'s packed ->
    frame scramble) against accidental overlap."""
    _bi, _bit_i, length = PRESET_ATTRS[attr_name]
    max_val = (1 << length) - 1
    field_name = SootherState._ATTR_MAP[attr_name]

    state = SootherState()
    for fn in SootherState._ATTR_MAP.values():
        setattr(state, fn, 0)
    setattr(state, field_name, max_val)

    cmd = build_preset_command(state, bytes(16))
    packed = bytes(cmd[out_idx] for out_idx in PRESET_PACKED_BYTE_TO_OUT_INDEX)

    for other_attr, (obi, obit_i, olength) in PRESET_ATTRS.items():
        expected = max_val if other_attr == attr_name else 0
        assert protocol._get_bits(packed, obi, obit_i, olength) == expected, other_attr


# decode_aux_state()'s wire attribute name -> SootherState field name, mirroring
# the (unexported) field_map inside decode_aux_state() itself.
AUX_FIELD_MAP = {
    "captiveSleepStageTimer": "captive_sleep_stage_timer",
    "sootheSleepStageTimer": "soothe_sleep_stage_timer",
    "sleepStageTimer": "sleep_stage_timer",
}


@pytest.mark.parametrize(
    "attr_name", list(AUX_ATTRS.keys()), ids=list(AUX_ATTRS.keys())
)
def test_decode_aux_state_bit_field_isolated(attr_name):
    """Setting a single AUX_ATTRS field to its max value in the raw buffer
    must affect only that field on the SootherState -- pins down AUX_ATTRS'
    byte/bit offsets against accidental overlap, same as STATE_ATTRS/
    PRESET_ATTRS above."""
    bi, bit_i, length = AUX_ATTRS[attr_name]
    max_val = (1 << length) - 1

    buf = bytearray(5)
    protocol._set_bits(buf, bi, bit_i, length, max_val)

    state = SootherState()
    decode_aux_state(buf, state)

    for other_attr, field_name in AUX_FIELD_MAP.items():
        expected = max_val if other_attr == attr_name else 0
        assert getattr(state, field_name) == expected, other_attr


def test_decode_infra_state_extracts_little_endian_fields():
    raw = bytes([0x01, 0x34, 0x12, 0x07, 0x00, 0x09, 0xCD, 0xAB])
    state = SootherState()

    decode_infra_state(raw, state)

    assert state.error == 0x01
    assert state.firmware_version == 0x1234  # little-endian 2-byte field
    assert state.firmware_bank == 0x07
    assert state.firmware_api_level == 0x09


def test_decode_infra_state_skips_fields_out_of_bounds():
    """A short buffer (e.g. a firmware that doesn't populate every field)
    must skip fields it doesn't cover instead of raising or reading garbage."""
    raw = bytes(4)  # covers error/firmwareVersion/firmwareBank only
    assert INFRA_ATTRS["firmwareApiLevel"]["byte_index"] + 1 > len(raw)
    state = SootherState()

    decode_infra_state(raw, state)

    assert state.error == 0
    assert state.firmware_version == 0
    assert state.firmware_bank == 0
    assert state.firmware_api_level is None


# ── Shared-key (firmware < 9) framing ────────────────────────────────────────


def test_frame_command_shared_key_layout():
    """The native encrypt core's shared-key branch, position by position."""
    prev_raw_state = bytes(range(0x10, 0x20))
    pt = bytes(range(0xA0, 0xAC))
    c0, c1, c2 = prev_raw_state[0], prev_raw_state[6], prev_raw_state[5]
    cmd = frame_command(pt, prev_raw_state, shared_key=True)
    assert list(cmd) == [
        pt[8], c1, pt[7], pt[11], c2, c0, pt[6], pt[1],
        pt[5], c0 ^ c2, pt[3], pt[10], pt[9], pt[4], pt[0], pt[2],
    ]  # fmt: skip


def test_frame_command_rejects_oversized_payload():
    with pytest.raises(ValueError):
        frame_command(bytes(13), bytes(16))


def test_build_state_command_shared_key_byte_placement():
    prev_raw_state = bytes(range(16))
    cmd = build_state_command(7, 200, prev_raw_state, shared_key=True)
    assert cmd[14] == 7
    assert cmd[7] == 200
    assert cmd[1] == prev_raw_state[6]
    assert cmd[4] == prev_raw_state[5]
    assert cmd[5] == prev_raw_state[0]
    assert cmd[9] == prev_raw_state[0] ^ prev_raw_state[5]
    for i in set(range(16)) - {1, 4, 5, 7, 9, 14}:
        assert cmd[i] == 0, i


def test_build_rtc_update_command_shared_key_places_command_id():
    cmd = build_rtc_update_command(
        bytes(16), weekday=3, total_seconds=0, shared_key=True
    )
    assert cmd[14] == RTC_UPDATE_COMMAND_ID
    assert cmd[7] == 3


def test_build_preset_command_shared_key_is_plain_frame():
    """Same packed payload as the unique-key frame, framed with the
    shared-key layout and no unique-key byte-15 checksum override."""
    state = SootherState(volume_level=9, nightlight_mode=1, sound_mode=13)
    unique = build_preset_command(state, bytes(16))
    packed = bytes(unique[i] for i in PRESET_PACKED_BYTE_TO_OUT_INDEX)
    shared = build_preset_command(state, bytes(16), shared_key=True)
    assert shared == frame_command(
        bytes([CMD_PRESET]) + packed, bytes(16), shared_key=True
    )

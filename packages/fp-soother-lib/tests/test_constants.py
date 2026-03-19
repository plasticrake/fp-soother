from fp_soother_lib.constants import (
    DEFAULTS,
    RAW_TO_STATE_MAP,
    STATE_ATTRS,
    STATE_BYTE_LENGTH,
)


def test_state_attrs_fit_within_state_buffer():
    for name, (byte_idx, bit_idx, length) in STATE_ATTRS.items():
        assert 0 <= byte_idx < STATE_BYTE_LENGTH, name
        assert 0 <= bit_idx < 8, name
        assert 1 <= length <= 16, name
        end_bit = bit_idx + length
        last_byte = byte_idx + (1 if end_bit > 8 else 0)
        assert last_byte < STATE_BYTE_LENGTH, name


def test_defaults_keys_are_known_state_attrs():
    assert set(DEFAULTS).issubset(STATE_ATTRS)


def test_raw_to_state_map_is_12_distinct_raw_byte_indices():
    assert len(RAW_TO_STATE_MAP) == 12
    assert len(set(RAW_TO_STATE_MAP)) == 12
    assert all(0 <= i < 16 for i in RAW_TO_STATE_MAP)

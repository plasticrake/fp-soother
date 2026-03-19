from fp_soother_lib.key_tables import KEY_REQUEST_KEYS, KEY_REQUEST_TABLES, PAIRING_KEYS


def test_pairing_keys_are_16_bytes():
    for peripheral_type, key in PAIRING_KEYS.items():
        assert len(key) == 16, peripheral_type


def test_key_request_keys_are_16_bytes():
    for peripheral_type, key in KEY_REQUEST_KEYS.items():
        assert len(key) == 16, peripheral_type


def test_key_request_tables_are_10_bytes():
    for peripheral_type, table in KEY_REQUEST_TABLES.items():
        assert len(table) == 10, peripheral_type


def test_same_peripheral_types_across_all_tables():
    assert set(PAIRING_KEYS) == set(KEY_REQUEST_KEYS) == set(KEY_REQUEST_TABLES)


def test_dyw47_peripheral_type_present():
    # Peripheral type 11 (dyw47) is the only one validated against real
    # hardware -- see key_tables.py's module docstring.
    assert 11 in PAIRING_KEYS
    assert 11 in KEY_REQUEST_KEYS
    assert 11 in KEY_REQUEST_TABLES

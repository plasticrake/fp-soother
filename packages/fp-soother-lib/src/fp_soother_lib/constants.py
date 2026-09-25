"""
BLE UUIDs and command constants for the Fisher Price Deluxe Soother (dyw47).

Protocol: SmartConnect (legacy)
Legacy type: 11
Requires pairing: yes

"""

# fmt: off

# ── BLE identifiers ──────────────────────────────────────────────────────────

SERVICE_UUID            = "E2BCFFF0-39B2-A193-C63C-8EF1BB786D55"

CHAR_STATE              = "E2BCFFF1-39B2-A193-C63C-8EF1BB786D55"  # read/notify - current device state
CHAR_STATE_UPDATE       = "E2BCFFF2-39B2-A193-C63C-8EF1BB786D55"  # write - send encrypted commands
CHAR_INFRA_UPDATE       = "E2BCFFF4-39B2-A193-C63C-8EF1BB786D55"  # write - infrastructure / pairing commands
CHAR_INFRA_STATE        = "E2BCFFF5-39B2-A193-C63C-8EF1BB786D55"  # read/notify - firmware version, error
CHAR_AUX_STATE          = "E2BCFFF8-39B2-A193-C63C-8EF1BB786D55"  # read/notify - sleep-stage timers
CHAR_UNIQUE_ID          = "E2BCFFF9-39B2-A193-C63C-8EF1BB786D55"  # read - static device-id string
CHAR_OTA                = "E2BCFFF6-39B2-A193-C63C-8EF1BB786D55"  # write - OTA firmware update

# The real app subscribes to notifications on all five of these before doing
# anything else (confirmed via a live Frida capture of
# -[CBPeripheral setNotifyValue:forCharacteristic:]).
NOTIFY_CHARACTERISTICS = [
    CHAR_STATE, CHAR_INFRA_UPDATE, CHAR_INFRA_STATE, CHAR_AUX_STATE, CHAR_UNIQUE_ID,
]

# ── Native library ───────────────────────────────────────────────────────────

PERIPHERAL_TYPE = 11          # dyw47 legacy_type
KEY_SIZE        = 16          # AES-128 key length in bytes

# dyw47.json's encryption_methods: firmware at or above this uses the
# per-device "uniqueKey" exchange (pairing.pair()); anything older uses the
# static "sharedKey" (key_tables.SHARED_ENCRYPTION_KEY) with no key exchange,
# and a different CHAR_STATE/command byte layout (see encryption.py).
UNIQUE_KEY_MIN_FIRMWARE_VERSION = 9

# ── State command IDs (updateCommandId in dyw47.json) ───────────────────────
CMD_PLAY_MODE                        = 1
CMD_SOUND_MODE                       = 2
CMD_VOLUME_LEVEL                     = 3
CMD_ANIMAL_PROJECTION_MODE           = 4
CMD_NIGHTLIGHT_MODE                  = 5
CMD_ANIMAL_PROJECTION_BRIGHTNESS     = 6
CMD_ANIMAL_PROJECTION_SPEED          = 7
CMD_STAR_PROJECTION_SEQUENCE_MODE    = 8
CMD_PROJECTOR_CUSTOM_SEQUENCE        = 9
CMD_STAR_PROJECTION_BRIGHTNESS       = 10
CMD_STAR_PROJECTION_SPEED            = 11
CMD_NIGHTLIGHT_BRIGHTNESS            = 12
CMD_SLEEP_STAGES_MODE                = 13
CMD_CAPTIVE_SLEEP_STAGE_TIMER        = 14
CMD_SOOTHE_SLEEP_STAGE_TIMER         = 15
CMD_SLEEP_STAGE_TIMER                = 16
CMD_SOUND_TIMER_SETTING              = 17
CMD_LIGHT_TIMER                      = 18
CMD_CAPTIVE_PLAYLIST_SELECTION       = 20
CMD_SOOTHE_PLAYLIST_SELECTION        = 21
CMD_PRESET                           = 22  # composite multi-attribute command, see PRESET_ATTRS
RTC_UPDATE_COMMAND_ID                = 26  # clock sync -- required once, right after pairing

# ── Infrastructure command IDs ───────────────────────────────────────────────
INFRA_CMD_ADVERTISEMENT_UPDATE       = 5
INFRA_CMD_FIRMWARE_UPDATE_START      = 6
INFRA_CMD_FIRMWARE_UPDATE_CANCEL     = 7
INFRA_CMD_FIRMWARE_VERIFY            = 8
INFRA_CMD_FIRMWARE_REBOOT            = 9
INFRA_CMD_CONNECTION_PARAMS_UPDATE   = 11

# ── Attribute layout in the 9-byte (post-descramble) state payload ──────────
#
# Each entry: (byte_index, bit_index, length_in_bits), LSB-first within byte.
# Fields crossing a byte boundary use a little-endian 16-bit read.
STATE_ATTRS = {
    "transmissionMode":                     (0, 0, 2),
    "playMode":                             (0, 2, 1),
    "soundMode":                            (0, 3, 5),
    "volumeLevel":                          (1, 0, 4),
    "animalProjectionMode":                 (1, 4, 2),
    "animalProjectionBrightness":           (1, 6, 4),
    "animalProjectionSpeed":                (2, 2, 2),
    "starProjectionSequenceMode":           (2, 4, 3),
    "starProjectionCustomSequenceColor0":   (2, 7, 3),
    "starProjectionCustomSequenceColor1":   (3, 2, 3),
    "starProjectionCustomSequenceColor2":   (3, 5, 3),
    "starProjectionBrightness":             (4, 0, 3),
    "starProjectionSpeed":                  (4, 3, 2),
    "nightlightMode":                       (4, 5, 1),
    "nightlightBrightness":                 (4, 6, 3),
    "sleepStagesMode":                      (5, 1, 2),
    "captivePlaylistSelection":             (5, 3, 5),
    "soothePlaylistSelection":              (6, 0, 5),
    "connectionState":                      (6, 5, 2),
    "firmwareUpgradeStatus":                (6, 7, 1),
    "soundModeExpiring":                    (7, 0, 1),
    "ledExpiring":                          (7, 1, 1),
    "soundTimerSetting":                    (7, 2, 4),
    "lightTimer":                           (7, 6, 4),
    "previousAnimalProjectionMode":         (8, 2, 2),
    "previousStarProjectionSequenceMode":   (8, 4, 3),
}

STATE_BYTE_LENGTH = 9

# Maps 9-byte state buffer index -> position in the 16-byte raw AES-CBC-decrypted
# CHAR_STATE plaintext. Ghidra-verified from the real native decrypt primitive's
# verifyPivot==true branch and cross-validated byte-for-byte against a real
# live capture of the app's own decrypt output: the raw decrypted block is
# NOT the state directly -- it must be descrambled first (see crypto.py's
# is_valid_state_decrypt()/descramble_decrypted_state()). state[i] = raw[MAP[i]].
RAW_TO_STATE_MAP = [8, 7, 11, 14, 12, 1, 5, 2, 0, 9, 13, 3]

# The same map for a shared-key (firmware < UNIQUE_KEY_MIN_FIRMWARE_VERSION)
# device: the native decrypt core's other (shared-key) branch, read from its
# arm64 disassembly and confirmed live against a firmware-8 dyw47. Entries
# 9-11 are random padding on that firmware, not stable zeros.
SHARED_KEY_RAW_TO_STATE_MAP = [8, 2, 9, 1, 13, 4, 12, 10, 7, 11, 15, 14]

# Attribute layout inside the CMD_PRESET (22) composite payload -- a
# "preset"/"favorite" apply is a single command bundling every settable
# attribute at once, instead of one command per attribute. Layout taken
# directly from dyw47.json's "presets" section (each entry's "commandBits"),
# NOT the same byte/bit positions as STATE_ATTRS above -- this is a separate,
# denser 8-byte packing with no gaps for read-only fields (transmissionMode,
# connectionState, the *Expiring flags, etc). Same (byte_index, bit_index,
# length_in_bits) shape and LSB-first convention as STATE_ATTRS, so it reuses
# protocol.py's _get_bits()/_set_bits(). Traced via a Blutter decompile of the
# real app's SmartCommand.append()/SmartModel.getPresetCommand(): the app
# appends each of these 21 fields' bits, in this exact order, into a running
# bit-packer -- confirming the JSON's byte/bit positions are simply the
# packer's natural output, not an independently-chosen layout. See
# protocol.py's build_preset_command() docstring for how this packed payload
# gets embedded into the final 16-byte command frame.
PRESET_ATTRS = {
    "playMode":                             (0, 0, 1),
    "soundMode":                            (0, 1, 5),
    "volumeLevel":                          (0, 6, 4),
    "animalProjectionMode":                 (1, 2, 2),
    "animalProjectionBrightness":           (1, 4, 4),
    "animalProjectionSpeed":                (2, 0, 2),
    "starProjectionSequenceMode":           (2, 2, 3),
    "starProjectionCustomSequenceColor0":   (2, 5, 3),
    "starProjectionCustomSequenceColor1":   (3, 0, 3),
    "starProjectionCustomSequenceColor2":   (3, 3, 3),
    "starProjectionBrightness":             (3, 6, 3),
    "starProjectionSpeed":                  (4, 1, 2),
    "nightlightMode":                       (4, 3, 1),
    "nightlightBrightness":                 (4, 4, 3),
    "sleepStagesMode":                      (4, 7, 2),
    "captivePlaylistSelection":             (5, 1, 5),
    "soothePlaylistSelection":              (5, 6, 5),
    "soundTimerSetting":                    (6, 3, 4),
    "lightTimer":                           (6, 7, 4),
    "previousAnimalProjectionMode":         (7, 3, 2),
    "previousStarProjectionSequenceMode":   (7, 5, 3),
}

PRESET_BYTE_LENGTH = 8  # 21 fields above sum to exactly 64 bits

# Attributes inside the auxState characteristic. Despite its own bit-layout
# table here, on the wire this is framed identically to CHAR_STATE: a 16-byte
# AES-128-CBC block (same session key) that must pass the same checksum and
# go through the same descramble_decrypted_state() byte permutation before
# these byte/bit offsets apply.
AUX_ATTRS = {
    "captiveSleepStageTimer":  (0, 2, 4),
    "sootheSleepStageTimer":   (2, 5, 4),
    "sleepStageTimer":         (4, 4, 4),
}

# Attributes in infrastructureState (raw byte access, not bit-packed)
INFRA_ATTRS = {
    "error":          {"byte_index": 0, "length": 1},
    "firmwareVersion":{"byte_index": 1, "length": 2},
    "firmwareBank":   {"byte_index": 3, "length": 1},
    "firmwareApiLevel":{"byte_index": 5, "length": 1},
    "crc":            {"byte_index": 6, "length": 2},
}

# ── Default attribute values ─────────────────────────────────────────────────
DEFAULTS = {
    "playMode":                            0,
    "soundMode":                           0,
    "volumeLevel":                         3,
    "animalProjectionMode":                0,
    "animalProjectionBrightness":          8,
    "animalProjectionSpeed":               1,
    "starProjectionSequenceMode":          0,
    "starProjectionCustomSequenceColor0":  0,
    "starProjectionCustomSequenceColor1":  0,
    "starProjectionCustomSequenceColor2":  0,
    "starProjectionBrightness":            6,
    "starProjectionSpeed":                 1,
    "nightlightMode":                      0,
    "nightlightBrightness":                3,
    "sleepStagesMode":                     0,
    "captivePlaylistSelection":            31,
    "soothePlaylistSelection":             31,
    "soundTimerSetting":                   15,
    "lightTimer":                          15,
    "previousAnimalProjectionMode":        0,
    "previousStarProjectionSequenceMode":  0,
}

# ── Connection state values (connectionState attribute) ──────────────────────
CONN_STATE_DISCONNECTED = 0
CONN_STATE_CONNECTED    = 1
CONN_STATE_PAIRING      = 2
CONN_STATE_PAIRED       = 3

CUSTOM_COLORS = {
    "off": 0,
    "red": 1,
    "orange": 2,
    "yellow": 3,
    "green": 4,
    "blue": 5,
    "purple": 6,
}

STAR_PROJECTION_SEQUENCES = {
    "rainbow":      1,
    "cool_colors":  2,
    "warm_colors":  3,
    "custom":       4,
}

STAR_PROJECTION_SPEEDS = {
    "slow":      0,
    "normal":    1,
    "fast":      2,
    "very_fast": 3,
}

ANIMAL_PROJECTION_MODES = {
    "on":         1,
    "lighthouse": 2,
    "candle":     3,
}

ANIMAL_PROJECTION_SPEEDS = {
    "slow": 1,
    "fast": 2,
}

SLEEP_STAGES_MODES = {
    "off":    0,
    "settle": 1,
    "soothe": 2,
    "sleep":  3,
}

SOUND_MODES = {
    "pink_noise":                1,
    "brown_noise":               2,
    "womb":                      3,
    "ocean":                     4,
    "nature":                    5,
    "wind":                      6,
    "its_raining_its_pouring":   7,
    "aurora":                    8,
    "six_little_ducks":          9,
    "frere_jacques":             10,
    "brahms_lullaby":            11,
    "somewhere":                 12,
    "daylight":                  13,
    "dreaming_dawn":             14,
    "motions":                   15,
    "polar_wind":                16,
}

# Settling Playlist (captive_playlist_selection): a 5-bit selection mask,
# independent of sound_mode's own preset index.
CAPTIVE_PLAYLIST_TRACKS = {
    "its_raining_its_pouring": 1,
    "aurora":                  2,
    "six_little_ducks":        4,
    "frere_jacques":           8,
    "brahms_lullaby":          16,
}

# Soothing Playlist (soothe_playlist_selection): a 5-bit selection mask.
SOOTHE_PLAYLIST_TRACKS = {
    "somewhere":     1,
    "daylight":      2,
    "dreaming_dawn": 4,
    "motions":       8,
    "polar_wind":    16,
}

# Device-defined timer durations for light_timer and sound_timer_setting.
TIMER_DURATIONS = {
    "5_minutes":  0,
    "10_minutes": 1,
    "15_minutes": 2,
    "20_minutes": 3,
    "25_minutes": 4,
    "30_minutes": 5,
    "60_minutes": 10,
    "90_minutes": 11,
    "continuous": 15,
}

# Sleep-stage timer durations for captive_sleep_stage_timer and
# soothe_sleep_stage_timer -- same 5-minute steps as TIMER_DURATIONS but with
# different gaps, and no "continuous" option (only the final Sleep stage can
# run continuously; see SLEEP_TIMER_DURATIONS).
SLEEP_STAGE_TIMER_DURATIONS = {
    "5_minutes":  0,
    "10_minutes": 1,
    "15_minutes": 2,
    "20_minutes": 3,
    "25_minutes": 4,
    "30_minutes": 5,
    "35_minutes": 6,
    "40_minutes": 7,
    "45_minutes": 8,
    "50_minutes": 9,
    "60_minutes": 11,
    "90_minutes": 13,
}

# Timer durations for sleep_stage_timer: SLEEP_STAGE_TIMER_DURATIONS plus the
# "continuous" option only the final Sleep stage supports.
SLEEP_TIMER_DURATIONS = {
    **SLEEP_STAGE_TIMER_DURATIONS,
    "continuous": 15,
}

# fmt: on

"""Registry mapping SootherState fields to their SootherClient setter and UI
presentation (label, range, or select options), grouped into sections and
labeled to match the real app's controls (see /App.md at the repo root)."""

from __future__ import annotations

import dataclasses

from fp_soother_lib.constants import PRESET_ATTRS
from fp_soother_lib.protocol import SootherState


@dataclasses.dataclass(frozen=True)
class Option:
    value: int
    label: str


@dataclasses.dataclass(frozen=True)
class Control:
    label: str
    setter: str
    section: str
    kind: str = "range"  # "bool" | "range" | "select" | "bitmask"
    minimum: int = 0
    maximum: int = 0
    options: tuple[Option, ...] = ()


@dataclasses.dataclass(frozen=True)
class Toggle:
    """An on/off switch whose "off" state is a fixed value (usually 0). The
    "on" state either restores the device's own remembered previous value
    (e.g. Star/Animal Projection resume their last mode) or, if
    restore_field is None, always uses default_on (e.g. Music & Sound
    always turns on to a fixed sound), per App.md."""

    label: str
    field: str
    section: str
    off_value: int
    restore_field: str | None
    default_on: int


# Device-defined timer durations; App.md lists these 9 named options (with
# gaps in the raw values) for both the sound and light/projection timers.
TIMER_OPTIONS: tuple[Option, ...] = (
    Option(0, "5 minutes"),
    Option(1, "10 minutes"),
    Option(2, "15 minutes"),
    Option(3, "20 minutes"),
    Option(4, "25 minutes"),
    Option(5, "30 minutes"),
    Option(10, "60 minutes"),
    Option(11, "90 minutes"),
    Option(15, "Continuous"),
)

# Sleep-stage timer durations (App.md): same 5-minute steps as TIMER_OPTIONS
# but with different gaps in the raw values and no "Continuous" option for
# the Settle/Soothe stages (only the final Sleep stage can run continuously).
SLEEP_STAGE_TIMER_OPTIONS: tuple[Option, ...] = (
    Option(0, "5 minutes"),
    Option(1, "10 minutes"),
    Option(2, "15 minutes"),
    Option(3, "20 minutes"),
    Option(4, "25 minutes"),
    Option(5, "30 minutes"),
    Option(6, "35 minutes"),
    Option(7, "40 minutes"),
    Option(8, "45 minutes"),
    Option(9, "50 minutes"),
    Option(11, "60 minutes"),
    Option(13, "90 minutes"),
)

SLEEP_TIMER_OPTIONS: tuple[Option, ...] = SLEEP_STAGE_TIMER_OPTIONS + (
    Option(15, "Continuous"),
)

SLEEP_STAGES_MODE_OPTIONS: tuple[Option, ...] = (
    Option(0, "Off"),
    Option(1, "Settle"),
    Option(2, "Soothe"),
    Option(3, "Sleep"),
)

# The Settling/Soothing playlists (App.md): each track is one bit of a 5-bit
# selection mask, independent of sound_mode's own preset index.
CAPTIVE_PLAYLIST_OPTIONS: tuple[Option, ...] = (
    Option(1, "It's Raining, It's Pouring"),
    Option(2, "Aurora"),
    Option(4, "Six Little Ducks"),
    Option(8, "Frere Jacques"),
    Option(16, "Brahms: Lullaby"),
)

SOOTHE_PLAYLIST_OPTIONS: tuple[Option, ...] = (
    Option(1, "Somewhere"),
    Option(2, "Daylight"),
    Option(4, "Dreaming Dawn"),
    Option(8, "Motions"),
    Option(16, "Polar Wind"),
)

# Top-level tabs, and which sections belong under each, per App.md's
# "Controls (Tab)" / "Sleep Stages (Tab)" headings.
TABS: tuple[tuple[str, str], ...] = (
    ("controls", "Controls"),
    ("sleep_stages", "Sleep Stages"),
)

SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("music", "Music & Sound", "controls"),
    ("nightlight", "Night Light", "controls"),
    ("animal", "Animal Projection", "controls"),
    ("star", "Star Projection", "controls"),
    ("timers", "Timers", "controls"),
    ("sleep_stages_timing", "Sleep Stages Timing", "sleep_stages"),
    ("sleep_stages_music", "Music & Sound", "sleep_stages"),
)

# The Custom sequence's per-slot palette, per App.md.
COLOR_OPTIONS: tuple[Option, ...] = (
    Option(0, "Off"),
    Option(1, "Red"),
    Option(2, "Orange"),
    Option(3, "Yellow"),
    Option(4, "Green"),
    Option(5, "Blue"),
    Option(6, "Purple"),
)

CONTROLS: dict[str, Control] = {
    "volume_level": Control(
        label="Volume", setter="set_volume", section="music", maximum=9
    ),
    "sound_mode": Control(
        label="Song / Sound",
        setter="set_sound_mode",
        section="music",
        kind="select",
        options=(
            Option(1, "Sounds: Pink Noise"),
            Option(2, "Sounds: Brown Noise"),
            Option(3, "Sounds: Womb"),
            Option(4, "Sounds: Ocean"),
            Option(5, "Sounds: Nature"),
            Option(6, "Sounds: Wind"),
            Option(7, "Settling: It's Raining, It's Pouring"),
            Option(8, "Settling: Aurora"),
            Option(9, "Settling: Six Little Ducks"),
            Option(10, "Settling: Frere Jacques"),
            Option(11, "Settling: Brahms: Lullaby"),
            Option(12, "Soothing: Somewhere"),
            Option(13, "Soothing: Daylight"),
            Option(14, "Soothing: Dreaming Dawn"),
            Option(15, "Soothing: Motions"),
            Option(16, "Soothing: Polar Wind"),
        ),
    ),
    "nightlight_mode": Control(
        label="On", setter="set_nightlight", section="nightlight", kind="bool"
    ),
    "nightlight_brightness": Control(
        label="Brightness",
        setter="set_nightlight_brightness",
        section="nightlight",
        maximum=7,
    ),
    "animal_projection_mode": Control(
        label="Mode",
        setter="set_animal_projection_mode",
        section="animal",
        kind="select",
        options=(Option(1, "On"), Option(2, "Lighthouse"), Option(3, "Candle")),
    ),
    "animal_projection_brightness": Control(
        label="Brightness",
        setter="set_animal_projection_brightness",
        section="animal",
        maximum=10,
    ),
    "animal_projection_speed": Control(
        label="Speed (Lighthouse only)",
        setter="set_animal_projection_speed",
        section="animal",
        kind="select",
        options=(Option(1, "Slow"), Option(2, "Fast")),
    ),
    "star_projection_sequence_mode": Control(
        label="Sequence",
        setter="set_star_projection_sequence_mode",
        section="star",
        kind="select",
        options=(
            Option(1, "Rainbow"),
            Option(2, "Cool Colors"),
            Option(3, "Warm Colors"),
            Option(4, "Custom"),
        ),
    ),
    "star_projection_brightness": Control(
        label="Brightness",
        setter="set_star_projection_brightness",
        section="star",
        maximum=6,
    ),
    "star_projection_speed": Control(
        label="Speed",
        setter="set_star_projection_speed",
        section="star",
        kind="select",
        options=(
            Option(0, "Slow"),
            Option(1, "Normal"),
            Option(2, "Fast"),
            Option(3, "Very Fast"),
        ),
    ),
    "sound_timer_setting": Control(
        label="Music & Sound",
        setter="set_sound_timer",
        section="timers",
        kind="select",
        options=TIMER_OPTIONS,
    ),
    "light_timer": Control(
        label="Projection & Light",
        setter="set_light_timer",
        section="timers",
        kind="select",
        options=TIMER_OPTIONS,
    ),
    "sleep_stages_mode": Control(
        label="Stages",
        setter="set_sleep_stages_mode",
        section="sleep_stages_timing",
        kind="select",
        options=SLEEP_STAGES_MODE_OPTIONS,
    ),
    "captive_sleep_stage_timer": Control(
        label="Settle Duration",
        setter="set_captive_sleep_stage_timer",
        section="sleep_stages_timing",
        kind="select",
        options=SLEEP_STAGE_TIMER_OPTIONS,
    ),
    "soothe_sleep_stage_timer": Control(
        label="Soothe Duration",
        setter="set_soothe_sleep_stage_timer",
        section="sleep_stages_timing",
        kind="select",
        options=SLEEP_STAGE_TIMER_OPTIONS,
    ),
    "sleep_stage_timer": Control(
        label="Sleep Duration",
        setter="set_sleep_stage_timer",
        section="sleep_stages_timing",
        kind="select",
        options=SLEEP_TIMER_OPTIONS,
    ),
    "captive_playlist_selection": Control(
        label="Settling Playlist",
        setter="set_captive_playlist_selection",
        section="music",
        kind="bitmask",
        maximum=31,
        options=CAPTIVE_PLAYLIST_OPTIONS,
    ),
    "soothe_playlist_selection": Control(
        label="Soothing Playlist",
        setter="set_soothe_playlist_selection",
        section="music",
        kind="bitmask",
        maximum=31,
        options=SOOTHE_PLAYLIST_OPTIONS,
    ),
}

TOGGLES: dict[str, Toggle] = {
    "star_projection_sequence_mode": Toggle(
        label="Star Projection",
        field="star_projection_sequence_mode",
        section="star",
        off_value=0,
        restore_field="previous_star_projection_sequence_mode",
        default_on=1,
    ),
    "animal_projection_mode": Toggle(
        label="Animal Projection",
        field="animal_projection_mode",
        section="animal",
        off_value=0,
        restore_field="previous_animal_projection_mode",
        default_on=1,
    ),
}

# The star projection "Custom" sequence value -- Custom Colors are only
# editable when star_projection_sequence_mode is set to this.
STAR_SEQUENCE_CUSTOM = 4

CUSTOM_COLOR_FIELDS = (
    "star_projection_custom_color0",
    "star_projection_custom_color1",
    "star_projection_custom_color2",
)

# Two saveable/sendable preset slots per device
PRESET_SLOTS: tuple[int, ...] = (1, 2)

# Exactly the fields the device's composite preset command bundles (see
# PRESET_ATTRS), named using SootherState's field names -- what gets captured
# on "Save" and what send_preset() expects as overrides.
PRESET_FIELDS: tuple[str, ...] = tuple(
    SootherState._ATTR_MAP[attr_name] for attr_name in PRESET_ATTRS
)

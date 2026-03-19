# App Controls and Layout

## Controls (Tab)

### Star Projection

Toggle on/off:

- off: (star_projection_sequence_mode = 0)
- on: (star_projection_sequence_mode = previousStarProjectionSequenceMode)

Below is only editable when the star projection is turned on.

Sequence: (star_projection_sequence_mode) 1-7

- 1: Rainbow
- 2: Cool Colors
- 3: Warm Colors
- 4: Custom

Custom Color 1: (star_projection_custom_color0)
Custom Color 2: (star_projection_custom_color1)
Custom Color 3: (star_projection_custom_color2)

Note: Custom Color values:

- 0 Off 0x000000
- 1 Red 0xFF5363
- 2 Orange 0xFFB178
- 3 Yellow 0xFCF37C
- 4 Green 0x00FF91
- 5 Blue 0x0085FF
- 6 Purple 0x5245FF

Brightness: (star_projection_brightness) 0-6 (0 = off, 6 = brightest)
Custom Colors (up to 3 colors): Red, Orange, Yellow, Green, Blue, Purple,

- star_projection_custom_color0
- star_projection_custom_color1
- star_projection_custom_color2

Speed: (star_projection_speed)

- Slow
- Normal
- Fast
- Very Fast

### Animal Projection

Toggle on/off:

- off: (animal_projection_mode = 0)
- on: (animal_projection_mode = previousAnimalProjectionMode)

Below is only editable when the animal projection is turned on.

Mode: (animal_projection_mode)

- 1: On
- 2: Lighthouse
- 3: Candle

Brightness: (animal_projection_brightness) 0-10 (0 = off, 10 = brightest)
Speed (only applicable to Lighthouse): (animal_projection_speed)

- 1: Slow
- 2: Fast

### Night Light

Toggle on/off: (nightlight_mode)

- Off: mode = 0
- On: mode = 1

Below is only editable when the night light is turned on.

Brightness: (nightlight_brightness) 0-7 (0 = off, 7 = brightest)

### Music & Sound

Toggle on/off:

- Off: sound_mode = 0
- On: sound_mode = (cached last sound_mode defaults to 1)

Below is only editable when the music & sound is turned on.

Volume: (volume_level) 0-9 (0 = off, 9 = loudest)
Song/Sound: (sound_mode)

- Sounds:
  - 1: Pink Noise
  - 2: Brown Noise
  - 3: Womb
  - 4: Ocean
  - 5: Nature
  - 6: Wind
- Settling:
  - 7: It's Raining, It's Pouring
  - 8: Aurora
  - 9: Six Little Ducks
  - 10: Frere Jacques
  - 11: Brahms: Lullaby
- Soothing:
  - 12: Somewhere
  - 13: Daylight
  - 14: Dreaming Dawn
  - 15: Motions
  - 16: Polar Wind

Settling Playlist: (captive_playlist_selection, 5-bit bitmask):

- 1: It's Raining, It's Pouring
- 2: Aurora
- 4: Six Little Ducks
- 8: Frere Jacques
- 16: Brahms: Lullaby

Soothing Playlist: (soothe_playlist_selection, 5-bit bitmask):

- 1: Somewhere
- 2: Daylight
- 4: Dreaming Dawn
- 8: Motions
- 16: Polar Wind

### Timer

Project & Light: (light_timer)

- 0: 5 min
- 1: 10 min
- 2: 15 min
- 3: 20 min
- 4: 25 min
- 5: 30 min
- 10: 60 min
- 11: 90 min
- 15: Continuous

Music & Sound: (sound_timer_setting)

- 0: 5 min
- 1: 10 min
- 2: 15 min
- 3: 20 min
- 4: 25 min
- 5: 30 min
- 10: 60 min
- 11: 90 min
- 15: Continuous

### Save as Preset

Above options can be saved as a preset. Preset 1 or Preset 2.

## Sleep Stages (Tab)

### Sleep Stages Timing

Stages: (sleepStagesMode)

- 0: Off
- 1: Settle
- 2: Soothe
- 3: Sleep

- Settle: (captive_sleep_stage_timer)
  - 0: 5 min
  - 1: 10 min
  - 2: 15 min
  - 3: 20 min
  - 4: 25 min
  - 5: 30 min
  - 6: 35 min
  - 7: 40 min
  - 8: 45 min
  - 9: 50 min
  - 11: 60 min
  - 13: 90 min

- Soothe: (soothe_sleep_stage_timer)
  - 0: 5 min
  - 1: 10 min
  - 2: 15 min
  - 3: 20 min
  - 4: 25 min
  - 5: 30 min
  - 6: 35 min
  - 7: 40 min
  - 8: 45 min
  - 9: 50 min
  - 11: 60 min
  - 13: 90 min

- Sleep: (sleep_stage_timer)
  - 0: 5 min
  - 1: 10 min
  - 2: 15 min
  - 3: 20 min
  - 4: 25 min
  - 5: 30 min
  - 6: 35 min
  - 7: 40 min
  - 8: 45 min
  - 9: 50 min
  - 11: 60 min
  - 13: 90 min
  - 15: Continuous

### Music & Sound for Sleep Stages

Volume: (volume_level) 0-9 (0 = off, 9 = loudest)

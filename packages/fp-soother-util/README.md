# fp-soother-util

Shared utilities used by other `fp-soother-*` packages.

Currently provides:

- Persistence for paired-device session keys, stored at
  `paired_devices.json` in an OS-appropriate user data directory by default
  (via `platformdirs`, e.g. `~/Library/Application Support/fp-soother` on
  macOS, `%LOCALAPPDATA%\fp-soother` on Windows, `~/.local/share/fp-soother`
  on Linux), so the CLI and web app can share the same set of paired
  devices.
- Persistence for per-device preset slots (a saved snapshot of settable
  field values), stored at `presets.json` in the same directory by default.

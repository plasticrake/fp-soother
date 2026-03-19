# fp-soother-web

A small local web UI for the Fisher-Price Smart Connect Deluxe Soother. Created
to provide a quick way to test **fp-soother-lib**.

- Shows previously paired devices, their live status, and lets you control them.
- Scans for nearby unpaired soothers and pairs them (device must already be
  in its own pairing mode).
- Paired devices are stored via `fp-soother-util` (shared with the CLI) in an
  OS-appropriate user data directory (`paired_devices.json`).
- Each device page has two saveable/sendable preset slots that snapshot and
  restore every settable field in one composite command (stored via
  `fp-soother-util` in the same directory as `presets.json`).
- Intended for local/LAN use only; no authentication.

## Run

```sh
uv run fp-soother-web
# or with custom host/port:
uv run fp-soother-web --host 0.0.0.0 --port 8080
```

Then open http://127.0.0.1:8000/.

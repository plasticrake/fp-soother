# AGENTS.md

## Project overview

This repository is a Python workspace for the Fisher-Price Smart Connect Deluxe Soother BLE device. The code is split into a reusable library package and a small CLI package.

- Root workspace config manages multiple packages via `uv`.
- Core Bluetooth/protocol logic lives under `packages/fp-soother-lib/`.
- The user-facing command-line wrapper lives under `packages/fp-soother-cli/`.
- The root README is intentionally minimal and should be updated when behavior or installation changes materially.

## Repository layout

- `README.md` — project overview and legal/disclaimer notes.
- `pyproject.toml` — workspace-level `uv` configuration.
- `packages/fp-soother-lib/` — core library implementation.
  - `src/fp_soother_lib/` — package source
- `packages/fp-soother-cli/` — CLI entry point.
  - `src/fp_soother_cli/` — CLI code
- `packages/fp-soother-util/` — shared persistence utilities used by the CLI and web packages.
  - `src/fp_soother_util/` — paired-device persistence
- `packages/fp-soother-web/` — FastAPI web UI.
  - `src/fp_soother_web/` — FastAPI routes, device management, Jinja templates, and HTMX assets

## Architecture

Four packages in the `uv` workspace, layered strictly bottom-to-top — `fp-soother-lib` has no dependency on the other packages; `fp-soother-util` is shared by the CLI and web packages; `fp-soother-cli` and `fp-soother-web` both depend on lib + util but not on each other.

`fp-soother-lib` and `fp-soother-web` each have their own `AGENTS.md` (auto-loaded when working in those directories) covering their file layout and package-specific notes in detail; see those before working in `packages/fp-soother-lib/` or `packages/fp-soother-web/`.

### fp-soother-util — shared persistence

`persistence.py` stores paired devices' session keys at `paired_devices.json` in an OS-appropriate user data directory (via `platformdirs`, e.g. `~/Library/Application Support/fp-soother` on macOS, `%LOCALAPPDATA%\fp-soother` on Windows, `~/.local/share/fp-soother` on Linux) (`save_paired_device`, `load_paired_device`, `list_paired_devices`, `forget_paired_device`). Both the CLI and the web app use this instead of re-pairing on every connection.

`presets.py` stores per-device preset slots (a snapshot of every `SootherClient.send_preset()`-eligible field's value) at `presets.json` in the same directory, keyed by device address then slot number (`save_preset`, `load_preset`, `list_presets`). Currently only `fp-soother-web` uses this (two saveable/sendable slots per device page).

### fp-soother-cli — Click-based CLI

`cli.py` wraps every command in `_with_client()`, which loads a saved session key by address (or scans for the first soother if no address is given) and opens a scoped `SootherClient.connect()`. Simple per-field setters (`set nightlight`, `set volume`, ...) are generated via `_set_command`/`_set_bool_command` helpers rather than hand-written per subcommand — follow that pattern when adding a new setting rather than writing a new command function from scratch.

### Reference material (not code)

- `App.md` — the app's control/tab layout and the meaning of each field's value range (colors, sound presets, timer settings, sleep-stage semantics).

## Working conventions

- Use the existing `uv` workspace workflow instead of ad hoc virtualenv setup.
- Prefer small, targeted edits that match the current package boundaries.
- Keep public APIs and CLI names stable unless the task explicitly requires a breaking change.
- Update docs, examples, or README entries when behavior or setup changes.
- Do not add broad refactors or unrelated cleanup in the same patch.

## Python and dependency expectations

- The library package targets Python 3.14.0 (`requires-python = ">=3.14.0"`).
- Use `uv` commands from the repository root.
- New dependencies should be added only where they are clearly needed and should be reflected in the relevant package `pyproject.toml`.

## Commands

Run everything from the repo root:

- `uv sync` — install/update the workspace environment
- `uv run ruff format` — format Python
- `pnpm install` — install Prettier tooling (one-time / after `package.json` changes)
- `pnpm run format` — format `.md`/`.toml`/`.yml`/`.yaml`/`.json` files with Prettier (`pnpm run format:check` to check without writing)
- `uv run ruff check` — lint
- `uv run ty check` — type-check (uses `ty`, not mypy)
- `uv run fp-soother-cli --help` — sanity-check the CLI entry point
- `uv run fp-soother-web` — run the FastAPI web UI (uvicorn)
- `uv run --package fp-soother-lib pytest packages/fp-soother-lib/tests` — run the `fp-soother-lib` test suite (pure crypto/protocol logic + a few `SootherClient` behavior tests; no real BLE hardware needed)

Useful CLI subcommands during manual verification (all take a BLE address, or omit it to auto-scan for the first soother found):

```bash
uv run fp-soother-cli scan
uv run fp-soother-cli pair <ADDRESS>          # device must be in its own pairing mode
uv run fp-soother-cli status <ADDRESS> --json
uv run fp-soother-cli set nightlight <ADDRESS> on
uv run fp-soother-cli set volume <ADDRESS> 8
uv run fp-soother-cli dump-gatt <ADDRESS>
```

## Validation before finishing

Run `uv run ruff format`, `uv run ruff check`, and `uv run ty check` from the repo root before considering a change complete (see Commands above). If the change touched any `.md`, `.toml`, `.yml`, `.yaml`, or `.json` file, also run `pnpm run format` (Prettier). If the change involves the CLI or a user-facing command, also validate it directly when practical, e.g. `uv run fp-soother-cli --help`.

`fp-soother-lib` has a `pytest` suite under `packages/fp-soother-lib/tests/` (dev deps: `pytest`, `pytest-asyncio`, `asyncio_mode = "auto"` in that package's `pyproject.toml`). Run it with `uv run --package fp-soother-lib pytest packages/fp-soother-lib/tests` whenever you touch `fp_soother_lib` — especially `constants.py`'s bit-layout tables, `encryption.py`, or `protocol.py` — and add/update tests to cover the behavior you changed. It deliberately does not cover live-BLE-connection flows (`pair()`, `_connect`, `refresh_state`, `_send_state_command`) since those would require mocking most of `bleak`/`bleak_retry_connector` rather than testing this library's own logic; if you add such coverage, keep it scoped to what you changed. The other packages have no test suite yet.

## Notes for agents

- Repository memory is not shared between AI agents. When verified project facts are added to repository memory, update this `AGENTS.md` with the reusable guidance so future agents receive it.
- `.md`/`.toml`/`.yml`/`.yaml`/`.json` formatting is handled by Prettier (`package.json`, `.prettierrc.json`, `.prettierignore`), not `ruff` — `ruff format` only touches Python. Requires `pnpm install` once (Node via any means, e.g. `mise`) to pull in `prettier` + `prettier-plugin-toml` (TOML needs the plugin; Prettier has built-in YAML and JSON support, no plugin needed).
- Treat this as a reverse-engineering and interoperability project: keep changes precise, safe, and well-documented.
- When unsure about a behavior change, prefer direct evidence from the existing implementation and package structure over assumptions.
- Protocol-level details specific to `fp-soother-lib` live in `packages/fp-soother-lib/AGENTS.md`, not here.

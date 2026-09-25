# fp-soother-lib

A Python BLE library for the **Fisher-Price Smart Connect Deluxe Soother** (model DYW47).

The official app was discontinued in 2024, leaving many users with a device that could no longer be fully controlled. This library gives you direct BLE control from Python.

## Usage

### Standalone (scans/connects by address)

```python
import asyncio
from fp_soother_lib import SootherClient


async def main():
    async with SootherClient.connect("AA:BB:CC:DD:EE:FF", session_key=key) as soother:
        if not soother.is_paired:
            await soother.pair()  # device must already be in pairing mode
        await soother.set_nightlight(True)
        print(soother.state)


asyncio.run(main())
```

If `address` is omitted, `SootherClient.connect()` scans for the first soother found.

### Firmware versions

The client reads the device's firmware version when it connects and picks the
matching crypto mode.

Firmware 9 and newer use a per-device session key from `pair()`, and the
device must be in its own pairing mode while you pair. Save `session_key` and
pass it back on later connects.

Firmware 8 and older use a static shared key and a different byte layout.
These devices need no pairing. The client sets the key on connect
(`uses_shared_key` is `True`), and `pair()` only syncs the device clock.

Tested against real firmware 8 and firmware 11 devices.

### Host-managed discovery (e.g. Home Assistant)

A host that owns its own BLE scanner (Home Assistant's `bluetooth` integration
is the main example) should resolve `BLEDevice` objects itself rather than
letting this library run its own scan. Pass `ble_device`/`ble_device_callback`
to `SootherClient` instead of relying on address-based discovery:

```python
from fp_soother_lib import SootherClient

client = SootherClient(address, session_key=key, ble_device_callback=my_resolver)
await client.open()
...
await client.close()
```

`my_resolver` is a zero-arg callable returning the host's current best
`BLEDevice` for `address` (e.g. Home Assistant's
`bluetooth.async_ble_device_from_address`), called fresh on every
(re)connect. See `AGENTS.md` in the repository root for the full rationale.

## Legal / Disclaimer

This is an independent, open-source project not affiliated with Fisher-Price or Mattel. Reverse engineering for interoperability purposes is generally permitted under applicable law (e.g. EU Software Directive, US DMCA §1201(f)). This project does not redistribute any Fisher-Price code or assets. Use at your own risk. "Fisher-Price" and "Deluxe Soother" are trademarks of their respective owners.

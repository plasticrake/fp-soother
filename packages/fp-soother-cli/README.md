# fp-soother-cli

Command-line interface for [fp-soother-lib](../fp-soother-lib), controlling a
Fisher-Price Smart Connect Deluxe Soother over BLE.

## Usage

```sh
fp-soother-cli scan
fp-soother-cli pair AA:BB:CC:DD:EE:FF
fp-soother-cli status AA:BB:CC:DD:EE:FF
fp-soother-cli status AA:BB:CC:DD:EE:FF --json
fp-soother-cli dump-gatt AA:BB:CC:DD:EE:FF
fp-soother-cli forget AA:BB:CC:DD:EE:FF

fp-soother-cli set play AA:BB:CC:DD:EE:FF on
fp-soother-cli set nightlight AA:BB:CC:DD:EE:FF off
fp-soother-cli set volume AA:BB:CC:DD:EE:FF 8
fp-soother-cli set sound-mode AA:BB:CC:DD:EE:FF 3
```

Run `fp-soother-cli --help` or `fp-soother-cli set --help` for the full list
of commands.

If `ADDRESS` is omitted for `pair` or `status`, the CLI scans and uses the
first soother it finds.

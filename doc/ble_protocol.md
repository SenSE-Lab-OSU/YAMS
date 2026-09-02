# BLE Characteristics and Behaviors

## Overview

YAMS controls MotionSenSE wearable devices in real time over Bluetooth Low Energy (BLE / GATT), via the **⌚️ MotionSenSE controller** tab (`yams/msense_collector.py`, using `simplepyble`). An older, currently unused `bleak`-based implementation (`yams/bluetooth_device.py`, `yams/bt_scanner.py`) targets the same UUIDs and is kept mainly for the `e_stop.py` emergency-stop script.

This is distinct from the USB mass-storage workflow described in [`file_download.md`](file_download.md) and [`data_extraction.md`](data_extraction.md), which retrieves recorded `.bin` files after the fact rather than talking to the device live.

## Custom collection-control service — `da39c930-1d81-48e2-9c68-d0ae4bbd351f`

| Characteristic UUID | Name | Properties | Payload | Behavior |
|---|---|---|---|---|
| `da39c931-1d81-48e2-9c68-d0ae4bbd351f` | Collection control | write, read | `uint32` LE | Write `1` to start recording on the device, `0` to stop. Also read as a status byte to report whether a recording is in progress. |
| `da39c932-1d81-48e2-9c68-d0ae4bbd351f` | Unix time sync | write | `uint64` LE | Writes the host's current Unix timestamp (`time.time()`), setting the device clock/RTC. Sent immediately before the start flag whenever a collection is started. |
| `da39c933-1d81-48e2-9c68-d0ae4bbd351f` | Participant encoding | write, read | `uint32` LE | Writes a numeric subject/session ID that tags the upcoming recording. Sent right after the time sync, before the start flag. Can also be read back to verify. |
| `da39c934-1d81-48e2-9c68-d0ae4bbd351f` | Erase / reset (`rst_char`) | write | `uint32` LE | Writing the fixed value `68` triggers a full flash erase on the device. In the UI this is gated behind an "Enable erase feature" checkbox that only unlocks the erase button once the entered passcode equals `68`. |

## ENMO streaming service — `da39c950-1d81-48e2-9c68-d0ae4bbd351f`

| Characteristic UUID | Name | Properties | Payload | Behavior |
|---|---|---|---|---|
| `da39c951-1d81-48e2-9c68-d0ae4bbd351f` | ENMO (real-time motion) stream | notify | 6 or 8 bytes | Device pushes live samples: bytes `0:4` decode as a `float32` LE ENMO value; the remainder is a rolling packet counter — `uint16` LE if the payload is 6 bytes, `uint32` LE if 8 bytes. Each sample is pushed to an LSL outlet and logged. Subscribed automatically whenever a collection is started or stopped (`register_senses`). |

## Standard (Bluetooth SIG) characteristics

| Characteristic UUID | Name | Service | Properties | Behavior |
|---|---|---|---|---|
| `00002a19-0000-1000-8000-00805f9b34fb` | Battery Level | Battery Service `0000180f-0000-1000-8000-00805f9b34fb` | read, notify | Single byte, 0–255, battery percent. Read once on connect and subscribed via notify; updates the "Battery: NN%" status shown per device in the UI. |
| `2A24` | Model Number String | Device Information Service `180A` | read | UTF-8 string identifying the device model, shown in device status (only in the older `bluetooth_device.py` path). |

## Command payload summary

Each "command" is a dedicated write-only (or write+read) characteristic taking a raw little-endian integer, rather than a shared command characteristic with an opcode byte:

| Value written | Characteristic | Effect |
|---|---|---|
| `1` (`uint32` LE) | `da39c931` | Start collection |
| `0` (`uint32` LE) | `da39c931` | Stop collection |
| current `time.time()` (`uint64` LE) | `da39c932` | Set device Unix clock |
| encoded subject/session int (`uint32` LE) | `da39c933` | Tag next recording with a participant ID |
| `68` (`uint32` LE) | `da39c934` | Erase flash (also acts as a client-side passcode gating the erase button) |

### Participant ID encoding

Two schemes are available (`yams/msense_collector.py:33-57`), selectable in the UI via "Encoding mode":

- **Legacy (hash-based)**: `int(sha256(f"{sub}_{ses}").hexdigest(), 16) % 32000`
- **Default**: digits parsed from `sub-XXXX` and `ses-YY` combined as `int(sub_number) * 100 + int(ses_number)`

### Start-collection sequence

When a collection is started (`collection_ctl`, `yams/msense_collector.py:439-465`), the writes happen in this order:

1. `da39c932` ← current Unix time
2. `da39c933` ← participant encoding
3. `da39c931` ← `1` (start)
4. Re-subscribe to ENMO (`da39c951`) and Battery Level (`00002a19`) notifications

Stopping a collection writes `da39c931` ← `0` and re-registers the same notifications.

## Key file references

| File | Contents |
|---|---|
| `yams/msense_collector.py` | Current `simplepyble`-based implementation: UUID constants, `collection_ctl`, `write_enc`, `erase_flash_data`, `register_enmo`/`register_battery`, `enmo_handler`/`battery_handler`, `get_services` (GATT discovery/debugging), `participant_encoding_legacy`/`participant_encoding_default` |
| `yams/bluetooth_device.py` | Older `bleak`-based UUID constants and `get_device_status`/`enmo_handler` |
| `yams/bt_scanner.py` | Older `bleak`-based start/stop/erase control and participant-hash encoding |
| `yams/e_stop.py` | Emergency-stop script built on the `bleak`-based collection control |

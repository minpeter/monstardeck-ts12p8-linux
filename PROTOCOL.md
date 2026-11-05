# TS12P8 protocol observations

Target: Monstar Gear Monstar Deck TS12P8, USB `0400:1003`.

This document separates static analysis, runtime observations and outstanding
physical verification. It is not an official manufacturer specification.

## Sources and artifact identity

- [Manufacturer download page](https://www.monstargear.co.kr/deckdownload?bmode=view&idx=168475157)
- [Manufacturer download folder](https://drive.google.com/drive/folders/1MulY3Lx1EapmnGuJOmc3supvug5hzUvX)
- [Product announcement and photograph](https://www.ilovepc.co.kr/news/articleView.html?idxno=50416)
- [Related, but not TS12P8-specific, Linux implementation](https://github.com/4ndv/mirajazz)
- [Official Mirabox SDK](https://github.com/MiraboxSpace/StreamDock-Device-SDK)

Analyzed manufacturer package: `MONSTAR-DECK_V3.zip`, downloaded from the
manufacturer-linked folder. SHA-256:

```
c806f3df94255efc80f9188bccab9581b69f4abb2813485678b5d7cf1608ddb6
```

Analyzed files:

| File | SHA-256 |
| --- | --- |
| `app/SDLibrary1.dll` | `c82982b851d8c4542935c197e007f9ed41d99aa342b330d402129a5eb0c331e4` |
| `app/MONSTAR DECK.exe` | `b13a46c34d7c4802459c201a9f83c7e052ed91d639eb82db57b5670ccf65` |

REA 6.5.0 and Ghidra 12.1 were used for native static analysis. GNU objdump
was used to cross-check Qt array indices that decompilation did not recover.
A temporary Windows VM attachment of only this HID device allowed observation
of the original software's USB traffic through Linux usbmon. Neither the hub
nor its networking device was passed through. The device was returned to the
Linux `usbhid` driver after capture. No firmware was flashed.

Manufacturer binaries, decompiled source, proprietary default artwork and user
photographs are not distributed here. The Python implementation is original.

## Identity and report sizes

- The main EXE at `0x140017a11–0x140017a36` puts `TS12P8`, VID `0x0400`
  and PID `0x1003` in one model record.
- The report descriptor advertises one vendor-defined input report and one
  output report, each 512 bytes, without numbered report IDs.
- The Windows DLL returned 512 for both `hid_get_output_report_lenght()`
  and `hid_get_input_report_lenght()` on the physical device.
- USB capture confirmed 512-byte interrupt OUT transfers on endpoint 1 and
  512-byte interrupt IN transfers on endpoint 2.
- Linux `hidraw.write()` still needs a leading zero report-ID byte: write 513
  bytes to send 512 bytes on USB. Do not put this extra zero into USB captures
  or interpret it as part of the command.

## Firmware query

The original application uses **GET_REPORT for an input report**, not a feature
report. The HID descriptor has no feature report. A Linux `HIDIOCGINPUT(513)`
query successfully read `V2.293.00.001` from the attached device. The zero
report-ID byte occupies the first byte of the ioctl buffer and is removed by
the library. A Windows call through the manufacturer's DLL returned the same
string. This is a read-only operation.

## Output commands

The table uses **USB payload offsets**, excluding the Linux zero report-ID byte.
All reports are zero-padded to 512 bytes. Command prefix: `43 52 54 00 00`
(`CRT\0\0`). Bytes 5 onward contain the command.

| Command | Additional fields | Observation |
| --- | --- | --- |
| `DIS` | none | OEM startup/wake |
| `CLE` | bytes 8–10 = zero; byte 11 = `ff` | OEM clear all key images |
| `BAT` | bytes 8–9 = zero; bytes 10–11 = JPEG byte count, big-endian; byte 12 = key 1–12 | OEM image transfer header |
| `STP` | none | OEM commit/refresh after image transfer |
| `LIG` | bytes 8–9 = zero; byte 10 = 0–100 | OEM brightness |
| `MOD` | bytes 8–9 = zero; byte 10 = ASCII `1`, `2` or `3` | OEM mode selection; `2` used for key display |
| `CONNECT` | none | OEM periodic connection maintenance, approximately 10 seconds apart |

The controller sends `CONNECT` every 5 seconds while a display/watch command
is running. A successful write is not an acknowledgement that the LCD updated.
The captured OEM image sequence did not produce per-command input ACKs.

### JPEG transfer

1. Send `BAT` with the complete JPEG length and a 1-based key index.
2. Send the JPEG stream in 512-byte reports, without command headers on those
   data reports. Zero-pad only the final report.
3. Send `STP` after the image(s).

The OEM EXE's TS12P8 branches select a four-column, three-row layout and a
70×70 image scaling size (`0x1402aa690`, `0x1402ad80a`, `0x1402adb99`).
Captured image transfers start with baseline JFIF JPEG bytes. The Python CLI
encodes 70×70 RGB baseline JPEG, quality 100, no chroma subsampling, 96 dpi.
The exact physical image orientation still needs visual confirmation.

Relevant DLL functions:

| Address | Function |
| --- | --- |
| `0x18001ac30` | `SDDevice::openHidDevice` |
| `0x18001ca30` | `SDDevice::readDataFromHidDevice` |
| `0x18001f350` | `SDDevice::sendPicSizeCommand` |
| `0x180021ed0` | `SDDevice::writeDataToHidDevice` |
| `0x180021a60` | `SDDevice::writeData` |
| `0x1800169b0` | `SDDevice::addModeChangedCommand` |
| `0x180015030` | `SDDevice::addFinishCommand` |

## Input: do not equate every ACK with a touch

The DLL's generic input branch forwards offsets 9 and 10 as a key number and
state. This is **not yet sufficient to declare a TS12P8 touch event format**.
An observed report began `41 43 4b 00 00 4f 4b 00 00 01 00` (`ACK..OK...`).
Its physical origin was not established, so it is not used as a test touch.

The manufacturer's package includes a warning that some command responses can
look like key presses on other models. Therefore `watch` and the display CLI
print exact reports as JSON and never execute keyboard events or commands.
No consumer should bind actions to the generic offsets until real press/release
captures on this model establish a discriminating rule.

## Verification boundary

Observed on physical hardware:

- Identity discovery and kernel identity validation.
- Read-only firmware query through both Linux hidraw and the OEM Windows DLL.
- OEM command ordering, image header fields, report length and JPEG streaming.
- Linux interrupt OUT payloads reaching the device successfully.

Not yet established: a user-confirmed Linux LCD update, image orientation,
complete touch press/release semantics and long-running reliability. The initial
single-image experiment did not change the visible factory screen. Later runs
added OEM mode selection, full-grid initialization and continuous heartbeat;
those require separate physical confirmation.

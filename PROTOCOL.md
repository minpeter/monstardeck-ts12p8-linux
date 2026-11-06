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
state. An early report began `41 43 4b 00 00 4f 4b 00 00 01 00`
(`ACK..OK...`); its physical origin was not established.

During a later heartbeat-only Linux `watch`, the user reported pressing the
screen buttons in order. The capture contained 28 reports, each 512 bytes:

`1, 2, 7, 3, 8, 8, 8, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12`

All had the nine-byte prefix `ACK\0\0OK\0\0`, the listed index at byte 9,
zero at byte 10 and zeros afterward. A preceding 15-minute watch had received
no reports. This establishes user-correlated input reception, but does not
establish one report per physical tap, complete corner mapping, or press/release edges.
In particular, do not interpret byte 10's observed zero as a released state.

`describe_report` annotates this exact shape with `key_candidate` and
`state_byte`, preserving the full raw payload. It leaves unknown lengths,
headers, out-of-range indices and reports with extra payload unannotated.
All observed repeated indices are preserved; there is no guessed debounce.

A separate controlled check requested holding only the upper-left button for
three seconds, then releasing it. After the user confirmed completion, the new
capture session contained exactly one report: `key_candidate: 1, state_byte: 0`.
This maps wire index 1 to the upper-left cell in the currently displayed layout.
No second edge report or held-repeat report was observed for this check.
Without synchronized gesture timing, the single packet cannot establish whether
it is emitted on contact or release. Do not synthesize a press/release pair.

The manufacturer's package warns that some command responses resemble presses
on other models. No consumer should bind actions to these candidates until a
controlled hold/release capture establishes a discriminating rule. The CLI
never executes keyboard events or commands.

## Verification boundary

Observed on physical hardware:

- Identity discovery and kernel identity validation.
- Read-only firmware query through both Linux hidraw and the OEM Windows DLL.
- OEM command ordering, image header fields, report length and JPEG streaming.
- Linux interrupt OUT payloads reaching the device successfully.
- User-correlated Linux input reports carrying every wire index from 1 through 12.

After the experiments, the user reported that the screen had changed to a
**4×4 button grid**. That observation takes precedence over the static model's
four-column, three-row setting. The initial grid's artwork and the complete
physical-cell mapping remain unconfirmed. A later, distinct Linux upload was
visually confirmed as described below. Do not infer 16 wire keys from the grid.

Still unverified: full-grid layout and image orientation, touch press/release
semantics and long-running LCD behavior.
The initial single-image experiment did not change the factory screen. Later
runs added OEM mode selection, full-grid initialization and continuous heartbeat.
Raw-input capture preserves the current display. The controlled hold check above
is complete; determining the emitting edge still needs synchronized timing.
A photograph would be needed to resolve the full layout discrepancy.

For a distinct visual check, a subsequent Linux upload sent a green 70×70 JPEG
labelled `LINUX / OK 1` to wire index 1, followed by `STP` and heartbeat.
It issued no `CLE` command and did not upload to other indices. The upload
completed without an OS write error. The user subsequently confirmed that this
green Linux artwork was visible on the physical screen.

That targeted-upload session subsequently completed its 86,400-second
heartbeat/read window with exit status 0 and no reported I/O error. It received
ten further key-shaped reports carrying indices 1 and 5, all with state byte 0.
Their gesture timing was not recorded, so they do not establish new press/release
semantics. This is a 24-hour host-side transport observation, not proof that the
LCD continuously showed the uploaded image. The bounded session is now stopped.

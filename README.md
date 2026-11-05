# Monstar Deck TS12P8 on Linux

Original Python/hidraw controller and reverse-engineering notes for the
**Monstar Gear Monstar Deck TS12P8**, USB `0400:1003`.

**Hardware research in progress.** Device discovery and firmware reads work on
real hardware. The original Windows program's USB image transfers have been
captured and reproduced in Linux. **A visible Linux LCD update and touch-event
semantics are not yet verified. Do not treat this as a working general-purpose
touchscreen driver.** See [PROTOCOL.md](PROTOCOL.md) for observations and limits.

The integrated hub, Ethernet and other peripherals are separate devices. This
controller opens only the matching HID interface. It does not replace a kernel
driver, unbind a USB device, reset a hub, update firmware or modify boot artwork.
The display is a small macro panel, not an HDMI/DisplayLink desktop monitor.

## Setup

Python 3.10 or newer. Pillow is required only for `show` and `demo`.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On Debian, the `python3-venv` package may be required to create the environment.
Use an isolated environment rather than installing Python packages into the
system interpreter. Root access to this one hidraw device is the simplest
initial setup on a headless machine. This project does not install broad USB
permission rules.

## Read firmware without changing the screen

```sh
sudo .venv/bin/python ts12p8.py info
# Or, without Pillow or a venv:
sudo python3 ts12p8.py info
```

Observed firmware: `V2.293.00.001`. The command checks the kernel's VID/PID before
opening a control session. If multiple matching devices are present, select one
explicitly:

```sh
sudo python3 ts12p8.py --device /dev/hidraw0 info
```

## Display experiments

```sh
# Render twelve original colored, numbered Linux tiles.
sudo .venv/bin/python ts12p8.py demo

# Clear the grid and send a custom image to one numbered zone.
sudo .venv/bin/python ts12p8.py show photo.png --key 1

# Bounded run for a manual hardware check.
sudo .venv/bin/python ts12p8.py demo --seconds 120
```

The CLI converts images to 70×70 baseline JPEG, sends the captured OEM command
format, selects key mode, maintains a five-second heartbeat and prints incoming
raw reports as JSON. By default it runs until Ctrl+C. A transport write success
is **not** evidence of a visible LCD update. Stopping a display command stops
connection maintenance; the device may return to its own idle screen.

The exact physical key orientation still needs confirmation. `--key` uses the
manufacturer's wire indices 1–12; do not assume the physical ordering until a
numbered-grid photograph establishes it.

## Observe raw input

```sh
sudo python3 ts12p8.py watch --seconds 120
```

No shell commands, simulated keystrokes or macros are executed. Reports are
printed with their actual byte count and complete hex payload. The device's
command responses must not be mistaken for presses: the generic manufacturer's
parser is not sufficient to establish touch semantics on this model.

Only one controller should use the device at a time. An advisory lock prevents
two instances of this tool from interleaving image streams; unrelated programs
may ignore that lock. Unplug/replug can change the hidraw node number.

## Library use

```python
from ts12p8 import Deck, discover, encode_image
from PIL import Image

with Image.open("photo.png") as image:
    jpeg = encode_image(image)

with Deck(discover()[0]) as deck:
    print(deck.firmware())
    deck.wake()
    deck.image(1, jpeg)
    deck.refresh()
    deck.brightness(100)
    deck.mode(2)
    for report in deck.reports(60):
        print(report.hex())
```

Encoding happens before any display mutation. `Deck.close()` closes the file
descriptor without sending sleep, reset or flash commands.

## Provenance

[Protocol notes](PROTOCOL.md) include binary hashes, native function addresses,
packet layouts, runtime observations and unresolved questions. The manufacturer
software is downloaded separately from its own website and is not redistributed.
No proprietary images, decompiled code, personal photographs or host-specific
captures are included. Related work: [mirajazz](https://github.com/4ndv/mirajazz)
and the [Mirabox SDK](https://github.com/MiraboxSpace/StreamDock-Device-SDK).

MIT license; unaffiliated with Monstar Gear or Mirabox.

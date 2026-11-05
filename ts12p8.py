#!/usr/bin/env python3
"""Linux hidraw control for the Monstar Deck TS12P8 (0400:1003)."""

import argparse
import fcntl
import io
import json
import os
from pathlib import Path
import select
import sys
import time

VID = 0x0400
PID = 0x1003
REPORT_SIZE = 512
KEY_COUNT = 12
KEY_SIZE = 70
PREFIX = b"CRT\0\0"


def discover():
    """Return only hidraw nodes whose kernel identity matches this model."""
    nodes = []
    for entry in sorted(Path("/sys/class/hidraw").glob("hidraw*")):
        fields = dict(line.split("=", 1) for line in
                      (entry / "device/uevent").read_text().splitlines() if "=" in line)
        identity = fields.get("HID_ID", "").split(":")
        if len(identity) == 3 and tuple(int(v, 16) for v in identity) == (3, VID, PID):
            nodes.append(Path("/dev") / entry.name)
    return nodes


def encode_image(image):
    """Match the OEM key JPEG dimensions, baseline encoding and 96 dpi."""
    image = image.convert("RGB").resize((KEY_SIZE, KEY_SIZE))
    data = io.BytesIO()
    image.save(data, "JPEG", quality=100, subsampling=0, progressive=False, dpi=(96, 96))
    return data.getvalue()


def describe_report(data):
    """Preserve raw input and annotate observed key-shaped ACKs, not touch events."""
    result = {"length": len(data), "hex": data.hex()}
    if (len(data) == REPORT_SIZE and data.startswith(b"ACK\0\0OK\0\0")
            and 1 <= data[9] <= KEY_COUNT and not any(data[11:])):
        result["key_candidate"] = data[9]
        result["state_byte"] = data[10]
    return result


class Deck:
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            identity = bytearray(8)
            fcntl.ioctl(self.fd, 0x80084803, identity, True)  # HIDIOCGRAWINFO
            import struct
            bus, vendor, product = struct.unpack("=Ihh", identity)
            if (bus, vendor, product) != (3, VID, PID):
                raise ValueError("Refusing to control a device other than USB 0400:1003")
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.fd)
            raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def firmware(self):
        data = bytearray(REPORT_SIZE + 1)
        # HIDIOCGINPUT: the OEM uses an input GET_REPORT, not a feature report.
        count = fcntl.ioctl(self.fd, 0xC000480A | (len(data) << 16), data, True)
        return bytes(data[1:count]).rstrip(b"\0").decode("ascii", errors="replace")

    def write_report(self, payload):
        if len(payload) > REPORT_SIZE:
            raise ValueError("Output report exceeds 512 bytes")
        report = b"\0" + payload.ljust(REPORT_SIZE, b"\0")
        if os.write(self.fd, report) != len(report):
            raise OSError("Short HID output report")

    def command(self, word, payload=b""):
        self.write_report(PREFIX + word + payload)

    def wake(self):
        self.command(b"DIS")

    def mode(self, mode):
        if mode not in (1, 2, 3):
            raise ValueError("Mode must be 1, 2 or 3")
        self.command(b"MOD", b"\0\0" + bytes([ord("0") + mode]))

    def brightness(self, percent):
        if not 0 <= percent <= 100:
            raise ValueError("Brightness must be between 0 and 100")
        self.command(b"LIG", b"\0\0" + bytes([percent]))

    def clear(self):
        self.command(b"CLE", b"\0\0\0\xff")

    def image(self, key, jpeg):
        if not 1 <= key <= KEY_COUNT:
            raise ValueError("Key must be between 1 and 12")
        if not 0 < len(jpeg) <= 65535:
            raise ValueError("JPEG size must be between 1 and 65535 bytes")
        if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
            raise ValueError("A baseline JPEG image is required")
        self.command(b"BAT", b"\0\0" + len(jpeg).to_bytes(2, "big") + bytes([key]))
        for offset in range(0, len(jpeg), REPORT_SIZE):
            self.write_report(jpeg[offset:offset + REPORT_SIZE])

    def refresh(self):
        self.command(b"STP")

    def keep_alive(self):
        self.command(b"CONNECT")

    def reports(self, seconds):
        """Yield exact input reports; do not mistake command responses for touches."""
        end = time.monotonic() + seconds if seconds else float("inf")
        heartbeat = 0.0
        while time.monotonic() < end:
            now = time.monotonic()
            if now >= heartbeat:
                self.keep_alive()
                heartbeat = now + 5
            ready, _, _ = select.select(
                [self.fd], [], [], max(0, min(end, heartbeat) - time.monotonic()))
            if ready:
                try:
                    data = os.read(self.fd, REPORT_SIZE)
                except BlockingIOError:
                    continue
                if not data:
                    raise OSError("HID device disconnected")
                yield data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=Path, help="Explicit /dev/hidrawN (identity is verified)")
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("info", help="Read firmware without changing the display")
    show = sub.add_parser("show", help="Display one image in a numbered touch zone")
    show.add_argument("image", type=Path)
    show.add_argument("--key", type=int, choices=range(1, 13), default=1)
    demo = sub.add_parser("demo", help="Display twelve numbered Linux tiles")
    watch = sub.add_parser("watch", help="Print raw input reports as JSON (no actions executed)")
    for command in (show, demo, watch):
        command.add_argument("--seconds", type=float, default=0,
                             help="Keep the connection alive for this many seconds; 0 waits until Ctrl+C")
    args = parser.parse_args(argv)
    if args.operation != "info" and not 0 <= args.seconds < float("inf"):
        parser.error("--seconds must be finite and nonnegative")
    path = args.device
    if path is None:
        nodes = discover()
        if len(nodes) != 1:
            parser.error(f"Found {len(nodes)} TS12P8 devices; specify --device")
        path = nodes[0]
    # Encode images before issuing any command, so decoding errors leave hardware unchanged.
    images = []
    if args.operation in ("show", "demo"):
        from PIL import Image, ImageDraw
        if args.operation == "show":
            with Image.open(args.image) as image:
                images.append((args.key, encode_image(image)))
        else:
            colors = ("#b32a30", "#168540", "#255db0", "#9e4c14")
            for key in range(1, 13):
                image = Image.new("RGB", (KEY_SIZE, KEY_SIZE), colors[(key - 1) % 4])
                draw = ImageDraw.Draw(image)
                draw.text((10, 13), "LINUX", fill="white")
                draw.text((25, 36), str(key), fill="white")
                images.append((key, encode_image(image)))
    with Deck(path) as deck:
        if args.operation == "info":
            print(json.dumps({"device": str(path), "vid": "0400", "pid": "1003",
                              "firmware": deck.firmware()}))
        elif args.operation == "watch":
            print(json.dumps({"listening": str(path), "seconds": args.seconds}), flush=True)
            for data in deck.reports(args.seconds):
                print(json.dumps(describe_report(data)), flush=True)
        else:
            deck.firmware()
            deck.wake()
            deck.clear()
            for key, jpeg in images:
                deck.image(key, jpeg)
            deck.refresh()
            deck.brightness(100)
            deck.mode(2)
            print(f"Sent {len(images)} image(s) to {path}; listening with heartbeat.", flush=True)
            for data in deck.reports(args.seconds):
                print(json.dumps(describe_report(data)), flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except (OSError, ValueError, ImportError) as exc:
        print(f"ts12p8: {exc}", file=sys.stderr)
        sys.exit(1)

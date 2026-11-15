#!/usr/bin/env python3
"""Send a file over a transparent UART radio link using stop-and-wait ACKs."""

"""
9600	32	150 [works]

9600	4	500
9600	8	500
9600	16	500
9600	32	500
9600	64  500 [tested with 1MB file]
9600	128	500
9600	192	500

"""

import argparse
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

import serial
from serial.tools import list_ports

from dx_lr42_protocol import (
    DEFAULT_CHUNK_SIZE, FrameParser, TYPE_ACK, TYPE_DATA, TYPE_DONE,
    TYPE_END, TYPE_ERROR, TYPE_META, TYPE_NAMES, send_frame
)


def show_ports():
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return
    print("Available serial ports:")
    for p in ports:
        print(f"  {p.device}: {p.description}")


def wait_for_response(ser, parser, transfer_id, expected_type, expected_seq,
                      timeout, acked_type=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        waiting = max(0.0, min(0.2, deadline - time.monotonic()))
        ser.timeout = waiting
        data = ser.read(4096)
        frames = parser.feed(data)
        for index, frame in enumerate(frames):
            if frame["transfer_id"] != transfer_id:
                continue
            if frame["type"] == TYPE_ERROR:
                parser.pending.extend(frames[index + 1:])
                raise RuntimeError(frame["payload"].decode("utf-8", "replace"))
            if frame["type"] == expected_type and frame["sequence"] == expected_seq:
                if expected_type == TYPE_ACK:
                    if not frame["payload"] or frame["payload"][0] != acked_type:
                        continue
                # Preserve any additional frames received in the same UART read
                # (e.g. ACK and DONE arriving together after the final packet).
                parser.pending.extend(frames[index + 1:])
                return frame
    return None


def send_reliably(ser, parser, frame_type, transfer_id, seq, total, payload,
                  retries, timeout, acked_type=None):
    for attempt in range(1, retries + 2):
        send_frame(ser, frame_type, transfer_id, seq, total, payload)
        response = wait_for_response(
            ser, parser, transfer_id, TYPE_ACK, seq, timeout, acked_type=frame_type
        )
        if response:
            return
        print(f"No ACK for {TYPE_NAMES.get(frame_type, frame_type)} seq={seq}; "
              f"retry {attempt}/{retries + 1}")
    raise TimeoutError(
        f"No ACK after {retries + 1} attempts for "
        f"{TYPE_NAMES.get(frame_type, frame_type)} sequence {seq}"
    )


def main():
    ap = argparse.ArgumentParser(description="Reliable DX-LR42 transparent-UART file sender")
    ap.add_argument("--port", required=False, help="COM port, e.g. COM5")
    ap.add_argument("--baud", type=int, default=9600, help="UART baud rate; default 9600")
    ap.add_argument("--file", help="File to send")
    ap.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
                    help="File data bytes per packet; default 160")
    ap.add_argument("--timeout", type=float, default=2.0, help="ACK timeout seconds")
    ap.add_argument("--retries", type=int, default=3, help="Retries per packet")
    ap.add_argument("--list-ports", action="store_true", help="List serial ports and exit")
    args = ap.parse_args()

    if args.list_ports:
        show_ports()
        return
    if not args.port or not args.file:
        ap.error("--port and --file are required unless --list-ports is used")
    path = Path(args.file)
    if not path.is_file():
        ap.error(f"File not found: {path}")
    if not 1 <= args.chunk_size <= 180:
        ap.error("--chunk-size must be between 1 and 180 bytes for the default packet budget")

    size = path.stat().st_size
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    sha256 = digest.hexdigest()
    chunk_count = (size + args.chunk_size - 1) // args.chunk_size
    transfer_id = secrets.randbits(32)

    metadata = json.dumps({
        "filename": path.name,
        "size": size,
        "sha256": sha256,
        "chunk_size": args.chunk_size,
    }, separators=(",", ":")).encode("utf-8")

    print(f"File: {path} ({size} bytes)")
    print(f"SHA-256: {sha256}")
    print(f"Chunks: {chunk_count}; transfer ID: {transfer_id:08X}")
    print(f"Opening {args.port} at {args.baud} baud, 8-N-1...")

    try:
        with serial.Serial(args.port, args.baud, bytesize=8, parity="N",
                           stopbits=1, timeout=0.2, write_timeout=5) as ser:
            time.sleep(0.3)
            ser.reset_input_buffer()
            parser = FrameParser()

            send_reliably(ser, parser, TYPE_META, transfer_id, 0, chunk_count,
                          metadata, args.retries, args.timeout)
            print("Receiver accepted file metadata.")

            sent = 0
            with path.open("rb") as f:
                for seq in range(chunk_count):
                    payload = f.read(args.chunk_size)
                    send_reliably(ser, parser, TYPE_DATA, transfer_id, seq,
                                  chunk_count, payload, args.retries, args.timeout)
                    sent += len(payload)
                    pct = 100.0 if size == 0 else sent * 100.0 / size
                    print(f"\rSent {sent}/{size} bytes ({pct:.1f}%)", end="", flush=True)

            print()
            send_reliably(ser, parser, TYPE_END, transfer_id, chunk_count,
                          chunk_count, b"", args.retries, args.timeout)

            done = wait_for_response(ser, parser, transfer_id, TYPE_DONE,
                                     chunk_count, args.timeout * (args.retries + 1))
            if not done:
                raise TimeoutError("Receiver did not confirm final file verification.")
            print("SUCCESS: receiver verified the file SHA-256.")
    except (serial.SerialException, OSError, TimeoutError, RuntimeError, ValueError) as exc:
        print(f"\nTRANSFER FAILED: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

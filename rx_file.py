#!/usr/bin/env python3
"""Receive a file over a transparent UART radio link using stop-and-wait ACKs."""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import serial
from serial.tools import list_ports

from dx_lr42_protocol import (
    FrameParser, TYPE_ACK, TYPE_DATA, TYPE_DONE, TYPE_END, TYPE_ERROR,
    TYPE_META, TYPE_NAMES, ack_frame, send_frame
)


def show_ports():
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return
    print("Available serial ports:")
    for p in ports:
        print(f"  {p.device}: {p.description}")


def send_error(ser, transfer_id, message):
    try:
        send_frame(ser, TYPE_ERROR, transfer_id, 0, 0, message.encode("utf-8")[:200])
    except serial.SerialException:
        pass


def safe_filename(name):
    # Do not allow a remote sender to choose a directory path.
    cleaned = Path(name).name
    if cleaned in ("", ".", ".."):
        raise ValueError("Invalid filename received")
    return cleaned


def main():
    ap = argparse.ArgumentParser(description="Reliable DX-LR42 transparent-UART file receiver")
    ap.add_argument("--port", help="COM port, e.g. COM6")
    ap.add_argument("--baud", type=int, default=9600, help="UART baud rate; default 9600")
    ap.add_argument("--out", default="received_files", help="Output directory")
    ap.add_argument("--list-ports", action="store_true", help="List serial ports and exit")
    args = ap.parse_args()

    if args.list_ports:
        show_ports()
        return
    if not args.port:
        ap.error("--port is required unless --list-ports is used")

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    parser = FrameParser()

    active_id = None
    metadata = None
    temp_path = None
    output_handle = None
    expected_seq = 0
    received_bytes = 0
    sha = hashlib.sha256()
    total_chunks = 0

    print(f"Listening on {args.port} at {args.baud} baud, 8-N-1...")
    print("Waiting for a sender. Press Ctrl+C to stop.")

    try:
        with serial.Serial(args.port, args.baud, bytesize=8, parity="N",
                           stopbits=1, timeout=0.2, write_timeout=5) as ser:
            ser.reset_input_buffer()
            while True:
                data = ser.read(4096)
                if not data:
                    continue

                for frame in parser.feed(data):
                    ft = frame["type"]
                    tid = frame["transfer_id"]
                    seq = frame["sequence"]
                    payload = frame["payload"]

                    if ft == TYPE_META:
                        try:
                            incoming = json.loads(payload.decode("utf-8"))
                            name = safe_filename(incoming["filename"])
                            size = int(incoming["size"])
                            expected_hash = str(incoming["sha256"]).lower()
                            chunk_size = int(incoming["chunk_size"])
                            if size < 0 or not 1 <= chunk_size <= 180:
                                raise ValueError("Invalid file size/chunk size")
                            if len(expected_hash) != 64:
                                raise ValueError("Invalid SHA-256 value")

                            # Start/restart only when a valid META packet arrives.
                            if output_handle:
                                output_handle.close()
                            active_id = tid
                            metadata = {
                                "filename": name,
                                "size": size,
                                "sha256": expected_hash,
                                "chunk_size": chunk_size,
                            }
                            total_chunks = (size + chunk_size - 1) // chunk_size
                            expected_seq = 0
                            received_bytes = 0
                            sha = hashlib.sha256()
                            temp_path = output_dir / (name + f".{tid:08X}.part")
                            output_handle = temp_path.open("wb")
                            print(f"\nIncoming: {name} ({size} bytes), "
                                  f"{total_chunks} chunks, ID={tid:08X}")
                            ack_frame(ser, tid, TYPE_META, seq)
                        except Exception as exc:
                            send_error(ser, tid, f"Bad metadata: {exc}")
                        continue

                    if tid != active_id or metadata is None:
                        continue

                    if ft == TYPE_DATA:
                        if seq < expected_seq:
                            # Duplicate retransmission: ACK again without writing twice.
                            ack_frame(ser, tid, TYPE_DATA, seq)
                            continue
                        if seq != expected_seq or seq >= total_chunks:
                            # Stop-and-wait sender should never be ahead; don't ACK bad order.
                            continue
                        if len(payload) == 0 and metadata["size"] != 0:
                            continue
                        if received_bytes + len(payload) > metadata["size"]:
                            send_error(ser, tid, "Received more bytes than declared file size")
                            continue

                        output_handle.write(payload)
                        output_handle.flush()
                        sha.update(payload)
                        received_bytes += len(payload)
                        expected_seq += 1
                        pct = 100.0 if metadata["size"] == 0 else received_bytes * 100.0 / metadata["size"]
                        print(f"\rReceived {received_bytes}/{metadata['size']} bytes ({pct:.1f}%)",
                              end="", flush=True)
                        ack_frame(ser, tid, TYPE_DATA, seq)
                        continue

                    if ft == TYPE_END:
                        if seq != total_chunks or expected_seq != total_chunks:
                            continue
                        output_handle.flush()
                        output_handle.close()
                        output_handle = None

                        actual_hash = sha.hexdigest()
                        if received_bytes != metadata["size"] or actual_hash != metadata["sha256"]:
                            send_error(ser, tid, "File size/SHA-256 verification failed")
                            print("\nERROR: file verification failed.")
                            if temp_path and temp_path.exists():
                                temp_path.unlink()
                            active_id = None
                            metadata = None
                            continue

                        final_path = output_dir / metadata["filename"]
                        if final_path.exists():
                            stem = final_path.stem
                            suffix = final_path.suffix
                            counter = 1
                            while final_path.exists():
                                final_path = output_dir / f"{stem}_{counter}{suffix}"
                                counter += 1
                        os.replace(temp_path, final_path)
                        print(f"\nSUCCESS: saved and verified {final_path}")
                        send_frame(ser, TYPE_DONE, tid, total_chunks, total_chunks,
                                   actual_hash.encode("ascii"))
                        active_id = None
                        metadata = None
                        temp_path = None
                        continue

    except KeyboardInterrupt:
        print("\nReceiver stopped.")
    except (serial.SerialException, OSError, ValueError) as exc:
        print(f"\nRECEIVER ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        if output_handle:
            output_handle.close()


if __name__ == "__main__":
    main()

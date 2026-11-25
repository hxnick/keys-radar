#!/usr/bin/env python3
"""Check the Codex App Server stdio handshake without starting a model turn."""

import argparse
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time


def send(stream, message):
    stream.write((json.dumps(message) + "\n").encode())
    stream.flush()


def receive_initialize(stream, timeout):
    deadline = time.monotonic() + timeout
    pending = b""
    with selectors.DefaultSelector() as ready:
        ready.register(stream, selectors.EVENT_READ)
        while ready.select(max(0, deadline - time.monotonic())):
            chunk = os.read(stream.fileno(), 8192)
            if not chunk:
                return "stdout closed before an initialize response"
            pending += chunk
            if len(pending) > 1_048_576:
                return "response exceeds the diagnostic limit"
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                except (ValueError, UnicodeError):
                    return "unexpected non-JSON response on stdout"
                if isinstance(message, dict) and message.get("id") == 1:
                    if isinstance(message.get("result"), dict):
                        return None
                    error = message.get("error")
                    if isinstance(error, dict) and type(error.get("code")) is int:
                        return f"initialize rejected (JSON-RPC code {error['code']})"
                    return "initialize response had no result object"
            if time.monotonic() >= deadline:
                break
    return "timed out waiting for initialize"


def stderr_hint(stderr):
    stderr.seek(0)
    captured = stderr.read(1_048_576).decode(errors="replace").lower()
    if "readonly database" in captured or "read-only database" in captured:
        return "Codex reported a read-only SQLite state database."
    if "operation not permitted" in captured or "permission denied" in captured:
        return "Codex reported an operation or directory permission error."
    if "unknown field" in captured or "invalid config" in captured:
        return "Codex reported a configuration error."
    return "No known diagnostic signature matched stderr."


def probe(args, temporary):
    command = [args.codex, "app-server", "--listen", "stdio://"]
    if args.isolated:
        command += ["-c", "sqlite_home=" + json.dumps(str(temporary)),
                    "-c", "log_dir=" + json.dumps(str(temporary))]
    with tempfile.TemporaryFile(dir=temporary) as stderr:
        try:
            worker = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)
        except OSError as error:
            print(f"FAIL: could not launch Codex ({error.strerror}).")
            return 1
        try:
            send(worker.stdin, {"id": 1, "method": "initialize",
                              "params": {"clientInfo": {"name": "keys-radar-s0-02", "version": "1.0.0"}}})
            failure = receive_initialize(worker.stdout, args.timeout)
            if failure is None:
                send(worker.stdin, {"method": "initialized"})
        except BrokenPipeError:
            failure = "App Server closed stdin during the handshake"
        finally:
            worker.stdin.close()
            try:
                worker.wait(timeout=2)
            except subprocess.TimeoutExpired:
                worker.terminate()
                try:
                    worker.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait()
            worker.stdout.close()
        if failure is None:
            print("PASS: Codex App Server stdio initialize/initialized.")
            return 0
        print(f"FAIL: {failure}. Process exit: {worker.returncode}.")
        print(stderr_hint(stderr))
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex", help="Codex executable")
    parser.add_argument("--timeout", type=int, default=20, choices=range(1, 61), metavar="SECONDS")
    parser.add_argument("--isolated", action="store_true", help="Use temporary SQLite state and log paths")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="keys-radar-stdio-") as temporary:
        print("Mode:", "isolated state" if args.isolated else "default Codex state", flush=True)
        return probe(args, Path(temporary))


if __name__ == "__main__":
    sys.exit(main())

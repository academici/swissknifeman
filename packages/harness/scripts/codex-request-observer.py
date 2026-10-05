#!/usr/bin/env python3
"""Transparent stdio observer at the native client/app-server boundary."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.provider.request_lifecycle import Observer, status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(status(args.output_dir)))
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("provide -- codex app-server [options], or --status")
    observer = Observer(args.output_dir)
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def relay(source, destination, direction):
        try:
            while line := source.readline():
                try:
                    message = json.loads(line)
                    if isinstance(message, dict):
                        observer.observe(direction, message)
                except (ValueError, KeyError, TypeError):
                    pass
                destination.write(line)
                destination.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            if direction == "client":
                child.stdin.close()

    writer = threading.Thread(target=relay, args=(sys.stdin.buffer, child.stdin, "client"), daemon=True)
    writer.start()
    try:
        relay(child.stdout, sys.stdout.buffer, "server")
        return child.wait()
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait()
        child.stdout.close()
        observer.disconnect(exit_code=child.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

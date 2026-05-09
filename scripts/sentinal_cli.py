#!/usr/bin/env python3
import argparse
import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_start_command(host: str = "0.0.0.0", port: int = 8000) -> list[str]:
    return [
        "uvicorn",
        "pi_app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]


def start(host: str = "0.0.0.0", port: int = 8000) -> int:
    env = os.environ.copy()
    env.setdefault("SENTINAL_ENABLE_SPEAKER", "0")
    print(f"[ready] Sentinal listening on {host}:{port}", flush=True)
    try:
        return subprocess.run(build_start_command(host=host, port=port), cwd=PROJECT_ROOT, env=env).returncode
    except KeyboardInterrupt:
        print("[stop] Sentinal stopped", flush=True)
        return 130


def main() -> None:
    parser = argparse.ArgumentParser(prog="sentinal")
    subparsers = parser.add_subparsers(dest="command", required=True)
    start_parser = subparsers.add_parser("start", help="Start Sentinal in foreground mode.")
    start_parser.add_argument("--host", default="0.0.0.0")
    start_parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.command == "start":
        raise SystemExit(start(host=args.host, port=args.port))


if __name__ == "__main__":
    main()

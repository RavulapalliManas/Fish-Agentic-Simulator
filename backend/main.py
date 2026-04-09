"""Executable entrypoint for the packaged FastAPI backend."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

APP_DIR = Path(__file__).resolve().parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from service import create_app  # noqa: E402  pylint: disable=wrong-import-position


def main() -> None:
    parser = argparse.ArgumentParser(description="Fish stimulus backend")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind")
    args = parser.parse_args()

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

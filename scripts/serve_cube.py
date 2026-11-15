"""Launch the cube explorer from any working directory, with clear bind failures."""

import argparse
import os
import socket
from pathlib import Path

import uvicorn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    try:
        with socket.socket() as probe:
            probe.bind((args.host, args.port))
    except OSError as error:
        parser.exit(
            1,
            f"Cannot open {args.host}:{args.port}: {error}. "
            "Run this command in your terminal if the agent sandbox blocks listening ports; "
            "choose another --port if the address is in use. No server was started.\n",
        )
    uvicorn.run("app:app", app_dir=str(root), host=args.host, port=args.port)


if __name__ == "__main__":
    main()

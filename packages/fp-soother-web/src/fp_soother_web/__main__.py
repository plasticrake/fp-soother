"""Entry point: run the Soother web UI with uvicorn."""

from __future__ import annotations

import argparse
import logging

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Soother web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log BLE command intentions and decrypted device state.",
    )
    args = parser.parse_args()
    if args.debug:
        # uvicorn's own logging config doesn't add handlers to the root
        # logger, so without this, fp_soother_lib's debug records would have
        # nowhere to go even with the logger's level raised.
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("fp_soother_lib").setLevel(logging.DEBUG)
        # bleak (and its backend) are noisy at DEBUG; keep them quiet even
        # though the root logger is otherwise permissive.
        logging.getLogger("bleak").setLevel(logging.WARNING)
    uvicorn.run(
        "fp_soother_web.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        log_level="debug" if args.debug else "info",
    )


if __name__ == "__main__":
    main()

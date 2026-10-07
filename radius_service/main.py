"""
Entry point: run the PowerHouse RADIUS gateway.

Environment (see config.py) is provided by /etc/faceapp/radius.env in
production via the facegym-radius systemd unit.
"""

import logging
import signal
import sys

from config import settings
from server import build_server


def main() -> int:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s - %(message)s",
        stream=sys.stderr,
    )

    server = build_server()
    logging.info(
        "RADIUS gateway starting: auth=%s:%s acct=%s:%s backend=%s",
        settings.LISTEN_HOST,
        settings.AUTH_PORT,
        settings.LISTEN_HOST,
        settings.ACCT_PORT,
        settings.BACKEND_API_URL,
    )

    stop = {"requested": False}

    def _stop(signum, frame):
        if not stop["requested"]:
            stop["requested"] = True
            logging.info("signal %s received — exiting", signum)
            # pyrad's Run() loops on poll(); there is no clean stop hook, so
            # the standard exit path for this simple gateway is sys.exit.
            sys.exit(0)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    try:
        server.Run()
    except (KeyboardInterrupt, SystemExit):
        logging.info("RADIUS gateway stopped")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

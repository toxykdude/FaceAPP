#!/usr/bin/env python
"""
Manual RADIUS test client (radtest equivalent).

Sends a PAP Access-Request with User-Name == User-Password == <document>
(the portal contract) and prints the reply code and attributes.

Usage:
    python tools/radtest.py <document> <server> [secret] [authport]

The secret defaults to $RADIUS_SHARED_SECRET (e.g. source
/etc/faceapp/radius.env first). Exits 0 on Access-Accept, 1 on reject,
2 on transport error — usable in the deploy verification checklist.
"""

import os
import socket
import sys

from pyrad import packet
from pyrad.client import Client
from pyrad.dictionary import Dictionary


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    document, server = sys.argv[1], sys.argv[2]
    secret = (
        sys.argv[3] if len(sys.argv) > 3 else os.getenv("RADIUS_SHARED_SECRET", "")
    )
    authport = int(sys.argv[4]) if len(sys.argv) > 4 else 1812
    if not secret:
        print("no secret: pass it or export RADIUS_SHARED_SECRET")
        return 2

    # Vendored minimal dictionary in this repo (same one the server loads).
    dict_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dictionary"
    )
    radius_dict = Dictionary(dict_path)

    client = Client(
        server,
        authport=authport,
        secret=secret.encode("utf-8"),
        dict=radius_dict,
    )
    # pyrad's Client requires a socket it can send from.
    client.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.socket.bind(("0.0.0.0", 0))

    req = client.CreateAuthPacket(code=packet.AccessRequest)
    req["User-Name"] = document
    req["User-Password"] = req.PwCrypt(document)
    req["NAS-IP-Address"] = "127.0.0.1"
    req["NAS-Port"] = 0

    try:
        reply = client.SendPacket(req)
    except Exception as exc:  # noqa: BLE001 — CLI tool reports anything
        print(f"ERROR: {exc}")
        return 2

    print(f"reply code: {reply.code}")
    for attr in reply.keys():
        print(f"  {attr}: {reply[attr][0]}")

    if reply.code == packet.AccessAccept:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

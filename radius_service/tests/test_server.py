"""
Unit tests for the RADIUS ⇄ backend gateway.

Offline: handlers are driven directly with crafted pyrad packets; the backend
client is a stub; SendReplyPacket is captured instead of hitting a socket.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyrad import packet  # noqa: E402
from pyrad.dictionary import Dictionary  # noqa: E402

import server as radius_server  # noqa: E402
from server import PowerHouseRadiusServer, _reply_message  # noqa: E402

import os

DICT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "dictionary"
)

SECRET = "test-radius-shared-secret"


class StubBackend:
    """Backend double with scriptable decisions."""

    def __init__(self, decision=None, error=None, acct_ok=True):
        self.decision = decision or {"allowed": True}
        self.error = error
        self.acct_ok = acct_ok
        self.authorize_calls = []
        self.accounting_calls = []

    def authorize(self, **kwargs):
        self.authorize_calls.append(kwargs)
        if self.error:
            raise self.error
        return self.decision

    def send_accounting(self, payload):
        self.accounting_calls.append(payload)
        return self.acct_ok


def make_server(backend):
    # addresses=[] → no sockets bound; handlers driven directly.
    srv = PowerHouseRadiusServer(
        addresses=[], secret=SECRET, backend=backend, authport=0, acctport=0
    )
    replies = []

    def capture(fd, reply):
        replies.append(reply)

    srv.SendReplyPacket = capture
    srv.replies = replies
    return srv


def auth_packet(document="1234567890", password=None, secret=SECRET):
    secret_b = secret.encode("utf-8") if isinstance(secret, str) else secret
    pkt = packet.AuthPacket(dict=Dictionary(DICT_PATH), secret=secret_b)
    pkt["User-Name"] = document
    pkt["User-Password"] = pkt.PwCrypt(password if password is not None else document)
    pkt["NAS-IP-Address"] = "10.162.36.1"
    pkt["Calling-Station-Id"] = "AA:BB:CC:DD:EE:FF"
    pkt["Framed-IP-Address"] = "10.162.40.55"
    pkt.fd = None
    pkt.source = ("10.162.36.1", 54321)
    return pkt


ALLOWED = {
    "allowed": True,
    "reason": None,
    "member_id": "m-1",
    "session_timeout_seconds": 14400,
    "idle_timeout_seconds": 1800,
    "acct_interim_interval_seconds": 600,
    "message_es": "¡Bienvenido!",
    "message_en": "Welcome!",
}
DENIED = {
    "allowed": False,
    "reason": "unpaid_membership",
    "message_es": "Pendiente de pago.",
    "message_en": "Payment pending.",
}


# --- Accept / reject ----------------------------------------------------------


def test_accept_carries_radius_attributes():
    backend = StubBackend(decision=ALLOWED)
    srv = make_server(backend)
    srv.HandleAuthPacket(auth_packet())

    assert len(srv.replies) == 1
    reply = srv.replies[0]
    assert reply.code == packet.AccessAccept
    assert reply["Session-Timeout"][0] == 14400
    assert reply["Idle-Timeout"][0] == 1800
    assert reply["Acct-Interim-Interval"][0] == 600
    assert "¡Bienvenido!" in reply["Reply-Message"][0]
    assert "Welcome!" in reply["Reply-Message"][0]


def test_reject_carries_bilingual_reply_message():
    backend = StubBackend(decision=DENIED)
    srv = make_server(backend)
    srv.HandleAuthPacket(auth_packet())

    reply = srv.replies[0]
    assert reply.code == packet.AccessReject
    assert "Pendiente de pago." in reply["Reply-Message"][0]
    assert "Payment pending." in reply["Reply-Message"][0]


def test_backend_translates_document_and_client_attrs():
    backend = StubBackend(decision=ALLOWED)
    srv = make_server(backend)
    srv.HandleAuthPacket(auth_packet(document="987654321"))

    call = backend.authorize_calls[0]
    assert call["document"] == "987654321"
    assert call["client_mac"] == "AA:BB:CC:DD:EE:FF"
    assert call["client_ip"] == "10.162.40.55"
    assert call["nas_ip"] == "10.162.36.1"


def test_backend_error_fails_closed():
    from backend_client import BackendError

    backend = StubBackend(error=BackendError("connection refused"))
    srv = make_server(backend)
    srv.HandleAuthPacket(auth_packet())

    assert srv.replies[0].code == packet.AccessReject
    assert "Servicio no disponible" in srv.replies[0]["Reply-Message"][0]


def test_password_mismatch_rejects():
    # Wrong shared secret ⇒ decrypted password is garbage ⇒ reject. This is
    # the implicit secret verification documented in server.py.
    backend = StubBackend(decision=ALLOWED)
    srv = make_server(backend)
    srv.HandleAuthPacket(
        auth_packet(document="1234567890", password="not-the-document")
    )
    assert srv.replies[0].code == packet.AccessReject
    assert backend.authorize_calls == []


def test_empty_username_rejects():
    backend = StubBackend(decision=ALLOWED)
    srv = make_server(backend)
    srv.HandleAuthPacket(auth_packet(document=""))
    assert srv.replies[0].code == packet.AccessReject


# --- Cooldown -----------------------------------------------------------------


def test_cooldown_locks_after_threshold_failures():
    backend = StubBackend(decision=DENIED)
    srv = make_server(backend)
    srv.cooldown = radius_server.Cooldown(threshold=3, cooldown_seconds=60)

    for _ in range(3):
        srv.HandleAuthPacket(auth_packet())
    assert len(backend.authorize_calls) == 3

    # Locked now: rejected WITHOUT a backend call.
    srv.HandleAuthPacket(auth_packet())
    assert len(backend.authorize_calls) == 3
    assert srv.replies[-1].code == packet.AccessReject


def test_cooldown_success_resets_failures():
    backend = StubBackend(decision=ALLOWED)
    srv = make_server(backend)
    srv.cooldown = radius_server.Cooldown(threshold=2, cooldown_seconds=60)

    srv.cooldown.record_failure("1234567890")
    srv.HandleAuthPacket(auth_packet())  # success resets
    assert srv.cooldown.is_locked("1234567890") is False
    assert srv.cooldown._fails.get("1234567890") is None


# --- Accounting ----------------------------------------------------------------


def acct_packet(status_code=1, secret=SECRET, **attrs):
    # Build exactly like a real NAS: serialize an AcctPacket (RequestPacket
    # computes the proper Request Authenticator), then decode it like the
    # server does — that is what makes VerifyAcctRequest() pass.
    secret_b = secret.encode("utf-8") if isinstance(secret, str) else secret
    send = packet.AcctPacket(dict=Dictionary(DICT_PATH), secret=secret_b)
    send.code = packet.AccountingRequest
    send["Acct-Status-Type"] = status_code
    send["User-Name"] = attrs.pop("user", "1234567890")
    send["Acct-Session-Id"] = attrs.pop("session", "sess-42")
    send["NAS-IP-Address"] = "10.162.36.1"
    send["Calling-Station-Id"] = "AA:BB:CC:DD:EE:FF"
    send["Framed-IP-Address"] = "10.162.40.55"
    if "input" in attrs:
        send["Acct-Input-Octets"] = attrs.pop("input")
    if "output" in attrs:
        send["Acct-Output-Octets"] = attrs.pop("output")
    if "time" in attrs:
        send["Acct-Session-Time"] = attrs.pop("time")
    if "cause" in attrs:
        send["Acct-Terminate-Cause"] = attrs.pop("cause")

    raw = send.RequestPacket()
    pkt = packet.AcctPacket(dict=Dictionary(DICT_PATH), secret=secret_b, packet=raw)
    pkt.fd = None
    pkt.source = ("10.162.36.1", 54321)
    return pkt


def test_acct_start_maps_and_acks():
    backend = StubBackend()
    srv = make_server(backend)
    srv.HandleAcctPacket(acct_packet(status_code=1, input=0, output=0))

    assert len(backend.accounting_calls) == 1
    payload = backend.accounting_calls[0]
    assert payload["status"] == "start"
    assert payload["username"] == "1234567890"
    assert payload["acct_session_id"] == "sess-42"
    assert payload["nas_ip"] == "10.162.36.1"
    assert payload["calling_station_id"] == "AA:BB:CC:DD:EE:FF"
    assert srv.replies[0].code == packet.AccountingResponse


def test_acct_stop_maps_cause_and_counters():
    backend = StubBackend()
    srv = make_server(backend)
    srv.HandleAcctPacket(
        acct_packet(status_code=2, input=111, output=222, time=3600, cause=1)
    )

    payload = backend.accounting_calls[0]
    assert payload["status"] == "stop"
    assert payload["acct_input_octets"] == 111
    assert payload["acct_output_octets"] == 222
    assert payload["acct_session_time"] == 3600
    assert payload["acct_terminate_cause"] == "1"


def test_acct_interim_maps():
    backend = StubBackend()
    srv = make_server(backend)
    srv.HandleAcctPacket(acct_packet(status_code=3, input=500))
    assert backend.accounting_calls[0]["status"] == "interim"
    assert backend.accounting_calls[0]["acct_input_octets"] == 500


def test_acct_bad_status_type_dropped():
    backend = StubBackend()
    srv = make_server(backend)
    srv.HandleAcctPacket(acct_packet(status_code=15))  # Accounting-On (NAS boot)
    # Accounting-On/Off (13/15) are NAS lifecycle events, not member
    # sessions — dropped without a backend call, no crash, no reply needed.
    assert backend.accounting_calls == []
    assert srv.replies == []


def test_acct_backend_failure_still_acks():
    # Accounting is telemetry: the NAS retransmits on missing ack, but we
    # must not wedge the RADIUS socket waiting on the backend.
    backend = StubBackend(acct_ok=False)
    srv = make_server(backend)
    srv.HandleAcctPacket(acct_packet(status_code=1))
    assert srv.replies and srv.replies[0].code == packet.AccountingResponse


# --- Helpers -------------------------------------------------------------------


def test_reply_message_bilingual_join_and_truncation():
    msg = _reply_message("Hola.", "Hello.")
    assert msg == "Hola. / Hello."
    long = _reply_message("x" * 400, "y" * 400)
    assert len(long.encode("utf-8")) <= 253

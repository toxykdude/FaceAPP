"""
PowerHouse RADIUS server — pfSense captive portal ⇄ FaceAPP backend.

Answers on the auth port (1812) and accounting port (1813) using pyrad.
Every Access-Request is translated into POST /wifi/authorize on the backend;
the accept/reject decision and the reply attributes (Session-Timeout,
Idle-Timeout, Acct-Interim-Interval, Reply-Message) come from the backend —
this service holds NO membership logic of its own.

FAIL CLOSED: if the backend is unreachable, errors, or the internal secret is
rejected, the answer is Access-Reject. A captive portal must never open on
uncertainty.

PAP contract: pfSense CP authenticates with PAP, and our portal page submits
the cédula as BOTH User-Name and User-Password. Enforcing
decrypt(password) == username doubles as shared-secret verification (a wrong
secret yields garbage after decryption) and keeps this gateway from ever
"authenticating" a packet it could not actually read.

Anti-brute-force: FAIL_THRESHOLD consecutive rejects for the same document
lock it for FAIL_COOLDOWN_SECONDS (in-memory; a restart clears it).
"""

import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

from pyrad import packet
from pyrad.dictionary import Dictionary
from pyrad.server import Server, RemoteHost

from backend_client import BackendClient, BackendError
from config import settings

logger = logging.getLogger(__name__)

# RFC 2865 attribute codes used for raw access. pyrad's string-key
# __getitem__ runs DecodeString on User-Password's STILL-ENCRYPTED bytes and
# mangles them; the integer-key access returns the raw bytes PwDecrypt needs.
ATTR_USER_PASSWORD = 2

# Bilingual strings for errors this service generates itself (backend
# denials arrive already bilingual from /wifi/authorize).
MSG_SERVICE_UNAVAILABLE = (
    "Servicio no disponible. Intenta más tarde.",
    "Service unavailable. Try again later.",
)
MSG_BAD_REQUEST = (
    "Solicitud inválida. Intenta de nuevo.",
    "Invalid request. Please try again.",
)

_ACCT_STATUS = {1: "start", 2: "stop", 3: "interim"}

# RADIUS string attributes are capped at 253 bytes — truncate defensively so
# a long bilingual Reply-Message can never produce an invalid packet.
_MAX_REPLY_MESSAGE_BYTES = 243  # headroom for " / " join and UTF-8 overhead


def _reply_message(es: str, en: str) -> str:
    joined = f"{es} / {en}"
    return joined.encode("utf-8")[:_MAX_REPLY_MESSAGE_BYTES].decode(
        "utf-8", errors="ignore"
    )


def _first(pkt: Any, attr: str) -> Optional[str]:
    """First value of an attribute as a stripped string, or None."""
    if attr not in pkt:
        return None
    value = pkt[attr][0]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


class Cooldown:
    """Per-document consecutive-failure lockout (thread-safe)."""

    def __init__(self, threshold: int, cooldown_seconds: int) -> None:
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._fails: Dict[str, int] = {}
        self._locked_until: Dict[str, float] = {}

    def is_locked(self, document: str) -> bool:
        with self._lock:
            return time.monotonic() < self._locked_until.get(document, 0)

    def record_failure(self, document: str) -> None:
        with self._lock:
            fails = self._fails.get(document, 0) + 1
            self._fails[document] = fails
            if fails >= self.threshold:
                self._locked_until[document] = (
                    time.monotonic() + self.cooldown_seconds
                )
                logger.warning(
                    "document locked for %ss after %s failed attempts",
                    self.cooldown_seconds,
                    document,
                )

    def record_success(self, document: str) -> None:
        with self._lock:
            self._fails.pop(document, None)
            self._locked_until.pop(document, None)


class PowerHouseRadiusServer(Server):
    """pyrad Server with FaceAPP-backed authorization and accounting."""

    def __init__(
        self,
        addresses,
        secret: str,
        backend: BackendClient,
        authport: int = 1812,
        acctport: int = 1813,
        dict_path: Optional[str] = None,
    ) -> None:
        import os

        if dict_path is None:
            # Vendored minimal dictionary (pyrad 2.5+ ships none) — see the
            # file header for why the attribute set is exactly this small.
            dict_path = os.path.join(os.path.dirname(__file__), "dictionary")
        # pyrad 2.5 requires a binary secret.
        secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
        super().__init__(
            addresses=addresses,
            authport=authport,
            acctport=acctport,
            hosts={
                # Accept requests from any source that proves the shared
                # secret — pfSense may source from different interfaces, and
                # network restriction is the firewall's job (runbook).
                "0.0.0.0": RemoteHost("0.0.0.0", secret_bytes, "pfsense-cp")
            },
            dict=Dictionary(dict_path),
            auth_enabled=True,
            acct_enabled=True,
            coa_enabled=False,
        )
        self.backend = backend
        self.cooldown = Cooldown(settings.FAIL_THRESHOLD, settings.FAIL_COOLDOWN_SECONDS)

    # --- Authentication -------------------------------------------------

    def HandleAuthPacket(self, pkt: Any) -> None:
        username = _first(pkt, "User-Name") or ""
        document = username.strip()
        logger.info("Access-Request for document=%r from %s", document, pkt.source)

        if not document:
            self._reject(pkt, MSG_BAD_REQUEST)
            return

        if self.cooldown.is_locked(document):
            logger.warning("document %r is locked out (brute-force cooldown)", document)
            self._reject(pkt, MSG_SERVICE_UNAVAILABLE)
            return

        # PAP contract + implicit secret verification (see module docstring).
        try:
            raw_password = pkt[ATTR_USER_PASSWORD][0]
            if isinstance(raw_password, str):  # defensive: never expected
                raw_password = raw_password.encode("utf-8")
            password = pkt.PwDecrypt(raw_password)
        except Exception as exc:  # malformed attribute
            logger.warning("undecryptable User-Password: %s", exc)
            self._reject(pkt, MSG_BAD_REQUEST)
            return
        if password != username:
            logger.warning(
                "User-Password does not match User-Name — wrong shared secret "
                "or non-conformant portal page (document=%r)",
                document,
            )
            self._reject(pkt, MSG_BAD_REQUEST)
            return

        try:
            decision = self.backend.authorize(
                document=document,
                client_mac=_first(pkt, "Calling-Station-Id"),
                client_ip=_first(pkt, "Framed-IP-Address"),
                nas_ip=_first(pkt, "NAS-IP-Address"),
            )
        except BackendError as exc:
            logger.error("authorize failed (fail closed): %s", exc)
            self.cooldown.record_failure(document)
            self._reject(pkt, MSG_SERVICE_UNAVAILABLE)
            return

        if not decision.get("allowed"):
            reason = decision.get("reason")
            logger.info("denied document=%r reason=%s", document, reason)
            self.cooldown.record_failure(document)
            self._reject(
                pkt,
                (decision.get("message_es", ""), decision.get("message_en", "")),
            )
            return

        self.cooldown.record_success(document)
        logger.info(
            "granted document=%r member=%s timeout=%ss",
            document,
            decision.get("member_id"),
            decision.get("session_timeout_seconds"),
        )

        reply = self.CreateReplyPacket(pkt)
        reply.code = packet.AccessAccept
        reply["Session-Timeout"] = [int(decision["session_timeout_seconds"])]
        reply["Idle-Timeout"] = [int(decision["idle_timeout_seconds"])]
        reply["Acct-Interim-Interval"] = [
            int(decision.get("acct_interim_interval_seconds") or 600)
        ]
        reply["Reply-Message"] = [
            _reply_message(
                decision.get("message_es", ""), decision.get("message_en", "")
            )
        ]
        self.SendReplyPacket(pkt.fd, reply)

    def _reject(self, pkt: Any, messages: Tuple[str, str]) -> None:
        reply = self.CreateReplyPacket(pkt)
        reply.code = packet.AccessReject
        reply["Reply-Message"] = [_reply_message(*messages)]
        self.SendReplyPacket(pkt.fd, reply)

    # --- Accounting -------------------------------------------------------

    def HandleAcctPacket(self, pkt: Any) -> None:
        try:
            if not pkt.VerifyAcctRequest():
                logger.warning("accounting packet failed verification from %s", pkt.source)
                return  # drop; do not ack garbage
            payload = self._acct_payload(pkt)
        except Exception as exc:
            logger.error("malformed accounting packet: %s", exc)
            return

        ok = self.backend.send_accounting(payload)
        logger.info(
            "acct %s session=%s user=%r forwarded=%s",
            payload["status"],
            payload["acct_session_id"],
            payload["username"],
            ok,
        )
        reply = self.CreateReplyPacket(pkt)
        reply.code = packet.AccountingResponse
        self.SendReplyPacket(pkt.fd, reply)

    @staticmethod
    def _acct_payload(pkt: Any) -> Dict[str, Any]:
        status_code = pkt["Acct-Status-Type"][0]
        status = _ACCT_STATUS.get(int(status_code))
        if status is None:
            raise ValueError(f"unsupported Acct-Status-Type {status_code}")

        payload: Dict[str, Any] = {
            "status": status,
            "username": _first(pkt, "User-Name") or "",
            "acct_session_id": _first(pkt, "Acct-Session-Id") or "",
            "nas_ip": _first(pkt, "NAS-IP-Address") or "",
        }
        for attr, key in (
            ("Framed-IP-Address", "framed_ip"),
            ("Calling-Station-Id", "calling_station_id"),
            ("Acct-Terminate-Cause", "acct_terminate_cause"),
        ):
            value = _first(pkt, attr)
            if value is not None:
                payload[key] = value
        for attr, key in (
            ("Acct-Input-Octets", "acct_input_octets"),
            ("Acct-Output-Octets", "acct_output_octets"),
            ("Acct-Session-Time", "acct_session_time"),
        ):
            if attr in pkt:
                payload[key] = int(pkt[attr][0])
        if "Event-Timestamp" in pkt:
            payload["event_timestamp"] = str(pkt["Event-Timestamp"][0])
        return payload


def build_server(
    backend: Optional[BackendClient] = None,
    addresses=None,
    authport: Optional[int] = None,
    acctport: Optional[int] = None,
) -> PowerHouseRadiusServer:
    """Factory wiring settings → server (main.py and tests)."""
    if not settings.RADIUS_SHARED_SECRET:
        raise RuntimeError(
            "RADIUS_SHARED_SECRET not configured — refusing to start a server "
            "that cannot verify pfSense"
        )
    return PowerHouseRadiusServer(
        addresses=addresses or [settings.LISTEN_HOST],
        secret=settings.RADIUS_SHARED_SECRET,
        backend=backend or BackendClient(),
        authport=authport or settings.AUTH_PORT,
        acctport=acctport or settings.ACCT_PORT,
    )

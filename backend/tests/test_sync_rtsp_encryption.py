"""
RTSP-at-rest encryption tests for the sync path (WS-6).

The direct camera API (api/cameras.py) already encrypts rtsp_url at rest, but
the sync push path did mass-assignment without encrypting, so cameras created
or edited via sync stored the RTSP URL (incl. embedded credentials) in
plaintext (cleartext-sensitive-data.camera-insert/update-authz-encryption,
CWE-312). sync now encrypts on INSERT and UPDATE, consistent with cameras.py.
"""

import uuid

from core.encryption import decrypt_string, encrypt_string
from models.camera import Camera


def _push(client, headers, *ops):
    return client.post(
        "/api/sync/push", headers=headers, json={"operations": list(ops)}
    ).json()


class TestSyncRtspEncryption:
    def test_camera_insert_encrypts_rtsp_url(self, client, auth_headers, db_session):
        plaintext = "rtsp://camuser:secretpass@10.0.0.5/stream"
        name = f"sync-cam-{uuid.uuid4().hex[:6]}"
        r = _push(
            client,
            auth_headers,
            {
                "table": "cameras",
                "operation": "INSERT",
                "data": {"name": name, "rtsp_url": plaintext},
            },
        )
        assert r["results"][0]["status"] == "success", r

        cam = db_session.query(Camera).filter_by(name=name).first()
        assert cam is not None
        # Stored value is NOT the plaintext (encrypted at rest)...
        assert cam.rtsp_url != plaintext
        # ...and round-trips back to the plaintext via decrypt_string.
        assert decrypt_string(cam.rtsp_url) == plaintext

    def test_camera_update_encrypts_rtsp_url(self, client, auth_headers, db_session):
        # Seed a camera with an already-encrypted URL (as cameras.py would).
        name = f"sync-cam-up-{uuid.uuid4().hex[:6]}"
        cam = Camera(
            name=name,
            rtsp_url=encrypt_string("rtsp://old:oldpass@host/stream"),
        )
        db_session.add(cam)
        db_session.commit()

        new_plaintext = "rtsp://new:newpass@10.0.0.9/stream"
        r = _push(
            client,
            auth_headers,
            {
                "table": "cameras",
                "operation": "UPDATE",
                "id": str(cam.id),
                "data": {"rtsp_url": new_plaintext},
            },
        )
        assert r["results"][0]["status"] == "success", r

        db_session.expire_all()
        refreshed = db_session.query(Camera).filter_by(name=name).first()
        assert refreshed.rtsp_url != new_plaintext  # encrypted at rest
        assert decrypt_string(refreshed.rtsp_url) == new_plaintext

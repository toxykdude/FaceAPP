"""Template-revocation race tests (reload vs invalidate).

A concurrent CV /reload (_load_templates) and backend member-delete
(/invalidate/{member_id}) can reinsert a revoked template: the reload reads
the backend snapshot BEFORE the delete commits and stores AFTER the
invalidate removed the member. The bounded 60s ``cv:revoked`` marker set is
the generation check that closes the race (see
TemplateCache.revoke_member).

The cv_service CI job has NO Redis service, so these tests patch
``recognition.template_cache.redis.from_url`` with an in-memory fake that
implements exactly the client surface TemplateCache uses. Each test gets a
fresh fake, so no keys leak between tests (and nothing touches real Redis).
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import main
from recognition.template_cache import TemplateCache
from tests.redis_fake import FakeRedis as _FakeRedis


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(
        "recognition.template_cache.redis.from_url", lambda *a, **k: fake
    )
    return fake


def _make_cache(fake_redis) -> TemplateCache:
    return TemplateCache()


def _sample_templates():
    return [
        {
            "member_id": "revoked-member",
            "embedding": [0.1] * 128,
            "name": "Revoked",
            "status": "active",
            "membership_status": "active",
            "membership_end_date": None,
        },
        {
            "member_id": "kept-member",
            "embedding": [0.2] * 128,
            "name": "Kept",
            "status": "active",
            "membership_status": "active",
            "membership_end_date": None,
        },
    ]


@pytest.mark.asyncio
async def test_revoked_member_skipped_on_reload(fake_redis, monkeypatch):
    cache = _make_cache(fake_redis)
    cache.revoke_member("revoked-member")

    async def _sync_templates():
        return _sample_templates()

    monkeypatch.setattr(
        main.service.api_client, "sync_templates", _sync_templates
    )

    await main.service._load_templates()

    assert cache.get_template("revoked-member") is None
    assert cache.get_template("kept-member") is not None
    assert cache.get_template("kept-member")["member_id"] == "kept-member"


def test_invalidate_marks_revoked(fake_redis, monkeypatch):
    cache = _make_cache(fake_redis)
    cache.store_template(
        "member-1",
        np.array([0.1] * 128),
        {"name": "Member One", "status": "active"},
    )
    assert cache.get_template("member-1") is not None

    monkeypatch.setattr(main.settings, "API_KEY", "revocation-test-key")
    client = TestClient(main.app)
    resp = client.post(
        "/invalidate/member-1", headers={"X-API-Key": "revocation-test-key"}
    )
    assert resp.status_code == 200
    assert resp.json()["member_id"] == "member-1"

    assert cache.is_revoked("member-1") is True
    assert cache.get_template("member-1") is None


def test_revocation_marker_expires(fake_redis):
    cache = _make_cache(fake_redis)
    cache.revoke_member("member-2")

    assert cache.is_revoked("member-2") is True
    ttl = cache.redis_client.ttl(cache.REVOKED_SET_KEY)
    assert 0 < ttl <= cache.REVOKED_MARKER_TTL

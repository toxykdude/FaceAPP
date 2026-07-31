"""Template-cache encryption tests (plaintext_biometric_redis_cache).

The cv_service CI job has no Redis service, so these tests patch
``recognition.template_cache.redis.from_url`` with the same in-memory
fake used by test_template_revocation.py.

Contract:
- with ENCRYPTION_KEY set, the raw Redis value must NOT contain the
  embedding bytes (or any plaintext of the record), and get_template
  must round-trip the embedding exactly;
- REQUIRE_PROD_SECRETS without a key must refuse to construct the cache;
- without a key and without REQUIRE_PROD_SECRETS the cache still works
  (dev fallback) with a loud warning;
- legacy cleartext records written before a key was enabled are still
  readable (loudly) so recognition survives rollout.
"""

import json

import numpy as np
import pytest

import config
from recognition.template_cache import TemplateCache
from tests.redis_fake import FakeRedis

# 32 raw bytes base64-encoded — a valid ENCRYPTION_KEY.
TEST_KEY = "ZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGQ="


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(
        "recognition.template_cache.redis.from_url", lambda *a, **k: fake
    )
    return fake


@pytest.fixture
def encrypted_settings(monkeypatch):
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", TEST_KEY)
    monkeypatch.setattr(config.settings, "REQUIRE_PROD_SECRETS", False)


def _embedding():
    return np.array([0.123456789] * 128, dtype=np.float32)


def test_store_template_encrypts_at_rest(fake_redis, encrypted_settings):
    cache = TemplateCache()
    embedding = _embedding()
    cache.store_template(
        "member-1",
        embedding,
        {"name": "Encrypted", "status": "active"},
    )

    raw = fake_redis.get("member:template:v0:member-1")
    assert raw is not None
    envelope = json.loads(raw)
    assert envelope.get("encrypted") is True
    # The plaintext record (embedding + metadata) must not appear anywhere
    # in the stored value.
    plaintext = json.dumps(
        {
            "template": embedding.tolist(),
            "member_id": "member-1",
            "name": "Encrypted",
            "status": "active",
            "membership_status": None,
            "membership_end_date": None,
        }
    )
    assert plaintext not in raw
    assert "0.123456789" not in raw


def test_get_template_roundtrips_encrypted(fake_redis, encrypted_settings):
    cache = TemplateCache()
    embedding = _embedding()
    cache.store_template(
        "member-1",
        embedding,
        {"name": "Roundtrip", "status": "active"},
    )

    cached = cache.get_template("member-1")
    assert cached is not None
    assert cached["member_id"] == "member-1"
    assert cached["name"] == "Roundtrip"
    assert np.allclose(cached["template"], embedding)


def test_get_all_active_templates_roundtrips_encrypted(fake_redis, encrypted_settings):
    cache = TemplateCache()
    cache.store_template(
        "member-1",
        _embedding(),
        {"name": "Active", "status": "active"},
    )
    cache.store_template(
        "member-2",
        _embedding(),
        {"name": "Inactive", "status": "inactive"},
    )

    active = cache.get_all_active_templates()
    assert [t["member_id"] for t in active] == ["member-1"]
    assert np.allclose(active[0]["template"], _embedding())


def test_require_prod_secrets_refuses_cleartext_cache(fake_redis, monkeypatch):
    """REQUIRE_PROD_SECRETS without ENCRYPTION_KEY must refuse to start."""
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "")
    monkeypatch.setattr(config.settings, "REQUIRE_PROD_SECRETS", True)
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        TemplateCache()


def test_dev_fallback_without_key_constructs(fake_redis, monkeypatch):
    """No key + REQUIRE_PROD_SECRETS off: dev fallback, still functional."""
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "")
    monkeypatch.setattr(config.settings, "REQUIRE_PROD_SECRETS", False)
    cache = TemplateCache()
    cache.store_template(
        "member-1",
        _embedding(),
        {"name": "Dev", "status": "active"},
    )
    raw = fake_redis.get("member:template:v0:member-1")
    assert "0.1234567" in raw  # cleartext, dev-only fallback
    assert cache.get_template("member-1") is not None


def test_legacy_plaintext_entry_readable_after_key_enabled(fake_redis, monkeypatch):
    """Entries written before encryption stay readable (loudly) during rollout."""
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "")
    monkeypatch.setattr(config.settings, "REQUIRE_PROD_SECRETS", False)
    legacy = TemplateCache()
    legacy.store_template(
        "member-1",
        _embedding(),
        {"name": "Legacy", "status": "active"},
    )
    # Enable the key afterwards
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", TEST_KEY)
    encrypted = TemplateCache()
    cached = encrypted.get_template("member-1")
    assert cached is not None
    assert cached["name"] == "Legacy"


def test_invalid_encryption_key_raises(fake_redis, monkeypatch):
    """A malformed key must raise ValueError, never silently weaken."""
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "too-short")
    monkeypatch.setattr(config.settings, "REQUIRE_PROD_SECRETS", False)
    cache = TemplateCache()  # constructs fine (key truthy)
    with pytest.raises(ValueError, match="32 bytes"):
        cache.store_template(
            "member-1",
            _embedding(),
            {"name": "BadKey", "status": "active"},
        )

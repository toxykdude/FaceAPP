"""Template availability during and after a reload, plus matcher snapshotting.

Two production defects motivate this file, both observed on the kiosk as
"the camera keeps disconnecting and recognizes nobody":

1. ``_load_templates`` used to publish the new cache version FIRST and only
   then fetch and store the templates. Because readers resolve keys against
   the published version, the whole sync window served an EMPTY cache:
   ``find_match`` logged "No templates in cache" and every member was denied
   at the door. Worse, ``sync_templates`` returns ``[]`` on a transient
   backend error, so one network blip wiped the cache until the next
   successful refresh (up to 10 minutes later, or indefinitely).

   The reload must therefore be invisible: readers keep serving the
   previously published version until a COMPLETE new one is ready.

2. ``find_match`` re-read and re-decrypted every template from Redis on every
   frame (~213 ms for 540 templates, of which only ~4 ms was similarity
   math). That ran on the asyncio event loop, pegged it, and made the
   WebSocket miss its ping deadline. The matcher now memoizes a decrypted
   matrix, which is only safe if the snapshot is dropped as soon as the
   template set changes — otherwise a revoked member keeps opening the door.

The cv_service CI job has NO Redis service, so these tests patch
``recognition.template_cache.redis.from_url`` with the shared in-memory fake.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

import main
from recognition.template_cache import TemplateCache
from recognition.template_matcher import TemplateMatcher
from tests.redis_fake import FakeRedis as _FakeRedis


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(
        "recognition.template_cache.redis.from_url", lambda *a, **k: fake
    )
    return fake


def _template(member_id, name, fill):
    return {
        "member_id": member_id,
        "embedding": [fill] * 128,
        "name": name,
        "status": "active",
        "membership_status": "active",
        "membership_end_date": None,
    }


def _original_set():
    return [_template("alice", "Alice", 0.1), _template("bob", "Bob", 0.2)]


def _replacement_set():
    return [_template("carol", "Carol", 0.3)]


async def _seed(monkeypatch, templates):
    """Populate the cache through a full, successful reload."""

    async def _sync():
        return templates

    monkeypatch.setattr(main.service.api_client, "sync_templates", _sync)
    await main.service._load_templates()


def _member_ids(cache):
    return sorted(t["member_id"] for t in cache.get_all_active_templates())


@pytest.mark.asyncio
async def test_readers_keep_previous_templates_during_reload(
    fake_redis, monkeypatch
):
    """A reload in flight must never expose an empty or partial cache.

    This is the defect that denied every member for the whole sync window.
    """
    await _seed(monkeypatch, _original_set())

    seen_during_fetch = {}
    seen_during_store = {}

    async def _slow_sync():
        # Runs after the reload has been staged but before anything is
        # stored — exactly where the old code had already published an
        # empty version.
        seen_during_fetch["ids"] = _member_ids(TemplateCache())
        return _replacement_set()

    real_store = TemplateCache.store_template

    def _observing_store(self, member_id, template, member_data):
        # Runs while the new version is only partially populated.
        seen_during_store.setdefault("ids", _member_ids(TemplateCache()))
        return real_store(self, member_id, template, member_data)

    monkeypatch.setattr(main.service.api_client, "sync_templates", _slow_sync)
    monkeypatch.setattr(TemplateCache, "store_template", _observing_store)

    await main.service._load_templates()

    assert seen_during_fetch["ids"] == ["alice", "bob"]
    assert seen_during_store["ids"] == ["alice", "bob"]
    # ...and the new set is live once the reload completes.
    assert _member_ids(TemplateCache()) == ["carol"]


@pytest.mark.asyncio
async def test_failed_sync_keeps_the_previous_templates(fake_redis, monkeypatch):
    """A backend blip returns [] — that must not wipe a populated cache."""
    await _seed(monkeypatch, _original_set())

    async def _failed_sync():
        return []

    monkeypatch.setattr(main.service.api_client, "sync_templates", _failed_sync)
    await main.service._load_templates()

    assert _member_ids(TemplateCache()) == ["alice", "bob"]


@pytest.mark.asyncio
async def test_raising_sync_keeps_the_previous_templates(fake_redis, monkeypatch):
    """An unexpected exception must also leave the published version intact."""
    await _seed(monkeypatch, _original_set())

    async def _raising_sync():
        raise RuntimeError("backend unreachable")

    monkeypatch.setattr(main.service.api_client, "sync_templates", _raising_sync)

    with pytest.raises(RuntimeError):
        await main.service._load_templates()

    assert _member_ids(TemplateCache()) == ["alice", "bob"]


@pytest.mark.asyncio
async def test_empty_first_load_is_still_allowed(fake_redis, monkeypatch):
    """A genuinely empty gym must not be blocked by the anti-wipe guard."""

    async def _empty_sync():
        return []

    monkeypatch.setattr(main.service.api_client, "sync_templates", _empty_sync)
    await main.service._load_templates()

    assert _member_ids(TemplateCache()) == []


class _StubRecognizer:
    """Stand-in for FaceRecognizer (whose __init__ loads FaceNet)."""

    @staticmethod
    def calculate_similarity(embedding1, embedding2):
        similarity = np.dot(embedding1, embedding2) / (
            np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
        )
        return float((similarity + 1) / 2)


@pytest.fixture
def matcher(monkeypatch):
    monkeypatch.setattr(
        "recognition.template_matcher.FaceRecognizer", _StubRecognizer
    )
    return TemplateMatcher()


@pytest.mark.asyncio
async def test_matcher_drops_a_removed_member_immediately(
    fake_redis, monkeypatch, matcher
):
    """Memoization must not keep a revoked member matchable.

    ``/invalidate/{member_id}`` removes one template without moving the cache
    version, so a snapshot keyed on the version alone would keep recognizing
    a deactivated member until the next full refresh.
    """
    await _seed(monkeypatch, _original_set())

    alice = np.array([0.1] * 128)
    member_id, _, _ = matcher.find_match(alice)
    assert member_id == "alice"

    TemplateCache().remove_template("alice")

    member_id, _, _ = matcher.find_match(alice)
    assert member_id != "alice"


@pytest.mark.asyncio
async def test_matcher_picks_up_a_reload_without_restart(
    fake_redis, monkeypatch, matcher
):
    """A published reload must invalidate an existing matcher's snapshot."""
    await _seed(monkeypatch, _original_set())
    assert matcher.find_match(np.array([0.1] * 128))[0] == "alice"

    await _seed(monkeypatch, _replacement_set())

    carol = np.array([0.3] * 128)
    assert matcher.find_match(carol)[0] == "carol"


@pytest.mark.asyncio
async def test_vectorized_scoring_matches_pairwise_similarity(
    fake_redis, monkeypatch, matcher
):
    """The batched cosine must reproduce calculate_similarity exactly.

    The scores are compared against CONFIDENCE_THRESHOLD, so any drift here
    silently moves the accept/reject boundary for every member.
    """
    await _seed(monkeypatch, _original_set())

    query = np.linspace(0.05, 0.4, 128)
    _, confidence, _ = matcher.find_match(query)

    expected = max(
        _StubRecognizer.calculate_similarity(query, np.array([fill] * 128))
        for fill in (0.1, 0.2)
    )
    assert confidence == pytest.approx(expected, abs=1e-6)

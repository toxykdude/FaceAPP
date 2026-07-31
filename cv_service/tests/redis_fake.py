"""Shared in-memory Redis fake for cv_service tests.

The cv_service CI job has NO Redis service, so tests that touch the
template cache patch ``recognition.template_cache.redis.from_url`` with
this stand-in, which implements exactly the client surface TemplateCache
uses (get/setex/incr/scan/delete/sadd/sismember/expire/ttl/ping).

Imported by test_template_revocation.py and
test_template_cache_encryption.py.
"""

import fnmatch


class FakeRedis:
    """Minimal in-memory stand-in for the redis client API TemplateCache uses.

    Supports: ping, get, setex, incr, scan, delete, sadd, sismember, expire,
    ttl. ``expire`` records the requested TTL so ``ttl`` can report it
    (0 < ttl <= 60 assertions).
    """

    def __init__(self):
        self._data = {}
        self._ttls = {}

    def ping(self):
        return True

    def get(self, key):
        return self._data.get(key)

    def setex(self, key, ttl, value):
        self._data[key] = value

    def incr(self, key):
        self._data[key] = int(self._data.get(key, 0)) + 1
        return self._data[key]

    def scan(self, cursor, match=None, count=100):
        keys = [
            k
            for k in self._data
            if match is None or fnmatch.fnmatch(k, match)
        ]
        return 0, keys

    def delete(self, *keys):
        for k in keys:
            self._data.pop(k, None)
            self._ttls.pop(k, None)
        return len(keys)

    def sadd(self, key, member):
        self._data.setdefault(key, set()).add(member)
        return 1

    def sismember(self, key, member):
        return member in self._data.get(key, set())

    def expire(self, key, ttl):
        self._ttls[key] = ttl
        return True

    def ttl(self, key):
        return self._ttls.get(key, -1)

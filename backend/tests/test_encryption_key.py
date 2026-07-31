"""Strict ENCRYPTION_KEY validation (S4: no silent padding/truncation).

get_encryption_key must accept exactly three forms — 44-char base64 with
padding, 64-char hex, raw text of exactly 32 bytes — each decoding to exactly
32 bytes for AES-256. Anything else raises ValueError with a clear message;
the old ``[:32].ljust(32, b"\\0")`` fallback is gone.
"""

import base64

import pytest

from core.config import settings
from core.encryption import decrypt_string, encrypt_string, get_encryption_key


def _key(monkeypatch, value):
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", value)
    return get_encryption_key()


class TestGetEncryptionKey:
    def test_short_raw_raises(self, monkeypatch):
        with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
            _key(monkeypatch, "short")

    def test_33_char_raw_raises(self, monkeypatch):
        with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
            _key(monkeypatch, "x" * 33)

    def test_32_char_raw_returns_32_bytes_and_round_trips(self, monkeypatch):
        monkeypatch.setattr(settings, "ENCRYPTION_KEY", "x" * 32)
        assert len(get_encryption_key()) == 32
        assert decrypt_string(encrypt_string("x")) == "x"

    def test_64_char_hex_returns_32_bytes(self, monkeypatch):
        key = _key(monkeypatch, (b"A" * 32).hex())
        assert len(key) == 32
        assert key == b"A" * 32

    def test_44_char_base64_with_padding_returns_32_bytes(self, monkeypatch):
        encoded = base64.b64encode(b"A" * 32).decode()
        assert len(encoded) == 44 and encoded.endswith("=")
        key = _key(monkeypatch, encoded)
        assert len(key) == 32
        assert key == b"A" * 32

    def test_base64_of_16_bytes_raises(self, monkeypatch):
        # base64 of 16 bytes is 24 chars, so it falls through to the raw
        # branch and fails the exact-32-bytes check.
        encoded = base64.b64encode(b"A" * 16).decode()
        assert len(encoded) == 24
        with pytest.raises(ValueError, match="32 bytes"):
            _key(monkeypatch, encoded)

    def test_invalid_44_char_base64_raises_clear_value_error(self, monkeypatch):
        # 44 chars ending in "=" with a non-base64 character must raise a
        # clear ValueError (wrapped from binascii), not leak a binascii error.
        invalid = "!" + "A" * 42 + "="
        assert len(invalid) == 44 and invalid.endswith("=")
        with pytest.raises(ValueError, match="ENCRYPTION_KEY") as excinfo:
            _key(monkeypatch, invalid)
        assert "binascii" not in type(excinfo.value).__name__.lower()

    def test_64_char_non_hex_raises_clear_value_error(self, monkeypatch):
        with pytest.raises(ValueError, match="hex") as excinfo:
            _key(monkeypatch, "z" * 64)
        assert "ENCRYPTION_KEY" in str(excinfo.value)
        assert type(excinfo.value).__name__ == "ValueError"

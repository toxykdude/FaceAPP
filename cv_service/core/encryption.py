"""
AES-256-GCM encryption utilities for the CV service.

Mirrors backend/core/encryption.py strictness: the key MUST decode to
exactly 32 bytes (AES-256). Three forms are accepted — 44-char base64
with padding, 64-char hex, or raw text of exactly 32 bytes — anything
else raises ValueError instead of silently padding/truncating to a weak
key.

Used to encrypt member face embeddings (biometric data) at rest in the
Redis template cache.
"""

import base64
import binascii
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from config import settings


def get_encryption_key() -> bytes:
    """Resolve ENCRYPTION_KEY to exactly 32 raw key bytes (AES-256).

    Accepted forms: 44-char base64 with padding, 64-char hex, or raw
    text of exactly 32 bytes. Anything else raises ValueError.
    """
    key = settings.ENCRYPTION_KEY
    if not key:
        raise ValueError("ENCRYPTION_KEY is not configured")

    # Base64: 44 chars with padding, must decode to exactly 32 bytes.
    if len(key) == 44 and key.endswith("="):
        try:
            decoded = base64.b64decode(key, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError(f"ENCRYPTION_KEY is not valid base64: {exc}") from exc
        if len(decoded) != 32:
            raise ValueError(
                f"ENCRYPTION_KEY must decode to 32 bytes (got {len(decoded)})"
            )
        return decoded

    # Hex: 64 hex characters, must decode to exactly 32 bytes.
    if len(key) == 64:
        try:
            decoded = bytes.fromhex(key)
        except ValueError as exc:
            raise ValueError(
                f"ENCRYPTION_KEY must be 64 hex characters (got invalid hex: {exc})"
            ) from exc
        if len(decoded) != 32:
            raise ValueError(
                f"ENCRYPTION_KEY must decode to 32 bytes (got {len(decoded)})"
            )
        return decoded

    # Raw: exactly 32 bytes.
    decoded = key.encode("utf-8")
    if len(decoded) != 32:
        raise ValueError(f"ENCRYPTION_KEY must decode to 32 bytes (got {len(decoded)})")
    return decoded


def encrypt_biometric_data(data: bytes) -> bytes:
    """Encrypt bytes with AES-256-GCM.

    Returns:
        Encrypted blob (96-bit IV + tag + ciphertext).
    """
    key = get_encryption_key()

    # 96-bit random nonce (recommended length for GCM).
    iv = os.urandom(12)

    cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
    encryptor = cipher.encryptor()

    ciphertext = encryptor.update(data) + encryptor.finalize()

    # Authentication tag (GCM) — verifies integrity on decrypt.
    tag = encryptor.tag

    return iv + tag + ciphertext


def decrypt_biometric_data(encrypted_data: bytes) -> bytes:
    """Decrypt a blob produced by :func:`encrypt_biometric_data`.

    The GCM authentication tag is verified; corrupted or tampered data
    raises an exception instead of returning garbage.
    """
    key = get_encryption_key()

    iv = encrypted_data[:12]
    tag = encrypted_data[12:28]
    ciphertext = encrypted_data[28:]

    cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend())
    decryptor = cipher.decryptor()

    return decryptor.update(ciphertext) + decryptor.finalize()

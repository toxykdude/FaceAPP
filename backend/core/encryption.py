"""
AES-256 encryption utilities for biometric data.
"""

import base64
import binascii
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding

from core.config import settings


def get_encryption_key() -> bytes:
    """
    Get the encryption key from settings.

    The key MUST decode to exactly 32 bytes (AES-256). Three forms are
    accepted: 44-char base64 with padding, 64-char hex, or raw text of
    exactly 32 bytes. Anything else raises ValueError instead of silently
    padding/truncating to a weak key.
    """
    key = settings.ENCRYPTION_KEY

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
    """
    Encrypt biometric template data using AES-256-GCM.

    Args:
        data: Raw biometric template bytes

    Returns:
        Encrypted data (IV + tag + ciphertext)
    """
    key = get_encryption_key()

    # Generate random IV (16 bytes for AES)
    iv = os.urandom(16)

    # Create cipher
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
    encryptor = cipher.encryptor()

    # Encrypt data
    ciphertext = encryptor.update(data) + encryptor.finalize()

    # Get authentication tag
    tag = encryptor.tag

    # Return IV + tag + ciphertext
    return iv + tag + ciphertext


def decrypt_biometric_data(encrypted_data: bytes) -> bytes:
    """
    Decrypt biometric template data using AES-256-GCM.

    Args:
        encrypted_data: Encrypted data (IV + tag + ciphertext)

    Returns:
        Decrypted biometric template bytes
    """
    key = get_encryption_key()

    # Extract IV, tag, and ciphertext
    iv = encrypted_data[:16]
    tag = encrypted_data[16:32]
    ciphertext = encrypted_data[32:]

    # Create cipher
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend())
    decryptor = cipher.decryptor()

    # Decrypt data
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    return plaintext


def encrypt_string(data: str) -> str:
    """
    Encrypt a string (e.g., RTSP URL) and return base64-encoded result.

    Args:
        data: String to encrypt

    Returns:
        Base64-encoded encrypted string
    """
    encrypted = encrypt_biometric_data(data.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def decrypt_string(encrypted_data: str) -> str:
    """
    Decrypt a base64-encoded encrypted string.

    Args:
        encrypted_data: Base64-encoded encrypted string

    Returns:
        Decrypted string
    """
    encrypted_bytes = base64.b64decode(encrypted_data)
    decrypted = decrypt_biometric_data(encrypted_bytes)
    return decrypted.decode("utf-8")


# Aliases for convenience
encrypt_template = encrypt_biometric_data
decrypt_template = decrypt_biometric_data

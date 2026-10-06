"""AES-256-GCM encryption utilities for PII at rest.

Wire format: ``enc:v1:<base64(nonce_12 ‖ ciphertext ‖ tag_16)>``

When ``ENCRYPTION_KEY`` is not set the module operates in pass-through mode:
encrypt/encrypt_json return their input unchanged, and decrypt/decrypt_json
gracefully handle both encrypted and plain-text values.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"
_NONCE_LEN = 12  # AES-GCM nonce bytes

# ---------------------------------------------------------------------------
# Key loading
# ---------------------------------------------------------------------------

_encryption_key: Optional[bytes] = None


def _get_key() -> Optional[bytes]:
    global _encryption_key
    if _encryption_key is not None:
        return _encryption_key

    raw = os.getenv("ENCRYPTION_KEY", "")
    if not raw:
        return None

    try:
        _encryption_key = base64.b64decode(raw)
        if len(_encryption_key) != 32:
            logger.error(
                "ENCRYPTION_KEY must be 32 bytes (base64-encoded). "
                "Got %d bytes — encryption disabled.",
                len(_encryption_key),
            )
            _encryption_key = None
    except Exception:
        logger.error("ENCRYPTION_KEY is not valid base64 — encryption disabled.")
        _encryption_key = None

    return _encryption_key


def is_encryption_enabled() -> bool:
    """Return True when a valid encryption key is available.

    Called by the Alembic migrations, which skip their backfill rather than
    write plaintext into columns the app expects to be encrypted.
    """
    return _get_key() is not None


# ---------------------------------------------------------------------------
# Low-level encrypt / decrypt
# ---------------------------------------------------------------------------


def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* with AES-256-GCM.

    Returns ``enc:v1:<base64>`` or the original string if encryption is
    disabled (no key).
    """
    key = _get_key()
    if key is None:
        return plaintext

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    payload = base64.b64encode(nonce + ct).decode("ascii")
    return f"{PREFIX}{payload}"


def decrypt(value: str) -> str:
    """Decrypt *value* if it carries the ``enc:v1:`` prefix.

    Plain-text values are returned as-is (graceful fallback).
    """
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return value

    key = _get_key()
    if key is None:
        logger.warning("Encrypted value found but ENCRYPTION_KEY is not set.")
        return value

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(value[len(PREFIX) :])
    nonce = raw[:_NONCE_LEN]
    ct = raw[_NONCE_LEN:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")


# ---------------------------------------------------------------------------
# JSON helpers (for JSONB columns)
# ---------------------------------------------------------------------------


def encrypt_json(obj: Any) -> Any:
    """Serialize *obj* to JSON and encrypt.

    Returns an ``enc:v1:…`` string (stored as a JSONB string scalar) or
    the original dict when encryption is disabled.
    """
    if obj is None:
        return obj
    key = _get_key()
    if key is None:
        return obj
    return encrypt(json.dumps(obj, default=str))


def decrypt_json(value: Any) -> Dict[str, Any]:
    """Decrypt a JSONB value that may be encrypted or a plain dict.

    - ``dict`` → returned as-is  (legacy unencrypted row)
    - ``str`` starting with ``enc:v1:`` → decrypted then parsed
    - ``None`` → empty dict
    - anything else → empty dict
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        decrypted = decrypt(value)
        try:
            parsed = json.loads(decrypted)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


# ---------------------------------------------------------------------------
# HMAC blind index
# ---------------------------------------------------------------------------


def hmac_hash(value: str) -> str:
    """Deterministic HMAC-SHA256 hex digest for blind-index lookups."""
    key = _get_key()
    if key is None:
        return value
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Module-level reset (for tests)
# ---------------------------------------------------------------------------


def _reset_key() -> None:
    """Clear the cached key so the next call re-reads the env var."""
    global _encryption_key
    _encryption_key = None

"""Tests for the encryption utility module."""

import base64
import os
from unittest.mock import patch

import pytest

from voice_agent.utils.encryption import (
    _reset_key,
    decrypt,
    decrypt_json,
    encrypt,
    encrypt_json,
    hmac_hash,
)

# A deterministic 32-byte key for testing (base64-encoded)
TEST_KEY = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()


@pytest.fixture(autouse=True)
def reset_encryption_key():
    """Reset the cached key before each test."""
    _reset_key()
    yield
    _reset_key()


class TestEncryptDecrypt:
    def test_round_trip(self):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
            plaintext = "Hello, World!"
            encrypted = encrypt(plaintext)
            assert encrypted.startswith("enc:v1:")
            assert decrypt(encrypted) == plaintext

    def test_different_nonces(self):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
            a = encrypt("same")
            _reset_key()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
            b = encrypt("same")
        # Different nonces → different ciphertext
        assert a != b

    def test_decrypt_plain_text_passthrough(self):
        assert decrypt("plain text value") == "plain text value"

    def test_decrypt_empty_string(self):
        assert decrypt("") == ""

    def test_encrypt_passthrough_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ENCRYPTION_KEY", None)
            _reset_key()
            assert encrypt("hello") == "hello"

    def test_unicode_round_trip(self):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
            text = "Olá, tudo bem? 日本語テスト 🎉"
            assert decrypt(encrypt(text)) == text


class TestEncryptDecryptJson:
    def test_round_trip(self):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
            obj = {"questions": [{"id": "q1", "answer": "yes"}]}
            encrypted = encrypt_json(obj)
            assert isinstance(encrypted, str)
            assert encrypted.startswith("enc:v1:")
            assert decrypt_json(encrypted) == obj

    def test_decrypt_json_dict_passthrough(self):
        obj = {"key": "value"}
        assert decrypt_json(obj) == obj

    def test_decrypt_json_none_returns_empty_dict(self):
        assert decrypt_json(None) == {}

    def test_encrypt_json_none_returns_none(self):
        assert encrypt_json(None) is None

    def test_encrypt_json_passthrough_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ENCRYPTION_KEY", None)
            _reset_key()
            obj = {"key": "value"}
            assert encrypt_json(obj) == obj

    def test_nested_structure(self):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
            obj = {
                "questions": [
                    {
                        "question_id": "DOB",
                        "answer": "1990-01-15",
                        "turns": [
                            {
                                "user_message": "January fifteenth",
                                "llm_confidence": 0.95,
                            }
                        ],
                    }
                ]
            }
            result = decrypt_json(encrypt_json(obj))
            assert result == obj
            assert result["questions"][0]["turns"][0]["llm_confidence"] == 0.95


class TestHmacHash:
    def test_deterministic(self):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
            h1 = hmac_hash("1234567890")
            _reset_key()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
            h2 = hmac_hash("1234567890")
        assert h1 == h2

    def test_different_inputs_different_hashes(self):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
            h1 = hmac_hash("1234567890")
            h2 = hmac_hash("0987654321")
            assert h1 != h2

    def test_returns_hex_string(self):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
            h = hmac_hash("test")
            assert len(h) == 64  # SHA-256 hex digest
            assert all(c in "0123456789abcdef" for c in h)

    def test_passthrough_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ENCRYPTION_KEY", None)
            _reset_key()
            assert hmac_hash("phone") == "phone"


class TestCrossLanguageVector:
    """Generate a test vector that can be used in TypeScript tests."""

    def test_generate_vector(self):
        """Encrypt a known value and print for cross-language verification.

        The encrypted output changes each run (random nonce), so this test
        verifies round-trip only.  The TS test should use its own hardcoded
        vector produced by running this once.
        """
        with patch.dict(os.environ, {"ENCRYPTION_KEY": TEST_KEY}):
            plaintext = '{"name":"John","dob":"1990-01-15"}'
            encrypted = encrypt(plaintext)
            decrypted = decrypt(encrypted)
            assert decrypted == plaintext

            # Print for manual copy to TS tests (run with -s flag)
            print(f"\n--- Cross-language test vector ---")
            print(f"KEY (base64): {TEST_KEY}")
            print(f"PLAINTEXT: {plaintext}")
            print(f"ENCRYPTED: {encrypted}")
            print(f"--- end ---\n")

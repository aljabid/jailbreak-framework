from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENVELOPE_PREFIX = "jbfenc:v1:"


class ArtifactCipher:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("Artifact encryption key must be exactly 32 bytes")
        self._key = key
        self._cipher = AESGCM(key)
        self.key_id = hashlib.sha256(key).hexdigest()[:16]

    @classmethod
    def from_base64(cls, encoded_key: str) -> ArtifactCipher:
        try:
            key = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
        except Exception as exc:
            raise ValueError("Artifact encryption key is not valid base64") from exc
        return cls(key)

    @classmethod
    def from_environment(cls, variable: str = "JBF_ARTIFACT_ENCRYPTION_KEY") -> ArtifactCipher:
        value = os.getenv(variable)
        if not value:
            raise ValueError(f"{variable} is required")
        return cls.from_base64(value)

    @staticmethod
    def generate_key() -> str:
        return base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii")

    def encrypt_json(self, value: Any, *, context: str) -> str:
        nonce = os.urandom(12)
        plaintext = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        ciphertext = self._cipher.encrypt(
            nonce,
            plaintext,
            context.encode("utf-8"),
        )
        envelope = {
            "algorithm": "AES-256-GCM",
            "key_id": self.key_id,
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        }
        return ENVELOPE_PREFIX + base64.urlsafe_b64encode(
            json.dumps(envelope, sort_keys=True).encode("utf-8")
        ).decode("ascii")

    def decrypt_json(self, envelope: str, *, context: str) -> Any:
        if not envelope.startswith(ENVELOPE_PREFIX):
            raise ValueError("Value is not an encrypted artifact envelope")
        try:
            raw = base64.urlsafe_b64decode(envelope[len(ENVELOPE_PREFIX) :].encode("ascii"))
            payload = json.loads(raw)
            if payload["key_id"] != self.key_id:
                raise ValueError("Artifact was encrypted with a different key")
            nonce = base64.urlsafe_b64decode(payload["nonce"])
            ciphertext = base64.urlsafe_b64decode(payload["ciphertext"])
            plaintext = self._cipher.decrypt(
                nonce,
                ciphertext,
                context.encode("utf-8"),
            )
            return json.loads(plaintext)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Encrypted artifact authentication failed") from exc

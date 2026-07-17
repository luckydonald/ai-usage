"""Credential encryption with an environment-or-file managed key."""

import base64
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True, slots=True)
class EncryptedValue:
    ciphertext: bytes
    nonce: bytes
    version: int = 1
# end class


class CredentialCipher:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("credential key must be exactly 32 bytes")
        # end if
        self.key = key
        self.aes = AESGCM(key)
    # end def

    @classmethod
    def load(cls, default_path: Path) -> "CredentialCipher":
        encoded = os.environ.get("AI_USAGE_CREDENTIAL_KEY")
        key_file = Path(os.environ.get("AI_USAGE_CREDENTIAL_KEY_FILE", default_path))
        if encoded:
            key = base64.urlsafe_b64decode(encoded)
        elif key_file.exists():
            key = base64.urlsafe_b64decode(key_file.read_bytes().strip())
        else:
            key_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            key = secrets.token_bytes(32)
            descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(base64.urlsafe_b64encode(key) + b"\n")
            # end with
        # end if
        return cls(key)
    # end def

    def encrypt(self, value: bytes, associated_data: bytes) -> EncryptedValue:
        nonce = secrets.token_bytes(12)
        return EncryptedValue(
            ciphertext=self.aes.encrypt(nonce, value, associated_data),
            nonce=nonce,
        )
    # end def

    def decrypt(self, value: EncryptedValue, associated_data: bytes) -> bytes:
        if value.version != 1:
            raise ValueError(f"unsupported credential encryption version {value.version}")
        # end if
        return self.aes.decrypt(value.nonce, value.ciphertext, associated_data)
    # end def
# end class


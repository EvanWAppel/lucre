import logging
from base64 import b64decode, b64encode

from cryptography.fernet import Fernet

from config import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.encryption_key.encode())
    return _fernet


def encrypt(plaintext: str) -> str:
    token = _get_fernet().encrypt(plaintext.encode())
    return b64encode(token).decode()


def decrypt(ciphertext: str) -> str:
    token = b64decode(ciphertext.encode())
    return _get_fernet().decrypt(token).decode()

from cryptography.fernet import Fernet

from app.core.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.ENCRYPTION_KEY
        if isinstance(key, str):
            key = key.encode()
        _fernet = Fernet(key)
    return _fernet


def encrypt_token(value: str) -> bytes:
    return _get_fernet().encrypt(value.encode())


def decrypt_token(ciphertext: bytes) -> str:
    return _get_fernet().decrypt(ciphertext).decode()

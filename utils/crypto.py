import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class CryptoManager:
    """Профессиональный менеджер шифрования данных"""
    
    def __init__(self, master_password: str, salt: bytes = b'static_salt_for_init'):
        # В реальном приложении соль должна генерироваться один раз и храниться отдельно
        self.key = self._derive_key(master_password, salt)
        self.cipher = Fernet(self.key)

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Генерация ключа из пароля (KDF)"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def encrypt(self, plain_text: str) -> str:
        """Шифрование строки"""
        if not plain_text: return ""
        return self.cipher.encrypt(plain_text.encode()).decode()

    def decrypt(self, encrypted_text: str) -> str:
        """Расшифровка строки"""
        if not encrypted_text: return ""
        try:
            return self.cipher.decrypt(encrypted_text.encode()).decode()
        except Exception:
            return "DECRYPTION_ERROR"
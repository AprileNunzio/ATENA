import os
import base64
from cryptography.fernet import Fernet
from fastapi import HTTPException

# Chiave simmetrica pre-condivisa (PSK) per E2E Encryption
# In produzione questa chiave deve essere generata da ATENA e iniettata al primo setup
_ATENA_PSK = os.environ.get("ATENA_CONTEXT_PSK", Fernet.generate_key().decode())
_cipher = Fernet(_ATENA_PSK.encode())

class E2EEncryption:
    @staticmethod
    def encrypt_payload(data: str) -> str:
        return _cipher.encrypt(data.encode()).decode()

    @staticmethod
    def decrypt_payload(encrypted_data: str) -> str:
        try:
            return _cipher.decrypt(encrypted_data.encode()).decode()
        except Exception:
            raise HTTPException(status_code=403, detail="Decrittografia fallita. Chiave E2E non valida.")

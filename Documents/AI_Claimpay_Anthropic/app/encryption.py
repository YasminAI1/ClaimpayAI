from cryptography.fernet import Fernet
import hashlib

class DataEncryption:
    def __init__(self):
        self.key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.key)
        
    def encrypt_text(self, text: str) -> bytes:
        return self.cipher_suite.encrypt(text.encode())
        
    def decrypt_text(self, encrypted_text: bytes) -> str:
        return self.cipher_suite.decrypt(encrypted_text).decode()
        
    def hash_value(self, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()
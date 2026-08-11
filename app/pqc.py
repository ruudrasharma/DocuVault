
from cryptography.fernet import Fernet

def pqc_encrypt(data):
    """Encrypt data using Fernet (symmetric encryption as PQC fallback)."""
    try:
        key = Fernet.generate_key()  # Correct method for key generation
        f = Fernet(key)
        encrypted = f.encrypt(data.encode())
        return encrypted, key
    except Exception as e:
        print(f"Error in pqc_encrypt: {e}")
        raise

def pqc_decrypt(encrypted, key):
    """Decrypt data using Fernet."""
    try:
        f = Fernet(key)
        return f.decrypt(encrypted).decode()
    except Exception as e:
        print(f"Error in pqc_decrypt: {e}")
        raise



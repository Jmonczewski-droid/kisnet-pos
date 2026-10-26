import hashlib
import hmac
import secrets
from typing import Tuple

def hash_pin(pin: str) -> str:
    """Hash a PIN using PBKDF2 with SHA-256"""
    # Generate a random salt
    salt = secrets.token_bytes(16)
    
    # Hash the pin with PBKDF2
    key = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt, 200000)
    
    # Return the hash in a recognizable format
    return f"pbkdf2_sha256${200000}${salt.hex()}${key.hex()}"

def verify_pin(pin: str, stored: str) -> bool:
    """Verify a PIN against its stored hash"""
    try:
        # Parse the stored hash format
        algorithm, iterations_str, salt_hex, key_hex = stored.split('$')
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        
        # Hash the provided pin with the same salt and iterations
        computed_key = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt, iterations)
        
        # Compare the keys using constant-time comparison
        return hmac.compare_digest(computed_key, expected_key)
    except (ValueError, TypeError):
        # Return False if the stored string is malformed
        return False

def new_token() -> str:
    """Generate a new token"""
    return secrets.token_urlsafe(32)

def hash_token(token: str) -> str:
    """Hash a token using SHA-256"""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()
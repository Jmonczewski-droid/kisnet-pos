import pytest
from app.core.security import hash_pin, verify_pin, new_token, hash_token

def test_hash_pin_verify_pin_roundtrip():
    """Test that hashing and verifying a PIN works correctly"""
    pin = "1234"
    stored = hash_pin(pin)
    assert verify_pin(pin, stored) == True
    assert verify_pin("wrong", stored) == False

def test_two_hashes_of_same_pin_differ():
    """Test that two hashes of the same PIN are different (due to random salt)"""
    pin = "1234"
    hash1 = hash_pin(pin)
    hash2 = hash_pin(pin)
    assert hash1 != hash2

def test_verify_pin_on_malformed_stored_string_returns_false():
    """Test that verify_pin returns False on malformed stored string"""
    # Test with completely invalid format
    assert verify_pin("1234", "invalid_format") == False
    
    # Test with missing components
    assert verify_pin("1234", "pbkdf2_sha256$100000$salt$key") == False
    
    # Test with invalid iterations
    assert verify_pin("1234", "pbkdf2_sha256$invalid$salt$key") == False

def test_hash_token_deterministic():
    """Test that hash_token is deterministic"""
    token = "test_token"
    hash1 = hash_token(token)
    hash2 = hash_token(token)
    assert hash1 == hash2

def test_new_token_returns_distinct_strings():
    """Test that new_token returns distinct strings of length >= 40"""
    token1 = new_token()
    token2 = new_token()
    assert len(token1) >= 40
    assert len(token2) >= 40
    assert token1 != token2
"""Тести хешування паролів і JWT-токенів (app/security.py)."""

import datetime

import jwt

from app.config import JWT_ALGORITHM, JWT_SECRET
from app.security import create_token, decode_token, hash_password, verify_password


def test_password_roundtrip():
    h = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong-pass", h)


def test_password_salt_is_unique():
    # Один пароль → різні хеші (унікальна сіль)
    assert hash_password("same") != hash_password("same")


def test_verify_rejects_malformed_stored():
    assert not verify_password("x", "not-a-valid-hash")
    assert not verify_password("x", "")


def test_token_roundtrip_carries_claims():
    token = create_token("alice", "admin", 7)
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "alice"
    assert payload["role"] == "admin"
    assert payload["tv"] == 7


def test_decode_rejects_wrong_secret():
    token = jwt.encode({"sub": "x", "role": "admin"}, "some-other-secret", algorithm="HS256")
    assert decode_token(token) is None


def test_decode_rejects_expired():
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    token = jwt.encode({"sub": "x", "exp": past}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert decode_token(token) is None


def test_decode_rejects_garbage():
    assert decode_token("not.a.jwt") is None

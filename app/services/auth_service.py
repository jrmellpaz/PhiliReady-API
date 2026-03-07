"""
Authentication Service — JWT token management and password hashing.

Provides:
  - Password hashing/verification via passlib (bcrypt)
  - JWT access token creation/decoding via python-jose
  - Designed to be extensible — future OAuth/passkey providers can
    be added as additional functions without changing the token layer.

Configuration via environment variables:
  - JWT_SECRET_KEY: Secret key for signing tokens
  - JWT_ALGORITHM: Algorithm (default: HS256)
  - JWT_EXPIRY_MINUTES: Token expiry time (default: 1440 = 24 hours)
"""
import os
import bcrypt
from datetime import datetime, timedelta
from dotenv import load_dotenv
from jose import JWTError, jwt

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-to-a-random-secret-key-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRY_MINUTES = int(os.getenv("JWT_EXPIRY_MINUTES", "1440"))  # 24 hours

# ── Password Hashing ──────────────────────────────────────────────────────
# Using bcrypt directly — more reliable on Python 3.14 than passlib.

def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    # bcrypt requires bytes
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


# ── JWT Token Management ──────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    Create a signed JWT access token.

    Args:
        data: Payload data (typically {"sub": email, "role": role})
        expires_delta: Custom expiry time (defaults to JWT_EXPIRY_MINUTES)

    Returns:
        Encoded JWT string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=EXPIRY_MINUTES)

    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT access token.

    Returns:
        Decoded payload dict

    Raises:
        JWTError: If token is invalid, expired, or tampered with
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

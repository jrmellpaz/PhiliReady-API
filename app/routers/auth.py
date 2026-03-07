"""
Auth Router — JWT authentication endpoints.

POST /api/v1/auth/register  — Create a new account (admin only)
POST /api/v1/auth/login     — Login and receive JWT access token
GET  /api/v1/auth/me        — Get current user profile

Future extensibility:
  - OAuth (Google) can be added as POST /api/v1/auth/google
  - Passkeys can be added as POST /api/v1/auth/passkey/*
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.db.database import get_db
from app.db.models import User
from app.deps import get_current_user, require_admin
from app.services.auth_service import hash_password, verify_password, create_access_token
from app.schemas.responses import CamelModel

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Request/Response Models ───────────────────────────────────────────────

class RegisterRequest(CamelModel):
    """Request body for creating a new user account."""
    email:     str    # User's email address
    password:  str    # Plain-text password (will be hashed)
    full_name: str    # Display name
    role:      str = "lgu"  # "admin" or "lgu"


class LoginRequest(CamelModel):
    """Request body for logging in."""
    email:    str
    password: str


class TokenResponse(CamelModel):
    """JWT token response after successful login."""
    access_token: str
    token_type:   str = "bearer"


class UserResponse(CamelModel):
    """User profile response (excludes password)."""
    id:        int
    email:     str
    full_name: str
    role:      str


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    body: RegisterRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Create a new user account. Admin-only.

    After creating an LGU user, use the admin endpoint to assign
    city access: POST /api/v1/admin/users/{id}/cities
    """
    # Check if email already exists
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{body.email}' is already registered",
        )

    # Validate role
    if body.role not in ("admin", "lgu"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'admin' or 'lgu'",
        )

    # Create the user with hashed password
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate with email + password. Returns a JWT access token.

    Include the token in subsequent requests:
      Authorization: Bearer <token>
    """
    user = db.query(User).filter(User.email == body.email).first()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Create JWT with user email and role in payload
    token = create_access_token(data={
        "sub": user.email,
        "role": user.role,
    })

    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    """
    Get the current authenticated user's profile.
    Requires a valid JWT token.
    """
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
    )

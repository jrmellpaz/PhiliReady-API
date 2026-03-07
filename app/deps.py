"""
FastAPI Dependencies — Authentication and authorization helpers.

Provides dependency functions for route-level access control:
  - get_current_user: Extracts and validates JWT from Authorization header
  - get_optional_user: Same but returns None for unauthenticated requests
  - require_admin: Restricts endpoint to admin users only
  - require_city_access: Checks if user has edit access to a specific city

Usage in routers:
    @router.patch("/cities/{pcode}")
    def update_city(
        pcode: str,
        user: User = Depends(require_city_access),
        db: Session = Depends(get_db),
    ):
        ...
"""
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError

from app.db.database import get_db
from app.db.models import User, UserCityAccess
from app.services.auth_service import decode_access_token

# ── Bearer Token Extraction ───────────────────────────────────────────────
# HTTPBearer extracts the token from "Authorization: Bearer <token>" header

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Extract and validate the JWT token. Returns the authenticated User.
    Raises 401 if token is missing, expired, or invalid.
    """
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Look up the user in the database
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(optional_security),
    db: Session = Depends(get_db),
) -> User | None:
    """
    Same as get_current_user but returns None for unauthenticated requests
    instead of raising 401. Useful for endpoints that work differently
    for authenticated vs. anonymous users.
    """
    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
        email: str = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None

    return db.query(User).filter(User.email == email).first()


def require_admin(user: User = Depends(get_current_user)) -> User:
    """
    Dependency that restricts access to admin users only.
    Raises 403 if the authenticated user is not an admin.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


class RequireCityAccess:
    """
    Dependency class that checks if a user has edit access to a specific city.

    Admin users can edit any city. LGU users can only edit cities
    assigned to them via the user_city_access table.

    Usage:
        @router.patch("/cities/{pcode}")
        def update_city(
            pcode: str,
            user: User = Depends(RequireCityAccess()),
            db: Session = Depends(get_db),
        ):
            ...
    """

    async def __call__(
        self,
        pcode: str,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        # Admins bypass the city access check
        if user.role == "admin":
            return user

        # LGU users — check the user_city_access junction table
        access = (
            db.query(UserCityAccess)
            .filter(
                UserCityAccess.user_id == user.id,
                UserCityAccess.city_pcode == pcode,
            )
            .first()
        )

        if access is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have edit access to city '{pcode}'. "
                       "Contact an admin to request access.",
            )

        return user

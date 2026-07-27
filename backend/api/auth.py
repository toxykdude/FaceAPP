"""
Authentication API endpoints.
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_user
from core.security import verify_password, create_access_token
from core.config import settings
from core.auth_attempts import (
    is_locked_out,
    record_failed_attempt,
    clear_failed_attempts,
    get_remaining_lockout,
)
from models.user import User
from schemas.user import Token, LoginRequest, UserResponse

from core.rate_limiter import limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
def login(request: Request, credentials: LoginRequest, db: Session = Depends(get_db)):
    """
    Login with username and password.

    Returns JWT access token.
    Rate limited: 5 requests/minute per IP.
    Account locked for 15 minutes after 5 failed attempts.
    """
    # Check account lockout
    if is_locked_out(credentials.username):
        remaining = get_remaining_lockout(credentials.username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked. Try again in {remaining // 60} minutes.",
        )

    # Get user by username
    user = db.query(User).filter(User.username == credentials.username).first()

    if not user:
        record_failed_attempt(credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        record_failed_attempt(credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user"
        )

    # Clear failed attempts on successful login
    clear_failed_attempts(credentials.username)

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )

    # Audit log
    from core.audit import log_action

    log_action(
        db,
        action="login",
        resource_type="session",
        user_id=str(user.id),
        username=user.username,
    )

    # Serialize user manually
    from schemas.user import UserResponse

    user_data = UserResponse.model_validate(user, from_attributes=True)

    return {"access_token": access_token, "token_type": "bearer", "user": user_data}


@router.post("/logout")
def logout(request: Request, current_user: User = Depends(get_current_user)):
    """
    Logout current user. Blacklists the JWT token.
    """
    from core.security import blacklist_token

    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        blacklist_token(token)

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user information.
    """
    return current_user

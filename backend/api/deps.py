"""
FastAPI dependencies for authentication and database sessions.
"""
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text

from core.database import SessionLocal
from core.security import decode_access_token
from models.user import User, UserRole
from models.member import Member

# Security scheme
security = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency.
    
    Usage:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token.
    
    Usage:
        @app.get("/me")
        def read_current_user(current_user: User = Depends(get_current_user)):
            return current_user
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decode token
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if payload is None:
        raise credentials_exception
    
    # Check if token is blacklisted
    from core.security import is_token_blacklisted
    if is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user ID from token
    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user (alias for get_current_user).
    """
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require admin role.
    
    Usage:
        @app.delete("/users/{user_id}")
        def delete_user(user_id: str, admin: User = Depends(require_admin)):
            # Only admins can delete users
            pass
    """
    if current_user.role.upper() != UserRole.ADMIN.value.upper():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return current_user


async def require_staff(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require staff or admin role.
    
    Usage:
        @app.post("/members")
        def create_member(member: MemberCreate, staff: User = Depends(require_staff)):
            # Staff and admins can create members
            pass
    """
    if current_user.role.upper() not in [UserRole.ADMIN.value.upper(), UserRole.STAFF.value.upper()]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff access required"
        )
    
    return current_user

async def get_current_member(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Member:
    """
    Get current authenticated member from JWT token (type: "member").
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if payload is None:
        raise credentials_exception
    
    # Verify this is a member token, not a staff token
    if payload.get("type") != "member":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Member access required"
        )
    
    from core.security import is_token_blacklisted
    if is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    member_id = payload.get("sub")
    if member_id is None:
        raise credentials_exception
    
    member = db.query(Member).filter(Member.id == member_id).first()
    if member is None:
        raise credentials_exception
    
    if member.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive member account"
        )
    
    return member


def get_portal_session(
    member: Member = Depends(get_current_member),
) -> Generator[Session, None, None]:
    """
    Database session using member_portal role with RLS enforced.
    Automatically sets app.member_id from the authenticated member's JWT.
    """
    from core.database import PortalSessionLocal
    db = PortalSessionLocal()
    try:
        db.execute(text("SET LOCAL app.member_id = :mid"), {"mid": str(member.id)})
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def require_page(page: str):
    """Check if current user has access to a specific page."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.upper() == UserRole.ADMIN.value.upper():
            return current_user  # Admins always have access

        perms = current_user.permissions or {}
        pages = perms.get('pages', [])

        if 'all' in pages or page in pages:
            return current_user

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Access denied to {page}")
    return _check

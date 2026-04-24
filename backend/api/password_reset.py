"""
Password reset endpoints (forgot password flow).
"""
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from api.deps import get_db
from models.user import User
from models.password_reset import PasswordResetToken
from core.security import get_password_hash
from core.email import email_service
from core.config import settings
from core.audit import log_action
from schemas.sync import MessageResponse

router = APIRouter(prefix="/auth", tags=["Password Reset"])


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Request a password reset link via email.
    
    Always returns success to prevent email enumeration.
    """
    # Find user by email
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user:
        # Don't reveal that email doesn't exist
        return {"message": "If an account with that email exists, a reset link has been sent."}
    
    # Invalidate any existing tokens for this user
    existing = db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == str(user.id),
        PasswordResetToken.used == "false"
    ).all()
    for t in existing:
        t.used = "true"
    
    # Generate secure token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    
    reset_token = PasswordResetToken(
        user_id=str(user.id),
        token=token,
        email=user.email,
        used="false",
        created_at=datetime.now(timezone.utc),
        expires_at=expires_at
    )
    db.add(reset_token)
    db.commit()
    
    # Build reset URL
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost')
    reset_url = f"{frontend_url}/reset-password?token={token}"
    
    # Send email
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #1a1a2e; padding: 20px; border-radius: 10px 10px 0 0;">
            <h1 style="color: #fff; margin: 0; font-size: 24px;">🏋️ PowerHouse Gym</h1>
        </div>
        <div style="background: #fff; padding: 30px; border: 1px solid #ddd; border-radius: 0 0 10px 10px;">
            <h2 style="color: #333;">Password Reset Request</h2>
            <p style="color: #555;">Hello {user.username},</p>
            <p style="color: #555;">We received a request to reset your password. Click the button below to create a new password:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_url}" style="background: #2e7d32; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Reset Password</a>
            </div>
            <p style="color: #888; font-size: 14px;">Or copy this link to your browser:</p>
            <p style="color: #2e7d32; word-break: break-all; font-size: 13px;">{reset_url}</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="color: #999; font-size: 12px;">This link expires in 1 hour. If you didn't request this, you can safely ignore this email.</p>
        </div>
    </div>
    """
    
    body = f"""
Hello {user.username},

We received a request to reset your PowerHouse Gym password.

Reset your password by visiting:
{reset_url}

This link expires in 1 hour.

If you didn't request this, ignore this email.
"""
    
    email_service._send_email(
        to=user.email,
        subject="PowerHouse Gym - Password Reset",
        body=body.strip(),
        html=html
    )
    
    # Audit
    log_action(db, action="forgot_password", resource_type="user",
               resource_id=str(user.id), details={"email": user.email})
    db.commit()
    
    return {"message": "If an account with that email exists, a reset link has been sent."}


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Reset password using token from email.
    """
    # Find token
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == request.token,
        PasswordResetToken.used == "false"
    ).first()
    
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Check expiry
    now = datetime.now(timezone.utc)
    # Handle both aware and naive datetimes
    expires = reset_token.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    
    if now > expires:
        reset_token.used = "true"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired. Please request a new one."
        )
    
    # Find user
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found"
        )
    
    # Update password
    user.password_hash = get_password_hash(request.new_password)
    
    # Mark token as used
    reset_token.used = "true"
    
    # Audit
    log_action(db, action="reset_password", resource_type="user",
               resource_id=str(user.id), username=user.username)
    
    db.commit()
    
    return {"message": "Password has been reset successfully. You can now log in with your new password."}

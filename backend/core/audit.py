"""
Audit logging helper.
"""
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from models.audit_log import AuditLog


def log_action(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
):
    """
    Log an audit action.
    
    Args:
        db: Database session
        action: Action type (create, update, delete, login, logout)
        resource_type: Type of resource (member, membership, camera, user)
        resource_id: ID of affected resource
        user_id: ID of user performing action
        username: Username of user
        details: Additional details dict (stored as JSON)
        ip_address: Client IP
        user_agent: Client user agent
    """
    try:
        log = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=datetime.now(timezone.utc)
        )
        db.add(log)
        db.flush()  # Don't commit — let the calling endpoint handle the transaction
    except Exception:
        # Audit logging should never break the main operation
        pass

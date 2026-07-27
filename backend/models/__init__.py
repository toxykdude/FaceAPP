"""
Models package initialization.
Import all models here for Alembic auto-detection.
"""

from core.database import Base

# Import all models
from models.user import User, UserRole
from models.member import Member, MemberStatus
from models.membership import Membership, MembershipType, MembershipStatus
from models.sale import SalesTransaction, PaymentMethod
from models.event import AccessEvent
from models.camera import Camera
from models.biometric import BiometricTemplate
from models.enrollment_request import EnrollmentRequest
from models.setting import Setting

__all__ = [
    "Base",
    "User",
    "UserRole",
    "Member",
    "MemberStatus",
    "Membership",
    "MembershipType",
    "MembershipStatus",
    "SalesTransaction",
    "PaymentMethod",
    "AccessEvent",
    "Camera",
    "BiometricTemplate",
    "EnrollmentRequest",
    "Setting",
]

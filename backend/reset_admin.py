"""
Reset admin password script.
"""

import sys
import os
from sqlalchemy.orm import Session
from core.database import SessionLocal
from core.security import get_password_hash
from models.user import User


def reset_admin():
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "EbUdnMO5c1GO56QPPNRS6HWEoG2yo8p4")

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.username == admin_username).first()
        if user:
            print(f"Resetting password for user: {admin_username}")
            user.password_hash = get_password_hash(admin_password)
            db.commit()
            print("✓ Password reset successfully")
        else:
            print(f"✗ User {admin_username} not found")
    except Exception as e:
        print(f"✗ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    reset_admin()

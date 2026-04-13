"""
Membership auto-expiry task.

Marks memberships as expired when their end_date has passed.
Designed to be run as a cron job or scheduled task.
"""
from datetime import date
from sqlalchemy.orm import joinedload
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal
from models.membership import Membership, MembershipStatus


def expire_memberships():
    """Mark expired memberships (end_date < today) as expired."""
    db = SessionLocal()
    try:
        today = date.today()
        
        # Find active memberships that have passed their end_date
        # Use joinedload to access member relationship for email notifications
        expired = db.query(Membership).options(joinedload(Membership.member)).filter(
            Membership.status == MembershipStatus.ACTIVE.value,
            Membership.end_date < today
        ).all()
        
        count = 0
        for membership in expired:
            membership.status = MembershipStatus.EXPIRED.value
            
            # Send notification email
            try:
                from core.email import email_service
                if membership.member and membership.member.email:
                    email_service.send_membership_expired(
                        membership.member.email,
                        membership.member.full_name
                    )
            except Exception:
                pass  # Email failure should not block expiry
            
            count += 1
        
        db.commit()
        
        if count > 0:
            print(f"Expired {count} memberships")
        else:
            print("No memberships to expire")
        
        return count
    except Exception as e:
        db.rollback()
        print(f"Error expiring memberships: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    expire_memberships()

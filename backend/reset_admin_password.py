
import sys
import os
from sqlalchemy.orm import Session
from core.database import SessionLocal
from core.security import get_password_hash
from models.user import User

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def reset_password(username="admin", new_password="admin123"):
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"User {username} not found")
            return
        
        user.password_hash = get_password_hash(new_password)
        db.commit()
        print(f"Password for {username} reset successfully to {new_password}")
    except Exception as e:
        print(f"Error resetting password: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    reset_password()

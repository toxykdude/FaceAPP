"""
Database initialization script.
Creates tables and seeds initial admin user.
"""
import sys
import os
import uuid
from sqlalchemy.orm import Session

from core.database import engine, SessionLocal
from core.security import get_password_hash
from models import Base, User, UserRole


def init_db():
    """Initialize database with tables and default admin user."""
    print("Creating database tables...")
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    print("✓ Tables created successfully")
    
    # Get admin credentials from environment
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    
    # Create default admin user
    db: Session = SessionLocal()
    
    try:
        # Check if admin already exists
        existing_admin = db.query(User).filter(User.username == admin_username).first()
        
        if existing_admin:
            print("⚠ Admin user already exists, skipping creation")
        else:
            print("Creating default admin user...")
            
            admin_user = User(
                id=uuid.uuid4(),
                username=admin_username,
                email="admin@powerhouse.local",
                password_hash=get_password_hash(admin_password),
                role=UserRole.ADMIN,
                is_active=True
            )
            
            db.add(admin_user)
            db.commit()
            
            print("✓ Admin user created successfully")
            print("\n" + "="*60)
            print("DEFAULT ADMIN CREDENTIALS")
            print("="*60)
            print(f"Username: {admin_username}")
            print(f"Password: {admin_password}")
            print("\n⚠ IMPORTANT: Change the admin password immediately!")
            print("="*60 + "\n")
    
    except Exception as e:
        print(f"✗ Error creating admin user: {e}")
        db.rollback()
        sys.exit(1)
    
    finally:
        db.close()
    
    print("\n✓ Database initialization complete!")


if __name__ == "__main__":
    init_db()

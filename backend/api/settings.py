from typing import List, Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.deps import get_db, require_admin
from models.setting import Setting
from schemas.setting import SettingCreate, SettingResponse, SettingUpdate

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get("", response_model=List[SettingResponse])
def get_settings(db: Session = Depends(get_db), current_user = Depends(require_admin)):
    """Get all system settings."""
    return db.query(Setting).all()

@router.get("/public", response_model=Dict[str, Any])
def get_public_settings(db: Session = Depends(get_db)):
    """Return specific public settings necessary for app initialization."""
    public_keys = ["app_name", "theme_mode", "business_name", "business_logo"]
    settings = db.query(Setting).filter(Setting.key.in_(public_keys)).all()
    return {s.key: s.value for s in settings}

@router.get("/{key}", response_model=SettingResponse)
def get_setting(key: str, db: Session = Depends(get_db), current_user = Depends(require_admin)):
    """Get a specific setting by key."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    return setting

@router.put("/{key}", response_model=SettingResponse)
def update_setting(key: str, update_data: SettingUpdate, db: Session = Depends(get_db), current_user = Depends(require_admin)):
    """Update or create a setting."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        setting = Setting(
            key=key, 
            value=update_data.value, 
            description=update_data.description
        )
        db.add(setting)
    else:
        setting.value = update_data.value
        if update_data.description:
            setting.description = update_data.description
            
    db.commit()
    db.refresh(setting)
    return setting

@router.post("/bulk", response_model=List[SettingResponse])
def bulk_update_settings(settings: List[SettingCreate], db: Session = Depends(get_db), current_user = Depends(require_admin)):
    """Update multiple settings at once."""
    results = []
    for s in settings:
        existing = db.query(Setting).filter(Setting.key == s.key).first()
        if existing:
            existing.value = s.value
            if s.description:
                existing.description = s.description
            existing.category = s.category
            results.append(existing)
        else:
            new_setting = Setting(
                key=s.key, 
                value=s.value, 
                description=s.description, 
                category=s.category
            )
            db.add(new_setting)
            results.append(new_setting)
    
    db.commit()
    for r in results:
        db.refresh(r)
    return results

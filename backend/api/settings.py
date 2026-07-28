from typing import List, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from datetime import datetime
import os
from sqlalchemy.orm import Session
from api.deps import get_db, require_admin
from models.setting import Setting
from schemas.setting import SettingCreate, SettingResponse, SettingUpdate
from services.timezone import invalidate_app_tz_cache

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("", response_model=List[SettingResponse])
def get_settings(db: Session = Depends(get_db), current_user=Depends(require_admin)):
    """Get all system settings."""
    return db.query(Setting).all()


@router.get("/public", response_model=Dict[str, Any])
def get_public_settings(db: Session = Depends(get_db)):
    """Return specific public settings necessary for app initialization."""
    public_keys = [
        "app_name",
        "theme_mode",
        "business_name",
        "business_logo",
        "timezone",
    ]
    settings = db.query(Setting).filter(Setting.key.in_(public_keys)).all()
    return {s.key: s.value for s in settings}


# NOTE: Static routes (/logo, /upload-logo, /bulk) MUST be defined BEFORE
# the catch-all /{key} route, otherwise FastAPI matches them as {key}="logo" etc.


@router.get("/logo")
def get_logo():
    """Serve the uploaded logo."""
    upload_dir = "/var/lib/powerhouse/uploads"
    for ext in ["png", "jpg", "jpeg", "gif", "svg", "ico", "webp"]:
        path = os.path.join(upload_dir, f"logo.{ext}")
        if os.path.exists(path):
            media_types = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "gif": "image/gif",
                "svg": "image/svg+xml",
                "ico": "image/x-icon",
                "webp": "image/webp",
            }
            return FileResponse(path, media_type=media_types.get(ext, "image/png"))

    # Return default logo from frontend
    default_path = "/opt/powerhouse-membership/frontend/public/logo.png"
    if os.path.exists(default_path):
        return FileResponse(default_path, media_type="image/png")

    raise HTTPException(404, "No logo found")


@router.post("/upload-logo")
async def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Upload a custom logo for the organization."""
    # Validate file type
    allowed_types = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/svg+xml",
        "image/x-icon",
        "image/webp",
    ]
    if file.content_type not in allowed_types:
        raise HTTPException(
            400, f"Invalid file type. Allowed: {', '.join(allowed_types)}"
        )

    # Save file
    upload_dir = "/var/lib/powerhouse/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    # Remove old logo files
    for old in os.listdir(upload_dir):
        if old.startswith("logo."):
            os.remove(os.path.join(upload_dir, old))

    # Determine extension
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png"
    logo_path = os.path.join(upload_dir, f"logo.{ext}")

    contents = await file.read()
    with open(logo_path, "wb") as f:
        f.write(contents)

    # Update setting
    logo_url = f"/api/settings/logo?t={int(datetime.now().timestamp())}"
    setting = db.query(Setting).filter(Setting.key == "business_logo").first()
    if not setting:
        setting = Setting(
            key="business_logo",
            value=logo_url,
            category="general",
            description="Organization logo URL",
        )
        db.add(setting)
    else:
        setting.value = logo_url
    db.commit()

    return {"url": logo_url, "message": "Logo uploaded successfully"}


@router.post("/bulk", response_model=List[SettingResponse])
def bulk_update_settings(
    settings: List[SettingCreate],
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
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
                key=s.key, value=s.value, description=s.description, category=s.category
            )
            db.add(new_setting)
            results.append(new_setting)

    db.commit()
    # Invalidate the cached app timezone if any written key was the timezone
    # setting, so the new zone takes effect on the next request.
    if any(s.key == "timezone" for s in settings):
        invalidate_app_tz_cache()
    for r in results:
        db.refresh(r)
    return results


@router.get("/{key}", response_model=SettingResponse)
def get_setting(
    key: str, db: Session = Depends(get_db), current_user=Depends(require_admin)
):
    """Get a specific setting by key."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    return setting


@router.put("/{key}", response_model=SettingResponse)
def update_setting(
    key: str,
    update_data: SettingUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Update or create a setting."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        setting = Setting(
            key=key, value=update_data.value, description=update_data.description
        )
        db.add(setting)
    else:
        setting.value = update_data.value
        if update_data.description:
            setting.description = update_data.description

    db.commit()
    # Invalidate the cached app timezone if any of the written keys was the
    # timezone setting (bulk path covers the single-row case too).
    if key == "timezone":
        invalidate_app_tz_cache()
    db.refresh(setting)
    return setting

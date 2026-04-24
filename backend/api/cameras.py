"""
Cameras API endpoints.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import glob
import platform
import os

from api.deps import get_db, require_staff, require_admin
from core.encryption import encrypt_string, decrypt_string
from models.user import User
from models.camera import Camera
from schemas.camera import (
    CameraCreate,
    CameraUpdate,
    CameraResponse,
    CameraListResponse
)

router = APIRouter(prefix="/cameras", tags=["Cameras"])


@router.get("", response_model=CameraListResponse)
def list_cameras(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    List all cameras with pagination and filtering.
    
    - **skip**: Number of records to skip
    - **limit**: Maximum number of records to return
    - **enabled**: Filter by enabled status
    """
    query = db.query(Camera)
    
    # Filter by enabled status
    if enabled is not None:
        query = query.filter(Camera.enabled == enabled)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    cameras = query.order_by(Camera.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "cameras": cameras
    }


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
def create_camera(
    camera: CameraCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Create a new camera.
    
    Requires admin role. RTSP URL will be encrypted before storage.
    """
    # Check if camera name already exists
    existing = db.query(Camera).filter(Camera.name == camera.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Camera name already exists"
        )
    
    # Encrypt RTSP URL
    encrypted_url = encrypt_string(camera.rtsp_url)
    
    # Create camera
    db_camera = Camera(
        name=camera.name,
        rtsp_url=encrypted_url,
        location=camera.location,
        location_id=camera.location_id,
        fps=camera.fps,
        resolution_width=camera.resolution_width,
        resolution_height=camera.resolution_height,
        enabled=camera.enabled,
        confidence_threshold=camera.confidence_threshold
    )
    
    db.add(db_camera)
    db.commit()
    db.refresh(db_camera)
    
    return db_camera


@router.get("/devices/detect")
def get_available_devices(
    current_user: User = Depends(require_staff)
):
    """
    Detect available USB video devices on the server.
    Checks both /dev/video* nodes and /sys/class/video4linux/ entries.
    """
    devices = []
    seen_paths = set()
    
    if platform.system() == "Linux":
        # Method 1: Check /dev/video* (normal systems)
        video_devices = sorted(glob.glob("/dev/video*"))
        for dev in video_devices:
            if dev not in seen_paths:
                name = f"USB Camera ({dev})"
                sys_name_path = f"/sys/class/video4linux/{os.path.basename(dev)}/name"
                if os.path.exists(sys_name_path):
                    try:
                        with open(sys_name_path) as f:
                            sys_name = f.read().strip()
                        if sys_name:
                            name = f"{sys_name} ({dev})"
                    except:
                        pass
                devices.append({"path": dev, "name": name})
                seen_paths.add(dev)
        
        # Method 2: Check /sys/class/video4linux/ (LXC containers without /dev nodes)
        sys_v4l_dir = "/sys/class/video4linux"
        if os.path.isdir(sys_v4l_dir):
            for entry in sorted(os.listdir(sys_v4l_dir)):
                if entry.startswith("video"):
                    dev_path = f"/dev/{entry}"
                    if dev_path in seen_paths:
                        continue
                    
                    name = f"USB Camera (/{entry})"
                    sys_name_path = f"{sys_v4l_dir}/{entry}/name"
                    dev_exists = os.path.exists(dev_path)
                    
                    if os.path.exists(sys_name_path):
                        try:
                            with open(sys_name_path) as f:
                                sys_name = f.read().strip()
                            if sys_name:
                                name = f"{sys_name} (/{entry})"
                        except:
                            pass
                    
                    status = "ready" if dev_exists else "needs_passthrough"
                    devices.append({
                        "path": dev_path if dev_exists else entry,
                        "name": name,
                        "status": status,
                        "info": "Device detected but /dev node missing — USB passthrough needed in Proxmox" if not dev_exists else None,
                    })
                    seen_paths.add(dev_path)
    else:
        # Fallback for Windows/Mac - return common indices
        devices = [
            {"path": "0", "name": "Default Camera (Index 0)"},
            {"path": "1", "name": "Camera Index 1"},
            {"path": "2", "name": "Camera Index 2"},
        ]
        
    return {"devices": devices}


@router.get("/{camera_id}", response_model=CameraResponse)
def get_camera(
    camera_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    Get camera by ID.
    """
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found"
        )
    
    return camera


@router.put("/{camera_id}", response_model=CameraResponse)
def update_camera(
    camera_id: str,
    camera_update: CameraUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Update camera information.
    
    Requires admin role.
    """
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found"
        )
    
    # Check name uniqueness if updating
    if camera_update.name and camera_update.name != camera.name:
        existing = db.query(Camera).filter(Camera.name == camera_update.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Camera name already exists"
            )
    
    # Update fields
    update_data = camera_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "rtsp_url" and value:
            # Encrypt new RTSP URL
            setattr(camera, field, encrypt_string(value))
        else:
            setattr(camera, field, value)
    
    camera.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(camera)
    
    return camera


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(
    camera_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Delete a camera.
    
    Requires admin role.
    """
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found"
        )
    
    db.delete(camera)
    db.commit()
    
    return None


@router.get("/{camera_id}/rtsp-url")
def get_camera_rtsp_url(
    camera_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get decrypted RTSP URL for a camera.
    
    Requires admin role. Used by CV service to connect to cameras.
    """
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found"
        )
    
    # Decrypt RTSP URL
    try:
        rtsp_url = decrypt_string(camera.rtsp_url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt RTSP URL"
        )
    
    return {"rtsp_url": rtsp_url}



@router.post("/{camera_id}/test")
def test_camera_connection(
    camera_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Test camera connection.
    Try to open the RTSP stream and read a frame.
    """
    import cv2
    
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found"
        )
    
    try:
        url = decrypt_string(camera.rtsp_url)
        
        # Determine source (USB index or URL string)
        source = url
        if url.isdigit():
            source = int(url)
            
        # Open video capture
        cap = cv2.VideoCapture(source)
        
        if not cap.isOpened():
            return {"status": "failed", "message": "Could not open video source"}
            
        # Try to read a frame
        ret, _ = cap.read()
        cap.release()
        
        if ret:
            return {"status": "success", "message": "Successfully connected and read a frame"}
        else:
            return {"status": "failed", "message": "Connected but failed to grab a frame"}
            
    except Exception as e:
        return {"status": "error", "message": f"Connection error: {str(e)}"}

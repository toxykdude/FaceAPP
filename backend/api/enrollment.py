"""
Face enrollment API endpoints.

Generates FaceNet embeddings during enrollment and stores them encrypted in the database.
The CV service loads these embeddings into Redis cache for real-time recognition.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import numpy as np
import cv2
import logging
import json

import httpx

from api.deps import get_db, get_current_user
from models.member import Member
from models.biometric import BiometricTemplate
from models.user import User
from models.camera import Camera
from core.encryption import encrypt_template, decrypt_string
from schemas.member import BiometricEnrollmentResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enrollment", tags=["enrollment"])

# FaceNet model (lazy loaded)
_face_net_model = None


async def notify_cv_invalidation(member_id: str):
    """Notify CV service to invalidate a member's cached template."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"http://localhost:8001/invalidate/{member_id}")
    except Exception:
        pass  # CV service might be down, non-critical


def _get_face_net():
    """Lazy-load FaceNet model."""
    global _face_net_model
    if _face_net_model is None:
        import torch
        from facenet_pytorch import InceptionResnetV1
        device = torch.device('cpu')  # Always CPU for enrollment (no GPU needed)
        _face_net_model = InceptionResnetV1(pretrained='vggface2').eval().to(device)
        logger.info("FaceNet model loaded for enrollment")
    return _face_net_model


def _generate_embedding(face_roi: np.ndarray) -> np.ndarray:
    """
    Generate a 512-dimensional FaceNet embedding from a face ROI.
    
    Args:
        face_roi: BGR image of the face
        
    Returns:
        Normalized 512-d embedding as numpy array
    """
    import torch
    from PIL import Image
    
    model = _get_face_net()
    device = next(model.parameters()).device
    
    # BGR -> RGB
    face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
    
    # Resize to 160x160 (FaceNet input)
    face_resized = cv2.resize(face_rgb, (160, 160))
    
    # Convert to tensor: HWC -> CHW, normalize to [-1, 1]
    face_tensor = torch.from_numpy(np.array(face_resized)).float()
    face_tensor = face_tensor.permute(2, 0, 1)
    face_tensor = (face_tensor - 127.5) / 128.0
    face_tensor = face_tensor.unsqueeze(0).to(device)
    
    # Generate embedding
    with torch.no_grad():
        embedding = model(face_tensor)
    
    # Convert to numpy and L2-normalize
    embedding_np = embedding.cpu().numpy().flatten()
    embedding_np = embedding_np / np.linalg.norm(embedding_np)
    
    return embedding_np


def _detect_and_extract_face(img: np.ndarray):
    """
    Detect a single face in an image and extract the ROI with padding.
    
    Returns:
        Tuple of (face_roi, bbox) or raises HTTPException
    """
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)
    
    if len(faces) == 0:
        raise HTTPException(status_code=400, detail="No face detected in image")
    
    if len(faces) > 1:
        raise HTTPException(
            status_code=400,
            detail="Multiple faces detected. Please upload image with single face."
        )
    
    # Extract face with 10% padding
    (x, y, w, h) = faces[0]
    padding = int(min(w, h) * 0.1)
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(img.shape[1], x + w + padding)
    y2 = min(img.shape[0], y + h + padding)
    
    face_roi = img[y1:y2, x1:x2]
    
    # Calculate quality score based on face size relative to image
    quality_score = min(1.0, (w * h) / (img.shape[0] * img.shape[1]) * 10)
    
    return face_roi, quality_score


class CameraEnrollmentRequest(BaseModel):
    camera_id: str


# --- Endpoints ---


@router.post("/{member_id}/enroll", response_model=BiometricEnrollmentResponse)
async def enroll_member_face(
    member_id: str,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Enroll a member's face from uploaded image.
    
    Generates a FaceNet embedding (512-d vector) and stores it encrypted.
    """
    # Get member
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Check if already enrolled
    existing = db.query(BiometricTemplate).filter(
        BiometricTemplate.member_id == member_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Member already enrolled. Delete existing enrollment first."
        )
    
    try:
        # Read image
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image format")
        
        # Detect face and extract ROI
        face_roi, quality_score = _detect_and_extract_face(img)
        
        # Quality threshold - reject low quality photos
        MIN_QUALITY = 0.9
        if quality_score < MIN_QUALITY:
            raise HTTPException(
                status_code=400,
                detail=f"Face photo quality too low ({quality_score:.2f}). Minimum required: {MIN_QUALITY}. Please use a clearer, closer photo with better lighting."
            )
        
        # Generate FaceNet embedding
        embedding = _generate_embedding(face_roi)
        
        # Serialize embedding to JSON-compatible bytes
        template_data = json.dumps(embedding.tolist()).encode('utf-8')
        
        # Encrypt and store
        encrypted_template = encrypt_template(template_data)
        
        biometric_template = BiometricTemplate(
            member_id=member_id,
            template_data=encrypted_template,
            quality_score=quality_score,
            encryption_key_id="v1"
        )
        
        db.add(biometric_template)
        member.facial_data_enrolled = True
        db.commit()
        db.refresh(biometric_template)
        
        # Invalidate CV cache so new template gets picked up on next reload
        await notify_cv_invalidation(member_id)
        
        logger.info(f"Face enrolled for member {member_id} (quality: {quality_score:.2f})")
        
        return BiometricEnrollmentResponse(
            success=True,
            message="Face enrolled successfully",
            quality_score=quality_score,
            member_id=member_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enrollment error for member {member_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Enrollment failed: {str(e)}")


@router.delete("/{member_id}/enroll")
async def delete_enrollment(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a member's biometric enrollment."""
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    template = db.query(BiometricTemplate).filter(
        BiometricTemplate.member_id == member_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="No enrollment found for this member")
    
    db.delete(template)
    member.facial_data_enrolled = False
    db.commit()
    
    # Invalidate CV cache
    await notify_cv_invalidation(member_id)
    
    logger.info(f"Enrollment deleted for member {member_id}")
    return {"success": True, "message": "Enrollment deleted successfully"}


@router.get("/{member_id}/status")
async def get_enrollment_status(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get enrollment status for a member."""
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    template = db.query(BiometricTemplate).filter(
        BiometricTemplate.member_id == member_id
    ).first()
    
    if template:
        return {
            "enrolled": True,
            "quality_score": template.quality_score,
            "enrolled_at": template.enrolled_at.isoformat(),
            "updated_at": template.updated_at.isoformat()
        }
    else:
        return {
            "enrolled": False,
            "quality_score": None,
            "enrolled_at": None,
            "updated_at": None
        }


@router.post("/{member_id}/verify")
async def verify_face(
    member_id: str,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Verify a face against enrolled template using FaceNet cosine similarity.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    template = db.query(BiometricTemplate).filter(
        BiometricTemplate.member_id == member_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Member not enrolled")
    
    try:
        from core.encryption import decrypt_template
        
        # Read uploaded image
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image format")
        
        # Detect and extract face
        face_roi, _ = _detect_and_extract_face(img)
        
        # Generate embedding for uploaded face
        query_embedding = _generate_embedding(face_roi)
        
        # Decrypt stored embedding
        decrypted = decrypt_template(template.template_data)
        stored_embedding = np.array(json.loads(decrypted.decode('utf-8')))
        
        # Cosine similarity
        similarity = np.dot(query_embedding, stored_embedding) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(stored_embedding)
        )
        similarity = (similarity + 1) / 2  # Normalize to 0-1 range
        
        return {
            "match": bool(similarity >= 0.85),
            "confidence": float(similarity),
            "member_id": member_id,
            "member_name": member.full_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verification error: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@router.post("/{member_id}/enroll/camera", response_model=BiometricEnrollmentResponse)
async def enroll_member_camera(
    member_id: str,
    request: CameraEnrollmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Enroll a member's face from a connected system camera (RTSP or USB).
    Uses FaceNet to generate a real embedding.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    existing = db.query(BiometricTemplate).filter(
        BiometricTemplate.member_id == member_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Member already enrolled. Delete existing enrollment first."
        )
    
    camera = db.query(Camera).filter(Camera.id == request.camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    try:
        rtsp_url = decrypt_string(camera.rtsp_url)
        video_source = rtsp_url
        
        if isinstance(video_source, str) and video_source.isdigit():
            video_source = int(video_source)
        
        cap = cv2.VideoCapture(video_source)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Could not connect to camera")
        
        # Let auto-exposure settle
        for _ in range(5):
            cap.read()
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret or frame is None:
            raise HTTPException(status_code=500, detail="Failed to capture frame from camera")
        
        # Detect face and extract ROI
        face_roi, quality_score = _detect_and_extract_face(frame)
        
        # Quality threshold - reject low quality captures
        MIN_QUALITY = 0.9
        if quality_score < MIN_QUALITY:
            raise HTTPException(
                status_code=400,
                detail=f"Face capture quality too low ({quality_score:.2f}). Minimum required: {MIN_QUALITY}. Please ensure good lighting and face the camera directly."
            )
        
        # Generate FaceNet embedding
        embedding = _generate_embedding(face_roi)
        
        # Serialize and encrypt
        template_data = json.dumps(embedding.tolist()).encode('utf-8')
        encrypted_template = encrypt_template(template_data)
        
        biometric_template = BiometricTemplate(
            member_id=member_id,
            template_data=encrypted_template,
            quality_score=quality_score,
            encryption_key_id="v1"
        )
        
        db.add(biometric_template)
        member.facial_data_enrolled = True
        db.commit()
        db.refresh(biometric_template)
        
        # Invalidate CV cache so new template gets picked up on next reload
        await notify_cv_invalidation(member_id)
        
        logger.info(f"Face enrolled from camera {camera.name} for member {member_id}")
        
        return BiometricEnrollmentResponse(
            success=True,
            message=f"Face enrolled from {camera.name}",
            quality_score=quality_score,
            member_id=member_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Camera enrollment error for member {member_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Enrollment failed: {str(e)}")

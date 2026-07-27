"""
Face enrollment API endpoints.

Uses MTCNN for face detection (same as CV service), face alignment with
eye landmarks, and multi-embedding averaging via data augmentation for
robust recognition.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import numpy as np
import cv2
import logging
import json
from typing import List, Tuple

import httpx

from api.deps import get_db, get_current_user
from models.member import Member
from models.biometric import BiometricTemplate
from models.user import User
from models.camera import Camera
from core.config import settings
from core.encryption import encrypt_template, decrypt_string
from schemas.member import BiometricEnrollmentResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enrollment", tags=["enrollment"])

# ---------------------------------------------------------------------------
# Lazy-loaded models (shared across requests)
# ---------------------------------------------------------------------------
_face_net_model = None
_mtcnn_detector = None


def _get_mtcnn():
    """Lazy-load MTCNN detector (same config as CV service)."""
    global _mtcnn_detector
    if _mtcnn_detector is None:
        import torch
        from facenet_pytorch import MTCNN

        _mtcnn_detector = MTCNN(
            keep_all=True,
            device=torch.device("cpu"),
            min_face_size=80,
            thresholds=[0.6, 0.7, 0.8],
        )
        logger.info("MTCNN detector loaded for enrollment")
    return _mtcnn_detector


def _get_face_net():
    """Lazy-load FaceNet model."""
    global _face_net_model
    if _face_net_model is None:
        import torch
        from facenet_pytorch import InceptionResnetV1

        _face_net_model = (
            InceptionResnetV1(pretrained="vggface2").eval().to(torch.device("cpu"))
        )
        logger.info("FaceNet model loaded for enrollment")
    return _face_net_model


# ---------------------------------------------------------------------------
# CV service notification
# ---------------------------------------------------------------------------


async def notify_cv_reload():
    """
    Trigger full template reload on CV service after enrollment.

    This ensures the newly enrolled template is available immediately
    instead of waiting for the next periodic refresh (10 minutes).
    """
    try:
        headers = {}
        if settings.CV_API_KEY:
            headers["X-API-Key"] = settings.CV_API_KEY
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.CV_SERVICE_URL}/reload", headers=headers
            )
            logger.info(f"CV service reload after enrollment: {resp.status_code}")
    except Exception as e:
        logger.warning(f"Failed to reload CV templates: {e}")


# ---------------------------------------------------------------------------
# Face alignment
# ---------------------------------------------------------------------------


def _align_face(face_roi: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
    """
    Align face using eye landmarks via affine transformation.

    Rotates the image so both eyes are on a horizontal line, which is
    the alignment FaceNet was trained on.

    Args:
        face_roi: BGR face image
        landmarks: MTCNN landmarks [[left_eye, right_eye, nose, left_mouth, right_mouth]]

    Returns:
        Aligned face image
    """
    if landmarks is None:
        return face_roi

    left_eye = landmarks[0]  # (x, y)
    right_eye = landmarks[1]  # (x, y)

    # Angle between eyes
    dy = right_eye[1] - left_eye[1]
    dx = right_eye[0] - left_eye[0]
    angle = np.degrees(np.arctan2(dy, dx))

    # Center point between eyes
    center = ((left_eye[0] + right_eye[0]) / 2.0, (left_eye[1] + right_eye[1]) / 2.0)

    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    h, w = face_roi.shape[:2]
    aligned = cv2.warpAffine(face_roi, M, (w, h), flags=cv2.INTER_CUBIC)

    return aligned


# ---------------------------------------------------------------------------
# Data augmentation for multi-embedding
# ---------------------------------------------------------------------------


def _augment_face(face_roi: np.ndarray) -> List[np.ndarray]:
    """
    Generate augmented versions of a face for robust multi-embedding.

    Returns 6 versions: original, +5 deg, -5 deg, brighter, darker, flipped.
    """
    augmented = [face_roi]
    h, w = face_roi.shape[:2]

    # Slight rotation +5 degrees
    M1 = cv2.getRotationMatrix2D((w / 2, h / 2), 5, 1.0)
    augmented.append(
        cv2.warpAffine(face_roi, M1, (w, h), borderMode=cv2.BORDER_REFLECT)
    )

    # Slight rotation -5 degrees
    M2 = cv2.getRotationMatrix2D((w / 2, h / 2), -5, 1.0)
    augmented.append(
        cv2.warpAffine(face_roi, M2, (w, h), borderMode=cv2.BORDER_REFLECT)
    )

    # Brightness increase (+15%)
    augmented.append(cv2.convertScaleAbs(face_roi, alpha=1.15, beta=10))

    # Brightness decrease (-15%)
    augmented.append(cv2.convertScaleAbs(face_roi, alpha=0.85, beta=-10))

    # Horizontal flip (simulates opposite angle)
    augmented.append(cv2.flip(face_roi, 1))

    return augmented


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------


def _generate_single_embedding(face_roi: np.ndarray) -> np.ndarray:
    """Generate one FaceNet 512-d embedding from a face ROI."""
    import torch

    model = _get_face_net()

    # BGR -> RGB, resize to 160x160
    face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
    face_resized = cv2.resize(face_rgb, (160, 160))

    # To tensor, normalize to [-1, 1]
    face_tensor = torch.from_numpy(np.array(face_resized)).float()
    face_tensor = face_tensor.permute(2, 0, 1)
    face_tensor = (face_tensor - 127.5) / 128.0
    face_tensor = face_tensor.unsqueeze(0)

    with torch.no_grad():
        embedding = model(face_tensor)

    embedding_np = embedding.cpu().numpy().flatten()
    embedding_np = embedding_np / np.linalg.norm(embedding_np)
    return embedding_np


def _generate_multi_embedding(face_roi: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Generate robust embedding by averaging multiple augmented versions.

    Returns:
        (averaged_normalized_embedding, consistency_score)
        consistency_score reflects how stable the embeddings are across
        augmentations (higher = more reliable enrollment).
    """
    faces = _augment_face(face_roi)
    embeddings = [_generate_single_embedding(f) for f in faces]

    embeddings_arr = np.array(embeddings)
    avg = np.mean(embeddings_arr, axis=0)
    avg = avg / np.linalg.norm(avg)  # Re-normalize

    # Consistency: cosine similarity between each augmented and the mean
    sims = [float(np.dot(e, avg)) for e in embeddings]
    consistency = float(np.mean(sims))

    return avg, consistency


# ---------------------------------------------------------------------------
# Face detection + extraction (MTCNN)
# ---------------------------------------------------------------------------


def _detect_and_extract_face(img: np.ndarray) -> Tuple[np.ndarray, float, np.ndarray]:
    """
    Detect face using MTCNN (same detector as CV service), extract aligned ROI.

    Returns:
        (face_roi_aligned, quality_score, landmarks_or_None)
    """
    mtcnn = _get_mtcnn()

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    boxes, probs, landmarks = mtcnn.detect(rgb, landmarks=True)

    if boxes is None or len(boxes) == 0:
        raise HTTPException(
            status_code=400,
            detail="No face detected in image. Ensure your face is clearly visible with good lighting.",
        )

    # Pick largest face if multiple detected
    if len(boxes) > 1:
        areas = [(b[2] - b[0]) * (b[3] - b[1]) for b in boxes]
        best = int(np.argmax(areas))
    else:
        best = 0

    box = boxes[best]
    prob = float(probs[best]) if probs is not None else 0.0
    face_landmarks = landmarks[best] if landmarks is not None else None

    if prob < 0.9:
        raise HTTPException(
            status_code=400,
            detail=f"Face detection confidence too low ({prob:.2f}). Use a clearer, more frontal photo.",
        )

    # Extract with generous 30% padding
    x1, y1, x2, y2 = box.astype(int)
    w, h = x2 - x1, y2 - y1
    pad = int(min(w, h) * 0.3)
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(img.shape[1], x2 + pad)
    y2 = min(img.shape[0], y2 + pad)

    face_roi = img[y1:y2, x1:x2]

    # Adjust landmarks to ROI coordinates and align
    if face_landmarks is not None:
        adjusted = face_landmarks.copy()
        adjusted[:, 0] -= x1
        adjusted[:, 1] -= y1
        face_roi = _align_face(face_roi, adjusted)

    # Quality assessment (sharpness + brightness + size + MTCNN confidence)
    gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
    sharpness = min(cv2.Laplacian(gray, cv2.CV_64F).var() / 300.0, 1.0)
    mean_bright = gray.mean()
    brightness = max(0.0, 1.0 - abs(mean_bright - 130) / 130.0)
    face_area_ratio = (w * h) / (img.shape[0] * img.shape[1])
    size_score = min(face_area_ratio * 5.0, 1.0)

    quality = sharpness * 0.4 + brightness * 0.25 + size_score * 0.2 + prob * 0.15

    return face_roi, quality, face_landmarks


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CameraEnrollmentRequest(BaseModel):
    camera_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{member_id}/enroll", response_model=BiometricEnrollmentResponse)
async def enroll_member_face(
    member_id: str,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enroll a member's face from an uploaded image.

    Uses MTCNN detection, face alignment, and multi-embedding averaging
    for robust recognition.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Remove existing enrollment (re-enrollment)
    existing = (
        db.query(BiometricTemplate)
        .filter(BiometricTemplate.member_id == member_id)
        .first()
    )
    if existing:
        db.delete(existing)
        db.flush()

    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image format")

        # MTCNN detection + alignment
        face_roi, quality_score, _ = _detect_and_extract_face(img)

        if quality_score < 0.4:
            raise HTTPException(
                status_code=400,
                detail=f"Face quality too low ({quality_score:.2f}). Use better lighting and face the camera directly.",
            )

        # Multi-embedding with augmentation
        embedding, consistency = _generate_multi_embedding(face_roi)
        final_quality = max(quality_score, consistency)

        # Encrypt and store
        template_data = json.dumps(embedding.tolist()).encode("utf-8")
        encrypted_template = encrypt_template(template_data)

        biometric = BiometricTemplate(
            member_id=member_id,
            template_data=encrypted_template,
            quality_score=final_quality,
            encryption_key_id="v1",
        )
        db.add(biometric)
        member.facial_data_enrolled = True
        db.commit()
        db.refresh(biometric)

        # Reload CV service templates immediately
        await notify_cv_reload()

        logger.info(
            f"Enrolled member {member_id}: quality={final_quality:.2f}, "
            f"consistency={consistency:.2f} (multi-embedding)"
        )

        return BiometricEnrollmentResponse(
            success=True,
            message="Face enrolled successfully",
            quality_score=final_quality,
            member_id=member_id,
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
    current_user: User = Depends(get_current_user),
):
    """Delete a member's biometric enrollment."""
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    template = (
        db.query(BiometricTemplate)
        .filter(BiometricTemplate.member_id == member_id)
        .first()
    )

    if not template:
        raise HTTPException(
            status_code=404, detail="No enrollment found for this member"
        )

    db.delete(template)
    member.facial_data_enrolled = False
    db.commit()

    await notify_cv_reload()

    logger.info(f"Enrollment deleted for member {member_id}")
    return {"success": True, "message": "Enrollment deleted successfully"}


@router.get("/{member_id}/status")
async def get_enrollment_status(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get enrollment status for a member."""
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    template = (
        db.query(BiometricTemplate)
        .filter(BiometricTemplate.member_id == member_id)
        .first()
    )

    if template:
        return {
            "enrolled": True,
            "quality_score": template.quality_score,
            "enrolled_at": template.enrolled_at.isoformat(),
            "updated_at": template.updated_at.isoformat(),
        }
    return {
        "enrolled": False,
        "quality_score": None,
        "enrolled_at": None,
        "updated_at": None,
    }


@router.post("/{member_id}/verify")
async def verify_face(
    member_id: str,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify a face against enrolled template."""
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    template = (
        db.query(BiometricTemplate)
        .filter(BiometricTemplate.member_id == member_id)
        .first()
    )

    if not template:
        raise HTTPException(status_code=404, detail="Member not enrolled")

    try:
        from core.encryption import decrypt_template

        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image format")

        # MTCNN detection + alignment for verification too
        face_roi, _, _ = _detect_and_extract_face(img)

        # Multi-embedding for verification
        query_embedding, _ = _generate_multi_embedding(face_roi)

        # Decrypt stored embedding
        decrypted = decrypt_template(template.template_data)
        stored_embedding = np.array(json.loads(decrypted.decode("utf-8")))

        # Cosine similarity
        similarity = np.dot(query_embedding, stored_embedding) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(stored_embedding)
        )
        similarity = (similarity + 1) / 2  # Normalize to 0-1

        return {
            "match": bool(similarity >= 0.85),
            "confidence": float(similarity),
            "member_id": member_id,
            "member_name": member.full_name,
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
    current_user: User = Depends(get_current_user),
):
    """Enroll face from connected camera with MTCNN and multi-embedding."""
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    existing = (
        db.query(BiometricTemplate)
        .filter(BiometricTemplate.member_id == member_id)
        .first()
    )
    if existing:
        db.delete(existing)
        db.flush()

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
        for _ in range(10):
            cap.read()

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            raise HTTPException(
                status_code=500, detail="Failed to capture frame from camera"
            )

        # MTCNN detection + alignment
        face_roi, quality_score, _ = _detect_and_extract_face(frame)

        if quality_score < 0.4:
            raise HTTPException(
                status_code=400,
                detail=f"Face capture quality too low ({quality_score:.2f}). Ensure good lighting.",
            )

        # Multi-embedding
        embedding, consistency = _generate_multi_embedding(face_roi)
        final_quality = max(quality_score, consistency)

        template_data = json.dumps(embedding.tolist()).encode("utf-8")
        encrypted_template = encrypt_template(template_data)

        biometric = BiometricTemplate(
            member_id=member_id,
            template_data=encrypted_template,
            quality_score=final_quality,
            encryption_key_id="v1",
        )
        db.add(biometric)
        member.facial_data_enrolled = True
        db.commit()
        db.refresh(biometric)

        await notify_cv_reload()

        logger.info(f"Camera enrolled member {member_id} from {camera.name}")

        return BiometricEnrollmentResponse(
            success=True,
            message=f"Face enrolled from {camera.name}",
            quality_score=final_quality,
            member_id=member_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Camera enrollment error for member {member_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Enrollment failed: {str(e)}")

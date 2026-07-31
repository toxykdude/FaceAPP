"""
Main CV service application with Streaming API.
"""

import asyncio
import hmac
import sys
import time
import cv2
import numpy as np
import io
from typing import Any, Dict, NamedTuple, Optional
from loguru import logger
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    HTTPException,
    Body,
    Depends,
    Header,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from config import settings
from stream.rtsp_processor import RTSPStreamProcessor
from validation.access_validator import AccessValidator
from api.backend_client import BackendAPIClient


# Models
class StartCameraRequest(BaseModel):
    camera_id: str
    rtsp_url: str
    fps: int = 5

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp_url(cls, v: str) -> str:
        """Validate RTSP URL to prevent SSRF and injection (VULN-2 fix)."""
        import ipaddress
        from urllib.parse import urlparse

        if not v or not v.strip():
            raise ValueError("RTSP URL cannot be empty")
        v = v.strip()

        if ".." in v or "\n" in v or "\r" in v:
            raise ValueError("Invalid characters in URL")

        # Local device paths (USB cameras)
        if v.startswith("/dev/video"):
            return v
        # Browser/WebRTC sources (kiosk internal)
        if v.startswith("browser:") or v.startswith("client:"):
            return v

        # Network URLs — validate scheme and block internal IPs
        allowed_schemes = ("rtsp://", "http://", "https://")
        if not any(v.lower().startswith(scheme) for scheme in allowed_schemes):
            raise ValueError(
                f"URL must start with one of: rtsp://, http://, https://, /dev/video"
            )

        # Block internal/private IPs to prevent SSRF
        try:
            parsed = urlparse(v)
            hostname = parsed.hostname
            if hostname:
                # Block common internal hostnames
                if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
                    raise ValueError(
                        "URLs pointing to internal addresses are not allowed"
                    )
                # Block private IP ranges
                try:
                    ip = ipaddress.ip_address(hostname)
                    if ip.is_private or ip.is_loopback or ip.is_reserved:
                        raise ValueError(
                            "URLs pointing to private/internal addresses are not allowed"
                        )
                except ValueError:
                    pass  # Not an IP, could be a hostname — allow
        except Exception as e:
            if "not allowed" in str(e):
                raise
        return v


class StopCameraRequest(BaseModel):
    camera_id: str


async def verify_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """
    Verify API key for CV service endpoints.

    When API_KEY is set in environment, ALL requests must include a matching
    X-API-Key header.

    FAIL CLOSED (S2): when API_KEY is not configured, every request is rejected
    with 503 (service misconfiguration) instead of silently allowed.
    Comparison uses hmac.compare_digest to be timing-safe.
    """
    if not settings.API_KEY:
        raise HTTPException(status_code=503, detail="API_KEY not configured")
    if not hmac.compare_digest(x_api_key or "", settings.API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


def save_member_photo(member_id: str, frame, face_bbox=None):
    """Save a member's face photo for profile/tooltips."""
    try:
        import os

        photo_dir = "/var/lib/powerhouse/member-photos"
        os.makedirs(photo_dir, exist_ok=True)

        # Crop face from frame if bbox provided
        if face_bbox is not None and len(face_bbox) == 4:
            x, y, w, h = [int(v) for v in face_bbox]
            padding = int(min(w, h) * 0.3)
            x1 = max(0, x - padding)
            y1 = max(0, y - padding)
            x2 = min(frame.shape[1], x + w + padding)
            y2 = min(frame.shape[0], y + h + padding)
            face_crop = frame[y1:y2, x1:x2]
        else:
            face_crop = frame

        photo_path = os.path.join(photo_dir, f"{member_id}.jpg")
        cv2.imwrite(photo_path, face_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        logger.info(f"Saved member photo: {photo_path}")
        return photo_path
    except Exception as e:
        logger.error(f"Failed to save member photo: {e}")
        return None


class CVService:
    """Main computer vision service."""

    def __init__(self):
        """Initialize CV service."""
        self.processors: Dict[str, RTSPStreamProcessor] = {}
        self.validator = AccessValidator()
        self.api_client = BackendAPIClient()

        # Store event loop reference for thread-safe coroutine scheduling
        self._event_loop = None  # Set during startup()

        # Event deduplication: {member_id+camera_id: last_event_timestamp}
        self._recent_events: Dict[str, float] = {}
        self._event_cooldown = 30.0  # seconds between events for same member+camera

        # Frames from WebSocket-connected browser cameras (for MJPEG re-stream)
        self._ws_frames: Dict[str, "np.ndarray"] = {}
        self._camera_sync_lock = asyncio.Lock()

        # Configure logging
        logger.remove()
        logger.add(
            sys.stderr,
            level=settings.LOG_LEVEL,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        )

    async def startup(self):
        """Load templates and auto-start cameras from backend."""
        # Capture running event loop (we're inside async context now)
        self._event_loop = asyncio.get_running_loop()
        logger.info("CV Service starting up...")

        # 1. Load templates into Redis cache
        await self._load_templates()

        # 2. Auto-start enabled cameras
        await self._auto_start_cameras()

        # 3. Schedule periodic refresh (every 10 minutes)
        asyncio.create_task(self._periodic_refresh())

    async def _load_templates(self):
        """Load all enrolled member templates from backend into Redis cache."""
        from recognition.template_cache import TemplateCache

        cache = TemplateCache()

        if not cache.ping():
            logger.warning("Redis not available — skipping template sync")
            return

        # Atomic reload: increment version first
        cache.increment_version()

        templates = await self.api_client.sync_templates()

        loaded = 0
        for t in templates:
            import numpy as np

            embedding = np.array(t["embedding"])
            member_data = {
                "name": t["name"],
                "status": t["status"],
                "membership_status": t.get("membership_status"),
                "membership_end_date": t.get("membership_end_date"),
            }

            cache.store_template(t["member_id"], embedding, member_data)
            loaded += 1

        logger.info(
            f"Loaded {loaded} templates into Redis cache (version {cache._version})"
        )

        # Clean old version keys to prevent unbounded Redis growth
        try:
            current_v = cache._version
            for v in range(max(0, current_v - 2), current_v):  # Keep last 2 versions
                pattern = f"member:template:v{v}:*"
                keys = cache._scan_keys(pattern)
                if keys:
                    cache.redis_client.delete(*keys)
                    logger.debug(f"Cleaned {len(keys)} keys from version {v}")
        except Exception as e:
            logger.warning(f"Redis cleanup failed: {e}")

    async def _auto_start_cameras(self, requested_camera_id: Optional[str] = None):
        """Reconcile running processors with enabled backend camera config."""
        async with self._camera_sync_lock:
            await self._reconcile_cameras(requested_camera_id)

    async def _reconcile_cameras(self, requested_camera_id: Optional[str] = None):
        cameras = await self.api_client.get_cameras()
        configured = {cam["id"]: cam for cam in cameras if cam.get("rtsp_url")}

        if requested_camera_id:
            configured = {
                camera_id: cam
                for camera_id, cam in configured.items()
                if camera_id == requested_camera_id
            }
        else:
            for camera_id in set(self.processors) - set(configured):
                self.stop_camera(camera_id)

        started = 0
        for camera_id, cam in configured.items():
            rtsp_url = cam["rtsp_url"]
            fps = cam.get("fps", 5)
            processor = self.processors.get(camera_id)
            if processor and processor.rtsp_url == rtsp_url and processor.fps == fps:
                continue

            try:
                await self.start_camera(
                    camera_id=camera_id,
                    rtsp_url=rtsp_url,
                    fps=fps,
                )
                started += 1
            except Exception as e:
                logger.error(f"Failed to start camera {cam['name']}: {e}")

        logger.info(
            f"Reconciled cameras: started/restarted {started}, "
            f"configured {len(configured)}"
        )

    async def _periodic_refresh(self):
        """Periodically refresh templates and cameras."""
        while True:
            await asyncio.sleep(600)  # Every 10 minutes
            try:
                logger.info("Periodic refresh: reloading templates...")
                await self._load_templates()
                await self._auto_start_cameras()
            except Exception as e:
                logger.error(f"Periodic refresh failed: {e}")

    async def start_camera(self, camera_id: str, rtsp_url: str, fps: int = 5):
        """Start processing camera stream."""
        if camera_id in self.processors:
            logger.warning(f"Camera {camera_id} already running — restarting")
            self.stop_camera(camera_id)

        processor = RTSPStreamProcessor(camera_id, rtsp_url, fps)
        processor.start(on_recognition=self._on_recognition)

        self.processors[camera_id] = processor
        logger.info(f"Started camera {camera_id}")

    def stop_camera(self, camera_id: str):
        """Stop processing camera stream."""
        if camera_id not in self.processors:
            return

        processor = self.processors[camera_id]
        processor.stop()
        del self.processors[camera_id]
        logger.info(f"Stopped camera {camera_id}")

    def _on_recognition(
        self, member_id, confidence, camera_id, frame, face_bbox, member_data
    ):
        """Callback for recognition events (called from sync Thread)."""
        try:
            asyncio.run_coroutine_threadsafe(
                self._process_recognition(
                    member_id, confidence, camera_id, frame, face_bbox, member_data
                ),
                self._event_loop,
            )
        except Exception as e:
            logger.error(f"Error scheduling recognition task: {e}")

    async def _process_recognition(
        self, member_id, confidence, camera_id, frame, face_bbox, member_data
    ):
        """Process recognition result with deduplication."""
        try:
            # Event deduplication: skip if same member+camera seen recently
            event_key = f"{member_id}:{camera_id}"
            now = time.time()
            last_seen = self._recent_events.get(event_key, 0)
            if now - last_seen < self._event_cooldown:
                return  # Skip duplicate event

            self._recent_events[event_key] = now

            # Validate access. days_remaining is only surfaced to the kiosk
            # over the WebSocket path; RTSP events don't render it.
            access_granted, denial_reason, _ = await self.validator.validate_access(
                member_id, confidence, camera_id
            )

            # Save snapshot for denied events
            snapshot_path = None
            if not access_granted and frame is not None:
                try:
                    import os

                    snapshot_dir = "/var/lib/powerhouse/snapshots"
                    os.makedirs(snapshot_dir, exist_ok=True)

                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"denied_{camera_id[:8]}_{timestamp}.jpg"
                    filepath = os.path.join(snapshot_dir, filename)

                    # Validate path to prevent traversal
                    real_dir = os.path.realpath(snapshot_dir)
                    if not os.path.realpath(filepath).startswith(real_dir + os.sep):
                        logger.warning(f"Invalid snapshot path rejected: {filepath}")
                        snapshot_path = None
                    else:
                        cv2.imwrite(
                            filepath, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                        )
                        snapshot_path = filepath
                        logger.info(f"Saved denied access snapshot: {filepath}")
                except Exception as e:
                    logger.error(f"Failed to save snapshot: {e}")

            # Log event to backend
            await self.api_client.create_access_event(
                camera_id=camera_id,
                member_id=member_id,
                confidence_score=confidence,
                access_granted=access_granted,
                denial_reason=denial_reason,
                frame_snapshot_path=snapshot_path,
            )

            # Save member photo on successful recognition
            if access_granted and frame is not None:
                save_member_photo(member_id, frame, face_bbox)

            # Log result
            name = member_data["name"] if member_data else "Unknown"
            if access_granted:
                logger.info(f"ACCESS GRANTED - {name} ({confidence:.2f})")
            else:
                logger.warning(
                    f"ACCESS DENIED - {name} ({denial_reason}, {confidence:.2f})"
                )

        except Exception as e:
            logger.error(f"Error processing recognition: {e}")

    async def shutdown(self):
        """Shutdown service."""
        logger.info("Shutting down CV service...")
        for camera_id in list(self.processors.keys()):
            self.stop_camera(camera_id)
        await self.validator.close()
        await self.api_client.close()
        logger.info("CV service shutdown complete")


# Global Service Instance
_start_time = time.time()
service = CVService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.SERVICE_NAME} API")
    await service.startup()
    yield
    # Shutdown
    await service.shutdown()


app = FastAPI(
    title="PowerHouse CV Service",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,  # Never expose docs — internal service
    redoc_url=None,
    openapi_url=None,  # VULN-4 fix: block OpenAPI spec disclosure
)

# Configure CORS — strict origin allowlist (VULN-011)
_cv_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
# Remove localhost origins in production-like setups when API_KEY is set
if settings.API_KEY:
    _blocked = {"http://localhost", "http://localhost:3000", "http://localhost:8080"}
    _cv_cors_origins = [o for o in _cv_cors_origins if o not in _blocked]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cv_cors_origins if _cv_cors_origins else ["http://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root(_: str = Depends(verify_api_key)):
    return {"status": "running", "cameras": list(service.processors.keys())}


@app.post("/cameras/start")
async def start_camera_endpoint(
    request: StartCameraRequest, _: None = Depends(verify_api_key)
):
    try:
        await service.start_camera(request.camera_id, request.rtsp_url, request.fps)
        return {"status": "started", "camera_id": request.camera_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to start camera: {str(e)}")


@app.post("/cameras/stop")
async def stop_camera_endpoint(
    request: StopCameraRequest, _: None = Depends(verify_api_key)
):
    service.stop_camera(request.camera_id)
    return {"status": "stopped", "camera_id": request.camera_id}


@app.get("/stream/{camera_id}")
async def video_feed(camera_id: str, _: str = Depends(verify_api_key)):
    """MJPEG Video Feed — works for both RTSP and WebSocket-sourced cameras."""
    if camera_id not in service.processors and camera_id not in service._ws_frames:
        await service._auto_start_cameras(camera_id)
        if camera_id not in service.processors:
            raise HTTPException(
                status_code=404, detail="Camera not configured or enabled"
            )

    return StreamingResponse(
        generate_mjpeg(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


async def generate_mjpeg(camera_id: str):
    """Async generator for MJPEG stream."""
    while True:
        frame = None

        # Try RTSP processor first
        processor = service.processors.get(camera_id)
        if processor and processor.is_running:
            frame = processor.get_latest_frame()

        # Fall back to WebSocket-sourced frames
        if frame is None:
            frame = service._ws_frames.get(camera_id)

        if frame is None:
            await asyncio.sleep(0.05)
            continue

        # Encode to JPEG
        ret, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if not ret:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )

        # Limit stream FPS to save bandwidth
        await asyncio.sleep(0.1)


class WsPipelineComponents(NamedTuple):
    """The recognition models a WebSocket connection processes frames with."""

    detector: Any
    quality_assessor: Any
    liveness_detector: Any
    recognizer: Any
    matcher: Any


def build_ws_pipeline_components() -> WsPipelineComponents:
    """Load the recognition models for one WebSocket connection."""
    from detection.face_detector import FaceDetector
    from detection.quality_assessor import FaceQualityAssessor
    from detection.liveness_detector import liveness_detector
    from recognition.face_recognizer import FaceRecognizer
    from recognition.template_matcher import TemplateMatcher

    return WsPipelineComponents(
        detector=FaceDetector(),
        quality_assessor=FaceQualityAssessor(),
        liveness_detector=liveness_detector,
        recognizer=FaceRecognizer(),
        matcher=TemplateMatcher(),
    )


async def process_ws_frame(
    frame: "np.ndarray",
    camera_id: str,
    components: WsPipelineComponents,
    frame_count: int,
    fps: Optional[float],
) -> Optional[Dict]:
    """
    Run the recognition pipeline over a single browser-pushed frame.

    Mirrors RTSPStreamProcessor._process_frame. Returns the message to send
    back to the kiosk, or None when the frame yielded nothing worth reporting
    (too blurry to trust, or a suspected spoof).
    """
    # Detect faces with landmarks for alignment
    faces_with_lm = components.detector.detect_faces_with_landmarks(frame)
    if not faces_with_lm:
        return {
            "type": "status",
            "fps": fps,
            "frames_processed": frame_count,
            "faces": 0,
        }

    # Process largest face only (sort by area)
    faces_with_lm.sort(key=lambda f: f[0][2] * f[0][3], reverse=True)
    largest_face, largest_landmarks = faces_with_lm[0]

    # Align face using eye landmarks (matches enrollment pipeline)
    face_roi = components.detector.align_face(frame, largest_face, largest_landmarks)

    # Quality check
    quality_score, _ = components.quality_assessor.assess_quality(face_roi)
    if quality_score < 0.5:
        return None

    # Liveness check (anti-spoofing)
    is_live, liveness_details = components.liveness_detector.check_liveness(
        frame, face_roi, largest_face
    )
    if not is_live:
        logger.warning(f"Spoof detected via WS camera {camera_id}: {liveness_details}")
        return None

    # Generate embedding and match
    embedding = components.recognizer.generate_embedding(face_roi)
    member_id, confidence, member_data = components.matcher.find_match(embedding)

    # Validate access
    access_granted, denial_reason, days_remaining = (
        await service.validator.validate_access(member_id, confidence, camera_id)
    )

    # Event deduplication (same logic as _process_recognition)
    event_key = f"{member_id}:{camera_id}"
    now = time.time()
    last_seen = service._recent_events.get(event_key, 0)
    is_duplicate = (now - last_seen) < service._event_cooldown

    if not is_duplicate:
        service._recent_events[event_key] = now

        # Save snapshot for denied events
        snapshot_path = None
        if not access_granted:
            try:
                import os

                snapshot_dir = "/var/lib/powerhouse/snapshots"
                os.makedirs(snapshot_dir, exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"denied_{camera_id[:8]}_{timestamp}.jpg"
                filepath = os.path.join(snapshot_dir, filename)

                # Validate path to prevent traversal
                real_dir = os.path.realpath(snapshot_dir)
                if not os.path.realpath(filepath).startswith(real_dir + os.sep):
                    logger.warning(f"Invalid snapshot path rejected: {filepath}")
                else:
                    cv2.imwrite(filepath, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    snapshot_path = filepath
            except Exception as e:
                logger.error(f"Failed to save snapshot: {e}")

        # Log to backend
        await service.api_client.create_access_event(
            camera_id=camera_id,
            member_id=member_id,
            confidence_score=confidence,
            access_granted=access_granted,
            denial_reason=denial_reason,
            frame_snapshot_path=snapshot_path,
        )

    # Save member photo on successful recognition
    if access_granted and not is_duplicate:
        save_member_photo(member_id, frame, largest_face)

    name = member_data["name"] if member_data else "Unknown"
    bbox = (
        [
            int(largest_face[0]),
            int(largest_face[1]),
            int(largest_face[2]),
            int(largest_face[3]),
        ]
        if largest_face
        else None
    )

    return {
        "type": "recognition",
        "member_id": member_id,
        "member_name": name,
        "confidence": round(confidence, 3),
        "access_granted": access_granted,
        "denial_reason": denial_reason,
        "face_bbox": bbox,
        "membership_end_date": (
            member_data.get("membership_end_date") if member_data else None
        ),
        "days_remaining": days_remaining,
    }


@app.websocket("/ws/camera/{camera_id}")
async def websocket_camera_feed(websocket: WebSocket, camera_id: str):
    """
    WebSocket endpoint for browser-pushed camera frames.

    Note: WebSocket auth uses query parameter ?api_key=... when API_KEY is set.
    Connection is rejected if key doesn't match.
    """
    # Validate API key via query parameter for WebSocket (headers not available)
    if settings.API_KEY:
        api_key = websocket.query_params.get("api_key")
        if api_key != settings.API_KEY:
            await websocket.close(code=4001, reason="Invalid API key")
            return

    await websocket.accept()
    logger.info(f"WebSocket connected for camera {camera_id}")

    components = build_ws_pipeline_components()

    frame_count = 0
    last_process_time = 0.0
    min_frame_interval = 0.2  # 5fps max processing

    try:
        while True:
            # Receive JPEG frame as binary
            data = await websocket.receive_bytes()

            current_time = time.time()

            # Skip if processing too fast
            if current_time - last_process_time < min_frame_interval:
                continue

            # Real elapsed time since the last PROCESSED frame. Unknown on the
            # first frame, which has no predecessor to measure against.
            fps = (
                round(1.0 / (current_time - last_process_time), 1)
                if last_process_time
                else None
            )
            last_process_time = current_time
            frame_count += 1

            # Decode JPEG
            nparr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is None:
                continue

            # Store frame so MJPEG /stream endpoint can serve it remotely.
            # Deliberately before recognition: the remote view keeps working
            # even when the recognition pipeline is failing.
            service._ws_frames[camera_id] = frame

            try:
                payload = await process_ws_frame(
                    frame, camera_id, components, frame_count, fps
                )
            except Exception as e:
                # One bad frame — or a transient recognition/backend fault —
                # must never take the connection down. The kiosk renders a
                # dropped WebSocket as "Camera unavailable", so escalating a
                # frame error to a disconnect misreports a software fault as a
                # broken camera. Log it and let the next frame try again.
                logger.exception(
                    f"Frame {frame_count} failed for camera {camera_id}: {e}"
                )
                continue

            if payload is not None:
                await websocket.send_json(payload)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for camera {camera_id}")
    except Exception as e:
        logger.error(f"WebSocket error for camera {camera_id}: {e}")
    finally:
        service._ws_frames.pop(camera_id, None)
        logger.info(f"WebSocket cleanup for camera {camera_id}")


@app.post("/reload")
async def reload_templates(_: None = Depends(verify_api_key)):
    """Manually trigger template reload from backend."""
    await service._load_templates()
    return {"status": "ok", "message": "Templates reloaded"}


@app.post("/invalidate/{member_id}")
async def invalidate_member(member_id: str, _: None = Depends(verify_api_key)):
    """Invalidate specific member template (called by backend on member update/deactivation)."""
    from recognition.template_cache import TemplateCache

    cache = TemplateCache()
    cache.remove_template(member_id)
    logger.info(f"Invalidated template for member {member_id}")
    return {"status": "ok", "member_id": member_id}


@app.get("/health")
async def health_check(_: str = Depends(verify_api_key)):
    """Comprehensive health check with camera status and metrics."""
    from recognition.template_cache import TemplateCache

    cameras_health = {}
    for cam_id, processor in service.processors.items():
        cameras_health[cam_id] = processor.get_health()

    # Get template count from cache
    cache = TemplateCache()
    template_count = 0
    try:
        if cache.ping():
            template_count = len(cache.get_all_active_templates())
    except Exception as e:
        logger.debug(f"Template cache ping failed: {e}")
        pass

    return {
        "status": "healthy",
        "version": settings.SERVICE_VERSION,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "cameras": {"total": len(service.processors), "details": cameras_health},
        "templates_cached": template_count,
        "recent_events_tracked": len(service._recent_events),
    }


if __name__ == "__main__":
    import uvicorn

    try:
        uvicorn.run(app, host="0.0.0.0", port=8001)
    except KeyboardInterrupt:
        pass

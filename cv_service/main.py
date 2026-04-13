"""
Main CV service application with Streaming API.
"""
import asyncio
import sys
import time
import cv2
import io
from typing import Dict, Optional
from loguru import logger
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from stream.rtsp_processor import RTSPStreamProcessor
from validation.access_validator import AccessValidator
from api.backend_client import BackendAPIClient

# Models
class StartCameraRequest(BaseModel):
    camera_id: str
    rtsp_url: str
    fps: int = 5

class StopCameraRequest(BaseModel):
    camera_id: str

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
        
        # Configure logging
        logger.remove()
        logger.add(
            sys.stderr,
            level=settings.LOG_LEVEL,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
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
        
        templates = await self.api_client.sync_templates()
        
        loaded = 0
        for t in templates:
            import numpy as np
            
            embedding = np.array(t["embedding"])
            member_data = {
                "name": t["name"],
                "status": t["status"],
                "membership_status": t.get("membership_status")
            }
            
            cache.store_template(t["member_id"], embedding, member_data)
            loaded += 1
        
        logger.info(f"Loaded {loaded} templates into Redis cache")
    
    async def _auto_start_cameras(self):
        """Auto-start all enabled cameras from backend."""
        cameras = await self.api_client.get_cameras()
        
        started = 0
        for cam in cameras:
            rtsp_url = cam.get("rtsp_url")
            if not rtsp_url:
                logger.warning(f"Camera {cam['name']} has no RTSP URL — skipping")
                continue
            
            try:
                await self.start_camera(
                    camera_id=cam["id"],
                    rtsp_url=rtsp_url,
                    fps=cam.get("fps", 5)
                )
                started += 1
            except Exception as e:
                logger.error(f"Failed to start camera {cam['name']}: {e}")
        
        logger.info(f"Auto-started {started}/{len(cameras)} cameras")
    
    async def _periodic_refresh(self):
        """Periodically refresh templates and cameras."""
        while True:
            await asyncio.sleep(600)  # Every 10 minutes
            try:
                logger.info("Periodic refresh: reloading templates...")
                await self._load_templates()
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
    
    def _on_recognition(self, member_id, confidence, camera_id, frame, face_bbox, member_data):
        """Callback for recognition events (called from sync Thread)."""
        try:
            asyncio.run_coroutine_threadsafe(
                self._process_recognition(member_id, confidence, camera_id, frame, face_bbox, member_data),
                self._event_loop
            )
        except Exception as e:
            logger.error(f"Error scheduling recognition task: {e}")
    
    async def _process_recognition(self, member_id, confidence, camera_id, frame, face_bbox, member_data):
        """Process recognition result with deduplication."""
        try:
            # Event deduplication: skip if same member+camera seen recently
            event_key = f"{member_id}:{camera_id}"
            now = time.time()
            last_seen = self._recent_events.get(event_key, 0)
            if now - last_seen < self._event_cooldown:
                return  # Skip duplicate event
            
            self._recent_events[event_key] = now
            
            # Validate access
            access_granted, denial_reason = await self.validator.validate_access(
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
                    
                    cv2.imwrite(filepath, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
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
                frame_snapshot_path=snapshot_path
            )
            
            # Log result
            name = member_data['name'] if member_data else 'Unknown'
            if access_granted:
                logger.info(f"ACCESS GRANTED - {name} ({confidence:.2f})")
            else:
                logger.warning(f"ACCESS DENIED - {name} ({denial_reason}, {confidence:.2f})")
        
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
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "running", "cameras": list(service.processors.keys())}

@app.post("/cameras/start")
async def start_camera_endpoint(request: StartCameraRequest):
    await service.start_camera(request.camera_id, request.rtsp_url, request.fps)
    return {"status": "started", "camera_id": request.camera_id}

@app.post("/cameras/stop")
async def stop_camera_endpoint(request: StopCameraRequest):
    service.stop_camera(request.camera_id)
    return {"status": "stopped", "camera_id": request.camera_id}

@app.get("/stream/{camera_id}")
def video_feed(camera_id: str):
    """MJPEG Video Feed."""
    if camera_id not in service.processors:
        raise HTTPException(status_code=404, detail="Camera not running")
    
    return StreamingResponse(
        generate_mjpeg(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

async def generate_mjpeg(camera_id: str):
    """Async generator for MJPEG stream."""
    processor = service.processors.get(camera_id)
    if not processor:
        return

    while True:
        if not processor.is_running:
            break
        
        frame = processor.get_latest_frame()
        if frame is None:
            await asyncio.sleep(0.05)
            continue
        
        # Encode to JPEG
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if not ret:
            continue
            
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        
        # Limit stream FPS to save bandwidth
        await asyncio.sleep(0.1)

@app.post("/reload")
async def reload_templates():
    """Manually trigger template reload from backend."""
    await service._load_templates()
    return {"status": "ok", "message": "Templates reloaded"}

if __name__ == "__main__":
    import uvicorn
    try:
        uvicorn.run(app, host="0.0.0.0", port=8001)
    except KeyboardInterrupt:
        pass

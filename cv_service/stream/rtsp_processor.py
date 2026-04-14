"""
RTSP stream processor for real-time face recognition.
"""
import cv2
import numpy as np
import time
from typing import Optional, Callable, Dict, Any
from loguru import logger
from threading import Thread, Event, Lock

from detection.face_detector import FaceDetector
from detection.quality_assessor import FaceQualityAssessor
from detection.liveness_detector import liveness_detector
from recognition.face_recognizer import FaceRecognizer
from recognition.template_matcher import TemplateMatcher
from config import settings


class RTSPStreamProcessor:
    """Process RTSP camera streams for face recognition."""
    
    def __init__(self, camera_id: str, rtsp_url: str, fps: int = 5):
        """
        Initialize RTSP stream processor.
        
        Args:
            camera_id: Camera UUID
            rtsp_url: RTSP stream URL
            fps: Target frames per second to process
        """
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.fps = fps
        self.frame_interval = 1.0 / fps
        
        # Components
        self.detector = FaceDetector()
        self.quality_assessor = FaceQualityAssessor()
        self.recognizer = FaceRecognizer()
        self.matcher = TemplateMatcher()
        self.liveness = liveness_detector
        
        # Stream state
        self.capture: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.stop_event = Event()
        self.thread: Optional[Thread] = None
        self.frame_lock = Lock()
        self.latest_frame: Optional[np.ndarray] = None
        
        # Callbacks
        self.on_recognition: Optional[Callable] = None
        
        # Health monitoring
        self.last_frame_time: float = 0
        self.total_frames_processed: int = 0
        self.total_faces_detected: int = 0
        self.last_error: Optional[str] = None
        self.connected: bool = False
        
        # Frame dropping: track processing time
        self._processing: bool = False
        self._frames_dropped: int = 0
    
    def start(self, on_recognition: Callable):
        """
        Start processing stream.
        
        Args:
            on_recognition: Callback function(member_id, confidence, camera_id, frame)
        """
        if self.is_running:
            logger.warning(f"Stream already running for camera {self.camera_id}")
            return
        
        self.on_recognition = on_recognition
        self.is_running = True
        self.stop_event.clear()
        
        # Start processing thread
        self.thread = Thread(target=self._process_stream, daemon=True)
        self.thread.start()
        
        logger.info(f"Started stream processing for camera {self.camera_id}")
    
    def stop(self):
        """Stop processing stream."""
        if not self.is_running:
            return
        
        self.is_running = False
        self.connected = False
        self.stop_event.set()
        
        if self.thread:
            self.thread.join(timeout=5)
        
        if self.capture:
            self.capture.release()
        
        logger.info(f"Stopped stream processing for camera {self.camera_id}")

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Get latest frame (thread-safe)."""
        with self.frame_lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()
    
    def _connect_stream(self) -> bool:
        """
        Connect to RTSP stream.
        
        Returns:
            True if connected, False otherwise
        """
        try:
            # Support both RTSP URLs and V4L2 device paths
            if self.rtsp_url.startswith("/dev/video"):
                device_index = int(self.rtsp_url.replace("/dev/video", ""))
                self.capture = cv2.VideoCapture(device_index)
                logger.info(f"Opening V4L2 device: {self.rtsp_url} (index {device_index})")
            else:
                self.capture = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, settings.FRAME_BUFFER_SIZE)
            
            if not self.capture.isOpened():
                logger.error(f"Failed to open stream: {self.rtsp_url}")
                self.connected = False
                self.last_error = f"Failed to open stream: {self.rtsp_url}"
                return False
            
            logger.info(f"Connected to stream: {self.camera_id}")
            self.connected = True
            return True
        
        except Exception as e:
            logger.error(f"Error connecting to stream: {e}")
            self.connected = False
            self.last_error = str(e)
            return False
    
    def _process_stream(self):
        """Main stream processing loop."""
        reconnect_attempts = 0
        
        while self.is_running and not self.stop_event.is_set():
            # Connect to stream
            if not self._connect_stream():
                reconnect_attempts += 1
                
                if reconnect_attempts >= settings.MAX_RECONNECT_ATTEMPTS:
                    logger.error(f"Max reconnect attempts reached for camera {self.camera_id}")
                    self.last_error = "Max reconnect attempts reached"
                    break
                
                logger.warning(f"Reconnecting in {settings.RECONNECT_DELAY}s...")
                time.sleep(settings.RECONNECT_DELAY)
                continue
            
            # Reset reconnect counter
            reconnect_attempts = 0
            
            # Process frames
            last_frame_time = 0
            
            while self.is_running and not self.stop_event.is_set():
                current_time = time.time()
                
                # Throttle frame rate
                if current_time - last_frame_time < self.frame_interval:
                    time.sleep(0.01)
                    continue
                
                # Read frame
                ret, frame = self.capture.read()
                
                if not ret:
                    logger.warning(f"Failed to read frame from camera {self.camera_id}")
                    self.last_error = "Failed to read frame"
                    break  # Reconnect
                
                last_frame_time = current_time
                self.last_frame_time = current_time
                
                # Process frame
                with self.frame_lock:
                    self.latest_frame = frame.copy()
                
                # Drop frame if previous frame still processing
                if self._processing:
                    self._frames_dropped += 1
                    continue  # Drop frame
                
                self._processing = True
                self._process_frame(frame)
                self.total_frames_processed += 1
                self._processing = False
            
            # Release capture before reconnecting
            if self.capture:
                self.capture.release()
    
    def _process_frame(self, frame: np.ndarray):
        """
        Process a single frame for face recognition.
        
        Args:
            frame: Frame from camera
        """
        try:
            # Detect faces
            faces = self.detector.detect_faces(frame)
            
            if faces:
                self.total_faces_detected += 1
            else:
                return  # No faces detected
            
            # Process largest face only
            largest_face = self.detector.get_largest_face(faces)
            if not largest_face:
                return
            
            # Extract face ROI
            face_roi = self.detector.extract_face_roi(frame, largest_face)
            
            # Assess quality
            quality_score, metrics = self.quality_assessor.assess_quality(face_roi)
            
            # Skip low quality faces
            if quality_score < 0.5:
                return
            

            # Anti-spoofing: liveness check
            is_live, liveness_details = self.liveness.check_liveness(frame, face_roi, largest_face)
            if not is_live:
                logger.warning(f"Spoof detected for camera {self.camera_id}: {liveness_details}")
                return  # Skip potential spoof
            
            # Generate embedding
            embedding = self.recognizer.generate_embedding(face_roi)
            
            # Match against templates
            member_id, confidence, member_data = self.matcher.find_match(embedding)
            
            # Trigger callback
            if self.on_recognition:
                self.on_recognition(
                    member_id=member_id,
                    confidence=confidence,
                    camera_id=self.camera_id,
                    frame=frame,
                    face_bbox=largest_face,
                    member_data=member_data
                )
        
        except Exception as e:
            logger.error(f"Error processing frame: {e}")

    def get_health(self) -> Dict[str, Any]:
        """Get stream health status."""
        now = time.time()
        frame_age = now - self.last_frame_time if self.last_frame_time > 0 else None
        
        return {
            "camera_id": self.camera_id,
            "is_running": self.is_running,
            "connected": self.connected,
            "last_frame_seconds_ago": round(frame_age, 1) if frame_age else None,
            "frozen": frame_age is not None and frame_age > 10,  # No frame for 10s = frozen
            "total_frames": self.total_frames_processed,
            "total_faces": self.total_faces_detected,
            "last_error": self.last_error,
            "fps_target": self.fps,
            "frames_dropped": self._frames_dropped,
        }

"""
RTSP stream processor for real-time face recognition.
"""
import cv2
import numpy as np
import time
from typing import Optional, Callable
from loguru import logger
from threading import Thread, Event, Lock

from detection.face_detector import FaceDetector
from detection.quality_assessor import FaceQualityAssessor
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
        
        # Stream state
        self.capture: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.stop_event = Event()
        self.thread: Optional[Thread] = None
        self.frame_lock = Lock()
        self.latest_frame: Optional[np.ndarray] = None
        
        # Callbacks
        self.on_recognition: Optional[Callable] = None
    
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
            self.capture = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, settings.FRAME_BUFFER_SIZE)
            
            if not self.capture.isOpened():
                logger.error(f"Failed to open stream: {self.rtsp_url}")
                return False
            
            logger.info(f"Connected to stream: {self.camera_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error connecting to stream: {e}")
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
                    break  # Reconnect
                
                last_frame_time = current_time
                
                # Process frame
                with self.frame_lock:
                    self.latest_frame = frame.copy()
                
                self._process_frame(frame)
            
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
            
            if not faces:
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

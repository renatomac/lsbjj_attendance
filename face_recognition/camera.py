import cv2
import numpy as np
import face_recognition
import logging
from django.conf import settings
import time
import os

logger = logging.getLogger(__name__)

class CameraManager:
    """Handle camera operations for Raspberry Pi"""
    
    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.camera = None
        self.is_raspberry_pi = self._detect_raspberry_pi()
        
    def _detect_raspberry_pi(self):
        """Detect if running on Raspberry Pi"""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                return 'Raspberry Pi' in f.read()
        except:
            return False
    
    def initialize_camera(self):
        """Initialize the camera"""
        if self.is_raspberry_pi:
            try:
                from picamera2 import Picamera2
                self.camera = Picamera2()
                config = self.camera.create_preview_configuration(
                    main={"size": (640, 480)}
                )
                self.camera.configure(config)
                self.camera.start()
                logger.info("Raspberry Pi camera initialized")
                return True
            except ImportError:
                logger.warning("Picamera2 not available, falling back to OpenCV")
                self.is_raspberry_pi = False
        
        # Fallback to OpenCV
        self.camera = cv2.VideoCapture(self.camera_index)
        if not self.camera.isOpened():
            logger.error("Failed to open camera")
            return False
        
        # Set resolution
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        logger.info("OpenCV camera initialized")
        return True
    
    def capture_frame(self):
        """Capture a single frame"""
        if self.camera is None:
            if not self.initialize_camera():
                return None
        
        try:
            if self.is_raspberry_pi:
                # Picamera2 capture
                frame = self.camera.capture_array()
                return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            else:
                # OpenCV capture
                ret, frame = self.camera.read()
                if ret:
                    return frame
                return None
        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            return None
    
    def capture_multiple_frames(self, count=5, delay=1):
        """Capture multiple frames with delay"""
        frames = []
        for i in range(count):
            logger.info(f"Capturing frame {i+1}/{count}")
            frame = self.capture_frame()
            if frame is not None:
                frames.append(frame)
            time.sleep(delay)
        return frames
    
    def release(self):
        """Release camera resources"""
        if self.camera:
            if self.is_raspberry_pi:
                self.camera.stop()
            else:
                self.camera.release()
            self.camera = None
    
    def generate_frames(self):
        """Generator for video streaming"""
        while True:
            frame = self.capture_frame()
            if frame is None:
                continue
            
            # Add overlay text
            cv2.putText(frame, "BJJ Gym Check-in", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, "Press button to check in", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Encode frame
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            time.sleep(0.03)  # ~30 FPS


class FaceRecognizer:
    """Handle face recognition operations"""
    
    def __init__(self):
        self.camera = CameraManager()
        self.known_face_encodings = []
        self.known_face_member_ids = []
        self.threshold = settings.FACE_RECOGNITION_THRESHOLD
        
    def load_known_faces(self):
        """Load all registered faces from database"""
        from attendance_app.models import LocalMember
        
        self.known_face_encodings = []
        self.known_face_member_ids = []
        
        members = LocalMember.objects.filter(face_registered=True)
        for member in members:
            encoding = member.load_face_encoding()
            if encoding is not None:
                self.known_face_encodings.append(encoding)
                self.known_face_member_ids.append(member.id)
        
        logger.info(f"Loaded {len(self.known_face_encodings)} known faces")
    
    def register_face(self, member_id, num_photos=5):
        """Register face for a member"""
        from attendance_app.models import LocalMember, FaceTrainingLog
        
        member = LocalMember.objects.get(id=member_id)
        log = FaceTrainingLog.objects.create(member=member, photos_attempted=num_photos)
        
        face_encodings = []
        
        # Capture multiple photos
        frames = self.camera.capture_multiple_frames(count=num_photos, delay=1)
        
        for frame in frames:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Find faces
            face_locations = face_recognition.face_locations(rgb_frame)
            
            if len(face_locations) == 1:
                # Get encoding
                encoding = face_recognition.face_encodings(rgb_frame, face_locations)
                if encoding:
                    face_encodings.append(encoding[0])
                    logger.info(f"Captured valid face encoding")
            else:
                logger.warning(f"Expected 1 face, found {len(face_locations)}")
        
        log.photos_successful = len(face_encodings)
        
        if len(face_encodings) >= settings.MIN_FACE_PHOTOS:
            # Average the encodings
            avg_encoding = np.mean(face_encodings, axis=0)
            
            # Save to member
            member.save_face_encoding(avg_encoding)
            member.face_photos_count = len(face_encodings)
            member.save()
            
            # Reload known faces
            self.load_known_faces()
            
            log.success = True
            log.save()
            
            return True, len(face_encodings)
        else:
            log.success = False
            log.error_message = f"Only {len(face_encodings)} good photos captured"
            log.save()
            
            return False, len(face_encodings)
    
    def recognize_face(self, frame=None):
        """Recognize face from frame"""
        if frame is None:
            frame = self.camera.capture_frame()
        
        if frame is None:
            return None, 0, "Failed to capture image"
        
        # Convert to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Find faces
        face_locations = face_recognition.face_locations(rgb_frame)
        
        if len(face_locations) == 0:
            return None, 0, "No face detected"
        
        if len(face_locations) > 1:
            return None, 0, f"Multiple faces detected ({len(face_locations)})"
        
        # Get face encoding
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        
        if not face_encodings:
            return None, 0, "Could not encode face"
        
        face_encoding = face_encodings[0]
        
        # Compare with known faces
        if len(self.known_face_encodings) == 0:
            return None, 0, "No registered faces in system"
        
        matches = face_recognition.compare_faces(
            self.known_face_encodings,
            face_encoding,
            tolerance=self.threshold
        )
        
        face_distances = face_recognition.face_distance(
            self.known_face_encodings,
            face_encoding
        )
        
        if True in matches:
            best_match_index = np.argmin(face_distances)
            member_id = self.known_face_member_ids[best_match_index]
            confidence = 1 - face_distances[best_match_index]
            
            return member_id, confidence, "Success"
        else:
            return None, 0, "No match found"
    
    def __del__(self):
        """Cleanup camera on deletion"""
        self.camera.release()
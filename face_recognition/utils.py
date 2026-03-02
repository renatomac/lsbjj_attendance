import cv2
import numpy as np
import os
from datetime import datetime

def check_camera_health(camera_id=0):
    """
    Check if camera is accessible and working
    Returns: (is_healthy: bool, message: str, details: dict)
    """
    try:
        # Try to open camera
        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            return False, "Camera could not be opened", {"camera_id": camera_id}
        
        # Try to read a frame
        ret, frame = cap.read()
        cap.release()
        
        if ret and frame is not None:
            return True, "Camera is working properly", {
                "camera_id": camera_id,
                "frame_shape": frame.shape,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return False, "Camera opened but could not read frame", {"camera_id": camera_id}
            
    except Exception as e:
        return False, f"Camera error: {str(e)}", {"camera_id": camera_id, "error": str(e)}

def load_face_encoding(filepath):
    """Load face encoding from numpy file"""
    try:
        if os.path.exists(filepath):
            return np.load(filepath)
        return None
    except Exception as e:
        print(f"Error loading face encoding: {e}")
        return None

def save_face_encoding(encoding, filepath):
    """Save face encoding to numpy file"""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        np.save(filepath, encoding)
        return True
    except Exception as e:
        print(f"Error saving face encoding: {e}")
        return False

def compare_faces(known_encoding, face_encoding, threshold=0.6):
    """
    Compare two face encodings
    Returns: (is_match: bool, distance: float)
    """
    if known_encoding is None or face_encoding is None:
        return False, 1.0
    
    # Calculate Euclidean distance
    distance = np.linalg.norm(known_encoding - face_encoding)
    return distance < threshold, distance

def get_available_cameras(max_cameras=5):
    """Check which camera indices are available"""
    available = []
    for i in range(max_cameras):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available.append(i)
            cap.release()
    return available

def preprocess_face_image(image):
    """Preprocess face image for recognition"""
    if image is None:
        return None
    
    # Convert to RGB if needed
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
    elif image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    return image

def resize_image(image, max_size=800):
    """Resize image while maintaining aspect ratio"""
    h, w = image.shape[:2]
    
    if max(h, w) > max_size:
        scale = max_size / max(h, w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        return cv2.resize(image, (new_w, new_h))
    return image

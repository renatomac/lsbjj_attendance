import cv2
import numpy as np
import os
import json
from datetime import datetime, timedelta, date
from django.utils import timezone
from django.core.files.storage import default_storage
from django.conf import settings
import base64
from io import BytesIO
from PIL import Image
import logging

logger = logging.getLogger(__name__)

# ==================== FACE RECOGNITION UTILS ====================

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

def get_face_encoding(image):
    """
    Extract face encoding from image
    Placeholder - replace with actual face recognition library
    """
    try:
        # This is a placeholder. You'll need to implement with actual face recognition
        # For example with face_recognition library:
        # import face_recognition
        # face_encodings = face_recognition.face_encodings(image)
        # return face_encodings[0] if face_encodings else None
        
        # Placeholder return
        logger.warning("get_face_encoding using placeholder - implement with actual face recognition")
        return np.random.rand(128)  # Random placeholder encoding
    except Exception as e:
        logger.error(f"Error getting face encoding: {e}")
        return None

def compare_faces(known_encoding, unknown_encoding, threshold=0.6):
    """
    Compare two face encodings
    Returns: (is_match: bool, distance: float)
    """
    if known_encoding is None or unknown_encoding is None:
        return False, 1.0
    
    # Calculate Euclidean distance
    distance = np.linalg.norm(known_encoding - unknown_encoding)
    return distance < threshold, distance

def load_face_encoding(filepath):
    """Load face encoding from numpy file"""
    try:
        full_path = os.path.join(settings.MEDIA_ROOT, filepath) if not os.path.isabs(filepath) else filepath
        if os.path.exists(full_path):
            return np.load(full_path)
        return None
    except Exception as e:
        logger.error(f"Error loading face encoding: {e}")
        return None

def save_face_encoding(encoding, filepath):
    """Save face encoding to numpy file"""
    try:
        full_path = os.path.join(settings.MEDIA_ROOT, filepath) if not os.path.isabs(filepath) else filepath
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        np.save(full_path, encoding)
        return True
    except Exception as e:
        logger.error(f"Error saving face encoding: {e}")
        return False

# ==================== IMAGE PROCESSING UTILS ====================

def base64_to_image(base64_string):
    """Convert base64 string to numpy array image"""
    try:
        # Remove data URL prefix if present
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        
        # Decode base64
        image_data = base64.b64decode(base64_string)
        image = Image.open(BytesIO(image_data))
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    except Exception as e:
        logger.error(f"Error converting base64 to image: {e}")
        return None

def image_to_base64(image, format='.jpg'):
    """Convert numpy array image to base64 string"""
    try:
        if format == '.jpg' or format == '.jpeg':
            success, buffer = cv2.imencode('.jpg', image)
        else:
            success, buffer = cv2.imencode('.png', image)
        
        if not success:
            return None
        
        image_base64 = base64.b64encode(buffer).decode('utf-8')
        return f"data:image/{format[1:]};base64,{image_base64}"
    except Exception as e:
        logger.error(f"Error converting image to base64: {e}")
        return None

def resize_image(image, max_size=800):
    """Resize image while maintaining aspect ratio"""
    try:
        h, w = image.shape[:2]
        
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)
            return cv2.resize(image, (new_w, new_h))
        return image
    except Exception as e:
        logger.error(f"Error resizing image: {e}")
        return image

# ==================== DATE/TIME UTILS ====================

def get_date_range(period='week'):
    """
    Get start and end dates for various periods
    period: 'day', 'week', 'month', 'year', 'all'
    """
    today = date.today()
    
    if period == 'day':
        start_date = today
        end_date = today
    elif period == 'week':
        start_date = today - timedelta(days=7)
        end_date = today
    elif period == 'month':
        start_date = today - timedelta(days=30)
        end_date = today
    elif period == 'year':
        start_date = today - timedelta(days=365)
        end_date = today
    else:  # 'all' or any other
        start_date = date(2000, 1, 1)
        end_date = today
    
    return start_date, end_date

def format_datetime(dt, format='%Y-%m-%d %H:%M:%S'):
    """Format datetime object"""
    if dt:
        return dt.strftime(format)
    return ''

# ==================== DATA PROCESSING UTILS ====================

def calculate_attendance_stats(queryset):
    """Calculate attendance statistics from a queryset"""
    total = queryset.count()
    if total == 0:
        return {
            'total': 0,
            'unique_members': 0,
            'by_method': {},
            'by_date': {}
        }
    
    unique_members = queryset.values('member').distinct().count()
    
    # Attendance by method
    by_method = {}
    for method in queryset.values_list('check_in_method', flat=True).distinct():
        by_method[method] = queryset.filter(check_in_method=method).count()
    
    return {
        'total': total,
        'unique_members': unique_members,
        'by_method': by_method,
        'average_daily': total / 30 if total > 30 else total  # Simple average
    }

def paginate_queryset(queryset, page, page_size=20):
    """Simple pagination helper"""
    start = (page - 1) * page_size
    end = start + page_size
    
    total = queryset.count()
    items = queryset[start:end]
    
    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size,
        'has_previous': page > 1,
        'has_next': end < total
    }

# ==================== FILE UTILS ====================

def ensure_dir(path):
    """Ensure directory exists"""
    os.makedirs(path, exist_ok=True)
    return path

def get_file_size(filepath):
    """Get file size in human readable format"""
    try:
        size_bytes = os.path.getsize(filepath)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    except Exception:
        return "Unknown"

def clean_old_files(directory, days=30):
    """Delete files older than specified days"""
    try:
        cutoff = timezone.now() - timedelta(days=days)
        count = 0
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                if mtime < cutoff:
                    os.remove(filepath)
                    count += 1
        return count
    except Exception as e:
        logger.error(f"Error cleaning old files: {e}")
        return 0

# ==================== VALIDATION UTILS ====================

def validate_image_file(file):
    """Validate if file is a valid image"""
    try:
        # Check file extension
        ext = os.path.splitext(file.name)[1].lower()
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
        if ext not in valid_extensions:
            return False, f"Invalid file extension. Must be one of: {', '.join(valid_extensions)}"
        
        # Try to open as image
        Image.open(file).verify()
        return True, "Valid image file"
    except Exception as e:
        return False, f"Invalid image file: {str(e)}"

def validate_phone_number(phone):
    """Simple phone number validation"""
    import re
    pattern = re.compile(r'^[\d\s\+\-\(\)]{10,}$')
    return bool(pattern.match(phone))

def validate_email(email):
    """Simple email validation"""
    import re
    pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    return bool(pattern.match(email))


def get_system_health():
    """
    Get overall system health status
    Returns: dict with system health information
    """
    import psutil
    import platform
    from datetime import datetime
    from django.conf import settings
    import os
    
    health_data = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'checks': {},
        'warnings': [],
        'errors': []
    }
    
    try:
        # Check disk usage
        disk_usage = psutil.disk_usage('/')
        disk_percent = disk_usage.percent
        disk_free_gb = disk_usage.free / (1024 * 1024 * 1024)
        health_data['checks']['disk_usage'] = {
            'status': 'warning' if disk_percent > 90 else 'healthy',
            'value': f"{disk_percent:.1f}%",
            'free': f"{disk_free_gb:.2f} GB",
            'message': f"Disk usage: {disk_percent:.1f}% ({disk_free_gb:.2f} GB free)"
        }
        if disk_percent > 90:
            health_data['warnings'].append(f"High disk usage: {disk_percent:.1f}%")
        elif disk_percent > 80:
            health_data['warnings'].append(f"Moderate disk usage: {disk_percent:.1f}%")
        
        # Check memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_available_gb = memory.available / (1024 * 1024 * 1024)
        health_data['checks']['memory_usage'] = {
            'status': 'warning' if memory_percent > 90 else 'healthy',
            'value': f"{memory_percent:.1f}%",
            'available': f"{memory_available_gb:.2f} GB",
            'message': f"Memory usage: {memory_percent:.1f}% ({memory_available_gb:.2f} GB available)"
        }
        if memory_percent > 90:
            health_data['warnings'].append(f"High memory usage: {memory_percent:.1f}%")
        
        # Check CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        health_data['checks']['cpu_usage'] = {
            'status': 'warning' if cpu_percent > 90 else 'healthy',
            'value': f"{cpu_percent:.1f}%",
            'cores': cpu_count,
            'message': f"CPU usage: {cpu_percent:.1f}% across {cpu_count} cores"
        }
        if cpu_percent > 90:
            health_data['warnings'].append(f"High CPU usage: {cpu_percent:.1f}%")
        
        # Check camera
        try:
            camera_healthy, camera_msg, camera_details = check_camera_health(0)
            health_data['checks']['camera'] = {
                'status': 'healthy' if camera_healthy else 'error',
                'message': camera_msg,
                'details': camera_details
            }
            if not camera_healthy:
                health_data['errors'].append(f"Camera issue: {camera_msg}")
        except Exception as e:
            health_data['checks']['camera'] = {
                'status': 'error',
                'message': f"Camera check failed: {str(e)}"
            }
            health_data['errors'].append(f"Camera check failed: {str(e)}")
        
        # Check database connection (with error handling)
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            
            health_data['checks']['database'] = {
                'status': 'healthy',
                'message': 'Database connection OK'
            }
        except Exception as e:
            health_data['checks']['database'] = {
                'status': 'error',
                'message': f"Database error: {str(e)}"
            }
            health_data['errors'].append(f"Database error: {str(e)}")
        
        # Check face recognition directories
        media_dir = settings.MEDIA_ROOT if hasattr(settings, 'MEDIA_ROOT') else 'media'
        faces_dir = os.path.join(media_dir, 'faces')
        checkin_dir = os.path.join(media_dir, 'checkin_photos')
        
        dirs_status = []
        for dir_path in [faces_dir, checkin_dir]:
            if os.path.exists(dir_path):
                try:
                    file_count = len([f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))])
                    dirs_status.append(f"{os.path.basename(dir_path)}: {file_count} files")
                except:
                    dirs_status.append(f"{os.path.basename(dir_path)}: error reading")
            else:
                dirs_status.append(f"{os.path.basename(dir_path)}: directory missing")
        
        health_data['checks']['storage_dirs'] = {
            'status': 'healthy',
            'message': ', '.join(dirs_status)
        }
        
        # Check network connectivity
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            health_data['checks']['network'] = {
                'status': 'healthy',
                'message': 'Internet connection available'
            }
        except OSError:
            health_data['checks']['network'] = {
                'status': 'warning',
                'message': 'No internet connection'
            }
            health_data['warnings'].append('No internet connection - sync may fail')
        except Exception as e:
            health_data['checks']['network'] = {
                'status': 'error',
                'message': f"Network check failed: {str(e)}"
            }
        
        # System info
        try:
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            days = uptime.days
            hours = uptime.seconds // 3600
            minutes = (uptime.seconds // 60) % 60
            
            health_data['system_info'] = {
                'platform': platform.platform(),
                'processor': platform.processor(),
                'python_version': platform.python_version(),
                'hostname': platform.node(),
                'boot_time': boot_time.isoformat(),
                'uptime': f"{days} days, {hours} hours, {minutes} minutes"
            }
        except Exception as e:
            health_data['system_info'] = {
                'error': f"Could not get system info: {str(e)}"
            }
        
        # Overall status
        if health_data['errors']:
            health_data['status'] = 'error'
        elif health_data['warnings']:
            health_data['status'] = 'warning'
        else:
            health_data['status'] = 'healthy'
        
    except Exception as e:
        health_data['status'] = 'error'
        health_data['errors'].append(f"Health check error: {str(e)}")
        import traceback
        health_data['traceback'] = traceback.format_exc()
    
    return health_data

def create_backup(backup_type='manual'):
    """
    Create a database backup
    Args:
        backup_type: 'manual', 'auto', or 'pre_sync'
    Returns:
        dict: Backup result with status, filename, and details
    """
    import os
    import json
    from datetime import datetime
    from django.core import serializers
    from django.conf import settings
    from .models import LocalMember, LocalAttendance, SyncLog, FaceTrainingLog, SystemStatus, OfflineQueue, Notification
    
    result = {
        'success': False,
        'filename': None,
        'size_bytes': 0,
        'records_count': 0,
        'error_message': '',
        'backup_type': backup_type,
        'timestamp': datetime.now().isoformat()
    }
    
    try:
        # Create backup directory if it doesn't exist
        backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"backup_{backup_type}_{timestamp}.json"
        filepath = os.path.join(backup_dir, filename)
        
        # Collect all model data
        backup_data = {
            'version': '1.0',
            'created_at': datetime.now().isoformat(),
            'backup_type': backup_type,
            'data': {}
        }
        
        # Define models to backup in order (respecting foreign keys)
        models_to_backup = [
            ('LocalMember', LocalMember),
            ('LocalAttendance', LocalAttendance),
            ('SyncLog', SyncLog),
            ('FaceTrainingLog', FaceTrainingLog),
            ('SystemStatus', SystemStatus),
            ('OfflineQueue', OfflineQueue),
            ('Notification', Notification),
        ]
        
        total_records = 0
        
        for model_name, model_class in models_to_backup:
            queryset = model_class.objects.all()
            count = queryset.count()
            total_records += count
            
            # Serialize to JSON
            data = serializers.serialize('json', queryset)
            backup_data['data'][model_name] = {
                'count': count,
                'records': json.loads(data)
            }
            
            print(f"Backed up {count} {model_name} records")
        
        # Write to file
        with open(filepath, 'w') as f:
            json.dump(backup_data, f, indent=2, default=str)
        
        # Get file size
        file_size = os.path.getsize(filepath)
        
        # Update result
        result['success'] = True
        result['filename'] = filename
        result['filepath'] = filepath
        result['size_bytes'] = file_size
        result['records_count'] = total_records
        result['size_mb'] = file_size / (1024 * 1024)
        
        # Save to BackupLog if the model exists
        try:
            from .models import BackupLog
            BackupLog.objects.create(
                backup_type=backup_type,
                filename=filename,
                size_bytes=file_size,
                records_count=total_records,
                status='success'
            )
        except (ImportError, Exception) as e:
            # BackupLog model might not exist or have different fields
            print(f"Could not save to BackupLog: {e}")
        
    except Exception as e:
        result['error_message'] = str(e)
        import traceback
        result['traceback'] = traceback.format_exc()
        print(f"Backup error: {e}")
    
    return result


def restore_from_backup(backup_filename):
    """
    Restore database from a backup file
    Args:
        backup_filename: Name of the backup file in the backups directory
    Returns:
        dict: Restore result with status and details
    """
    import os
    import json
    from django.core import serializers
    from django.conf import settings
    from django.db import transaction
    
    result = {
        'success': False,
        'message': '',
        'records_restored': 0,
        'errors': []
    }
    
    try:
        backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
        filepath = os.path.join(backup_dir, backup_filename)
        
        if not os.path.exists(filepath):
            result['message'] = f"Backup file not found: {backup_filename}"
            return result
        
        # Read backup file
        with open(filepath, 'r') as f:
            backup_data = json.load(f)
        
        # Start transaction for atomic restore
        with transaction.atomic():
            total_restored = 0
            
            # Define model order for restoration (reverse of backup order to handle FKs)
            model_order = [
                'Notification',
                'OfflineQueue',
                'SystemStatus',
                'FaceTrainingLog',
                'SyncLog',
                'LocalAttendance',
                'LocalMember',
            ]
            
            for model_name in model_order:
                if model_name in backup_data['data']:
                    model_info = backup_data['data'][model_name]
                    records = model_info['records']
                    
                    if records:
                        # Deserialize and save
                        for deserialized_object in serializers.deserialize('json', json.dumps(records)):
                            deserialized_object.save()
                            total_restored += 1
                        
                        print(f"Restored {model_info['count']} {model_name} records")
            
            result['success'] = True
            result['message'] = f"Successfully restored {total_restored} records"
            result['records_restored'] = total_restored
            result['backup_info'] = {
                'version': backup_data.get('version'),
                'created_at': backup_data.get('created_at'),
                'backup_type': backup_data.get('backup_type')
            }
        
    except Exception as e:
        result['message'] = f"Restore error: {str(e)}"
        result['errors'].append(str(e))
        import traceback
        result['traceback'] = traceback.format_exc()
    
    return result


def list_backups():
    """
    List all available backups
    Returns:
        list: List of backup files with metadata
    """
    import os
    from datetime import datetime
    from django.conf import settings
    
    backups = []
    
    try:
        backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
        
        if not os.path.exists(backup_dir):
            return backups
        
        for filename in os.listdir(backup_dir):
            if filename.endswith('.json') and filename.startswith('backup_'):
                filepath = os.path.join(backup_dir, filename)
                stat = os.stat(filepath)
                
                # Try to read backup metadata
                backup_info = {
                    'filename': filename,
                    'size_bytes': stat.st_size,
                    'size_mb': stat.st_size / (1024 * 1024),
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'created': datetime.fromtimestamp(stat.st_ctime).isoformat()
                }
                
                # Try to read the first few KB to get metadata
                try:
                    with open(filepath, 'r') as f:
                        first_lines = f.read(4096)  # Read first 4KB
                        import json
                        # Find the first complete JSON object
                        if first_lines.strip().startswith('{'):
                            # Try to parse partial JSON
                            import re
                            match = re.search(r'\{.*?"backup_type":\s*"([^"]+)".*?"created_at":\s*"([^"]+)"', first_lines, re.DOTALL)
                            if match:
                                backup_info['backup_type'] = match.group(1)
                                backup_info['created_at'] = match.group(2)
                except:
                    pass
                
                backups.append(backup_info)
        
        # Sort by modified date, newest first
        backups.sort(key=lambda x: x['modified'], reverse=True)
        
    except Exception as e:
        print(f"Error listing backups: {e}")
    
    return backups


def cleanup_old_backups(keep_days=30):
    """
    Delete backups older than specified days
    Args:
        keep_days: Number of days to keep backups
    Returns:
        int: Number of backups deleted
    """
    import os
    from datetime import datetime, timedelta
    from django.conf import settings
    
    deleted_count = 0
    
    try:
        backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
        
        if not os.path.exists(backup_dir):
            return 0
        
        cutoff_date = datetime.now() - timedelta(days=keep_days)
        
        for filename in os.listdir(backup_dir):
            if filename.endswith('.json') and filename.startswith('backup_'):
                filepath = os.path.join(backup_dir, filename)
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                if mtime < cutoff_date:
                    os.remove(filepath)
                    deleted_count += 1
                    print(f"Deleted old backup: {filename}")
        
    except Exception as e:
        print(f"Error cleaning up backups: {e}")
    
    return deleted_count

def restore_backup(backup_file):
    """
    Restore database from a backup file
    This is an alias for restore_from_backup to match the import in views.py
    Args:
        backup_file: Backup filename or file object
    Returns:
        dict: Restore result with status and details
    """
    import os
    import json
    from django.core import serializers
    from django.conf import settings
    from django.db import transaction
    
    result = {
        'success': False,
        'message': '',
        'records_restored': 0,
        'errors': []
    }
    
    try:
        # Handle different input types
        if hasattr(backup_file, 'name'):
            # It's a file upload object
            filename = backup_file.name
            content = backup_file.read()
            data = json.loads(content)
            result['restore_type'] = 'upload'
        else:
            # It's a filename string
            backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
            filepath = os.path.join(backup_dir, backup_file)
            
            if not os.path.exists(filepath):
                result['message'] = f"Backup file not found: {backup_file}"
                return result
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            filename = backup_file
            result['restore_type'] = 'file'
        
        # Validate backup data
        if 'data' not in data:
            result['message'] = "Invalid backup file: missing 'data' field"
            return result
        
        # Start transaction for atomic restore
        with transaction.atomic():
            total_restored = 0
            
            # Define model order for restoration (reverse of backup order to handle FKs)
            model_order = [
                'Notification',
                'OfflineQueue',
                'SystemStatus',
                'FaceTrainingLog',
                'SyncLog',
                'LocalAttendance',
                'LocalMember',
            ]
            
            for model_name in model_order:
                if model_name in data['data']:
                    model_info = data['data'][model_name]
                    records = model_info.get('records', [])
                    
                    if records:
                        # Deserialize and save
                        for deserialized_object in serializers.deserialize('json', json.dumps(records)):
                            deserialized_object.save()
                            total_restored += 1
                        
                        print(f"Restored {model_info.get('count', len(records))} {model_name} records")
            
            result['success'] = True
            result['message'] = f"Successfully restored {total_restored} records from {filename}"
            result['records_restored'] = total_restored
            result['backup_info'] = {
                'version': data.get('version', 'unknown'),
                'created_at': data.get('created_at', 'unknown'),
                'backup_type': data.get('backup_type', 'unknown'),
                'filename': filename
            }
        
    except json.JSONDecodeError as e:
        result['message'] = f"Invalid JSON in backup file: {str(e)}"
        result['errors'].append(str(e))
    except Exception as e:
        result['message'] = f"Restore error: {str(e)}"
        result['errors'].append(str(e))
        import traceback
        result['traceback'] = traceback.format_exc()
    
    return result

def restore_backup(backup_file):
    """
    Restore database from a backup file
    This is an alias for restore_from_backup to match the import in views.py
    """
    # If backup_file is a string, pass it directly
    if isinstance(backup_file, str):
        return restore_from_backup(backup_file)
    
    # If it's a file upload, save it temporarily then restore
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as tmp_file:
        for chunk in backup_file.chunks():
            tmp_file.write(chunk)
        tmp_path = tmp_file.name
    
    try:
        result = restore_from_backup(os.path.basename(tmp_path))
        # Add info about the uploaded file
        result['uploaded_file'] = backup_file.name
        return result
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
            
def generate_attendance_report(start_date=None, end_date=None, member_id=None, report_type='summary'):
    """
    Generate attendance report based on specified parameters
    
    Args:
        start_date: Start date for report (default: 30 days ago)
        end_date: End date for report (default: today)
        member_id: Filter by specific member (optional)
        report_type: 'summary', 'detailed', 'member', 'daily', 'monthly'
    
    Returns:
        dict: Report data
    """
    from datetime import datetime, timedelta, date
    from django.db.models import Count, Q, Avg, Min, Max
    from django.utils import timezone
    from .models import LocalAttendance, LocalMember
    
    # Set default dates if not provided
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    # Convert to date objects if they're strings
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Base queryset
    queryset = LocalAttendance.objects.filter(
        session_date__gte=start_date,
        session_date__lte=end_date
    )
    
    # Filter by member if specified
    if member_id:
        queryset = queryset.filter(member_id=member_id)
        member = LocalMember.objects.get(id=member_id)
        member_name = member.full_name
    else:
        member_name = None
    
    report_data = {
        'generated_at': datetime.now().isoformat(),
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        },
        'filters': {
            'member_id': member_id,
            'member_name': member_name
        },
        'report_type': report_type,
        'summary': {},
        'data': []
    }
    
    # Summary statistics
    total_attendances = queryset.count()
    unique_members = queryset.values('member').distinct().count()
    
    # Attendance by method
    method_stats = queryset.values('check_in_method').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Daily attendance trend
    daily_trend = queryset.values('session_date').annotate(
        count=Count('id')
    ).order_by('session_date')
    
    # Most active members
    top_members = queryset.values(
        'member__id', 'member__first_name', 'member__last_name'
    ).annotate(
        attendance_count=Count('id')
    ).order_by('-attendance_count')[:10]
    
    report_data['summary'] = {
        'total_attendances': total_attendances,
        'unique_members': unique_members,
        'average_daily': round(total_attendances / max((end_date - start_date).days, 1), 1),
        'by_method': {item['check_in_method']: item['count'] for item in method_stats},
        'daily_trend': list(daily_trend),
        'top_members': [
            {
                'id': item['member__id'],
                'name': f"{item['member__first_name']} {item['member__last_name']}",
                'count': item['attendance_count']
            }
            for item in top_members
        ]
    }
    
    # Generate different report types
    if report_type == 'detailed':
        # Detailed attendance records
        attendances = queryset.select_related('member').order_by('-session_date', '-check_in_time')[:500]
        report_data['data'] = [
            {
                'id': att.id,
                'member_id': att.member.id,
                'member_name': att.member.full_name,
                'session_date': att.session_date.isoformat(),
                'check_in_time': att.check_in_time.isoformat(),
                'check_in_method': att.check_in_method,
                'synced': att.synced
            }
            for att in attendances
        ]
    
    elif report_type == 'member' and member_id:
        # Member-specific detailed report
        attendances = queryset.select_related('member').order_by('-session_date')
        report_data['data'] = [
            {
                'id': att.id,
                'session_date': att.session_date.isoformat(),
                'check_in_time': att.check_in_time.isoformat(),
                'check_in_method': att.check_in_method,
                'synced': att.synced
            }
            for att in attendances
        ]
        
        # Add member stats
        report_data['member_stats'] = {
            'total': total_attendances,
            'first_attendance': attendances.aggregate(Min('session_date'))['session_date__min'],
            'last_attendance': attendances.aggregate(Max('session_date'))['session_date__max'],
            'by_method': {item['check_in_method']: item['count'] for item in method_stats}
        }
    
    elif report_type == 'monthly':
        # Monthly aggregation
        from django.db.models.functions import TruncMonth
        monthly = queryset.annotate(
            month=TruncMonth('session_date')
        ).values('month').annotate(
            count=Count('id'),
            unique_members=Count('member', distinct=True)
        ).order_by('month')
        
        report_data['monthly_data'] = list(monthly)
    
    return report_data


def export_attendance_report_csv(report_data):
    """
    Export attendance report as CSV data
    
    Args:
        report_data: Report data from generate_attendance_report
    
    Returns:
        str: CSV formatted string
    """
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Attendance Report'])
    writer.writerow([f"Generated: {report_data['generated_at']}"])
    writer.writerow([f"Date Range: {report_data['date_range']['start']} to {report_data['date_range']['end']}"])
    writer.writerow([])
    
    # Write summary
    writer.writerow(['SUMMARY STATISTICS'])
    writer.writerow(['Total Attendances', report_data['summary']['total_attendances']])
    writer.writerow(['Unique Members', report_data['summary']['unique_members']])
    writer.writerow(['Average Daily', report_data['summary']['average_daily']])
    writer.writerow([])
    
    # Write by method
    writer.writerow(['ATTENDANCE BY METHOD'])
    for method, count in report_data['summary']['by_method'].items():
        writer.writerow([method, count])
    writer.writerow([])
    
    # Write top members
    writer.writerow(['TOP MEMBERS'])
    writer.writerow(['Member', 'Attendance Count'])
    for member in report_data['summary']['top_members']:
        writer.writerow([member['name'], member['count']])
    writer.writerow([])
    
    # Write detailed data if available
    if report_data.get('data'):
        writer.writerow(['DETAILED ATTENDANCE RECORDS'])
        if 'member_name' in report_data['data'][0]:
            writer.writerow(['Date', 'Time', 'Method', 'Synced'])
            for record in report_data['data']:
                writer.writerow([
                    record['session_date'],
                    record['check_in_time'].split('T')[1][:8] if 'T' in record['check_in_time'] else record['check_in_time'],
                    record['check_in_method'],
                    'Yes' if record['synced'] else 'No'
                ])
        else:
            writer.writerow(['Member', 'Date', 'Time', 'Method', 'Synced'])
            for record in report_data['data']:
                writer.writerow([
                    record['member_name'],
                    record['session_date'],
                    record['check_in_time'].split('T')[1][:8] if 'T' in record['check_in_time'] else record['check_in_time'],
                    record['check_in_method'],
                    'Yes' if record['synced'] else 'No'
                ])
    
    return output.getvalue()


def generate_attendance_chart_data(report_data, chart_type='daily'):
    """
    Generate chart data for attendance visualizations
    
    Args:
        report_data: Report data from generate_attendance_report
        chart_type: 'daily', 'method', 'members', 'trend'
    
    Returns:
        dict: Chart.js compatible data
    """
    chart_data = {
        'type': chart_type,
        'labels': [],
        'datasets': []
    }
    
    if chart_type == 'daily' and 'daily_trend' in report_data['summary']:
        daily_data = report_data['summary']['daily_trend']
        chart_data['labels'] = [item['session_date'] for item in daily_data]
        chart_data['datasets'] = [
            {
                'label': 'Daily Attendance',
                'data': [item['count'] for item in daily_data],
                'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                'borderColor': 'rgba(54, 162, 235, 1)',
                'borderWidth': 1
            }
        ]
    
    elif chart_type == 'method' and 'by_method' in report_data['summary']:
        method_data = report_data['summary']['by_method']
        chart_data['labels'] = list(method_data.keys())
        chart_data['datasets'] = [
            {
                'label': 'Attendance by Method',
                'data': list(method_data.values()),
                'backgroundColor': [
                    'rgba(255, 99, 132, 0.2)',
                    'rgba(54, 162, 235, 0.2)',
                    'rgba(255, 206, 86, 0.2)',
                    'rgba(75, 192, 192, 0.2)',
                    'rgba(153, 102, 255, 0.2)',
                ],
                'borderColor': [
                    'rgba(255, 99, 132, 1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 206, 86, 1)',
                    'rgba(75, 192, 192, 1)',
                    'rgba(153, 102, 255, 1)',
                ],
                'borderWidth': 1
            }
        ]
    
    elif chart_type == 'members' and 'top_members' in report_data['summary']:
        members_data = report_data['summary']['top_members']
        chart_data['labels'] = [m['name'] for m in members_data]
        chart_data['datasets'] = [
            {
                'label': 'Top Members by Attendance',
                'data': [m['count'] for m in members_data],
                'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                'borderColor': 'rgba(75, 192, 192, 1)',
                'borderWidth': 1
            }
        ]
    
    return chart_data


def export_to_csv(queryset, model_name=None, fields=None, filename=None):
    """
    Export any queryset to CSV format
    
    Args:
        queryset: Django queryset to export
        model_name: Name of the model (for header)
        fields: List of fields to include (default: all fields)
        filename: Custom filename (optional)
    
    Returns:
        dict: Dictionary containing CSV data and metadata
    """
    import csv
    from io import StringIO
    from datetime import datetime
    
    if queryset is None or not queryset.exists():
        return {
            'success': False,
            'error': 'No data to export',
            'csv_data': None
        }
    
    # Determine model name if not provided
    if not model_name:
        model_name = queryset.model.__name__
    
    # Get all field names if not specified
    if not fields:
        # Get all field names from the model
        fields = [field.name for field in queryset.model._meta.fields]
        # Add any reverse relations or properties you might want
        if hasattr(queryset.model, 'export_fields'):
            fields = queryset.model.export_fields
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([f"{model_name} Export"])
    writer.writerow([f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([f"Records: {queryset.count()}"])
    writer.writerow([])  # Empty line
    
    # Write column headers
    writer.writerow([field.replace('_', ' ').title() for field in fields])
    
    # Write data rows
    for obj in queryset:
        row = []
        for field in fields:
            try:
                # Handle different field types
                if hasattr(obj, f'get_{field}_display'):
                    # For choice fields
                    value = getattr(obj, f'get_{field}_display')()
                elif hasattr(obj, field):
                    value = getattr(obj, field)
                    # Handle special types
                    if hasattr(value, 'strftime'):
                        # Datetime objects
                        value = value.strftime('%Y-%m-%d %H:%M:%S')
                    elif hasattr(value, 'all'):
                        # Many-to-many relationships
                        value = ', '.join(str(item) for item in value.all()[:5])
                        if value.count(',') >= 5:
                            value += '...'
                    elif hasattr(value, 'get'):
                        # Dictionary-like objects
                        value = str(value)
                else:
                    value = ''
                
                row.append(str(value) if value is not None else '')
            except Exception as e:
                row.append(f'[Error: {e}]')
        
        writer.writerow(row)
    
    # Generate filename if not provided
    if not filename:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{model_name.lower()}_export_{timestamp}.csv"
    
    return {
        'success': True,
        'model_name': model_name,
        'record_count': queryset.count(),
        'fields': fields,
        'filename': filename,
        'csv_data': output.getvalue(),
        'generated_at': datetime.now().isoformat()
    }


def export_attendance_to_csv(queryset=None, start_date=None, end_date=None):
    """
    Export attendance records to CSV with specific formatting
    
    Args:
        queryset: Optional attendance queryset
        start_date: Optional start date filter
        end_date: Optional end date filter
    
    Returns:
        dict: CSV export data
    """
    from .models import LocalAttendance
    from datetime import date, timedelta
    
    # Get queryset if not provided
    if queryset is None:
        queryset = LocalAttendance.objects.all()
        
        # Apply date filters if provided
        if start_date:
            if isinstance(start_date, str):
                from datetime import datetime
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            queryset = queryset.filter(session_date__gte=start_date)
        
        if end_date:
            if isinstance(end_date, str):
                from datetime import datetime
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            queryset = queryset.filter(session_date__lte=end_date)
    
    # Define fields for attendance export
    fields = [
        'id',
        'member',
        'session_date',
        'check_in_time',
        'check_in_method',
        'confidence_score',
        'synced',
        'sync_error',
        'notes'
    ]
    
    return export_to_csv(
        queryset=queryset.select_related('member'),
        model_name='Attendance',
        fields=fields,
        filename=f"attendance_export_{date.today().isoformat()}.csv"
    )


def export_members_to_csv(queryset=None, active_only=True):
    """
    Export member records to CSV
    
    Args:
        queryset: Optional member queryset
        active_only: Only export active members
    
    Returns:
        dict: CSV export data
    """
    from .models import LocalMember
    from datetime import date
    
    # Get queryset if not provided
    if queryset is None:
        queryset = LocalMember.objects.all()
        if active_only:
            queryset = queryset.filter(is_active=True)
    
    # Define fields for member export
    fields = [
        'id',
        'remote_id',
        'first_name',
        'last_name',
        'email',
        'phone',
        'member_type',
        'date_of_birth',
        'belt_rank',
        'stripes',
        'is_active',
        'face_registered',
        'face_photos_count',
        'created_at',
        'last_sync',
        'notes'
    ]
    
    return export_to_csv(
        queryset=queryset,
        model_name='Members',
        fields=fields,
        filename=f"members_export_{date.today().isoformat()}.csv"
    )


def export_sync_logs_to_csv(queryset=None, days=30):
    """
    Export sync logs to CSV
    
    Args:
        queryset: Optional sync log queryset
        days: Number of days to include
    
    Returns:
        dict: CSV export data
    """
    from .models import SyncLog
    from datetime import date, timedelta
    
    # Get queryset if not provided
    if queryset is None:
        start_date = date.today() - timedelta(days=days)
        queryset = SyncLog.objects.filter(start_time__date__gte=start_date)
    
    # Define fields for sync log export
    fields = [
        'sync_type',
        'status',
        'start_time',
        'end_time',
        'duration',
        'records_processed',
        'records_succeeded',
        'records_failed',
        'error_message',
        'triggered_by'
    ]
    
    return export_to_csv(
        queryset=queryset.select_related('triggered_by'),
        model_name='SyncLogs',
        fields=fields,
        filename=f"sync_logs_export_{date.today().isoformat()}.csv"
    )


def export_face_training_logs_to_csv(queryset=None, days=30):
    """
    Export face training logs to CSV
    
    Args:
        queryset: Optional face training log queryset
        days: Number of days to include
    
    Returns:
        dict: CSV export data
    """
    from .models import FaceTrainingLog
    from datetime import date, timedelta
    
    # Get queryset if not provided
    if queryset is None:
        start_date = date.today() - timedelta(days=days)
        queryset = FaceTrainingLog.objects.filter(started_at__date__gte=start_date)
    
    # Define fields for face training export
    fields = [
        'member',
        'photos_attempted',
        'photos_successful',
        'success',
        'started_at',
        'completed_at',
        'error_message',
        'trained_by'
    ]
    
    return export_to_csv(
        queryset=queryset.select_related('member', 'trained_by'),
        model_name='FaceTraining',
        fields=fields,
        filename=f"face_training_export_{date.today().isoformat()}.csv"
    )


def export_system_status_to_csv():
    """
    Export system status to CSV
    
    Returns:
        dict: CSV export data
    """
    from .models import SystemStatus
    from datetime import date
    
    queryset = SystemStatus.objects.all()
    
    fields = [
        'status_type',
        'key',
        'value',
        'is_healthy',
        'last_check',
        'message'
    ]
    
    return export_to_csv(
        queryset=queryset,
        model_name='SystemStatus',
        fields=fields,
        filename=f"system_status_export_{date.today().isoformat()}.csv"
    )


def export_offline_queue_to_csv(queryset=None, include_processed=False):
    """
    Export offline queue items to CSV
    
    Args:
        queryset: Optional offline queue queryset
        include_processed: Include processed items
    
    Returns:
        dict: CSV export data
    """
    from .models import OfflineQueue
    from datetime import date
    
    # Get queryset if not provided
    if queryset is None:
        queryset = OfflineQueue.objects.all()
        if not include_processed:
            queryset = queryset.filter(processed=False)
    
    fields = [
        'action_type',
        'priority',
        'data',
        'created_at',
        'processed',
        'processed_at',
        'error',
        'retry_count'
    ]
    
    return export_to_csv(
        queryset=queryset,
        model_name='OfflineQueue',
        fields=fields,
        filename=f"offline_queue_export_{date.today().isoformat()}.csv"
    )
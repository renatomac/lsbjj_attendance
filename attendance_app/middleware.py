"""
Custom middleware for attendance_app
"""

import logging
from django.utils import timezone
from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
import socket

logger = logging.getLogger(__name__)


class OnlineStatusMiddleware:
    """
    Middleware to check online/offline status and add it to request
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Check if we're online by trying to connect to a reliable host
        request.is_online = self.check_online_status()
        
        # Add online status to session for persistence across requests
        if hasattr(request, 'session'):
            request.session['is_online'] = request.is_online
        
        response = self.get_response(request)
        return response
    
    def check_online_status(self):
        """Check if we have internet connectivity"""
        try:
            # Try to connect to Google DNS
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            try:
                # Fallback to checking if we can reach the local network
                socket.create_connection(("192.168.1.1", 80), timeout=2)
                return True
            except OSError:
                return False


class AttendanceMiddleware:
    """
    Middleware for attendance tracking
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Add request timing
        request.start_time = timezone.now()
        
        # Process the request
        response = self.get_response(request)
        
        # Add duration header if in debug mode
        if settings.DEBUG and hasattr(request, 'start_time'):
            duration = (timezone.now() - request.start_time).total_seconds()
            response['X-Request-Duration'] = str(duration)
        
        return response


class LoginRequiredMiddleware:
    """
    Middleware to require login for all views except whitelisted ones
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # URLs that don't require login
        self.public_paths = [
            '/login/',
            '/admin/login/',
            '/static/',
            '/media/',
            '/accounts/login/',
            '/api/health/',
            '/api/status/',
        ]
        
    def __call__(self, request):
        # Skip middleware for non-html requests (like API)
        if request.path.startswith('/api/'):
            return self.get_response(request)
        
        # Check if user is authenticated for protected paths
        if not request.user.is_authenticated:
            # Check if the requested path is public
            path = request.path_info
            is_public = any(path.startswith(public_path) for public_path in self.public_paths)
            
            if not is_public and path != '/':
                # Redirect to login page
                login_url = reverse('login')
                return redirect(f"{login_url}?next={path}")
        
        response = self.get_response(request)
        return response


class OfflineModeMiddleware:
    """
    Middleware to handle offline mode functionality
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Get offline status from session or online status
        session_offline = request.session.get('offline_mode', False)
        is_online = getattr(request, 'is_online', True)
        
        # Determine if we should be in offline mode
        if session_offline or not is_online:
            request.offline_mode = True
            # Add header to response
            response = self.get_response(request)
            response['X-Offline-Mode'] = 'true'
        else:
            request.offline_mode = False
            response = self.get_response(request)
        
        return response


class APILoggingMiddleware:
    """
    Middleware to log API requests for debugging
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Log API requests
        if request.path.startswith('/api/'):
            logger.info(f"API Request: {request.method} {request.path}")
            
            # Log request body for POST/PUT in debug mode
            if settings.DEBUG and request.method in ['POST', 'PUT'] and request.body:
                try:
                    body = request.body.decode('utf-8')
                    if len(body) < 1000:  # Don't log huge bodies
                        logger.debug(f"Request body: {body}")
                except:
                    pass
        
        response = self.get_response(request)
        
        # Log API responses in debug mode
        if settings.DEBUG and request.path.startswith('/api/'):
            logger.info(f"API Response: {response.status_code}")
        
        return response


class CameraMiddleware:
    """
    Middleware to handle camera access across requests
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.camera_initialized = False
        
    def __call__(self, request):
        # Initialize camera only when needed
        camera_paths = ['/camera/', '/face/', '/attendance/face-checkin/']
        
        if any(request.path.startswith(path) for path in camera_paths):
            if not self.camera_initialized:
                try:
                    from face_recognition.camera import get_camera
                    camera = get_camera()
                    self.camera_initialized = True
                    request.camera_available = True
                    logger.info("Camera initialized successfully")
                except Exception as e:
                    logger.error(f"Failed to initialize camera: {e}")
                    request.camera_available = False
            else:
                request.camera_available = True
        else:
            request.camera_available = False
        
        response = self.get_response(request)
        return response


class SyncStatusMiddleware:
    """
    Middleware to track sync status and add it to responses
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        response = self.get_response(request)
        
        # Add sync status header for API responses
        if request.path.startswith('/api/'):
            try:
                from attendance_app.models import OfflineQueue
                pending_sync = OfflineQueue.objects.filter(processed=False).count()
                response['X-Pending-Sync'] = str(pending_sync)
            except:
                pass
        
        return response
    
class SystemHealthMiddleware:
    """
    Middleware to monitor system health and add health status to responses
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        response = self.get_response(request)
        
        # Add health headers for monitoring endpoints
        if request.path.startswith('/health') or request.path.startswith('/api/health'):
            try:
                from .utils import get_system_health
                health_data = get_system_health()
                
                # Add health status as headers
                response['X-System-Health'] = health_data.get('status', 'unknown')
                response['X-System-Checks'] = str(len(health_data.get('checks', {})))
                
                # If there are errors, add them as headers (truncated for header length limits)
                if health_data.get('errors'):
                    errors = ','.join(health_data['errors'][:3])
                    if errors:
                        response['X-System-Errors'] = errors[:200]  # Header length limit
                
                # Store health data in request for views to use
                request.system_health = health_data
                
            except Exception as e:
                logger.error(f"Error in SystemHealthMiddleware: {e}")
                request.system_health = {'status': 'error', 'errors': [str(e)]}
        
        return response
    
    def process_exception(self, request, exception):
        """Handle exceptions and log them"""
        logger.error(f"Unhandled exception in request to {request.path}: {exception}")
        
        # You could add custom error handling here
        if request.path.startswith('/api/'):
            # For API requests, we might want to return a JSON error response
            from django.http import JsonResponse
            return JsonResponse({
                'error': 'Internal server error',
                'detail': str(exception) if settings.DEBUG else None
            }, status=500)
        
        return None  # Let Django handle it normally
    
class SystemHealthMiddleware:
    """
    Middleware to monitor system health and add health status to responses
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        response = self.get_response(request)
        
        # Add health headers for monitoring endpoints
        if request.path.startswith('/health') or request.path.startswith('/api/health'):
            try:
                # Import here to avoid circular imports
                from .utils import get_system_health
                health_data = get_system_health()
                
                # Add health status as headers
                response['X-System-Health'] = health_data.get('status', 'unknown')
                
                # Store health data in request for views to use
                request.system_health = health_data
                
            except Exception as e:
                # Log the error but don't break the response
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error in SystemHealthMiddleware: {e}")
                request.system_health = {'status': 'error', 'errors': [str(e)]}
        
        return response
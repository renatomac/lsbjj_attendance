from django.core.cache import cache
from django.utils import timezone


def system_status(request):
    """Provide basic system status values for templates with safe fallbacks."""
    online_status = True
    pending_sync = 0
    last_sync = None

    # Try to get values from cache or models, but fail gracefully
    try:
        online_status = cache.get('online_status', True)
    except Exception:
        online_status = True

    try:
        from .models import LocalAttendance, SyncLog

        pending_sync = LocalAttendance.objects.filter(synced=False).count()
        last_sync = SyncLog.objects.filter(status='success').first()
    except Exception:
        pending_sync = 0
        last_sync = None

    return {
        'online_status': online_status,
        'pending_sync': pending_sync,
        'last_sync': last_sync,
        'system_health': {},
    }


def notifications(request):
    """Provide notifications and unread count for templates with safe fallbacks."""
    try:
        from .models import Notification
        from django.db.models import Q

        notifications_qs = Notification.objects.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        ).order_by('-created_at')[:5]
        unread_count = Notification.objects.filter(read=False).count()
    except Exception:
        notifications_qs = []
        unread_count = 0

    return {
        'notifications': notifications_qs,
        'unread_notifications': unread_count,
    }
    
def custom_context(request):
    """
    Add custom context variables to all templates
    """
    # Make sure request is not None and has session attribute
    if hasattr(request, 'session'):
        dark_mode = request.session.get('dark_mode', False)
    else:
        dark_mode = False
    
    context = {
        'dark_mode': dark_mode,
        'start_time': timezone.now(),
    }
    return context

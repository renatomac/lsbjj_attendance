from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from django.utils import timezone
from django.db.models import Count, Q, Sum, Avg
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from datetime import date, timedelta, datetime
import json
import logging
import os
import csv
from io import StringIO

from .models import (
    LocalMember, LocalAttendance, SyncLog, 
    FaceTrainingLog, SystemStatus, OfflineQueue,
    Notification, BackupLog
)
from .forms import (
    LoginForm, UserRegistrationForm, MemberSearchForm,
    ManualCheckinForm, DateRangeForm, FaceRegistrationForm,
    BulkCheckinForm, SettingsForm
)
from face_recognition.camera import CameraManager, FaceRecognizer
from face_recognition.utils import check_camera_health
from sync.sync_members import PythonAnywhereSync
from .utils import (
    get_system_health, create_backup, restore_backup,
    generate_attendance_report, export_to_csv
)

logger = logging.getLogger(__name__)

# Initialize face recognizer
face_recognizer = FaceRecognizer()
face_recognizer.load_known_faces()

# Initialize camera for streaming (lazy - will be initialized on first use)
camera = CameraManager()
_camera_initialized = False

def ensure_camera_initialized():
    """Ensure camera is initialized before use"""
    global _camera_initialized
    if not _camera_initialized:
        try:
            camera.initialize_camera()
            _camera_initialized = True
        except RuntimeError as e:
            logger.error(f"Failed to initialize camera: {e}")
            raise


# ==================== AUTHENTICATION VIEWS ====================

def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect('index')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.username}!')
                
                # Check if this is first login
                if user.last_login is None:
                    messages.info(request, 'This is your first login. Consider changing your password.')
                
                return redirect(request.GET.get('next', 'index'))
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    return render(request, 'attendance_app/login.html', {'form': form})


def logout_view(request):
    """User logout view"""
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


def register_view(request):
    """User registration view"""
    if request.user.is_authenticated:
        return redirect('index')
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful! Welcome to BJJ Attendance System.')
            
            # Create welcome notification
            Notification.objects.create(
                notification_type='success',
                title='Welcome!',
                message=f'Welcome to the BJJ Attendance System, {user.first_name}!'
            )
            
            return redirect('index')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'attendance_app/register.html', {'form': form})


@login_required
def profile_view(request):
    """User profile view"""
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.save()
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')
    
    return render(request, 'attendance_app/profile.html')


@login_required
def change_password(request):
    """Change password view"""
    if request.method == 'POST':
        user = request.user
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not user.check_password(old_password):
            messages.error(request, 'Current password is incorrect.')
        elif new_password != confirm_password:
            messages.error(request, 'New passwords do not match.')
        elif len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
        else:
            user.set_password(new_password)
            user.save()
            messages.success(request, 'Password changed successfully! Please login again.')
            return redirect('login')
    
    return render(request, 'attendance_app/change_password.html')


# ==================== DASHBOARD VIEWS ====================

@login_required
def index(request):
    """Dashboard home"""
    # Get cached stats or calculate
    stats = cache.get('dashboard_stats')
    if not stats:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = date(today.year, today.month, 1)
        
        # Basic stats
        stats = {
            'total_members': LocalMember.objects.count(),
            'active_members': LocalMember.objects.filter(is_active=True).count(),
            'inactive_members': LocalMember.objects.filter(is_active=False).count(),
            'today_attendance': LocalAttendance.objects.filter(session_date=today).count(),
            'week_attendance': LocalAttendance.objects.filter(session_date__gte=week_start).count(),
            'month_attendance': LocalAttendance.objects.filter(session_date__gte=month_start).count(),
            'face_registered': LocalMember.objects.filter(face_registered=True).count(),
            'face_pending': LocalMember.objects.filter(is_active=True, face_registered=False).count(),
            'adults': LocalMember.objects.filter(member_type='adult').count(),
            'children': LocalMember.objects.filter(member_type='child').count(),
        }
        
        # Belt distribution
        belt_stats = LocalMember.objects.filter(is_active=True).values('belt_rank').annotate(
            count=Count('id')
        ).order_by('belt_rank')
        stats['belt_distribution'] = list(belt_stats)
        
        # Cache for 5 minutes
        cache.set('dashboard_stats', stats, 300)
    
    # Recent attendance (always fresh)
    recent_attendance = LocalAttendance.objects.select_related('member').order_by('-check_in_time')[:15]
    
    # Today's check-ins by hour (for chart)
    today = date.today()
    hourly_checkins = []
    for hour in range(5, 22):  # 5 AM to 10 PM
        start = timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=hour)))
        end = start + timedelta(hours=1)
        count = LocalAttendance.objects.filter(
            check_in_time__gte=start,
            check_in_time__lt=end
        ).count()
        hourly_checkins.append({'hour': f"{hour}:00", 'count': count})
    
    # System health
    system_health = get_system_health()
    
    # Pending sync
    pending_sync = LocalAttendance.objects.filter(synced=False).count()
    
    # Notifications
    notifications = Notification.objects.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    ).filter(read=False).order_by('-created_at')[:5]
    
    # Last sync
    last_sync = SyncLog.objects.filter(status='success').first()
    
    context = {
        'stats': stats,
        'recent_attendance': recent_attendance,
        'hourly_checkins': json.dumps(hourly_checkins),
        'system_health': system_health,
        'pending_sync': pending_sync,
        'notifications': notifications,
        'last_sync': last_sync,
        'online_status': cache.get('online_status', True),
    }
    
    return render(request, 'attendance_app/index.html', context)


# ==================== CHECK-IN VIEWS ====================

@login_required
def manual_checkin(request):
    """Manual check-in by searching members"""
    search_form = MemberSearchForm(request.GET or None)
    members = []
    selected_member = None
    
    if request.method == 'POST':
        member_id = request.POST.get('member_id')
        member = get_object_or_404(LocalMember, id=member_id)
        notes = request.POST.get('notes', '')
        
        # Check if already checked in today
        existing = LocalAttendance.objects.filter(
            member=member,
            session_date=date.today()
        ).first()
        
        if existing:
            messages.warning(
                request, 
                f"{member.full_name} already checked in today at {existing.check_in_time.strftime('%I:%M %p')}"
            )
        else:
            # Create attendance record
            attendance = LocalAttendance.objects.create(
                member=member,
                check_in_method='manual',
                notes=notes
            )
            
            # Add to offline queue if needed
            if not cache.get('online_status', True):
                OfflineQueue.objects.create(
                    action_type='checkin',
                    data={
                        'attendance_id': attendance.id,
                        'member_id': member.id,
                        'check_in_time': attendance.check_in_time.isoformat()
                    }
                )
                messages.info(request, 'Check-in recorded locally. Will sync when online.')
            else:
                messages.success(request, f"Check-in recorded for {member.full_name}")
            
            # Log the check-in
            logger.info(f"Manual check-in: {member.full_name} by {request.user.username}")
        
        return redirect('manual_checkin')
    
    # Handle search
    if search_form.is_valid():
        search_term = search_form.cleaned_data.get('search', '')
        filter_active = search_form.cleaned_data.get('filter_active', 'active')
        filter_face = search_form.cleaned_data.get('filter_face', 'all')
        belt_rank = search_form.cleaned_data.get('belt_rank', '')
        
        members = LocalMember.objects.all()
        
        # Apply filters
        if filter_active == 'active':
            members = members.filter(is_active=True)
        elif filter_active == 'inactive':
            members = members.filter(is_active=False)
        
        if filter_face == 'registered':
            members = members.filter(face_registered=True)
        elif filter_face == 'not_registered':
            members = members.filter(face_registered=False)
        
        if belt_rank:
            members = members.filter(belt_rank=belt_rank)
        
        if search_term:
            members = members.filter(
                Q(first_name__icontains=search_term) |
                Q(last_name__icontains=search_term) |
                Q(email__icontains=search_term) |
                Q(phone__icontains=search_term)
            )
        
        members = members.order_by('last_name', 'first_name')[:50]
    
    # Recent check-ins
    recent = LocalAttendance.objects.select_related('member').order_by('-check_in_time')[:10]
    
    # Today's stats
    today = date.today()
    today_count = LocalAttendance.objects.filter(session_date=today).count()
    today_by_method = LocalAttendance.objects.filter(session_date=today).values(
        'check_in_method'
    ).annotate(count=Count('id'))
    
    context = {
        'search_form': search_form,
        'members': members,
        'recent': recent,
        'today_count': today_count,
        'today_by_method': today_by_method,
    }
    
    return render(request, 'attendance_app/manual_checkin.html', context)


@login_required
def face_checkin(request):
    """Face recognition check-in page"""
    return render(request, 'attendance_app/face_checkin.html')


@login_required
@require_http_methods(["POST"])
def face_checkin_api(request):
    """API endpoint for face recognition check-in"""
    try:
        # Ensure camera is initialized
        ensure_camera_initialized()
        
        # Perform face recognition
        member_id, confidence, message = face_recognizer.recognize_face()
        
        if member_id:
            try:
                member = LocalMember.objects.get(id=member_id)
                
                # Check if already checked in today
                existing = LocalAttendance.objects.filter(
                    member=member,
                    session_date=date.today()
                ).first()
                
                if existing:
                    return JsonResponse({
                        'success': False,
                        'message': f'{member.full_name} already checked in today',
                        'existing_checkin': {
                            'time': existing.check_in_time.strftime('%I:%M %p'),
                            'method': existing.get_check_in_method_display()
                        }
                    })
                
                # Create attendance
                attendance = LocalAttendance.objects.create(
                    member=member,
                    check_in_method='face',
                    confidence_score=confidence
                )
                
                # Capture and save check-in photo
                frame = face_recognizer.camera.capture_frame()
                if frame is not None:
                    attendance.save_checkin_photo(frame)
                
                # Update last seen
                member.last_seen = timezone.now()
                member.save(update_fields=['last_seen'])
                
                # Log success
                logger.info(f"Face check-in: {member.full_name} (confidence: {confidence:.2%})")
                
                return JsonResponse({
                    'success': True,
                    'message': f'Welcome {member.full_name}!',
                    'member': {
                        'id': member.id,
                        'name': member.full_name,
                        'belt': member.get_belt_rank_display(),
                        'stripes': member.stripes,
                        'confidence': f'{confidence:.1%}'
                    }
                })
                
            except LocalMember.DoesNotExist:
                logger.error(f"Face recognized but member not found: ID {member_id}")
                return JsonResponse({
                    'success': False,
                    'message': 'Member not found in database'
                })
        else:
            return JsonResponse({
                'success': False,
                'message': message
            })
            
    except Exception as e:
        logger.error(f"Face check-in error: {e}")
        return JsonResponse({
            'success': False,
            'message': 'System error during check-in'
        }, status=500)


def video_feed(request):
    """Stream video for face check-in page"""
    try:
        ensure_camera_initialized()
        return StreamingHttpResponse(
            camera.generate_frames(),
            content_type='multipart/x-mixed-replace; boundary=frame'
        )
    except RuntimeError as e:
        logger.error(f"Camera initialization failed: {e}")
        return JsonResponse({
            'success': False,
            'message': 'Camera is not available'
        }, status=503)


@login_required
def bulk_checkin(request):
    """Bulk check-in for multiple members"""
    if request.method == 'POST':
        form = BulkCheckinForm(request.POST)
        if form.is_valid():
            member_ids = form.cleaned_data['member_ids']
            check_in_date = form.cleaned_data['check_in_date']
            notes = form.cleaned_data['notes']
            
            created_count = 0
            skipped_count = 0
            
            for member_id in member_ids:
                member = LocalMember.objects.get(id=member_id)
                
                # Check if already checked in on this date
                existing = LocalAttendance.objects.filter(
                    member=member,
                    session_date=check_in_date
                ).first()
                
                if not existing:
                    LocalAttendance.objects.create(
                        member=member,
                        session_date=check_in_date,
                        check_in_method='bulk',
                        notes=notes
                    )
                    created_count += 1
                else:
                    skipped_count += 1
            
            messages.success(
                request, 
                f'Bulk check-in complete: {created_count} created, {skipped_count} skipped'
            )
            return redirect('reports')
    else:
        form = BulkCheckinForm()
    
    return render(request, 'attendance_app/bulk_checkin.html', {'form': form})


# ==================== MEMBER MANAGEMENT VIEWS ====================

@login_required
def members_list(request):
    """List all members with filters"""
    form = MemberSearchForm(request.GET or None)
    
    members = LocalMember.objects.all()
    
    if form.is_valid():
        search_term = form.cleaned_data.get('search', '')
        filter_active = form.cleaned_data.get('filter_active', 'active')
        filter_face = form.cleaned_data.get('filter_face', 'all')
        belt_rank = form.cleaned_data.get('belt_rank', '')
        
        if filter_active == 'active':
            members = members.filter(is_active=True)
        elif filter_active == 'inactive':
            members = members.filter(is_active=False)
        
        if filter_face == 'registered':
            members = members.filter(face_registered=True)
        elif filter_face == 'not_registered':
            members = members.filter(face_registered=False)
        
        if belt_rank:
            members = members.filter(belt_rank=belt_rank)
        
        if search_term:
            members = members.filter(
                Q(first_name__icontains=search_term) |
                Q(last_name__icontains=search_term) |
                Q(email__icontains=search_term) |
                Q(phone__icontains=search_term)
            )
    
    # Order and paginate
    members = members.order_by('last_name', 'first_name')
    paginator = Paginator(members, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistics
    stats = {
        'total': LocalMember.objects.count(),
        'active': LocalMember.objects.filter(is_active=True).count(),
        'inactive': LocalMember.objects.filter(is_active=False).count(),
        'face_registered': LocalMember.objects.filter(face_registered=True).count(),
        'face_pending': LocalMember.objects.filter(is_active=True, face_registered=False).count(),
        'adults': LocalMember.objects.filter(member_type='adult').count(),
        'children': LocalMember.objects.filter(member_type='child').count(),
    }
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'form': form,
    }
    
    return render(request, 'attendance_app/members_list.html', context)


@login_required
def member_detail(request, member_id):
    """View member details"""
    member = get_object_or_404(LocalMember, id=member_id)
    
    # Get attendance history
    attendance = member.attendances.order_by('-session_date')[:30]
    
    # Statistics
    total_attendance = member.attendances.count()
    
    # Attendance by month (last 6 months)
    six_months_ago = date.today() - timedelta(days=180)
    monthly_stats = member.attendances.filter(
        session_date__gte=six_months_ago
    ).extra(
        {'month': "strftime('%%Y-%%m', session_date)"}
    ).values('month').annotate(count=Count('id')).order_by('month')
    
    # Face training history
    face_logs = member.face_training_logs.order_by('-started_at')
    
    context = {
        'member': member,
        'attendance': attendance,
        'total_attendance': total_attendance,
        'monthly_stats': list(monthly_stats),
        'face_logs': face_logs,
    }
    
    return render(request, 'attendance_app/member_detail.html', context)


@login_required
def member_edit(request, member_id):
    """Edit member details"""
    member = get_object_or_404(LocalMember, id=member_id)
    
    if request.method == 'POST':
        # Update fields
        member.first_name = request.POST.get('first_name', member.first_name)
        member.last_name = request.POST.get('last_name', member.last_name)
        member.email = request.POST.get('email', member.email)
        member.phone = request.POST.get('phone', member.phone)
        member.belt_rank = request.POST.get('belt_rank', member.belt_rank)
        member.stripes = request.POST.get('stripes', member.stripes)
        member.member_type = request.POST.get('member_type', member.member_type)
        member.is_active = request.POST.get('is_active') == 'on'
        member.notes = request.POST.get('notes', '')
        
        member.save()
        messages.success(request, f'Member {member.full_name} updated successfully')
        return redirect('member_detail', member_id=member.id)
    
    return render(request, 'attendance_app/member_edit.html', {'member': member})


@login_required
def register_member(request):
    """Redirect to face registration (member registration is done through face registration)"""
    return redirect('register_face')


# ==================== FACE REGISTRATION VIEWS ====================

@login_required
def register_face(request):
    """Register face for a member"""
    if request.method == 'POST':
        form = FaceRegistrationForm(request.POST)
        if form.is_valid():
            member = form.cleaned_data['member']
            num_photos = form.cleaned_data['num_photos']
            
            success, count = face_recognizer.register_face(member.id, num_photos)
            
            if success:
                messages.success(
                    request, 
                    f'Face registered successfully for {member.full_name} with {count} photos!'
                )
                
                # Create notification
                Notification.objects.create(
                    notification_type='success',
                    title='Face Registration Complete',
                    message=f'Face registered for {member.full_name}',
                    created_by=request.user
                )
            else:
                messages.error(
                    request, 
                    f'Registration failed for {member.full_name}. Only {count} good photos captured.'
                )
            
            return redirect('members_list')
    else:
        form = FaceRegistrationForm()
    
    # Get members with pending registration
    pending_members = LocalMember.objects.filter(
        is_active=True, 
        face_registered=False
    ).order_by('last_name', 'first_name')
    
    # Recently registered
    recently_registered = LocalMember.objects.filter(
        face_registered=True
    ).order_by('-updated_at')[:10]
    
    context = {
        'form': form,
        'pending_members': pending_members,
        'recently_registered': recently_registered,
        'total_registered': LocalMember.objects.filter(face_registered=True).count(),
    }
    
    return render(request, 'attendance_app/register_face.html', context)


@login_required
def face_registration_status(request, member_id):
    """Check face registration status"""
    member = get_object_or_404(LocalMember, id=member_id)
    
    return JsonResponse({
        'member_id': member.id,
        'name': member.full_name,
        'face_registered': member.face_registered,
        'face_photos_count': member.face_photos_count,
        'last_training': member.face_training_logs.first().started_at.isoformat() if member.face_training_logs.exists() else None,
    })


# ==================== REPORTS VIEWS ====================

@login_required
def reports(request):
    """Attendance reports and analytics"""
    form = DateRangeForm(request.GET or None)
    
    if form.is_valid():
        date_from = form.cleaned_data['date_from']
        date_to = form.cleaned_data['date_to']
        member_type = form.cleaned_data['member_type']
        
        # Base queryset
        attendance = LocalAttendance.objects.filter(
            session_date__gte=date_from,
            session_date__lte=date_to
        )
        
        if member_type != 'all':
            attendance = attendance.filter(member__member_type=member_type)
        
        # Summary statistics
        total_checkins = attendance.count()
        unique_members = attendance.values('member').distinct().count()
        
        # Daily breakdown
        daily_stats = attendance.values('session_date').annotate(
            count=Count('id')
        ).order_by('session_date')
        
        # Method breakdown
        method_stats = attendance.values('check_in_method').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Top attendees
        top_attendees = attendance.values(
            'member__id', 'member__first_name', 'member__last_name'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Belt level breakdown
        belt_stats = attendance.values(
            'member__belt_rank'
        ).annotate(
            count=Count('id')
        ).order_by('member__belt_rank')
        
        context = {
            'form': form,
            'total_checkins': total_checkins,
            'unique_members': unique_members,
            'daily_stats': list(daily_stats),
            'method_stats': list(method_stats),
            'top_attendees': top_attendees,
            'belt_stats': list(belt_stats),
            'date_from': date_from,
            'date_to': date_to,
        }
    else:
        # Default to last 30 days
        context = {
            'form': form,
            'daily_stats': [],
            'method_stats': [],
        }
    
    return render(request, 'attendance_app/reports.html', context)


@login_required
def export_report(request):
    """Export attendance report as CSV"""
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if not date_from or not date_to:
        messages.error(request, 'Please select date range')
        return redirect('reports')
    
    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Date', 'Member Name', 'Member Type', 'Belt Rank', 
                     'Check-in Time', 'Method', 'Confidence', 'Notes'])
    
    # Get data
    attendance = LocalAttendance.objects.filter(
        session_date__gte=date_from,
        session_date__lte=date_to
    ).select_related('member').order_by('-session_date', '-check_in_time')
    
    for a in attendance:
        writer.writerow([
            a.session_date,
            a.member.full_name,
            a.member.get_member_type_display(),
            a.member.get_belt_rank_display(),
            a.check_in_time.strftime('%I:%M %p'),
            a.get_check_in_method_display(),
            f"{a.confidence_score:.2%}" if a.confidence_score else '',
            a.notes
        ])
    
    # Create response
    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="attendance_report_{date_from}_to_{date_to}.csv"'
    
    return response


# ==================== SYNC VIEWS ====================

@login_required
def sync_status(request):
    """View sync status and history"""
    # Get sync history
    sync_logs = SyncLog.objects.all().order_by('-start_time')[:50]
    
    # Pending sync items
    pending_attendance = LocalAttendance.objects.filter(synced=False).count()
    pending_queue = OfflineQueue.objects.filter(processed=False).count()
    
    # Last sync info
    last_sync = SyncLog.objects.filter(status='success').first()
    last_attempt = SyncLog.objects.order_by('-start_time').first()
    
    # Network status
    online_status = cache.get('online_status', True)
    
    # Determine success/failure for the template
    success = online_status and pending_attendance == 0 and pending_queue == 0
    
    # Create message
    if success:
        message = "All systems operational. No pending sync items."
    else:
        issues = []
        if not online_status:
            issues.append("offline")
        if pending_attendance > 0:
            issues.append(f"{pending_attendance} pending attendance records")
        if pending_queue > 0:
            issues.append(f"{pending_queue} pending queue items")
        message = f"Sync pending: {', '.join(issues)}"
    
    # Create sync details
    sync_details = f"""
Last sync: {last_attempt.start_time if last_attempt else 'Never'}
Status: {last_attempt.status if last_attempt else 'N/A'}
Records synced: {last_attempt.records_synced if last_attempt else 0}
    """.strip()
    
    context = {
        'sync_logs': sync_logs,
        'pending_attendance': pending_attendance,
        'pending_queue': pending_queue,
        'last_sync': last_sync,
        'last_attempt': last_attempt,
        'online_status': online_status,
        # Add these for your template
        'success': success,
        'message': message,
        'sync_details': sync_details,
    }
    
    return render(request, 'attendance_app/sync_status.html', context)

@login_required
@require_http_methods(["POST"])
def trigger_sync(request):
    """Manually trigger sync"""
    sync_type = request.POST.get('sync_type', 'attendance')
    
    # Check if sync already running
    running = SyncLog.objects.filter(status='running').exists()
    if running:
        messages.warning(request, 'A sync is already in progress')
        return redirect('sync_status')
    
    # Create sync log
    sync_log = SyncLog.objects.create(
        sync_type=sync_type,
        status='running',
        triggered_by=request.user
    )
    
    # Trigger sync in background (in production, use Celery)
    # For now, we'll do a simple sync
    try:
        sync_client = PythonAnywhereSync()
        
        if sync_type in ['members', 'full']:
            # Sync members
            members_result = sync_client.sync_members()
            sync_log.records_processed += members_result.get('processed', 0)
            sync_log.records_succeeded += members_result.get('succeeded', 0)
            sync_log.records_failed += members_result.get('failed', 0)
        
        if sync_type in ['attendance', 'full']:
            # Sync attendance
            unsynced = LocalAttendance.objects.filter(synced=False)[:100]
            if unsynced:
                attendance_result = sync_client.sync_attendance(unsynced)
                sync_log.records_processed += attendance_result.get('processed', 0)
                sync_log.records_succeeded += attendance_result.get('succeeded', 0)
                sync_log.records_failed += attendance_result.get('failed', 0)
        
        sync_log.status = 'success'
        sync_log.end_time = timezone.now()
        sync_log.save()
        
        messages.success(request, f'Sync completed successfully!')
        
    except Exception as e:
        sync_log.status = 'failed'
        sync_log.error_message = str(e)
        sync_log.end_time = timezone.now()
        sync_log.save()
        
        messages.error(request, f'Sync failed: {str(e)}')
    
    return redirect('sync_status')


# ==================== SYSTEM VIEWS ====================

@login_required
def system_settings(request):
    """System settings view"""
    if request.method == 'POST':
        form = SettingsForm(request.POST)
        if form.is_valid():
            # Save settings to cache/database
            cache.set('pythonanywhere_url', form.cleaned_data['pythonanywhere_url'])
            cache.set('pythonanywhere_api_key', form.cleaned_data['pythonanywhere_api_key'])
            cache.set('sync_interval', form.cleaned_data['sync_interval'])
            cache.set('face_threshold', form.cleaned_data['face_threshold'])
            cache.set('min_face_photos', form.cleaned_data['min_face_photos'])
            cache.set('camera_index', form.cleaned_data['camera_index'])
            cache.set('items_per_page', form.cleaned_data['items_per_page'])
            
            # Update session for dark mode
            request.session['dark_mode'] = form.cleaned_data['dark_mode']
            
            messages.success(request, 'Settings saved successfully')
            return redirect('system_settings')
    else:
        # Load current settings
        initial = {
            'pythonanywhere_url': cache.get('pythonanywhere_url', ''),
            'pythonanywhere_api_key': cache.get('pythonanywhere_api_key', ''),
            'sync_interval': cache.get('sync_interval', 300),
            'face_threshold': cache.get('face_threshold', 0.6),
            'min_face_photos': cache.get('min_face_photos', 3),
            'camera_index': cache.get('camera_index', 0),
            'items_per_page': cache.get('items_per_page', 25),
            'dark_mode': request.session.get('dark_mode', False),
        }
        form = SettingsForm(initial=initial)
    
    # System info
    import platform
    import psutil
    
    system_info = {
        'hostname': platform.node(),
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'django_version': '4.2.7',
        'cpu_usage': psutil.cpu_percent(),
        'memory_usage': psutil.virtual_memory().percent,
        'disk_usage': psutil.disk_usage('/').percent,
        'uptime': timezone.now() - timezone.datetime.fromtimestamp(psutil.boot_time()),
    }
    
    context = {
        'form': form,
        'system_info': system_info,
    }
    
    return render(request, 'attendance_app/settings.html', context)


@login_required
def system_health(request):
    """System health check view"""
    health_data = get_system_health()
    
    # Get recent errors
    recent_errors = []
    log_file = 'logs/errors.log'
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            recent_errors = f.readlines()[-10:]
    
    context = {
        'health': health_data,
        'recent_errors': recent_errors,
    }
    
    return render(request, 'attendance_app/health.html', context)


@login_required
def camera_test(request):
    """Test camera functionality"""
    if request.method == 'POST':
        try:
            # Test camera
            ensure_camera_initialized()
            camera_health = check_camera_health()
            
            # Try to capture a frame
            frame = camera.capture_frame()
            
            if frame is not None:
                messages.success(request, 'Camera is working properly')
            else:
                messages.error(request, 'Camera test failed')
            
            return JsonResponse({
                'success': frame is not None,
                'camera_health': camera_health
            })
        except RuntimeError as e:
            logger.error(f"Camera test failed: {e}")
            messages.error(request, f'Camera error: {str(e)}')
            return JsonResponse({
                'success': False,
                'camera_health': {'status': 'error', 'message': str(e)}
            }, status=503)
    
    return render(request, 'attendance_app/camera_test.html')


@login_required
def create_backup_view(request):
    """Create database backup"""
    if request.method == 'POST':
        backup_type = request.POST.get('backup_type', 'manual')
        
        try:
            backup = create_backup(backup_type)
            messages.success(
                request, 
                f'Backup created successfully: {backup.filename} ({backup.size_mb:.2f} MB)'
            )
        except Exception as e:
            messages.error(request, f'Backup failed: {str(e)}')
        
        return redirect('system_settings')
    
    # List recent backups
    backups = BackupLog.objects.order_by('-created_at')[:20]
    
    return render(request, 'attendance_app/backups.html', {'backups': backups})


# ==================== API VIEWS ====================

@login_required
@require_http_methods(["GET"])
def api_recent_face_checkins(request):
    """API endpoint for recent face checkins"""
    limit = int(request.GET.get('limit', 10))
    
    recent = LocalAttendance.objects.filter(
        check_in_method='face'
    ).select_related('member').order_by('-check_in_time')[:limit]
    
    data = []
    for attendance in recent:
        data.append({
            'time': attendance.check_in_time.strftime('%H:%M'),
            'member': attendance.member.full_name,
            'belt': attendance.member.get_belt_rank_display(),
            'confidence': f"{attendance.confidence_score:.1%}" if attendance.confidence_score else 'N/A'
        })
    
    return JsonResponse({'checkins': data})


@csrf_exempt
@require_http_methods(["POST"])
def api_checkin(request):
    """API endpoint for external check-in"""
    api_key = request.headers.get('X-API-Key')
    
    if api_key != cache.get('api_key'):
        return JsonResponse({'error': 'Invalid API key'}, status=401)
    
    try:
        data = json.loads(request.body)
        member_id = data.get('member_id')
        method = data.get('method', 'api')
        timestamp = data.get('timestamp')
        
        member = LocalMember.objects.get(id=member_id, is_active=True)
        
        # Check for duplicate
        check_date = date.today()
        if timestamp:
            check_date = datetime.fromisoformat(timestamp).date()
        
        existing = LocalAttendance.objects.filter(
            member=member,
            session_date=check_date
        ).first()
        
        if existing:
            return JsonResponse({
                'success': False,
                'message': 'Already checked in today',
                'existing_checkin': existing.check_in_time.isoformat()
            })
        
        # Create attendance
        attendance = LocalAttendance(
            member=member,
            check_in_method=method,
            notes=data.get('notes', '')
        )
        
        if timestamp:
            attendance.check_in_time = datetime.fromisoformat(timestamp)
        
        attendance.save()
        
        return JsonResponse({
            'success': True,
            'attendance_id': attendance.id,
            'check_in_time': attendance.check_in_time.isoformat()
        })
        
    except LocalMember.DoesNotExist:
        return JsonResponse({'error': 'Member not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def api_member_search(request):
    """API endpoint for member search (AJAX)"""
    search_term = request.GET.get('q', '')
    
    if len(search_term) < 2:
        return JsonResponse({'results': []})
    
    members = LocalMember.objects.filter(
        Q(first_name__icontains=search_term) |
        Q(last_name__icontains=search_term) |
        Q(email__icontains=search_term)
    ).filter(is_active=True)[:20]
    
    results = [{
        'id': m.id,
        'text': f"{m.full_name} ({m.get_belt_rank_display()})",
        'belt': m.belt_rank,
        'stripes': m.stripes,
        'face_registered': m.face_registered
    } for m in members]
    
    return JsonResponse({'results': results})


@login_required
def api_today_stats(request):
    """API endpoint for today's stats (AJAX)"""
    today = date.today()
    
    total = LocalAttendance.objects.filter(session_date=today).count()
    by_hour = []
    
    for hour in range(5, 22):
        start = timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=hour)))
        end = start + timedelta(hours=1)
        count = LocalAttendance.objects.filter(
            check_in_time__gte=start,
            check_in_time__lt=end
        ).count()
        by_hour.append({'hour': hour, 'count': count})
    
    by_method = LocalAttendance.objects.filter(session_date=today).values(
        'check_in_method'
    ).annotate(count=Count('id'))
    
    recent = LocalAttendance.objects.filter(session_date=today).select_related('member').order_by('-check_in_time')[:10]
    
    return JsonResponse({
        'total': total,
        'by_hour': by_hour,
        'by_method': list(by_method),
        'recent': [{
            'name': r.member.full_name,
            'time': r.check_in_time.strftime('%I:%M %p'),
            'method': r.get_check_in_method_display()
        } for r in recent]
    })
    
    
def test_simple_login(request):
    """Super simple login view for testing"""
    from django.contrib.auth import authenticate, login
    from django.http import HttpResponse
    
    print("=" * 50)
    print("Simple test login called")
    print(f"Method: {request.method}")
    
    if request.method == 'POST':
        print("POST data:", request.POST)
        username = request.POST.get('username')
        password = request.POST.get('password')
        print(f"Username: {username}, Password: {'*' * len(password) if password else 'None'}")
        
        user = authenticate(request, username=username, password=password)
        print(f"Authenticated user: {user}")
        
        if user:
            login(request, user)
            return redirect('index')
        else:
            return HttpResponse("Login failed", status=401)
    
    # Simple HTML form
    html = """
    <html>
    <body>
        <h2>Simple Test Login</h2>
        <form method="post">
            <input type="text" name="username" placeholder="Username"><br>
            <input type="password" name="password" placeholder="Password"><br>
            <button type="submit">Login</button>
        </form>
    </body>
    </html>
    """
    return HttpResponse(html)

def test_template(request):
    return render(request, 'test/minimal.html')

def face_registration_complete(request):
    """Display face registration completion page."""
    return render(request, 'attendance_app/face_registration_complete.html')
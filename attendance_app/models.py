from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import date, timedelta
import numpy as np
import os
import json


class LocalMember(models.Model):
    """Cached copy of members from PythonAnywhere CRM"""
    
    MEMBER_TYPES = [
        ('adult', 'Adult'),
        ('child', 'Child'),
    ]
    
    BELT_RANKS = [
        ('white', 'White'),
        ('blue', 'Blue'),
        ('purple', 'Purple'),
        ('brown', 'Brown'),
        ('black', 'Black'),
        ('red', 'Red'),
        ('gray_white', 'Gray/White'),
        ('gray', 'Gray'),
        ('gray_black', 'Gray/Black'),
        ('yellow_white', 'Yellow/White'),
        ('yellow', 'Yellow'),
        ('yellow_black', 'Yellow/Black'),
        ('orange_white', 'Orange/White'),
        ('orange', 'Orange'),
        ('orange_black', 'Orange/Black'),
        ('green_white', 'Green/White'),
        ('green', 'Green'),
        ('green_black', 'Green/Black'),
    ]
    
    # Remote sync fields
    remote_id = models.IntegerField(unique=True, null=True, blank=True)
    last_sync = models.DateTimeField(auto_now=True)
    
    # Personal info
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    member_type = models.CharField(max_length=10, choices=MEMBER_TYPES, default='adult')
    date_of_birth = models.DateField(null=True, blank=True)
    
    # BJJ info
    belt_rank = models.CharField(max_length=50, choices=BELT_RANKS, default='white')
    stripes = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(4)])
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Local metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Face recognition
    face_registered = models.BooleanField(default=False)
    face_photos_count = models.IntegerField(default=0)
    face_encoding_path = models.CharField(max_length=500, blank=True, null=True)
    
    # Photo URL from remote
    photo_url = models.URLField(max_length=500, blank=True, null=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['remote_id']),
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['face_registered']),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
    
    def save_face_encoding(self, encoding):
        """Save face encoding to file"""
        if encoding is not None:
            filename = f"face_{self.id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.npy"
            filepath = os.path.join('media', 'faces', filename)
            np.save(filepath, encoding)
            self.face_encoding_path = filepath
            self.face_registered = True
            self.save()
    
    def load_face_encoding(self):
        """Load face encoding from file"""
        if self.face_encoding_path and os.path.exists(self.face_encoding_path):
            return np.load(self.face_encoding_path)
        return None
    
    def get_belt_display_with_stripes(self):
        """Get belt display with stripes"""
        belt_display = dict(self.BELT_RANKS).get(self.belt_rank, self.belt_rank)
        if self.stripes:
            return f"{belt_display} ({'⭐' * self.stripes})"
        return belt_display


class LocalAttendance(models.Model):
    """Local attendance records before sync to PythonAnywhere"""
    
    CHECK_IN_METHODS = [
        ('manual', 'Manual Entry'),
        ('face', 'Face Recognition'),
        ('qr', 'QR Code'),
        ('nfc', 'NFC Card'),
        ('api', 'API'),
        ('bulk', 'Bulk Import'),
    ]
    
    member = models.ForeignKey(
        LocalMember, 
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    
    session_date = models.DateField(default=date.today)
    check_in_time = models.DateTimeField(default=timezone.now)
    check_in_method = models.CharField(max_length=20, choices=CHECK_IN_METHODS)
    confidence_score = models.FloatField(null=True, blank=True)  # For face recognition
    
    # Sync status
    synced = models.BooleanField(default=False)
    sync_error = models.TextField(blank=True)
    sync_attempts = models.IntegerField(default=0)
    last_sync_attempt = models.DateTimeField(null=True, blank=True)
    remote_attendance_id = models.IntegerField(null=True, blank=True)  # ID from PythonAnywhere
    
    # Additional data
    notes = models.TextField(blank=True)
    photo_path = models.CharField(max_length=500, blank=True, null=True)  # Check-in photo
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-check_in_time']
        indexes = [
            models.Index(fields=['member', 'session_date']),
            models.Index(fields=['synced']),
            models.Index(fields=['check_in_time']),
            models.Index(fields=['session_date']),
        ]
        unique_together = ['member', 'session_date']  # One check-in per member per day
    
    def __str__(self):
        return f"{self.member} - {self.session_date}"
    
    def save_checkin_photo(self, image_array):
        """Save check-in photo"""
        if image_array is not None:
            from PIL import Image
            import cv2
            
            filename = f"checkin_{self.member.id}_{self.check_in_time.strftime('%Y%m%d_%H%M%S')}.jpg"
            filepath = os.path.join('media', 'checkin_photos', filename)
            
            # Convert and save
            if isinstance(image_array, np.ndarray):
                cv2.imwrite(filepath, cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR))
            
            self.photo_path = filepath
            self.save(update_fields=['photo_path'])
            
    remote_attendance_id = models.IntegerField(null=True, blank=True)
    sync_attempts = models.IntegerField(default=0)
    sync_error = models.TextField(null=True, blank=True)
    last_sync_attempt = models.DateTimeField(null=True, blank=True)
    next_sync_attempt = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        # Prevent duplicate syncs
        unique_together = ['member', 'session_date', 'check_in_time']

class SyncLog(models.Model):
    """Track sync operations with PythonAnywhere"""
    
    SYNC_TYPES = [
        ('members', 'Members Sync'),
        ('attendance', 'Attendance Sync'),
        ('full', 'Full Sync'),
        ('manual', 'Manual Sync'),
    ]
    
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('partial', 'Partial Success'),
    ]
    
    sync_type = models.CharField(max_length=50, choices=SYNC_TYPES)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    records_processed = models.IntegerField(default=0)
    records_succeeded = models.IntegerField(default=0)
    records_failed = models.IntegerField(default=0)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    error_message = models.TextField(blank=True)
    details = models.JSONField(default=dict)
    
    # Who triggered the sync
    triggered_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='sync_logs'
    )
    
    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['sync_type']),
        ]
    
    def __str__(self):
        return f"{self.sync_type} - {self.start_time}"
    
    def duration(self):
        """Get sync duration"""
        if self.end_time:
            return self.end_time - self.start_time
        return None


class FaceTrainingLog(models.Model):
    """Track face registration sessions"""
    
    member = models.ForeignKey(LocalMember, on_delete=models.CASCADE, related_name='face_training_logs')
    photos_attempted = models.IntegerField(default=0)
    photos_successful = models.IntegerField(default=0)
    success = models.BooleanField(default=False)
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    error_message = models.TextField(blank=True)
    training_data = models.JSONField(default=dict, blank=True)
    
    # Who performed the training
    trained_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    class Meta:
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.member} - {self.started_at}"


class SystemStatus(models.Model):
    """Track system health and status"""
    
    STATUS_TYPES = [
        ('camera', 'Camera Status'),
        ('network', 'Network Status'),
        ('storage', 'Storage Status'),
        ('sync', 'Sync Status'),
        ('face_recognition', 'Face Recognition Status'),
        ('system', 'System Health'),
    ]
    
    status_type = models.CharField(max_length=50, choices=STATUS_TYPES, db_index=True)
    key = models.CharField(max_length=100)
    value = models.JSONField(default=dict)
    is_healthy = models.BooleanField(default=True)
    last_check = models.DateTimeField(auto_now=True)
    message = models.CharField(max_length=255, blank=True)
    
    class Meta:
        unique_together = ['status_type', 'key']
        indexes = [
            models.Index(fields=['status_type', 'is_healthy']),
        ]
    
    def __str__(self):
        return f"{self.status_type}: {self.key}"


class OfflineQueue(models.Model):
    """Queue for actions that need to be processed when online"""
    
    ACTION_TYPES = [
        ('checkin', 'Check-in'),
        ('member_update', 'Member Update'),
        ('photo_upload', 'Photo Upload'),
        ('bulk_sync', 'Bulk Sync'),
    ]
    
    PRIORITIES = [
        (1, 'High'),
        (2, 'Medium'),
        (3, 'Low'),
    ]
    
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    priority = models.IntegerField(choices=PRIORITIES, default=2)
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    
    class Meta:
        ordering = ['priority', 'created_at']
        indexes = [
            models.Index(fields=['processed', 'priority']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.action_type} - {self.created_at}"
    
    def can_retry(self):
        """Check if action can be retried"""
        return self.retry_count < self.max_retries


class Notification(models.Model):
    """System notifications"""
    
    NOTIFICATION_TYPES = [
        ('info', 'Information'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]
    
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='info')
    title = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)
    read_by = models.ManyToManyField(User, blank=True, related_name='read_notifications')
    expires_at = models.DateTimeField(null=True, blank=True)
    action_url = models.CharField(max_length=500, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['read', 'created_at']),
            models.Index(fields=['notification_type']),
        ]
    
    def __str__(self):
        return self.title


class BackupLog(models.Model):
    """Track database backups"""
    
    BACKUP_TYPES = [
        ('auto', 'Automatic'),
        ('manual', 'Manual'),
        ('pre_sync', 'Pre-Sync'),
    ]
    
    backup_type = models.CharField(max_length=20, choices=BACKUP_TYPES)
    filename = models.CharField(max_length=500)
    size_bytes = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='success')
    error_message = models.TextField(blank=True)
    records_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.backup_type} - {self.created_at}"
    
    @property
    def size_mb(self):
        """Get size in MB"""
        return self.size_bytes / (1024 * 1024)
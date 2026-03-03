from django.contrib import admin
from .models import LocalMember, LocalAttendance, SyncLog, FaceTrainingLog, SystemStatus, OfflineQueue, Notification, BackupLog

@admin.register(LocalMember)
class LocalMemberAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'member_type', 'belt_rank', 'stripes', 'is_active', 'face_registered')
    list_filter = ('member_type', 'belt_rank', 'is_active', 'face_registered', 'created_at')
    search_fields = ('first_name', 'last_name', 'email', 'phone')
    ordering = ('last_name', 'first_name')
    readonly_fields = ('remote_id', 'last_sync', 'created_at', 'updated_at', 'face_encoding_path', 'face_photos_count')
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'member_type', 'date_of_birth')
        }),
        ('BJJ Information', {
            'fields': ('belt_rank', 'stripes')
        }),
        ('Face Recognition', {
            'fields': ('face_registered', 'face_photos_count', 'face_encoding_path', 'photo_url')
        }),
        ('Sync & Status', {
            'fields': ('remote_id', 'is_active', 'notes', 'last_sync')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'Name'

@admin.register(LocalAttendance)
class LocalAttendanceAdmin(admin.ModelAdmin):
    list_display = ('member', 'session_date', 'check_in_time', 'check_in_method', 'synced')
    list_filter = ('check_in_method', 'synced', 'session_date', 'check_in_time')
    search_fields = ('member__first_name', 'member__last_name', 'notes')
    readonly_fields = ('created_at', 'updated_at', 'photo_path', 'confidence_score')
    date_hierarchy = 'session_date'
    actions = ['mark_as_synced', 'retry_sync']
    
    def mark_as_synced(self, request, queryset):
        queryset.update(synced=True)
    mark_as_synced.short_description = "Mark selected as synced"
    
    def retry_sync(self, request, queryset):
        queryset.update(synced=False, sync_attempts=0, sync_error='')
    retry_sync.short_description = "Reset sync for selected"

@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ('sync_type', 'start_time', 'end_time', 'status', 'records_processed')
    list_filter = ('sync_type', 'status', 'start_time')
    readonly_fields = ('start_time', 'end_time', 'records_processed', 'records_succeeded', 'records_failed', 'error_message', 'details')
    date_hierarchy = 'start_time'

@admin.register(FaceTrainingLog)
class FaceTrainingLogAdmin(admin.ModelAdmin):
    list_display = ('member', 'started_at', 'completed_at', 'success', 'photos_successful')
    list_filter = ('success', 'started_at')
    search_fields = ('member__first_name', 'member__last_name')
    readonly_fields = ('started_at', 'completed_at', 'photos_attempted', 'photos_successful', 'error_message', 'training_data')

@admin.register(SystemStatus)
class SystemStatusAdmin(admin.ModelAdmin):
    list_display = ('status_type', 'key', 'is_healthy', 'last_check', 'message')
    list_filter = ('status_type', 'is_healthy', 'last_check')
    search_fields = ('key', 'message')
    readonly_fields = ('last_check',)

@admin.register(OfflineQueue)
class OfflineQueueAdmin(admin.ModelAdmin):
    list_display = ('action_type', 'priority', 'created_at', 'processed', 'retry_count')
    list_filter = ('action_type', 'priority', 'processed', 'created_at')
    readonly_fields = ('created_at', 'processed_at', 'retry_count')
    actions = ['retry_selected']
    
    def retry_selected(self, request, queryset):
        queryset.update(processed=False, retry_count=0, error='')
    retry_selected.short_description = "Retry selected items"

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'notification_type', 'created_at', 'read')
    list_filter = ('notification_type', 'read', 'created_at')
    search_fields = ('title', 'message')
    readonly_fields = ('created_at',)
    filter_horizontal = ('read_by',)

@admin.register(BackupLog)
class BackupLogAdmin(admin.ModelAdmin):
    list_display = ('backup_type', 'created_at', 'status', 'size_mb', 'records_count')
    list_filter = ('backup_type', 'status', 'created_at')
    readonly_fields = ('filename', 'size_bytes', 'created_at', 'error_message', 'records_count')
    
    def size_mb(self, obj):
        return f"{obj.size_mb:.2f} MB"
    size_mb.short_description = 'Size'
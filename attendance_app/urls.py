from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('profile/', views.profile_view, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    
    # Dashboard
    path('', views.index, name='index'),
    
    # Check-in
    path('checkin/manual/', views.manual_checkin, name='manual_checkin'),
    path('checkin/face/', views.face_checkin, name='face_checkin'),
    path('checkin/face/api/', views.face_checkin_api, name='face_checkin_api'),
    path('checkin/bulk/', views.bulk_checkin, name='bulk_checkin'),
    
    # Video feed
    path('video-feed/', views.video_feed, name='video_feed'),
    
    # Members
    path('members/', views.members_list, name='members_list'),
    path('members/register/', views.register_member, name='register_member'),
    path('member/<int:member_id>/', views.member_detail, name='member_detail'),
    path('member/<int:member_id>/edit/', views.member_edit, name='member_edit'),
    
    # Face registration
    path('face/register/', views.register_face, name='register_face'),
    path('face/registration/complete/', views.face_registration_complete, name='face_registration_complete'),  
    path('face/status/<int:member_id>/', views.face_registration_status, name='face_registration_status'),
    
    # API endpoints
    path('api/recent-face-checkins/', views.api_recent_face_checkins, name='api_recent_face_checkins'),
    
    # Reports
    path('reports/', views.reports, name='reports'),
    path('reports/export/', views.export_report, name='export_report'),
    
    # Sync
    path('sync/', views.sync_status, name='sync_status'),
    path('sync/trigger/', views.trigger_sync, name='trigger_sync'),
    
    # System
    path('settings/', views.system_settings, name='system_settings'),
    path('health/', views.system_health, name='system_health'),
    path('camera/test/', views.camera_test, name='camera_test'),
    path('backup/create/', views.create_backup_view, name='create_backup'),
    
    path('test-login/', views.test_simple_login, name='test_login'),
    path('test-template/', views.test_template, name='test_template'),
]

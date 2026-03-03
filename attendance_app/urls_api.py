from django.urls import path
from . import views

urlpatterns = [
    # API endpoints
    path('checkin/', views.api_checkin, name='api_checkin'),
    path('members/search/', views.api_member_search, name='api_member_search'),
    path('stats/today/', views.api_today_stats, name='api_today_stats'),
]
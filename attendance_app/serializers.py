
# api/serializers.py
from rest_framework import serializers
from django.apps import apps

Member = apps.get_model('crm', 'Member')

class MemberSyncSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ['id', 'first_name', 'last_name', 'email', 'is_active', 'member_type']

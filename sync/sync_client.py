import requests
import logging
from django.conf import settings
from django.utils import timezone
from attendance_app.models import LocalMember, LocalAttendance
import json

logger = logging.getLogger(__name__)

class PythonAnywhereSync:
    """Sync client for PythonAnywhere CRM"""
    
    def __init__(self):
        self.api_url = settings.PYTHONANYWHERE_URL
        self.api_key = settings.PYTHONANYWHERE_API_KEY
        self.headers = {
            'Authorization': f'Token {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    def sync_members(self, full=False):
        """Fetch members from PythonAnywhere"""
        result = {
            'processed': 0,
            'succeeded': 0,
            'failed': 0,
            'errors': []
        }
        
        try:
            # Get last sync time
            last_sync = None
            if not full:
                last_sync = LocalMember.objects.aggregate(last=models.Max('last_sync'))['last']
            
            params = {}
            if last_sync:
                params['updated_after'] = last_sync.isoformat()
            
            response = requests.get(
                f"{self.api_url}/api/members/",
                headers=self.headers,
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                members_data = response.json()
                
                for member_data in members_data:
                    result['processed'] += 1
                    try:
                        member, created = LocalMember.objects.update_or_create(
                            remote_id=member_data['id'],
                            defaults={
                                'first_name': member_data['first_name'],
                                'last_name': member_data['last_name'],
                                'email': member_data.get('email'),
                                'phone': member_data.get('phone'),
                                'member_type': member_data.get('member_type', 'adult'),
                                'belt_rank': member_data.get('belt_rank', 'white'),
                                'stripes': member_data.get('stripes', 0),
                                'is_active': member_data.get('is_active', True),
                                'photo_url': member_data.get('photo'),
                                'last_sync': timezone.now()
                            }
                        )
                        
                        if member_data.get('date_of_birth'):
                            member.date_of_birth = member_data['date_of_birth']
                            member.save()
                        
                        result['succeeded'] += 1
                        logger.info(f"{'Created' if created else 'Updated'} member: {member.full_name}")
                        
                    except Exception as e:
                        result['failed'] += 1
                        result['errors'].append(str(e))
                        logger.error(f"Error syncing member {member_data.get('id')}: {e}")
                
            else:
                error_msg = f"API error: {response.status_code} - {response.text}"
                result['errors'].append(error_msg)
                logger.error(error_msg)
                
        except Exception as e:
            result['errors'].append(str(e))
            logger.error(f"Sync error: {e}")
        
        return result
    
    def sync_attendance(self, attendance_records):
        """Push attendance records to PythonAnywhere"""
        result = {
            'processed': 0,
            'succeeded': 0,
            'failed': 0,
            'errors': []
        }
        
        for record in attendance_records:
            result['processed'] += 1
            
            try:
                member = record.member
                
                if not member.remote_id:
                    error_msg = f"Member {member.full_name} has no remote ID"
                    result['errors'].append(error_msg)
                    result['failed'] += 1
                    record.sync_error = error_msg
                    record.sync_attempts += 1
                    record.save()
                    continue
                
                data = {
                    'member_id': member.remote_id,
                    'date': record.session_date.isoformat(),
                    'check_in_time': record.check_in_time.isoformat(),
                    'method': record.check_in_method,
                    'notes': record.notes or '',
                    'confidence': record.confidence_score
                }
                
                response = requests.post(
                    f"{self.api_url}/api/attendance/",
                    headers=self.headers,
                    json=data,
                    timeout=10
                )
                
                if response.status_code in [200, 201]:
                    record.synced = True
                    record.sync_error = None
                    record.sync_attempts += 1
                    record.last_sync_attempt = timezone.now()
                    
                    # Store remote attendance ID if returned
                    response_data = response.json()
                    if 'id' in response_data:
                        record.remote_attendance_id = response_data['id']
                    
                    record.save()
                    result['succeeded'] += 1
                    logger.info(f"Synced attendance for {member.full_name}")
                    
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    record.sync_error = error_msg
                    record.sync_attempts += 1
                    record.last_sync_attempt = timezone.now()
                    record.save()
                    
                    result['failed'] += 1
                    result['errors'].append(error_msg)
                    logger.error(f"Failed to sync attendance: {error_msg}")
                    
            except Exception as e:
                record.sync_error = str(e)
                record.sync_attempts += 1
                record.last_sync_attempt = timezone.now()
                record.save()
                
                result['failed'] += 1
                result['errors'].append(str(e))
                logger.error(f"Error syncing attendance: {e}")
        
        return result
import requests
import logging
from django.conf import settings
from django.utils import timezone
from django.db import models
from attendance_app.models import LocalMember, LocalAttendance
import json
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class PythonAnywhereSync:
    """Sync client for PythonAnywhere CRM"""
    
    def __init__(self):
        self.api_key = settings.PYTHONANYWHERE_API_KEY
        self.base_url = settings.PYTHONANYWHERE_URL.rstrip('/')
        # Fix: Use consistent API structure - match your CRM's actual endpoints
        self.api_base = f"{self.base_url}/api"
        self.headers = {
            'Authorization': f'Token {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _make_request(self, method, endpoint, **kwargs):
        """Make API request with retry logic"""
        url = f"{self.api_base}{endpoint}"
        response = requests.request(method, url, headers=self.headers, timeout=30, **kwargs)
        
        if response.status_code >= 500:
            # Server errors are retryable
            response.raise_for_status()
        elif response.status_code >= 400:
            # Client errors need investigation
            logger.error(f"API Error {response.status_code}: {response.text}")
            
        return response
    
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
            
            # Fix: Correct endpoint - match your CRM's GetMembers view
            response = self._make_request('GET', '/members/', params=params)
            
            if response.status_code == 200:
                members_data = response.json()
                
                for member_data in members_data:
                    result['processed'] += 1
                    try:
                        member, created = LocalMember.objects.update_or_create(
                            remote_id=member_data['id'],  # Use CRM's ID
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
                        
                        # Handle additional fields
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
        """Push attendance records to PythonAnywhere - now supports batch"""
        result = {
            'processed': 0,
            'succeeded': 0,
            'failed': 0,
            'errors': []
        }
        
        # Group records by date for potential batching
        records_to_sync = [r for r in attendance_records if not r.synced and r.sync_attempts < 3]
        
        if not records_to_sync:
            return result
        
        # Use batch endpoint if available (preferred)
        if len(records_to_sync) > 1:
            return self._sync_attendance_batch(records_to_sync)
        
        # Individual sync for single records
        for record in records_to_sync:
            result['processed'] += 1
            
            try:
                member = record.member
                
                if not member.remote_id:
                    error_msg = f"Member {member.full_name} has no remote ID"
                    self._mark_record_failed(record, error_msg)
                    result['errors'].append(error_msg)
                    result['failed'] += 1
                    continue
                
                data = {
                    'member_id': member.remote_id,
                    'date': record.session_date.isoformat(),
                    'check_in_time': record.check_in_time.isoformat() if record.check_in_time else None,
                    'method': record.check_in_method,
                    'notes': record.notes or '',
                    'confidence': record.confidence_score,
                    'local_attendance_id': record.id  # Help CRM track duplicates
                }
                
                # Fix: Use the correct endpoint - PiAttendanceCompat
                response = self._make_request('POST', '/attendance/', json=data)
                
                if response.status_code in [200, 201]:
                    self._mark_record_success(record, response)
                    result['succeeded'] += 1
                    logger.info(f"Synced attendance for {member.full_name}")
                    
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    self._mark_record_failed(record, error_msg)
                    result['failed'] += 1
                    result['errors'].append(error_msg)
                    
            except Exception as e:
                self._mark_record_failed(record, str(e))
                result['failed'] += 1
                result['errors'].append(str(e))
        
        return result
    
    def _sync_attendance_batch(self, records):
        """Sync multiple attendance records in one batch"""
        result = {
            'processed': len(records),
            'succeeded': 0,
            'failed': 0,
            'errors': []
        }
        
        # Prepare batch payload
        batch_data = []
        for record in records:
            if not record.member.remote_id:
                result['failed'] += 1
                result['errors'].append(f"Member {record.member.full_name} has no remote ID")
                continue
                
            batch_data.append({
                'member_id': record.member.remote_id,
                'date': record.session_date.isoformat(),
                'check_in_time': record.check_in_time.isoformat() if record.check_in_time else None,
                'method': record.check_in_method,
                'notes': record.notes or '',
                'confidence': record.confidence_score,
                'local_attendance_id': record.id
            })
        
        if not batch_data:
            return result
        
        try:
            # Use the batch endpoint
            response = self._make_request('POST', '/sync/attendance/', json=batch_data)
            
            if response.status_code == 201:
                response_data = response.json()
                
                # Map results back to local records
                for item in response_data.get('results', []):
                    try:
                        record = LocalAttendance.objects.get(id=item.get('local_id'))
                        if 'error' not in item:
                            self._mark_record_success(record, response=None, crm_id=item.get('crm_id'))
                            result['succeeded'] += 1
                        else:
                            self._mark_record_failed(record, item['error'])
                            result['failed'] += 1
                            result['errors'].append(item['error'])
                    except LocalAttendance.DoesNotExist:
                        pass
                        
                logger.info(f"Batch sync complete: {response_data.get('created', 0)} created, {response_data.get('updated', 0)} updated")
            else:
                # Fall back to individual sync
                for record in records:
                    self._mark_record_failed(record, "Batch sync failed, will retry individually")
                result['failed'] = len(records)
                
        except Exception as e:
            for record in records:
                self._mark_record_failed(record, str(e))
            result['failed'] = len(records)
            result['errors'].append(str(e))
        
        return result
    
    def _mark_record_success(self, record, response=None, crm_id=None):
        """Mark a record as successfully synced"""
        record.synced = True
        record.sync_error = None
        record.sync_attempts += 1
        record.last_sync_attempt = timezone.now()
        
        if response:
            try:
                response_data = response.json()
                if 'id' in response_data:
                    record.remote_attendance_id = response_data['id']
            except:
                pass
        elif crm_id:
            record.remote_attendance_id = crm_id
            
        record.save()
    
    def _mark_record_failed(self, record, error_msg):
        """Mark a record as failed and prepare for retry"""
        record.sync_error = error_msg
        record.sync_attempts += 1
        record.last_sync_attempt = timezone.now()
        record.save()
        
        if record.sync_attempts < 3:
            # Schedule for next sync
            record.next_sync_attempt = timezone.now() + timedelta(minutes=5)
            record.save()
    
    def test_connection(self):
        """Test the API connection by fetching members (requires valid token)"""
        try:
            # Try to fetch members - this will test both connection and token validity
            response = requests.get(
                f"{self.api_base}/members/",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                members = response.json()
                print(f"✅ Connection successful! Found {len(members)} members")
                return True
            elif response.status_code == 401:
                print("❌ Authentication failed - your API token may be invalid")
                print("   Get a new token with: python manage.py get_api_token")
                return False
            else:
                print(f"❌ Connection failed: {response.status_code}")
                print(response.text[:200])
                return False
                
        except requests.exceptions.ConnectionError:
            print("❌ Connection error - cannot reach the server")
            print(f"   Check that {self.base_url} is correct and accessible")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def get_new_token(self, username, password):
        """Get a new API token using username/password"""
        try:
            response = requests.post(
                f"{self.api_base}/token/obtain/",  # Note: /obtain/ is needed
                json={
                    'username': username,
                    'password': password
                },
                timeout=10
            )
            
            if response.status_code == 200:
                token = response.json().get('token')
                print(f"✅ New token obtained: {token[:20]}...")
                return token
            else:
                print(f"❌ Failed to get token: {response.status_code}")
                print(response.text)
                return None
                
        except Exception as e:
            print(f"❌ Error getting token: {e}")
            return None
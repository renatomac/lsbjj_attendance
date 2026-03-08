from django.core.management.base import BaseCommand
from sync.sync_client import PythonAnywhereSync  
from attendance_app.models import SyncLog
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sync members from PythonAnywhere'
    
    def add_arguments(self, parser):
        parser.add_argument('--full', action='store_true', help='Perform full sync')
    
    def handle(self, *args, **options):
        self.stdout.write('Starting member sync...')
        
        sync_log = SyncLog.objects.create(
            sync_type='members',
            status='running'
        )
        
        try:
            sync_client = PythonAnywhereSync()
            result = sync_client.sync_members(full=options['full'])
            
            sync_log.records_processed = result.get('processed', 0)
            sync_log.records_succeeded = result.get('succeeded', 0)
            sync_log.records_failed = result.get('failed', 0)
            sync_log.status = 'success'
            sync_log.details = result
            
            self.stdout.write(self.style.SUCCESS(
                f'Sync complete: {result.get("succeeded", 0)} members synced'
            ))
            
        except Exception as e:
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            self.stdout.write(self.style.ERROR(f'Sync failed: {e}'))
        
        sync_log.end_time = timezone.now()
        sync_log.save()
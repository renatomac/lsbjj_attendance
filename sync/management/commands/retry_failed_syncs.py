from django.core.management.base import BaseCommand
from django.utils import timezone
from attendance_app.models import LocalAttendance
from sync.sync_client import PythonAnywhereSync
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Retry failed attendance syncs'
    
    def handle(self, *args, **options):
        self.stdout.write('Checking for failed syncs...')
        
        # Find records that need retry
        failed_records = LocalAttendance.objects.filter(
            synced=False,
            sync_attempts__lt=3,
            next_sync_attempt__lte=timezone.now()
        )[:50]  # Process in batches
        
        if not failed_records:
            self.stdout.write('No failed records to retry')
            return
        
        self.stdout.write(f'Retrying {failed_records.count()} records...')
        
        sync_client = PythonAnywhereSync()
        result = sync_client.sync_attendance(failed_records)
        
        self.stdout.write(self.style.SUCCESS(
            f'Retry complete: {result["succeeded"]} succeeded, {result["failed"]} failed'
        ))
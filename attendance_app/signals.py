from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import LocalMember, LocalAttendance

# Add your signal handlers here
# For example:

@receiver(post_save, sender=LocalMember)
def member_saved(sender, instance, created, **kwargs):
    """Handle member save events"""
    if created:
        print(f"New member created: {instance}")
    # Add your logic here

@receiver(post_save, sender=LocalAttendance)
def attendance_saved(sender, instance, created, **kwargs):
    """Handle attendance save events"""
    if created:
        print(f"New attendance recorded: {instance}")
    # Add your logic here

# You can add more signals as needed
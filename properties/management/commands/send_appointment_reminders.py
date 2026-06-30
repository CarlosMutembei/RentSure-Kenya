import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from properties.models import ViewingAppointment

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Send email/SMS reminders for confirmed viewings within 24 hours'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate sending reminders without actually sending',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        now = timezone.now()
        tomorrow = now + timedelta(hours=24)

        # Find confirmed appointments that:
        # - are not yet reminded
        # - have preferred_date and preferred_time in the future (or today within the next 24h)
        # - not already checked in
        appointments = ViewingAppointment.objects.filter(
            status='confirmed',
            reminder_sent=False,
            checked_in=False,
        ).exclude(
            preferred_date__lt=now.date(),
        )

        # Further filter by time: only those within the next 24 hours
        upcoming = []
        for app in appointments:
            # Combine date and time (naive)
            naive_datetime = timezone.datetime.combine(app.preferred_date, app.preferred_time)
            # Make it timezone-aware using the current timezone
            app_datetime = timezone.make_aware(naive_datetime, timezone.get_current_timezone())
            if app_datetime >= now and app_datetime <= tomorrow:
                upcoming.append(app)

        self.stdout.write(f"Found {len(upcoming)} appointments needing reminders.")

        for app in upcoming:
            self.send_reminder(app, dry_run)
            if not dry_run:
                app.reminder_sent = True
                app.save()
                self.stdout.write(f"Reminder sent for appointment {app.id} (tenant: {app.tenant.email})")
            else:
                self.stdout.write(f"DRY RUN: would send reminder for appointment {app.id}")

    def send_reminder(self, appointment, dry_run=False):
        tenant_email = appointment.tenant.email
        property_title = appointment.property.title
        address = appointment.property.address_text
        date_str = appointment.preferred_date.strftime('%A, %B %d, %Y')
        time_str = appointment.preferred_time.strftime('%I:%M %p')

        subject = f"Upcoming Viewing: {property_title}"
        message = f"""
Dear {appointment.tenant.username},

This is a reminder for your viewing appointment at:

🏠 {property_title}
📍 {address}
📅 {date_str} at {time_str}

Please arrive on time. Use the QR code available in your dashboard for quick check‑in.

If you need to cancel or reschedule, log in to your RentSure dashboard.

Best,
RentSure Team
"""

        if dry_run:
            self.stdout.write(f"Would send email to {tenant_email}")
            return

        # Send email
        try:
            send_mail(
                subject=subject,
                message=message.strip(),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[tenant_email],
                fail_silently=False,
            )
            # Optionally send SMS via Africa's Talking
            # self.send_sms(appointment.tenant.phone, message)
        except Exception as e:
            logger.error(f"Failed to send reminder for appointment {appointment.id}: {e}")
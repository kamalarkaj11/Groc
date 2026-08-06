"""
Management command to migrate phone numbers from Profile to UserProfile for existing users.

This fixes the issue where users who signed up with phone numbers before the sync signal
was added may have empty UserProfile.phone_number fields.

Usage:
    python manage.py migrate_phone_numbers
    python manage.py migrate_phone_numbers --dry-run
    python manage.py migrate_phone_numbers --user-id 123
"""
import logging
from django.core.management.base import BaseCommand
from django.db.models import Q
from store.models import UserProfile, Profile

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate phone numbers from Profile to UserProfile for existing users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without making changes',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Migrate only a specific user by ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        user_id = options['user_id']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Build base queryset
        user_profiles = UserProfile.objects.select_related('user', 'user__phone_profile')

        if user_id:
            user_profiles = user_profiles.filter(user_id=user_id)
            self.stdout.write(f'Migrating phone number for user ID: {user_id}')
        else:
            # Find UserProfiles where phone_number is empty/null but Profile has a valid phone
            user_profiles = user_profiles.filter(
                Q(phone_number__isnull=True) | Q(phone_number='')
            )

        total_count = user_profiles.count()
        self.stdout.write(f'Found {total_count} UserProfile(s) to check')

        migrated = 0
        skipped = 0
        errors = 0

        for user_profile in user_profiles:
            user = user_profile.user
            phone_profile = getattr(user, 'phone_profile', None)

            if not phone_profile:
                skipped += 1
                logger.info(f'Skipped user {user.id}: no Profile exists')
                continue

            profile_phone = phone_profile.phone_number

            if not profile_phone or profile_phone == 'pending':
                skipped += 1
                logger.info(f'Skipped user {user.id}: Profile has no valid phone number')
                continue

            # Check if UserProfile already has this phone (shouldn't happen, but safety check)
            if user_profile.phone_number == profile_phone:
                skipped += 1
                logger.info(f'Skipped user {user.id}: UserProfile already has phone number')
                continue

            # Migrate the phone number
            if dry_run:
                self.stdout.write(
                    f'Would migrate: User {user.id} ({user.username}) - {profile_phone}'
                )
            else:
                try:
                    user_profile.phone_number = profile_phone
                    user_profile.save(update_fields=['phone_number'])
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Migrated: User {user.id} ({user.username}) - {profile_phone}'
                        )
                    )
                    migrated += 1
                except Exception as exc:
                    self.stdout.write(
                        self.style.ERROR(
                            f'Error migrating user {user.id}: {exc}'
                        )
                    )
                    errors += 1

        # Summary
        self.stdout.write('')
        self.stdout.write('=' * 60)
        if dry_run:
            self.stdout.write(f'DRY RUN SUMMARY:')
            self.stdout.write(f'  Would migrate: {total_count - skipped}')
        else:
            self.stdout.write(f'MIGRATION SUMMARY:')
            self.stdout.write(f'  Migrated: {migrated}')
        self.stdout.write(f'  Skipped: {skipped}')
        self.stdout.write(f'  Errors: {errors}')
        self.stdout.write(f'  Total checked: {total_count}')
        self.stdout.write('=' * 60)

        if dry_run and total_count - skipped > 0:
            self.stdout.write('')
            self.stdout.write(
                self.style.WARNING(
                    'Run without --dry-run to apply these changes'
                )
            )
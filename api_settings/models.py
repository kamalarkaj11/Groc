import logging
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.signing import Signer, BadSignature

logger = logging.getLogger("api_settings")

signer = Signer()


class APIKeyCategory(models.TextChoices):
    MOVIES = 'movies', 'Movies'
    GROCERY = 'grocery', 'Grocery'
    PAYMENT = 'payment', 'Payment'
    EMAIL = 'email', 'Email'
    OTP = 'otp', 'OTP'
    MAPS = 'maps', 'Maps'
    WEATHER = 'weather', 'Weather'
    CUSTOM = 'custom', 'Custom'


class APIKeyStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    INACTIVE = 'inactive', 'Inactive'


class ConnectionStatus(models.TextChoices):
    UNKNOWN = 'unknown', 'Unknown'
    CONNECTED = 'connected', 'Connected'
    FAILED = 'failed', 'Failed'
    TIMEOUT = 'timeout', 'Timeout'
    UNAVAILABLE = 'unavailable', 'Service Unavailable'
    AUTH_FAILED = 'auth_failed', 'Authentication Failed'


class APIKey(models.Model):
    """Model to store encrypted API keys with metadata."""
    name = models.CharField(max_length=200, help_text="API name for identification")
    provider = models.CharField(max_length=200, help_text="API provider name")
    api_key_encrypted = models.TextField(help_text="Encrypted API key")
    base_url = models.URLField(max_length=500, help_text="API base URL")
    category = models.CharField(
        max_length=20,
        choices=APIKeyCategory.choices,
        default=APIKeyCategory.CUSTOM,
    )
    status = models.CharField(
        max_length=10,
        choices=APIKeyStatus.choices,
        default=APIKeyStatus.ACTIVE,
    )
    connection_status = models.CharField(
        max_length=20,
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.UNKNOWN,
    )
    is_deleted = models.BooleanField(default=False, help_text="Soft delete flag")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_tested = models.DateTimeField(null=True, blank=True)
    request_count = models.PositiveIntegerField(default=0, help_text="Number of API requests made")
    error_count = models.PositiveIntegerField(default=0, help_text="Number of API errors")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='api_keys_created',
    )
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='api_keys_updated',
    )

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['category', 'status']),
            models.Index(fields=['is_deleted']),
        ]

    def __str__(self):
        return f"{self.name} ({self.provider})"

    def set_api_key(self, raw_key):
        """Encrypt and store the API key."""
        self.api_key_encrypted = signer.sign(raw_key)

    def get_api_key(self):
        """Decrypt and return the API key."""
        try:
            return signer.unsign(self.api_key_encrypted)
        except BadSignature:
            return None

    def get_masked_key(self):
        """Return a masked version of the API key."""
        raw_key = self.get_api_key()
        if not raw_key:
            return "************"
        if len(raw_key) <= 4:
            return "****"
        return "*" * (len(raw_key) - 4) + raw_key[-4:]

    def increment_request_count(self):
        """Increment the request count."""
        self.request_count += 1
        self.save(update_fields=['request_count'])

    def increment_error_count(self):
        """Increment the error count."""
        self.error_count += 1
        self.save(update_fields=['error_count'])

    def soft_delete(self):
        """Soft delete the API key."""
        self.is_deleted = True
        self.save(update_fields=['is_deleted'])

    def restore(self):
        """Restore a soft-deleted API key."""
        self.is_deleted = False
        self.save(update_fields=['is_deleted'])


class APIKeyActivityLog(models.Model):
    """Log of all API key related activities."""
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('restore', 'Restore'),
        ('test', 'Test Connection'),
        ('view_key', 'View Key'),
        ('toggle_status', 'Toggle Status'),
        ('export', 'Export'),
    ]

    api_key = models.ForeignKey(
        APIKey, on_delete=models.CASCADE, related_name='activity_logs',
        null=True, blank=True,
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['action', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.action} - {self.user} - {self.timestamp}"


class APIKeyErrorLog(models.Model):
    """Error log for API key related errors."""
    api_key = models.ForeignKey(
        APIKey, on_delete=models.CASCADE, related_name='error_logs',
        null=True, blank=True,
    )
    error_message = models.TextField()
    status_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Error {self.status_code} - {self.timestamp}"
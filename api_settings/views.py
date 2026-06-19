import csv
import logging
import requests

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views import View
from django.utils import timezone
from django.db.models import Q
from django.contrib import messages

from .models import (
    APIKey, APIKeyActivityLog, APIKeyErrorLog,
    APIKeyCategory, APIKeyStatus, ConnectionStatus,
)
from .forms import APIKeyForm

logger = logging.getLogger("api_settings")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_superuser(user):
    return user.is_authenticated and user.is_superuser


def superuser_required(view_func):
    decorated = user_passes_test(is_superuser, login_url="/", redirect_field_name=None)(view_func)
    return decorated


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_activity(user, api_key, action, description="", request=None):
    """Log an API key activity."""
    ip = get_client_ip(request) if request else None
    APIKeyActivityLog.objects.create(
        api_key=api_key,
        user=user,
        action=action,
        description=description,
        ip_address=ip,
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class APISettingsDashboardView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Main API Settings dashboard with list, stats, search, and filter."""

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request):
        # Query params for search & filter
        search = request.GET.get('search', '').strip()
        category = request.GET.get('category', '').strip()
        status = request.GET.get('status', '').strip()
        conn_status = request.GET.get('conn_status', '').strip()

        qs = APIKey.objects.filter(is_deleted=False)

        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(provider__icontains=search) |
                Q(base_url__icontains=search)
            )
        if category:
            qs = qs.filter(category=category)
        if status:
            qs = qs.filter(status=status)
        if conn_status:
            qs = qs.filter(connection_status=conn_status)

        # Stats
        all_keys = APIKey.objects.filter(is_deleted=False)
        stats = {
            'total': all_keys.count(),
            'active': all_keys.filter(status=APIKeyStatus.ACTIVE).count(),
            'inactive': all_keys.filter(status=APIKeyStatus.INACTIVE).count(),
            'failed': all_keys.filter(connection_status=ConnectionStatus.FAILED).count(),
            'connected': all_keys.filter(connection_status=ConnectionStatus.CONNECTED).count(),
        }

        context = {
            'api_keys': qs,
            'stats': stats,
            'search': search,
            'category': category,
            'status': status,
            'conn_status': conn_status,
            'categories': APIKeyCategory.choices,
            'statuses': APIKeyStatus.choices,
            'connection_statuses': ConnectionStatus.choices,
        }
        return render(request, 'api_settings.html', context)


# ---------------------------------------------------------------------------
# Add API Key
# ---------------------------------------------------------------------------

class APIKeyCreateView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Add a new API key."""

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request):
        form = APIKeyForm()
        return render(request, 'api_settings_form.html', {'form': form, 'action': 'Add'})

    def post(self, request):
        form = APIKeyForm(request.POST)
        if form.is_valid():
            api_key = form.save(commit=False)
            api_key.created_by = request.user
            api_key.updated_by = request.user
            api_key.save()
            log_activity(request.user, api_key, 'create', f"Created API key: {api_key.name}", request)
            messages.success(request, f'API key "{api_key.name}" created successfully.')
            return redirect('api_settings:api_settings_page')
        return render(request, 'api_settings_form.html', {'form': form, 'action': 'Add'})


# ---------------------------------------------------------------------------
# Edit API Key
# ---------------------------------------------------------------------------

class APIKeyUpdateView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Edit an existing API key."""

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request, pk):
        api_key = get_object_or_404(APIKey, pk=pk, is_deleted=False)
        form = APIKeyForm(instance=api_key)
        return render(request, 'api_settings_form.html', {
            'form': form, 'action': 'Edit', 'api_key': api_key,
        })

    def post(self, request, pk):
        api_key = get_object_or_404(APIKey, pk=pk, is_deleted=False)
        form = APIKeyForm(request.POST, instance=api_key)
        if form.is_valid():
            api_key = form.save(commit=False)
            api_key.updated_by = request.user
            api_key.save()
            log_activity(request.user, api_key, 'update', f"Updated API key: {api_key.name}", request)
            messages.success(request, f'API key "{api_key.name}" updated successfully.')
            return redirect('api_settings:api_settings_page')
        return render(request, 'api_settings_form.html', {
            'form': form, 'action': 'Edit', 'api_key': api_key,
        })


# ---------------------------------------------------------------------------
# Delete API Key (Soft Delete)
# ---------------------------------------------------------------------------

class APIKeyDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Soft delete an API key."""

    def test_func(self):
        return self.request.user.is_superuser

    def post(self, request, pk):
        api_key = get_object_or_404(APIKey, pk=pk, is_deleted=False)
        api_key.soft_delete()
        log_activity(request.user, api_key, 'delete', f"Soft deleted API key: {api_key.name}", request)
        messages.success(request, f'API key "{api_key.name}" deleted successfully.')
        return redirect('api_settings:api_settings_page')


# ---------------------------------------------------------------------------
# Restore API Key
# ---------------------------------------------------------------------------

class APIKeyRestoreView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Restore a soft-deleted API key."""

    def test_func(self):
        return self.request.user.is_superuser

    def post(self, request, pk):
        api_key = get_object_or_404(APIKey, pk=pk, is_deleted=True)
        api_key.restore()
        log_activity(request.user, api_key, 'restore', f"Restored API key: {api_key.name}", request)
        messages.success(request, f'API key "{api_key.name}" restored successfully.')
        return redirect('api_settings:api_settings_page')


# ---------------------------------------------------------------------------
# Toggle Status
# ---------------------------------------------------------------------------

class APIKeyToggleStatusView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Toggle API key active/inactive status."""

    def test_func(self):
        return self.request.user.is_superuser

    def post(self, request, pk):
        api_key = get_object_or_404(APIKey, pk=pk, is_deleted=False)
        if api_key.status == APIKeyStatus.ACTIVE:
            api_key.status = APIKeyStatus.INACTIVE
            new_status = 'Inactive'
        else:
            api_key.status = APIKeyStatus.ACTIVE
            new_status = 'Active'
        api_key.updated_by = request.user
        api_key.save(update_fields=['status', 'updated_by'])
        log_activity(request.user, api_key, 'toggle_status', f"Changed status to {new_status}", request)
        return JsonResponse({'success': True, 'status': api_key.status})


# ---------------------------------------------------------------------------
# Test Connection
# ---------------------------------------------------------------------------

class APIKeyTestConnectionView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Test connection for a specific API key."""

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request, pk):
        api_key = get_object_or_404(APIKey, pk=pk, is_deleted=False)
        raw_key = api_key.get_api_key()
        base_url = api_key.base_url

        if not raw_key or not base_url:
            api_key.connection_status = ConnectionStatus.FAILED
            api_key.save(update_fields=['connection_status'])
            log_activity(request.user, api_key, 'test', "Test failed: Missing key or URL", request)
            return JsonResponse({
                'success': False,
                'status': 'failed',
                'message': 'API key or base URL not configured.',
                'status_code': None,
                'timestamp': timezone.now().isoformat(),
            })

        try:
            response = requests.get(
                base_url,
                headers={'Authorization': f'Bearer {raw_key}', 'x-api-key': raw_key},
                timeout=15,
            )
            status_code = response.status_code

            if status_code == 200:
                conn_status = ConnectionStatus.CONNECTED
                message = 'Connected'
                success = True
            elif status_code == 401 or status_code == 403:
                conn_status = ConnectionStatus.AUTH_FAILED
                message = 'Authentication Failed'
                success = False
            elif status_code == 404:
                conn_status = ConnectionStatus.UNAVAILABLE
                message = 'Service Unavailable'
                success = False
            elif status_code == 429:
                conn_status = ConnectionStatus.FAILED
                message = 'Rate limit exceeded'
                success = False
            else:
                conn_status = ConnectionStatus.FAILED
                message = f'Unexpected status: {status_code}'
                success = False

            api_key.connection_status = conn_status
            api_key.last_tested = timezone.now()
            api_key.save(update_fields=['connection_status', 'last_tested'])

            log_activity(request.user, api_key, 'test', f"Test result: {message} (HTTP {status_code})", request)

            return JsonResponse({
                'success': success,
                'status': conn_status,
                'message': message,
                'status_code': status_code,
                'timestamp': timezone.now().isoformat(),
            })

        except requests.Timeout:
            api_key.connection_status = ConnectionStatus.TIMEOUT
            api_key.last_tested = timezone.now()
            api_key.save(update_fields=['connection_status', 'last_tested'])
            log_activity(request.user, api_key, 'test', "Test failed: Timeout", request)
            return JsonResponse({
                'success': False,
                'status': 'timeout',
                'message': 'Connection timed out.',
                'status_code': None,
                'timestamp': timezone.now().isoformat(),
            })
        except requests.ConnectionError:
            api_key.connection_status = ConnectionStatus.UNAVAILABLE
            api_key.last_tested = timezone.now()
            api_key.save(update_fields=['connection_status', 'last_tested'])
            log_activity(request.user, api_key, 'test', "Test failed: Connection error", request)
            return JsonResponse({
                'success': False,
                'status': 'unavailable',
                'message': 'Service Unavailable.',
                'status_code': None,
                'timestamp': timezone.now().isoformat(),
            })
        except requests.RequestException as exc:
            api_key.connection_status = ConnectionStatus.FAILED
            api_key.last_tested = timezone.now()
            api_key.save(update_fields=['connection_status', 'last_tested'])
            log_activity(request.user, api_key, 'test', f"Test failed: {exc}", request)
            return JsonResponse({
                'success': False,
                'status': 'failed',
                'message': f'Request error: {exc}',
                'status_code': None,
                'timestamp': timezone.now().isoformat(),
            })


# ---------------------------------------------------------------------------
# Reveal Key (superuser only)
# ---------------------------------------------------------------------------

class APIKeyRevealView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Reveal the full API key (superuser only)."""

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request, pk):
        api_key = get_object_or_404(APIKey, pk=pk, is_deleted=False)
        raw_key = api_key.get_api_key()
        log_activity(request.user, api_key, 'view_key', "Revealed API key", request)
        return JsonResponse({'success': True, 'key': raw_key})


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

class APIKeyExportView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Export API keys to CSV."""

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request):
        api_keys = APIKey.objects.filter(is_deleted=False)
        log_activity(request.user, None, 'export', f"Exported {api_keys.count()} API keys", request)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="api_keys_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Name', 'Provider', 'API Key (Masked)', 'Base URL',
            'Category', 'Status', 'Connection Status', 'Last Tested',
            'Request Count', 'Error Count', 'Created At', 'Updated At',
        ])
        for key in api_keys:
            writer.writerow([
                key.id, key.name, key.provider, key.get_masked_key(),
                key.base_url, key.get_category_display(), key.get_status_display(),
                key.get_connection_status_display(),
                key.last_tested.strftime('%Y-%m-%d %H:%M:%S') if key.last_tested else 'Never',
                key.request_count, key.error_count,
                key.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                key.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            ])

        return response


# ---------------------------------------------------------------------------
# Activity Log
# ---------------------------------------------------------------------------

class APIKeyActivityLogView(LoginRequiredMixin, UserPassesTestMixin, View):
    """View activity logs for API keys."""

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request):
        logs = APIKeyActivityLog.objects.select_related('api_key', 'user')[:100]
        return render(request, 'api_settings_activity.html', {'logs': logs})


# ---------------------------------------------------------------------------
# Error Log
# ---------------------------------------------------------------------------

class APIKeyErrorLogView(LoginRequiredMixin, UserPassesTestMixin, View):
    """View error logs for API keys."""

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request):
        errors = APIKeyErrorLog.objects.select_related('api_key')[:100]
        return render(request, 'api_settings_errors.html', {'errors': errors})


# ---------------------------------------------------------------------------
# API Status (JSON)
# ---------------------------------------------------------------------------

class APIKeyStatusView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Get API status as JSON."""

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request):
        api_keys = APIKey.objects.filter(is_deleted=False)
        data = []
        for key in api_keys:
            data.append({
                'id': key.id,
                'name': key.name,
                'provider': key.provider,
                'status': key.status,
                'connection_status': key.connection_status,
                'masked_key': key.get_masked_key(),
                'base_url': key.base_url,
                'category': key.category,
                'last_tested': key.last_tested.isoformat() if key.last_tested else None,
                'request_count': key.request_count,
                'error_count': key.error_count,
            })
        return JsonResponse({'apis': data})


# ---------------------------------------------------------------------------
# Legacy views (kept for backward compatibility)
# ---------------------------------------------------------------------------

# Legacy views removed — all routes use class-based views above.
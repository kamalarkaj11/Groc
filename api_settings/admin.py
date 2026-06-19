from django.contrib import admin
from .models import APIKey, APIKeyActivityLog, APIKeyErrorLog


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ['name', 'provider', 'category', 'status', 'connection_status', 'updated_at']
    list_filter = ['category', 'status', 'connection_status', 'is_deleted']
    search_fields = ['name', 'provider', 'base_url']
    readonly_fields = ['api_key_encrypted', 'created_at', 'updated_at', 'last_tested']


@admin.register(APIKeyActivityLog)
class APIKeyActivityLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'user', 'api_key', 'timestamp']
    list_filter = ['action']
    readonly_fields = ['timestamp']


@admin.register(APIKeyErrorLog)
class APIKeyErrorLogAdmin(admin.ModelAdmin):
    list_display = ['api_key', 'status_code', 'timestamp']
    readonly_fields = ['timestamp']

from django.urls import path
from . import views

app_name = "api_settings"

urlpatterns = [
    # Dashboard
    path("", views.APISettingsDashboardView.as_view(), name="api_settings_page"),

    # CRUD
    path("add/", views.APIKeyCreateView.as_view(), name="api_key_add"),
    path("<int:pk>/edit/", views.APIKeyUpdateView.as_view(), name="api_key_edit"),
    path("<int:pk>/delete/", views.APIKeyDeleteView.as_view(), name="api_key_delete"),
    path("<int:pk>/restore/", views.APIKeyRestoreView.as_view(), name="api_key_restore"),

    # Actions
    path("<int:pk>/toggle-status/", views.APIKeyToggleStatusView.as_view(), name="api_key_toggle_status"),
    path("<int:pk>/test/", views.APIKeyTestConnectionView.as_view(), name="api_key_test"),
    path("<int:pk>/reveal/", views.APIKeyRevealView.as_view(), name="api_key_reveal"),

    # Export
    path("export/csv/", views.APIKeyExportView.as_view(), name="api_key_export"),

    # Logs
    path("activity/", views.APIKeyActivityLogView.as_view(), name="api_key_activity"),
    path("errors/", views.APIKeyErrorLogView.as_view(), name="api_key_errors"),

    # Status JSON
    path("status/", views.APIKeyStatusView.as_view(), name="api_status"),
]
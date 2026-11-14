"""
URL configuration for monitoring project.
"""
from django.contrib import admin
from django.urls import include, path

from monitor_app.views import (
    ActiveAlerts,
    DashboardView,
    LatestRecordFetch,
    MetricsFetch,
    MetricsPush,
    ThresholdCreateView,
    ThresholdDeleteView,
    ThresholdListView,
    ThresholdUpdateView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('api/v1/metrics/push/', MetricsPush.as_view(), name="metrics_push"),
    path('dashboard/', DashboardView, name='dashboard'),
    path('thresholds/', ThresholdListView.as_view(), name='threshold-list'),
    path('thresholds/add/', ThresholdCreateView.as_view(), name='threshold-add'),
    path('thresholds/<int:pk>/edit/', ThresholdUpdateView.as_view(), name='threshold-edit'),
    path('thresholds/<int:pk>/delete/', ThresholdDeleteView.as_view(), name='threshold-delete'),
    path('api/v1/metrics/timeseries/', MetricsFetch.as_view(), name='metrics-fetch-api'),
    path('api/v1/metrics/latest/', LatestRecordFetch.as_view(), name='latest-record-fetch-api'),
    path('api/v1/alerts/active/', ActiveAlerts.as_view(), name='active-alerts-api'),
]

from django.urls import path
from . import views

urlpatterns = [
    path("tenants/<slug:tenant_slug>/records/", views.list_records, name="records-list"),
    path("tenants/<slug:tenant_slug>/records/<uuid:record_id>/", views.record_detail, name="record-detail"),
    path("tenants/<slug:tenant_slug>/stats/", views.dashboard_stats, name="stats"),
]

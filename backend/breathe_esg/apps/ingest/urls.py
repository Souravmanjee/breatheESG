from django.urls import path
from . import views

urlpatterns = [
    path("tenants/<slug:tenant_slug>/upload/", views.upload_file, name="upload"),
    path("tenants/<slug:tenant_slug>/ingestion-runs/", views.list_ingestion_runs, name="ingestion-runs"),
]

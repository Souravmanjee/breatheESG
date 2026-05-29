from django.urls import path
from . import views

urlpatterns = [
    path("tenants/<slug:tenant_slug>/records/<uuid:record_id>/review/", views.review_action, name="review-action"),
    path("tenants/<slug:tenant_slug>/bulk-review/", views.bulk_review, name="bulk-review"),
]

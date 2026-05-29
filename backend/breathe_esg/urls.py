from django.contrib import admin
from django.urls import path, include
from breathe_esg import admin as _  # noqa: F401 — registers all models
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("breathe_esg.apps.tenants.urls")),
    path("api/", include("breathe_esg.apps.ingest.urls")),
    path("api/", include("breathe_esg.apps.emissions.urls")),
    path("api/", include("breathe_esg.apps.review.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

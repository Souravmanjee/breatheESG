from django.contrib import admin
from django.urls import path, include
from breathe_esg import admin as _  # noqa: F401 — registers all models
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.db import connection

def health_check(request):
    try:
        connection.ensure_connection()
        return JsonResponse({"status": "healthy", "database": "connected"})
    except Exception as e:
        return JsonResponse({"status": "unhealthy", "error": str(e)}, status=500)

urlpatterns = [
    path("api/health/", health_check),
    path("admin/", admin.site.urls),
    path("api/auth/", include("breathe_esg.apps.tenants.urls")),
    path("api/", include("breathe_esg.apps.ingest.urls")),
    path("api/", include("breathe_esg.apps.emissions.urls")),
    path("api/", include("breathe_esg.apps.review.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


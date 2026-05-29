from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from breathe_esg.apps.tenants.models import Tenant, TenantMembership


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get("username")
    password = request.data.get("password")
    user = authenticate(username=username, password=password)
    if not user:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    token, _ = Token.objects.get_or_create(user=user)
    memberships = TenantMembership.objects.filter(user=user).select_related("tenant")

    return Response({
        "token": token.key,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
        "tenants": [
            {
                "id": str(m.tenant.id),
                "name": m.tenant.name,
                "slug": m.tenant.slug,
                "role": m.role,
            }
            for m in memberships
        ],
    })


@api_view(["POST"])
def logout_view(request):
    request.user.auth_token.delete()
    return Response({"message": "Logged out"})


@api_view(["GET"])
def me_view(request):
    memberships = TenantMembership.objects.filter(user=request.user).select_related("tenant")
    return Response({
        "user": {
            "id": request.user.id,
            "username": request.user.username,
            "email": request.user.email,
        },
        "tenants": [
            {
                "id": str(m.tenant.id),
                "name": m.tenant.name,
                "slug": m.tenant.slug,
                "role": m.role,
            }
            for m in memberships
        ],
    })

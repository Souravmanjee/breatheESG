"""
Tenant model - multi-tenancy foundation.

Every data record in the system is scoped to a Tenant. We use a simple
foreign-key approach (row-level tenancy) rather than schema-per-tenant.
Tradeoff: simpler to build and deploy, but requires care to always filter
by tenant in every query. We enforce this via a TenantScopedManager.
"""

from django.db import models
from django.contrib.auth.models import User
import uuid


class Tenant(models.Model):
    """
    An enterprise client of Breathe ESG.
    All data - emission records, ingestion runs, approvals - belongs to one.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)  # used in API paths
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


class TenantMembership(models.Model):
    """
    Links a Django User to a Tenant with a role.
    One user can belong to multiple tenants (e.g., a Breathe ESG analyst).
    """
    ROLE_ANALYST = "analyst"
    ROLE_ADMIN = "admin"
    ROLE_AUDITOR = "auditor"  # read-only, can't approve

    ROLE_CHOICES = [
        (ROLE_ANALYST, "Analyst"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_AUDITOR, "Auditor"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ANALYST)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "tenant")

    def __str__(self):
        return f"{self.user.username} @ {self.tenant.name} ({self.role})"

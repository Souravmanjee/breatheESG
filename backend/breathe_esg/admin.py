from django.contrib import admin
from breathe_esg.apps.tenants.models import Tenant, TenantMembership
from breathe_esg.apps.ingest.models import IngestionRun, RawRow
from breathe_esg.apps.emissions.models import EmissionRecord, EmissionFactor, EmissionRecordEdit


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "created_at"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "role", "joined_at"]
    list_filter = ["tenant", "role"]


@admin.register(IngestionRun)
class IngestionRunAdmin(admin.ModelAdmin):
    list_display = ["tenant", "source_type", "status", "original_filename", "uploaded_by", "uploaded_at", "row_count_parsed", "row_count_failed"]
    list_filter = ["tenant", "source_type", "status"]
    readonly_fields = ["id", "uploaded_at", "started_at", "completed_at"]


@admin.register(EmissionRecord)
class EmissionRecordAdmin(admin.ModelAdmin):
    list_display = ["tenant", "scope", "category", "source_type", "status", "normalized_value_kg_co2e", "activity_date", "is_suspicious"]
    list_filter = ["tenant", "scope", "category", "source_type", "status", "is_suspicious"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "unit", "kg_co2e_per_unit", "source", "valid_from", "valid_to"]


@admin.register(EmissionRecordEdit)
class EmissionRecordEditAdmin(admin.ModelAdmin):
    list_display = ["record", "edited_by", "field_name", "old_value", "new_value", "edited_at"]
    readonly_fields = ["id", "edited_at"]

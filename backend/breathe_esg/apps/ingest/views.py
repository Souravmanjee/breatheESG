"""
Ingest views.

The upload endpoint is the entry point for all data.
It:
1. Creates an IngestionRun
2. Saves the file
3. Runs the appropriate parser synchronously (async via Celery in production)
4. Creates RawRow objects for all rows
5. Creates EmissionRecord objects for successfully parsed rows
6. Returns a summary
"""

from datetime import datetime
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from breathe_esg.apps.tenants.models import Tenant, TenantMembership
from breathe_esg.apps.ingest.models import IngestionRun, RawRow
from breathe_esg.apps.emissions.models import EmissionRecord, EmissionFactor
from breathe_esg.apps.ingest.parsers.sap_parser import parse_sap_file
from breathe_esg.apps.ingest.parsers.utility_parser import parse_utility_file
from breathe_esg.apps.ingest.parsers.travel_parser import parse_travel_file


def get_tenant_or_403(request, tenant_slug):
    """Get tenant if user is a member, else raise 403."""
    try:
        membership = TenantMembership.objects.get(
            user=request.user, tenant__slug=tenant_slug
        )
        return membership.tenant, membership.role
    except TenantMembership.DoesNotExist:
        return None, None


@api_view(["POST"])
def upload_file(request, tenant_slug):
    """
    POST /api/tenants/{tenant_slug}/upload/
    Body: multipart/form-data with fields:
      - file: the CSV/TSV file
      - source_type: "sap" | "utility" | "travel"
      - notes: optional string
      - country_code: optional (for utility, determines emission factor)
    """
    tenant, role = get_tenant_or_403(request, tenant_slug)
    if not tenant:
        return Response({"error": "Not a member of this tenant"}, status=403)

    if role == TenantMembership.ROLE_AUDITOR:
        return Response({"error": "Auditors cannot upload files"}, status=403)

    file_obj = request.FILES.get("file")
    source_type = request.data.get("source_type")
    notes = request.data.get("notes", "")
    country_code = request.data.get("country_code", "DEFAULT")

    if not file_obj:
        return Response({"error": "No file provided"}, status=400)

    if source_type not in ("sap", "utility", "travel"):
        return Response({"error": "source_type must be sap, utility, or travel"}, status=400)

    # Create ingestion run
    run = IngestionRun.objects.create(
        tenant=tenant,
        source_type=source_type,
        status=IngestionRun.STATUS_PARSING,
        original_file=file_obj,
        original_filename=file_obj.name,
        uploaded_by=request.user,
        started_at=timezone.now(),
        notes=notes,
    )

    try:
        file_content = file_obj.read()

        # Parse
        if source_type == "sap":
            parsed_rows = parse_sap_file(file_content, file_obj.name)
        elif source_type == "utility":
            parsed_rows = parse_utility_file(file_content, file_obj.name, country_code)
        else:
            parsed_rows = parse_travel_file(file_content, file_obj.name)

        run.status = IngestionRun.STATUS_PARSED
        run.row_count_total = len(parsed_rows)

        # Create RawRows and EmissionRecords
        created_records = 0
        failed_rows = 0

        for parsed in parsed_rows:
            raw_row = RawRow.objects.create(
                ingestion_run=run,
                row_index=parsed.get("row_index", 0),
                raw_data=parsed.get("raw_data", {}),
                parse_error=parsed.get("parse_error", ""),
            )

            if parsed.get("parse_error"):
                failed_rows += 1
                continue

            # Create EmissionRecord
            try:
                # Look up emission factor
                ef = None
                ef_value = parsed.get("emission_factor_value_used")

                # Try to find an existing emission factor in DB
                category = parsed.get("category", "")
                ef_qs = EmissionFactor.objects.filter(
                    category__icontains=category.replace("fuel_", "").replace("travel_", ""),
                ).order_by("-valid_from").first()

                if ef_qs:
                    ef = ef_qs
                    if not ef_value:
                        ef_value = ef.kg_co2e_per_unit

                # Calculate co2e if not already done by parser
                co2e = parsed.get("normalized_value_kg_co2e")
                if co2e is None and ef_value and parsed.get("normalized_value"):
                    co2e = Decimal(str(parsed["normalized_value"])) * Decimal(str(ef_value))

                EmissionRecord.objects.create(
                    tenant=tenant,
                    ingestion_run=run,
                    source_row=raw_row,
                    source_type=source_type,
                    scope=parsed.get("scope", "1"),
                    category=category,
                    activity_description=parsed.get("activity_description", ""),
                    raw_value=parsed.get("raw_value", 0),
                    raw_unit=parsed.get("raw_unit", ""),
                    normalized_value=parsed.get("normalized_value", 0),
                    normalized_unit=parsed.get("normalized_unit", ""),
                    unit_conversion_factor=parsed.get("unit_conversion_factor", 1),
                    emission_factor=ef,
                    emission_factor_value_used=ef_value,
                    normalized_value_kg_co2e=co2e,
                    activity_date=parsed.get("activity_date"),
                    reporting_period_start=parsed.get("reporting_period_start"),
                    reporting_period_end=parsed.get("reporting_period_end"),
                    location_code=parsed.get("location_code", ""),
                    location_name=parsed.get("location_name", ""),
                    country_code=parsed.get("country_code", ""),
                    source_metadata=parsed.get("source_metadata", {}),
                    is_suspicious=parsed.get("is_suspicious", False),
                    suspicion_reason=parsed.get("suspicion_reason", ""),
                    status=EmissionRecord.STATUS_PENDING,
                )
                created_records += 1
            except Exception as e:
                raw_row.parse_error = f"EmissionRecord creation failed: {e}"
                raw_row.save()
                failed_rows += 1

        run.status = IngestionRun.STATUS_NORMALIZED
        run.row_count_parsed = created_records
        run.row_count_failed = failed_rows
        run.completed_at = timezone.now()
        run.save()

        return Response({
            "ingestion_run_id": str(run.id),
            "status": run.status,
            "total_rows": run.row_count_total,
            "parsed_rows": run.row_count_parsed,
            "failed_rows": run.row_count_failed,
            "message": f"Ingestion complete. {created_records} records created, {failed_rows} rows skipped.",
        }, status=201)

    except Exception as e:
        run.status = IngestionRun.STATUS_FAILED
        run.error_message = str(e)
        run.completed_at = timezone.now()
        run.save()
        return Response({"error": f"Ingestion failed: {e}"}, status=500)


@api_view(["GET"])
def list_ingestion_runs(request, tenant_slug):
    """GET /api/tenants/{tenant_slug}/ingestion-runs/"""
    tenant, role = get_tenant_or_403(request, tenant_slug)
    if not tenant:
        return Response({"error": "Not a member of this tenant"}, status=403)

    runs = IngestionRun.objects.filter(tenant=tenant).order_by("-uploaded_at")[:50]
    return Response([
        {
            "id": str(r.id),
            "source_type": r.source_type,
            "status": r.status,
            "original_filename": r.original_filename,
            "uploaded_by": r.uploaded_by.username if r.uploaded_by else None,
            "uploaded_at": r.uploaded_at.isoformat(),
            "row_count_total": r.row_count_total,
            "row_count_parsed": r.row_count_parsed,
            "row_count_failed": r.row_count_failed,
            "notes": r.notes,
        }
        for r in runs
    ])

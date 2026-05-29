from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from django.db.models import Sum, Count, Q
from rest_framework.decorators import api_view
from rest_framework.response import Response

from breathe_esg.apps.tenants.models import TenantMembership
from breathe_esg.apps.emissions.models import EmissionRecord, EmissionFactor, EmissionRecordEdit


def get_tenant_or_403(request, tenant_slug):
    try:
        membership = TenantMembership.objects.get(
            user=request.user, tenant__slug=tenant_slug
        )
        return membership.tenant, membership.role
    except TenantMembership.DoesNotExist:
        return None, None


def record_to_dict(r):
    return {
        "id": str(r.id),
        "scope": r.scope,
        "scope_display": r.get_scope_display(),
        "category": r.category,
        "category_display": r.get_category_display(),
        "source_type": r.source_type,
        "status": r.status,
        "status_display": r.get_status_display(),
        "activity_description": r.activity_description,
        "raw_value": str(r.raw_value),
        "raw_unit": r.raw_unit,
        "normalized_value": str(r.normalized_value),
        "normalized_unit": r.normalized_unit,
        "normalized_value_kg_co2e": str(r.normalized_value_kg_co2e) if r.normalized_value_kg_co2e else None,
        "activity_date": r.activity_date.isoformat() if r.activity_date else None,
        "reporting_period_start": r.reporting_period_start.isoformat() if r.reporting_period_start else None,
        "reporting_period_end": r.reporting_period_end.isoformat() if r.reporting_period_end else None,
        "location_code": r.location_code,
        "location_name": r.location_name,
        "country_code": r.country_code,
        "source_metadata": r.source_metadata,
        "is_suspicious": r.is_suspicious,
        "suspicion_reason": r.suspicion_reason,
        "reviewed_by": r.reviewed_by.username if r.reviewed_by else None,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "review_notes": r.review_notes,
        "created_at": r.created_at.isoformat(),
        "ingestion_run_id": str(r.ingestion_run_id) if r.ingestion_run_id else None,
    }


@api_view(["GET"])
def list_records(request, tenant_slug):
    """
    GET /api/tenants/{tenant_slug}/records/
    Query params:
      status: pending|approved|locked|flagged|rejected
      scope: 1|2|3
      source_type: sap|utility|travel
      suspicious: true|false
      page: int
    """
    tenant, role = get_tenant_or_403(request, tenant_slug)
    if not tenant:
        return Response({"error": "Not a member of this tenant"}, status=403)

    qs = EmissionRecord.objects.filter(tenant=tenant).select_related(
        "reviewed_by", "ingestion_run"
    )

    # Filters
    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)

    scope_filter = request.query_params.get("scope")
    if scope_filter:
        qs = qs.filter(scope=scope_filter)

    source_filter = request.query_params.get("source_type")
    if source_filter:
        qs = qs.filter(source_type=source_filter)

    suspicious_filter = request.query_params.get("suspicious")
    if suspicious_filter == "true":
        qs = qs.filter(is_suspicious=True)

    total_count = qs.count()
    page = int(request.query_params.get("page", 1))
    page_size = 50
    offset = (page - 1) * page_size
    records = qs.order_by("-activity_date")[offset:offset + page_size]

    return Response({
        "count": total_count,
        "page": page,
        "page_size": page_size,
        "results": [record_to_dict(r) for r in records],
    })


# Unit conversion mappings
UNIT_CONVERSIONS = {
    # SAP / general fuel
    "L": Decimal("1.0"),
    "LT": Decimal("1.0"),
    "GAL": Decimal("3.78541"),
    "KG": Decimal("1.0"),
    "G": Decimal("0.001"),
    "T": Decimal("1000.0"),
    "M3": Decimal("1.0"),
    "FT3": Decimal("0.0283168"),
    # Utility / electricity
    "KWH": Decimal("1.0"),
    "kWh": Decimal("1.0"),
    "WH": Decimal("0.001"),
    "Wh": Decimal("0.001"),
    "MWH": Decimal("1000.0"),
    "MWh": Decimal("1000.0"),
    # Travel
    "KM": Decimal("1.0"),
    "km": Decimal("1.0"),
    "NIGHT": Decimal("1.0"),
    "night": Decimal("1.0"),
}

UNIT_TO_STANDARD = {
    "L": "L", "LT": "L", "GAL": "L",
    "KG": "kg", "G": "kg", "T": "kg",
    "M3": "m3", "FT3": "m3",
    "KWH": "kWh", "kWh": "kWh", "WH": "kWh", "Wh": "kWh", "MWH": "kWh", "MWh": "kWh",
    "KM": "km", "km": "km",
    "NIGHT": "night", "night": "night",
}


def find_emission_factor(category, country_code, normalized_unit, metadata=None):
    db_cat = category.replace("fuel_", "").replace("travel_", "")
    
    if db_cat == "electricity":
        if country_code:
            target = f"electricity_{country_code.lower()}"
        else:
            target = "electricity_default"
    elif db_cat == "flight":
        cabin_class = "economy"
        if metadata and isinstance(metadata, dict):
            cabin_class = metadata.get("cabin_class", "economy").lower()
        if "business" in cabin_class:
            target = "flight_business"
        else:
            target = "flight_economy"
    elif db_cat == "ground":
        target = "taxi"
    else:
        target = db_cat

    # Look up factor
    ef = EmissionFactor.objects.filter(
        category__icontains=target
    ).order_by("-valid_from").first()
    
    if not ef:
        ef = EmissionFactor.objects.filter(
            category__icontains=db_cat
        ).order_by("-valid_from").first()
        
    return ef


@api_view(["GET", "PATCH"])
def record_detail(request, tenant_slug, record_id):
    """GET or PATCH /api/tenants/{tenant_slug}/records/{record_id}/"""
    tenant, role = get_tenant_or_403(request, tenant_slug)
    if not tenant:
        return Response({"error": "Not a member of this tenant"}, status=403)

    try:
        record = EmissionRecord.objects.get(id=record_id, tenant=tenant)
    except EmissionRecord.DoesNotExist:
        return Response({"error": "Not found"}, status=404)

    if request.method == "PATCH":
        if role == TenantMembership.ROLE_AUDITOR:
            return Response({"error": "Auditors cannot edit records"}, status=403)

        if record.status in (EmissionRecord.STATUS_LOCKED, EmissionRecord.STATUS_APPROVED):
            return Response({"error": f"Cannot edit record in {record.status} status"}, status=400)

        data = request.data
        reason = data.get("reason_for_edit", "Manual edit via analyst panel")

        changes = []

        # Update date
        if "activity_date" in data:
            try:
                new_date = datetime.strptime(data["activity_date"], "%Y-%m-%d").date()
                if new_date != record.activity_date:
                    changes.append(("activity_date", record.activity_date, new_date))
                    record.activity_date = new_date
                    record.reporting_period_start = date(new_date.year, 1, 1)
                    record.reporting_period_end = date(new_date.year, 12, 31)
            except (ValueError, TypeError):
                return Response({"error": f"Invalid date format for activity_date: {data['activity_date']}"}, status=400)

        # Update metadata if provided (e.g. flight cabin class)
        metadata_changed = False
        if "source_metadata" in data and isinstance(data["source_metadata"], dict):
            # Merging dicts to preserve other metadata keys
            new_metadata = {**record.source_metadata, **data["source_metadata"]}
            if new_metadata != record.source_metadata:
                changes.append(("source_metadata", record.source_metadata, new_metadata))
                record.source_metadata = new_metadata
                metadata_changed = True

        # Simple updates
        for field in ["location_code", "location_name", "country_code"]:
            if field in data and data[field] != getattr(record, field):
                changes.append((field, getattr(record, field), data[field]))
                setattr(record, field, data[field])

        # Value / unit updates
        value_changed = False
        unit_changed = False

        if "raw_value" in data:
            try:
                new_val = Decimal(str(data["raw_value"]))
                if new_val != record.raw_value:
                    if new_val <= 0:
                        return Response({"error": "Quantity must be greater than zero"}, status=400)
                    changes.append(("raw_value", record.raw_value, new_val))
                    record.raw_value = new_val
                    value_changed = True
            except (InvalidOperation, ValueError, TypeError):
                return Response({"error": f"Invalid number for raw_value: {data['raw_value']}"}, status=400)

        if "raw_unit" in data and data["raw_unit"] != record.raw_unit:
            new_unit = data["raw_unit"]
            changes.append(("raw_unit", record.raw_unit, new_unit))
            record.raw_unit = new_unit
            unit_changed = True

        # Re-calc if value, unit, country, or metadata changes
        if value_changed or unit_changed or ("country_code" in data) or metadata_changed:
            unit_str = record.raw_unit.upper()
            conv = UNIT_CONVERSIONS.get(unit_str, Decimal("1.0"))
            norm_unit = UNIT_TO_STANDARD.get(unit_str, record.raw_unit)

            record.unit_conversion_factor = conv
            record.normalized_value = record.raw_value * conv
            record.normalized_unit = norm_unit

            # Re-lookup EF
            ef = find_emission_factor(record.category, record.country_code, norm_unit, record.source_metadata)
            if ef:
                record.emission_factor = ef
                record.emission_factor_value_used = ef.kg_co2e_per_unit
                record.normalized_value_kg_co2e = record.normalized_value * ef.kg_co2e_per_unit
            else:
                if record.emission_factor_value_used:
                    record.normalized_value_kg_co2e = record.normalized_value * record.emission_factor_value_used
                else:
                    return Response({"error": f"No emission factor found for category {record.category} and unit {norm_unit}"}, status=400)

        if changes:
            record.save()
            for field, old_val, new_val in changes:
                EmissionRecordEdit.objects.create(
                    record=record,
                    edited_by=request.user,
                    field_name=field,
                    old_value=str(old_val),
                    new_value=str(new_val),
                    reason=reason,
                )

    data = record_to_dict(record)

    # Include edit history
    edits = record.edits.select_related("edited_by").order_by("edited_at")
    data["edits"] = [
        {
            "field": e.field_name,
            "old_value": e.old_value,
            "new_value": e.new_value,
            "edited_by": e.edited_by.username if e.edited_by else None,
            "edited_at": e.edited_at.isoformat(),
            "reason": e.reason,
        }
        for e in edits
    ]

    # Include source row raw data
    if record.source_row:
        data["source_row"] = {
            "row_index": record.source_row.row_index,
            "raw_data": record.source_row.raw_data,
        }

    return Response(data)


@api_view(["GET"])
def dashboard_stats(request, tenant_slug):
    """
    GET /api/tenants/{tenant_slug}/stats/
    Returns summary statistics for the analyst dashboard.
    """
    tenant, role = get_tenant_or_403(request, tenant_slug)
    if not tenant:
        return Response({"error": "Not a member of this tenant"}, status=403)

    qs = EmissionRecord.objects.filter(tenant=tenant)

    # Status counts
    status_counts = dict(
        qs.values("status").annotate(count=Count("id")).values_list("status", "count")
    )

    # Total CO2e by scope (approved + locked records only for the report)
    scope_totals = dict(
        qs.filter(status__in=["approved", "locked"])
        .values("scope")
        .annotate(total=Sum("normalized_value_kg_co2e"))
        .values_list("scope", "total")
    )

    # Total CO2e by source type
    source_totals = dict(
        qs.filter(status__in=["approved", "locked"])
        .values("source_type")
        .annotate(total=Sum("normalized_value_kg_co2e"))
        .values_list("source_type", "total")
    )

    # Suspicious records count
    suspicious_count = qs.filter(is_suspicious=True, status="pending").count()

    return Response({
        "status_counts": {
            "pending": status_counts.get("pending", 0),
            "flagged": status_counts.get("flagged", 0),
            "approved": status_counts.get("approved", 0),
            "locked": status_counts.get("locked", 0),
            "rejected": status_counts.get("rejected", 0),
        },
        "total_records": qs.count(),
        "suspicious_pending": suspicious_count,
        "scope_totals_kg_co2e": {
            "scope_1": float(scope_totals.get("1", 0) or 0),
            "scope_2": float(scope_totals.get("2", 0) or 0),
            "scope_3": float(scope_totals.get("3", 0) or 0),
        },
        "source_totals_kg_co2e": {
            "sap": float(source_totals.get("sap", 0) or 0),
            "utility": float(source_totals.get("utility", 0) or 0),
            "travel": float(source_totals.get("travel", 0) or 0),
        },
    })

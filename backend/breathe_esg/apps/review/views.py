"""
Review views - the analyst workflow.

State transitions allowed:
  pending → approved    (analyst approves)
  pending → flagged     (analyst flags for attention)
  pending → rejected    (analyst rejects)
  flagged → pending     (analyst clears flag)
  flagged → approved    (analyst approves flagged record)
  approved → locked     (admin locks for audit)

Locked records cannot be modified. This is the audit-freeze point.
"""

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from breathe_esg.apps.tenants.models import TenantMembership
from breathe_esg.apps.emissions.models import EmissionRecord, EmissionRecordEdit


def get_tenant_membership(request, tenant_slug):
    try:
        return TenantMembership.objects.get(user=request.user, tenant__slug=tenant_slug)
    except TenantMembership.DoesNotExist:
        return None


ALLOWED_TRANSITIONS = {
    EmissionRecord.STATUS_PENDING: [
        EmissionRecord.STATUS_APPROVED,
        EmissionRecord.STATUS_FLAGGED,
        EmissionRecord.STATUS_REJECTED,
    ],
    EmissionRecord.STATUS_FLAGGED: [
        EmissionRecord.STATUS_PENDING,
        EmissionRecord.STATUS_APPROVED,
        EmissionRecord.STATUS_REJECTED,
    ],
    EmissionRecord.STATUS_APPROVED: [
        EmissionRecord.STATUS_LOCKED,
    ],
}


@api_view(["POST"])
def review_action(request, tenant_slug, record_id):
    """
    POST /api/tenants/{tenant_slug}/records/{record_id}/review/
    Body: { "action": "approve"|"reject"|"flag"|"lock"|"unflag", "notes": "..." }
    """
    membership = get_tenant_membership(request, tenant_slug)
    if not membership:
        return Response({"error": "Not a member of this tenant"}, status=403)

    try:
        record = EmissionRecord.objects.get(id=record_id, tenant=membership.tenant)
    except EmissionRecord.DoesNotExist:
        return Response({"error": "Not found"}, status=404)

    action = request.data.get("action")
    notes = request.data.get("notes", "")

    ACTION_TO_STATUS = {
        "approve": EmissionRecord.STATUS_APPROVED,
        "reject": EmissionRecord.STATUS_REJECTED,
        "flag": EmissionRecord.STATUS_FLAGGED,
        "unflag": EmissionRecord.STATUS_PENDING,
        "lock": EmissionRecord.STATUS_LOCKED,
    }

    new_status = ACTION_TO_STATUS.get(action)
    if not new_status:
        return Response({"error": f"Unknown action: {action}"}, status=400)

    # Check permission: only admins can lock
    if new_status == EmissionRecord.STATUS_LOCKED and membership.role != TenantMembership.ROLE_ADMIN:
        return Response({"error": "Only admins can lock records"}, status=403)

    # Auditors can't take any review action
    if membership.role == TenantMembership.ROLE_AUDITOR:
        return Response({"error": "Auditors cannot take review actions"}, status=403)

    # Check transition is valid
    allowed = ALLOWED_TRANSITIONS.get(record.status, [])
    if new_status not in allowed:
        return Response({
            "error": f"Cannot transition from {record.status!r} to {new_status!r}",
            "allowed_actions": [
                k for k, v in ACTION_TO_STATUS.items() if v in allowed
            ],
        }, status=400)

    old_status = record.status
    record.status = new_status
    record.reviewed_by = request.user
    record.reviewed_at = timezone.now()
    record.review_notes = notes
    record.save()

    # Write to audit trail
    EmissionRecordEdit.objects.create(
        record=record,
        edited_by=request.user,
        field_name="status",
        old_value=old_status,
        new_value=new_status,
        reason=notes or f"Action: {action}",
    )

    return Response({
        "id": str(record.id),
        "status": record.status,
        "status_display": record.get_status_display(),
        "reviewed_by": request.user.username,
        "reviewed_at": record.reviewed_at.isoformat(),
    })


@api_view(["POST"])
def bulk_review(request, tenant_slug):
    """
    POST /api/tenants/{tenant_slug}/bulk-review/
    Body: { "record_ids": [...], "action": "approve"|"reject"|"flag" }

    Allows an analyst to approve/reject/flag multiple records at once.
    Used in the dashboard when reviewing a batch upload.
    """
    membership = get_tenant_membership(request, tenant_slug)
    if not membership:
        return Response({"error": "Not a member of this tenant"}, status=403)

    if membership.role == TenantMembership.ROLE_AUDITOR:
        return Response({"error": "Auditors cannot take review actions"}, status=403)

    record_ids = request.data.get("record_ids", [])
    action = request.data.get("action")
    notes = request.data.get("notes", "")

    ACTION_TO_STATUS = {
        "approve": EmissionRecord.STATUS_APPROVED,
        "reject": EmissionRecord.STATUS_REJECTED,
        "flag": EmissionRecord.STATUS_FLAGGED,
    }

    new_status = ACTION_TO_STATUS.get(action)
    if not new_status:
        return Response({"error": f"Unknown bulk action: {action}"}, status=400)

    records = EmissionRecord.objects.filter(
        id__in=record_ids,
        tenant=membership.tenant,
    )

    updated = 0
    skipped = 0
    for record in records:
        allowed = ALLOWED_TRANSITIONS.get(record.status, [])
        if new_status not in allowed:
            skipped += 1
            continue

        old_status = record.status
        record.status = new_status
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.review_notes = notes
        record.save()

        EmissionRecordEdit.objects.create(
            record=record,
            edited_by=request.user,
            field_name="status",
            old_value=old_status,
            new_value=new_status,
            reason=f"Bulk {action}: {notes}",
        )
        updated += 1

    return Response({
        "updated": updated,
        "skipped": skipped,
        "message": f"{updated} records {action}d, {skipped} skipped (invalid transition).",
    })

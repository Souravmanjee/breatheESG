"""
Ingestion models.

Design principle: we keep a full audit of WHAT came in, HOW it came in,
and WHEN. The IngestionRun is the envelope; RawRow is the unprocessed record;
after parsing+normalization, an EmissionRecord is created and linked back to
the RawRow so you can always trace "this emission figure came from row 47 of
the SAP export uploaded on 2024-03-15."

Why we store raw rows at all:
  - Re-parsing: if we improve our SAP parser, we can re-run against the raw.
  - Auditability: auditors may ask "what did the original file say?"
  - Debugging: if normalization produced a suspicious figure, analysts can
    see the exact source bytes.
"""

from django.db import models
from django.contrib.auth.models import User
import uuid

from breathe_esg.apps.tenants.models import Tenant


class IngestionRun(models.Model):
    """
    One ingestion event - a file upload or API pull.
    All RawRows and resulting EmissionRecords hang off this.
    """
    SOURCE_SAP = "sap"
    SOURCE_UTILITY = "utility"
    SOURCE_TRAVEL = "travel"

    SOURCE_CHOICES = [
        (SOURCE_SAP, "SAP Fuel & Procurement"),
        (SOURCE_UTILITY, "Utility (Electricity)"),
        (SOURCE_TRAVEL, "Corporate Travel"),
    ]

    STATUS_PENDING = "pending"      # upload received, not yet parsed
    STATUS_PARSING = "parsing"      # parser running
    STATUS_PARSED = "parsed"        # rows extracted, awaiting normalization
    STATUS_NORMALIZED = "normalized"  # emission records created
    STATUS_FAILED = "failed"        # parsing or normalization error

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PARSING, "Parsing"),
        (STATUS_PARSED, "Parsed"),
        (STATUS_NORMALIZED, "Normalized"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="ingestion_runs")
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # The uploaded file - stored so we can re-parse later
    original_file = models.FileField(upload_to="uploads/%Y/%m/", null=True, blank=True)
    original_filename = models.CharField(max_length=500, blank=True)

    # Metadata about this run
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="ingestion_runs"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Counts - set after parsing
    row_count_total = models.IntegerField(default=0)
    row_count_parsed = models.IntegerField(default=0)
    row_count_failed = models.IntegerField(default=0)

    # Error summary if STATUS_FAILED
    error_message = models.TextField(blank=True)

    # Free-form notes the uploader can attach (e.g., "Q1 2024 fuel data, plant DE01")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.tenant.name} / {self.source_type} / {self.uploaded_at:%Y-%m-%d}"


class RawRow(models.Model):
    """
    One raw, unparsed record from a source file.
    We store the raw data as JSON so we can re-parse if our parsers improve.

    row_index: 0-based position in the original file (useful for debugging)
    raw_data: the dict of column→value exactly as read from the file,
              before any normalization or type coercion.
    parse_error: if this row failed to parse, what went wrong.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ingestion_run = models.ForeignKey(
        IngestionRun, on_delete=models.CASCADE, related_name="raw_rows"
    )
    row_index = models.IntegerField()

    # Raw data preserved exactly as read from the file
    raw_data = models.JSONField()

    # Did this row parse successfully?
    parse_error = models.TextField(blank=True)  # empty means no error

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["row_index"]
        unique_together = ("ingestion_run", "row_index")

    def __str__(self):
        return f"Row {self.row_index} of {self.ingestion_run}"

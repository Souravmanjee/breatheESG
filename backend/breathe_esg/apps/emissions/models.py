"""
EmissionRecord - the normalized, auditable heart of the system.

Design decisions worth understanding:

1. We store BOTH raw and normalized values.
   raw_value + raw_unit = what the source said.
   normalized_value_kg_co2e = what we calculated after unit conversion
   and applying an emission factor.
   If an auditor questions a figure, we show them the chain:
   raw → unit conversion → emission factor → kgCO2e.

2. Scope is set at ingestion time based on source type + category:
   - SAP fuel (diesel, petrol, natural gas) → Scope 1
   - Utility electricity → Scope 2
   - Business travel → Scope 3

3. Approval state machine:
   PENDING → APPROVED (by an analyst with the right role)
   APPROVED → LOCKED (automatic, after sign-off; cannot be edited)
   PENDING → FLAGGED (analyst marks as suspicious, needs attention)
   FLAGGED → PENDING (analyst clears the flag)
   Any state → REJECTED (analyst rejects it entirely)

4. Edit history: every time a record is edited before locking, we write
   an EmissionRecordEdit row. This is the audit trail.

5. Multi-tenancy: every record has a tenant FK. We enforce this in the
   serializer and viewset, never trusting the client to send the right
   tenant_id.
"""

from django.db import models
from django.contrib.auth.models import User
import uuid

from breathe_esg.apps.tenants.models import Tenant
from breathe_esg.apps.ingest.models import IngestionRun, RawRow


class EmissionFactor(models.Model):
    """
    Lookup table of emission factors.
    e.g., diesel in litres → 2.68 kgCO2e/litre (DEFRA 2023)

    We store the factor SOURCE and YEAR so analysts can see which
    version of DEFRA/IPCC/EPA we applied. Emission factors change
    annually. A record locked in 2023 should retain the 2023 factor
    even if we update to 2024 factors later.
    """
    UNIT_LITRE = "L"
    UNIT_KG = "kg"
    UNIT_KWH = "kWh"
    UNIT_M3 = "m3"
    UNIT_KM = "km"
    UNIT_NIGHT = "night"

    UNIT_CHOICES = [
        (UNIT_LITRE, "Litre"),
        (UNIT_KG, "Kilogram"),
        (UNIT_KWH, "Kilowatt-hour"),
        (UNIT_M3, "Cubic metre"),
        (UNIT_KM, "Kilometre"),
        (UNIT_NIGHT, "Hotel night"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)  # e.g., "Diesel combustion"
    category = models.CharField(max_length=100)  # e.g., "diesel", "natural_gas", "electricity_uk"
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    kg_co2e_per_unit = models.DecimalField(max_digits=12, decimal_places=6)
    source = models.CharField(max_length=200)  # e.g., "DEFRA 2023", "EPA eGrid 2022"
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)  # null = still current
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "-valid_from"]

    def __str__(self):
        return f"{self.name} ({self.kg_co2e_per_unit} kgCO2e/{self.unit}, {self.source})"


class EmissionRecord(models.Model):
    """
    One normalized emission event.
    This is what analysts review, approve, and what goes to auditors.
    """

    # --- Scope classification ---
    SCOPE_1 = "1"  # Direct emissions (fuel combustion on-site or in owned vehicles)
    SCOPE_2 = "2"  # Indirect from purchased electricity
    SCOPE_3 = "3"  # All other indirect (travel, supply chain, etc.)

    SCOPE_CHOICES = [
        (SCOPE_1, "Scope 1 - Direct"),
        (SCOPE_2, "Scope 2 - Electricity"),
        (SCOPE_3, "Scope 3 - Indirect"),
    ]

    # --- Category (more specific than scope) ---
    CATEGORY_FUEL_DIESEL = "fuel_diesel"
    CATEGORY_FUEL_PETROL = "fuel_petrol"
    CATEGORY_FUEL_NATURAL_GAS = "fuel_natural_gas"
    CATEGORY_FUEL_LPG = "fuel_lpg"
    CATEGORY_ELECTRICITY = "electricity"
    CATEGORY_TRAVEL_FLIGHT = "travel_flight"
    CATEGORY_TRAVEL_HOTEL = "travel_hotel"
    CATEGORY_TRAVEL_GROUND = "travel_ground"
    CATEGORY_PROCUREMENT = "procurement"  # purchased goods with upstream emissions

    CATEGORY_CHOICES = [
        (CATEGORY_FUEL_DIESEL, "Fuel - Diesel"),
        (CATEGORY_FUEL_PETROL, "Fuel - Petrol/Gasoline"),
        (CATEGORY_FUEL_NATURAL_GAS, "Fuel - Natural Gas"),
        (CATEGORY_FUEL_LPG, "Fuel - LPG"),
        (CATEGORY_ELECTRICITY, "Electricity"),
        (CATEGORY_TRAVEL_FLIGHT, "Travel - Flight"),
        (CATEGORY_TRAVEL_HOTEL, "Travel - Hotel"),
        (CATEGORY_TRAVEL_GROUND, "Travel - Ground Transport"),
        (CATEGORY_PROCUREMENT, "Procurement"),
    ]

    # --- Review status ---
    STATUS_PENDING = "pending"
    STATUS_FLAGGED = "flagged"
    STATUS_APPROVED = "approved"
    STATUS_LOCKED = "locked"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending Review"),
        (STATUS_FLAGGED, "Flagged - Needs Attention"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_LOCKED, "Locked for Audit"),
        (STATUS_REJECTED, "Rejected"),
    ]

    # --- Primary key and tenant ---
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="emission_records")

    # --- Provenance: where did this come from? ---
    ingestion_run = models.ForeignKey(
        IngestionRun, on_delete=models.SET_NULL, null=True, related_name="emission_records"
    )
    source_row = models.OneToOneField(
        RawRow, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="emission_record",
        help_text="The raw row this record was derived from. Null if manually entered."
    )
    source_type = models.CharField(
        max_length=20, choices=IngestionRun.SOURCE_CHOICES,
        help_text="Which of the three source types produced this record."
    )

    # --- Classification ---
    scope = models.CharField(max_length=1, choices=SCOPE_CHOICES)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)

    # --- Activity data: what the source actually reported ---
    # We keep the raw value and unit exactly as they came in.
    # This is critical: an SAP export might say 500 L of diesel.
    # We store 500 and "L", not just the converted CO2e.
    activity_description = models.TextField(
        help_text="Human-readable description: 'Diesel purchase, Plant DE-01, vendor 4000123'"
    )
    raw_value = models.DecimalField(
        max_digits=18, decimal_places=4,
        help_text="Quantity as reported in the source file (before unit conversion)"
    )
    raw_unit = models.CharField(
        max_length=20,
        help_text="Unit as reported in source (e.g. 'L', 'GAL', 'KWH', 'M3', 'KG')"
    )

    # --- Normalization ---
    # After converting raw_value to a standard unit, what did we get?
    normalized_value = models.DecimalField(
        max_digits=18, decimal_places=4,
        help_text="Value in the unit expected by the emission factor (after conversion)"
    )
    normalized_unit = models.CharField(
        max_length=10,
        help_text="Standard unit used for emission factor lookup (e.g. 'L', 'kWh', 'km')"
    )
    unit_conversion_factor = models.DecimalField(
        max_digits=12, decimal_places=6, default=1.0,
        help_text="Multiplier applied to raw_value to get normalized_value"
    )

    # --- Emission calculation ---
    emission_factor = models.ForeignKey(
        EmissionFactor, on_delete=models.PROTECT, null=True, blank=True,
        help_text="The factor applied. Protected so we don't lose history."
    )
    emission_factor_value_used = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True,
        help_text="Snapshot of factor at time of calculation. Factor may change later."
    )
    normalized_value_kg_co2e = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True,
        help_text="Final emission value in kgCO2e. This is what goes to the report."
    )

    # --- Temporal ---
    # When did the activity happen? Not when we ingested it.
    # For SAP: the PO posting date. For utility: the billing period start.
    # For travel: the trip date. This determines which reporting period it's in.
    activity_date = models.DateField(
        help_text="Date of the activity (not the ingestion date)"
    )
    reporting_period_start = models.DateField(
        help_text="Start of the reporting period this record belongs to (usually Jan 1)"
    )
    reporting_period_end = models.DateField(
        help_text="End of the reporting period (usually Dec 31)"
    )

    # --- Location / plant data ---
    # For SAP: the plant (Werk) code. For utility: the meter/site ID.
    # For travel: origin location.
    location_code = models.CharField(max_length=100, blank=True)
    location_name = models.CharField(max_length=500, blank=True)
    country_code = models.CharField(max_length=3, blank=True, help_text="ISO 3166-1 alpha-2")

    # --- Source-specific metadata (flexible) ---
    # Rather than 15 nullable columns, we use JSON for the source-specific
    # fields that don't apply to all record types.
    # SAP: {"po_number": "4500001234", "vendor_id": "4000123", "plant_code": "DE01", "material_code": "10001234"}
    # Utility: {"meter_id": "MTR-001", "tariff": "HV-Commercial", "billing_period": "2024-02-01/2024-02-29"}
    # Travel: {"origin_iata": "LHR", "destination_iata": "JFK", "traveler_id": "EMP-001", "trip_class": "economy"}
    source_metadata = models.JSONField(
        default=dict, blank=True,
        help_text="Source-specific fields (PO number, meter ID, flight route, etc.)"
    )

    # --- Review workflow ---
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_records"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    # Analyst can flag suspected issues
    is_suspicious = models.BooleanField(
        default=False,
        help_text="Set by the parser if the value looks anomalous (e.g. 10x the rolling avg)"
    )
    suspicion_reason = models.TextField(blank=True)

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activity_date"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "scope"]),
            models.Index(fields=["tenant", "activity_date"]),
            models.Index(fields=["tenant", "reporting_period_start", "reporting_period_end"]),
        ]

    def __str__(self):
        return (
            f"{self.tenant.name} | {self.get_scope_display()} | "
            f"{self.get_category_display()} | {self.normalized_value_kg_co2e} kgCO2e"
        )

    @property
    def can_be_edited(self):
        return self.status not in (self.STATUS_LOCKED, self.STATUS_APPROVED)


class EmissionRecordEdit(models.Model):
    """
    Immutable log of every edit made to an EmissionRecord before it's locked.
    When an analyst changes a value (e.g., corrects a unit), we write a row here.

    This is append-only. We never update or delete these rows.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(
        EmissionRecord, on_delete=models.CASCADE, related_name="edits"
    )
    edited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    edited_at = models.DateTimeField(auto_now_add=True)

    # What changed: before and after snapshots of the changed fields
    field_name = models.CharField(max_length=100)
    old_value = models.TextField()
    new_value = models.TextField()
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["edited_at"]

    def __str__(self):
        return f"Edit to {self.record_id}: {self.field_name} by {self.edited_by}"

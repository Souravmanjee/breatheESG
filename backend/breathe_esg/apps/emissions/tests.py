from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from breathe_esg.apps.tenants.models import Tenant, TenantMembership
from breathe_esg.apps.emissions.models import EmissionRecord, EmissionFactor, EmissionRecordEdit
from breathe_esg.apps.ingest.parsers.sap_parser import parse_sap_file
from breathe_esg.apps.ingest.parsers.utility_parser import parse_utility_file
from breathe_esg.apps.ingest.parsers.travel_parser import parse_travel_file


class ParserTestCase(TestCase):
    def test_sap_parser_german_locale(self):
        sap_data = (
            "Werk\tBestellnummer\tKurztext\tMenge\tMeins\tLieferant\tBestelldatum\n"
            "DE01\t4500001234\tDieselkraftstoff purchase\t5000,00\tGAL\t4000123\t20240115\n"
        ).encode("utf-8")
        
        results = parse_sap_file(sap_data, "ME2M_test.txt")
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["parse_error"], "")
        self.assertEqual(row["scope"], "1")
        self.assertEqual(row["category"], "fuel_diesel")
        self.assertEqual(row["raw_value"], Decimal("5000.00"))
        self.assertEqual(row["raw_unit"], "GAL")
        # GAL -> L conversion factor: 3.78541
        self.assertEqual(row["unit_conversion_factor"], Decimal("3.78541"))
        self.assertEqual(row["normalized_value"], Decimal("5000") * Decimal("3.78541"))
        self.assertEqual(row["normalized_unit"], "L")
        self.assertEqual(row["activity_date"], date(2024, 1, 15))
        self.assertEqual(row["location_code"], "DE01")
        self.assertEqual(row["country_code"], "DE")

    def test_utility_parser_billing_summary(self):
        utility_data = (
            "Billing Period,Meter ID,Usage (kWh),Cost ($),Site\n"
            "2024-01-15 - 2024-02-14,MTR-BLR-001,18500,2200,Bangalore Office A\n"
        ).encode("utf-8")
        
        results = parse_utility_file(utility_data, "utility_test.csv", "IN")
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["parse_error"], "")
        self.assertEqual(row["scope"], "2")
        self.assertEqual(row["category"], "electricity")
        self.assertEqual(row["raw_value"], Decimal("18500"))
        self.assertEqual(row["raw_unit"], "kWh")
        self.assertEqual(row["normalized_unit"], "kWh")
        self.assertEqual(row["activity_date"], date(2024, 1, 30))  # Midpoint of 15th Jan and 14th Feb
        self.assertEqual(row["location_code"], "MTR-BLR-001")
        self.assertEqual(row["country_code"], "IN")

    def test_travel_parser_flight_distance(self):
        travel_data = (
            "Expense Type,Departure Date,Origin,Destination,Cabin Class,Employee Name\n"
            "Airfare,2024-01-20,BOM,LHR,business,Priya Sharma\n"
        ).encode("utf-8")
        
        results = parse_travel_file(travel_data, "travel_test.csv")
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["parse_error"], "")
        self.assertEqual(row["scope"], "3")
        self.assertEqual(row["category"], "travel_flight")
        self.assertEqual(row["raw_unit"], "km")
        # BOM -> LHR Haversine is ~7213km
        self.assertAlmostEqual(float(row["normalized_value"]), 7213.0, delta=10)
        self.assertEqual(row["source_metadata"]["cabin_class"], "business")


class RecordEditAndTenancyTestCase(TestCase):
    def setUp(self):
        # Create users
        self.user_a = User.objects.create_user("user_a", "a@test.com", "pass")
        self.user_b = User.objects.create_user("user_b", "b@test.com", "pass")
        
        # Create tenants
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        
        # Memberships
        TenantMembership.objects.create(user=self.user_a, tenant=self.tenant_a, role=TenantMembership.ROLE_ANALYST)
        TenantMembership.objects.create(user=self.user_b, tenant=self.tenant_b, role=TenantMembership.ROLE_ANALYST)
        
        # Seed emission factors
        self.ef_diesel = EmissionFactor.objects.create(
            name="Diesel combustion", category="diesel", unit="L",
            kg_co2e_per_unit=Decimal("2.6783"), source="DEFRA 2023",
            valid_from=date(2023, 1, 1)
        )
        self.ef_petrol = EmissionFactor.objects.create(
            name="Petrol combustion", category="petrol", unit="L",
            kg_co2e_per_unit=Decimal("2.1695"), source="DEFRA 2023",
            valid_from=date(2023, 1, 1)
        )
        
        # Seed record for Tenant A
        self.record_a = EmissionRecord.objects.create(
            tenant=self.tenant_a,
            source_type="sap",
            scope="1",
            category="fuel_diesel",
            activity_description="Test purchase",
            raw_value=Decimal("500"),
            raw_unit="L",
            normalized_value=Decimal("500"),
            normalized_unit="L",
            unit_conversion_factor=Decimal("1.0"),
            emission_factor=self.ef_diesel,
            emission_factor_value_used=Decimal("2.6783"),
            normalized_value_kg_co2e=Decimal("1339.15"),
            activity_date=date(2024, 1, 15),
            reporting_period_start=date(2024, 1, 1),
            reporting_period_end=date(2024, 12, 31),
            status=EmissionRecord.STATUS_PENDING
        )
        
        self.client = APIClient()

    def test_multi_tenancy_isolation(self):
        # Authenticate as User B (member of Tenant B)
        self.client.force_authenticate(user=self.user_b)
        
        # Try to view Tenant A's record - should return 403 or 404 depending on slug checks
        response = self.client.get(f"/api/tenants/tenant-a/records/{self.record_a.id}/")
        self.assertEqual(response.status_code, 403)
        
        # Try to edit Tenant A's record - should return 403
        response = self.client.patch(
            f"/api/tenants/tenant-a/records/{self.record_a.id}/",
            {"raw_value": 400, "reason_for_edit": "Attempt hijack"}
        )
        self.assertEqual(response.status_code, 403)

    def test_record_edit_recalculation_and_audit(self):
        self.client.force_authenticate(user=self.user_a)
        
        # Edit diesel volume from 500L to 1000L
        response = self.client.patch(
            f"/api/tenants/tenant-a/records/{self.record_a.id}/",
            {
                "raw_value": "1000",
                "reason_for_edit": "Corrected diesel fuel delivery slip volume"
            },
            format="json"
        )
        self.assertEqual(response.status_code, 200)
        
        # Check database update
        self.record_a.refresh_from_db()
        self.assertEqual(self.record_a.raw_value, Decimal("1000"))
        self.assertEqual(self.record_a.normalized_value, Decimal("1000"))
        # Recalculated: 1000 * 2.6783 = 2678.3
        self.assertEqual(self.record_a.normalized_value_kg_co2e, Decimal("2678.3000"))
        
        # Check audit trail log
        edits = EmissionRecordEdit.objects.filter(record=self.record_a)
        self.assertEqual(edits.count(), 1)
        edit = edits.first()
        self.assertEqual(edit.field_name, "raw_value")
        self.assertEqual(edit.old_value, "500.0000")
        self.assertEqual(edit.new_value, "1000")
        self.assertEqual(edit.reason, "Corrected diesel fuel delivery slip volume")
        self.assertEqual(edit.edited_by, self.user_a)

    def test_edit_factor_relookup(self):
        self.client.force_authenticate(user=self.user_a)
        
        # Change unit/category from L to GAL (Diesel still) or change unit to L but category petrol?
        # Actually let's change raw_unit to GAL and check factor/co2e re-calculation
        response = self.client.patch(
            f"/api/tenants/tenant-a/records/{self.record_a.id}/",
            {
                "raw_unit": "GAL",
                "reason_for_edit": "Switched from L to GAL"
            },
            format="json"
        )
        self.assertEqual(response.status_code, 200)
        
        self.record_a.refresh_from_db()
        self.assertEqual(self.record_a.raw_unit, "GAL")
        self.assertEqual(self.record_a.unit_conversion_factor, Decimal("3.78541"))
        self.assertEqual(self.record_a.normalized_value, Decimal("500") * Decimal("3.78541"))
        # Recalculated: 500 * 3.78541 * 2.6783 = 5069.2318
        self.assertAlmostEqual(float(self.record_a.normalized_value_kg_co2e), 5069.2, places=1)

    def test_edit_locked_records_blocked(self):
        self.client.force_authenticate(user=self.user_a)
        
        # Lock the record (mock locking status)
        self.record_a.status = EmissionRecord.STATUS_LOCKED
        self.record_a.save()
        
        # Attempt edit
        response = self.client.patch(
            f"/api/tenants/tenant-a/records/{self.record_a.id}/",
            {"raw_value": "2000", "reason_for_edit": "Locked change test"},
            format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("locked", response.data["error"])

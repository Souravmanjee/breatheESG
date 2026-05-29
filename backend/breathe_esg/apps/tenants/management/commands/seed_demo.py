"""
Management command to create demo tenant, users, and seed emission records.
Run: python manage.py seed_demo

Creates:
  - Tenant: "Acme Corp" (slug: acme)
  - Users: breatheEsgAdmin (password: Thanksforthetest)
  - Emission factors from DEFRA 2023
  - Sample emission records across all three sources
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date
from decimal import Decimal
import uuid

from breathe_esg.apps.tenants.models import Tenant, TenantMembership
from breathe_esg.apps.emissions.models import EmissionRecord, EmissionFactor
from breathe_esg.apps.ingest.models import IngestionRun, RawRow


class Command(BaseCommand):
    help = "Seed demo data for Breathe ESG prototype"

    def handle(self, *args, **options):
        self.stdout.write("Seeding demo data...")

        # Create emission factors
        self._seed_emission_factors()

        # Create tenant
        tenant, _ = Tenant.objects.get_or_create(
            slug="acme",
            defaults={"name": "Acme Industrial Corp"}
        )
        self.stdout.write(f"  Tenant: {tenant.name}")

        # Create users
        # Clean up legacy demo users
        User.objects.filter(username__in=["analyst", "admin_acme"]).delete()

        admin_user = self._create_user("breatheEsgAdmin", "admin@acme.com", "Thanksforthetest")

        TenantMembership.objects.get_or_create(
            user=admin_user, tenant=tenant,
            defaults={"role": TenantMembership.ROLE_ADMIN}
        )
        self.stdout.write(f"  User created: breatheEsgAdmin (password: Thanksforthetest)")

        # Create sample emission records
        self._seed_sap_records(tenant, admin_user)
        self._seed_utility_records(tenant, admin_user)
        self._seed_travel_records(tenant, admin_user)

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
        self.stdout.write("Login at /api/auth/login/ with:")
        self.stdout.write("  breatheEsgAdmin / Thanksforthetest")
        self.stdout.write("Tenant slug: acme")

    def _create_user(self, username, email, password):
        user, created = User.objects.get_or_create(username=username, defaults={"email": email})
        user.set_password(password)
        user.save()
        return user

    def _seed_emission_factors(self):
        factors = [
            # Fuels (DEFRA 2023)
            ("Diesel combustion", "diesel", "L", Decimal("2.6783"), "DEFRA 2023", date(2023, 1, 1)),
            ("Petrol combustion", "petrol", "L", Decimal("2.1695"), "DEFRA 2023", date(2023, 1, 1)),
            ("Natural gas combustion", "natural_gas", "m3", Decimal("2.0440"), "DEFRA 2023", date(2023, 1, 1)),
            ("LPG combustion", "lpg", "L", Decimal("1.5551"), "DEFRA 2023", date(2023, 1, 1)),
            # Electricity (IEA 2023 grid averages)
            ("Electricity - India grid", "electricity_in", "kWh", Decimal("0.7130"), "IEA 2023 / CEA 2022", date(2023, 1, 1)),
            ("Electricity - UK grid", "electricity_gb", "kWh", Decimal("0.2070"), "DEFRA 2023", date(2023, 1, 1)),
            ("Electricity - global average", "electricity_default", "kWh", Decimal("0.4500"), "IEA 2023", date(2023, 1, 1)),
            # Travel (DEFRA 2023)
            ("Flight - economy", "flight_economy", "km", Decimal("0.1551"), "DEFRA 2023", date(2023, 1, 1)),
            ("Flight - business class", "flight_business", "km", Decimal("0.4286"), "DEFRA 2023", date(2023, 1, 1)),
            ("Hotel stay - average", "hotel", "night", Decimal("20.6000"), "DEFRA 2023", date(2023, 1, 1)),
            ("Taxi / rideshare", "taxi", "km", Decimal("0.1491"), "DEFRA 2023", date(2023, 1, 1)),
        ]
        for name, category, unit, factor, source, valid_from in factors:
            EmissionFactor.objects.get_or_create(
                category=category,
                source=source,
                defaults={
                    "name": name,
                    "unit": unit,
                    "kg_co2e_per_unit": factor,
                    "valid_from": valid_from,
                }
            )
        self.stdout.write(f"  Emission factors seeded")

    def _seed_sap_records(self, tenant, user):
        run = IngestionRun.objects.create(
            tenant=tenant,
            source_type="sap",
            status=IngestionRun.STATUS_NORMALIZED,
            original_filename="ME2M_fuel_Q1_2024.txt",
            uploaded_by=user,
            uploaded_at=timezone.now(),
            started_at=timezone.now(),
            completed_at=timezone.now(),
            row_count_total=5,
            row_count_parsed=5,
            row_count_failed=0,
            notes="Q1 2024 fuel procurement from ME2M export, Plant DE01 and IN01",
        )

        ef_diesel = EmissionFactor.objects.filter(category="diesel").first()

        sap_records = [
            {
                "category": "fuel_diesel",
                "scope": "1",
                "description": "Diesel fuel purchase, Plant DE-01, Vendor 4000123 (Petronas GmbH)",
                "raw_value": Decimal("5000"), "raw_unit": "L",
                "norm_value": Decimal("5000"), "norm_unit": "L",
                "co2e": Decimal("13391.5"),
                "date": date(2024, 1, 15),
                "plant": "DE01", "plant_name": "Frankfurt Plant 1", "country": "DE",
                "metadata": {"po_number": "4500001234", "vendor_id": "4000123", "vendor_name": "Petronas GmbH", "plant_code": "DE01", "material_code": "10001234", "material_group": "Dieselkraftstoff"},
                "suspicious": False,
            },
            {
                "category": "fuel_diesel",
                "scope": "1",
                "description": "Diesel fuel purchase, Plant IN-01, Vendor 5000045 (Bharat Petroleum)",
                "raw_value": Decimal("8000"), "raw_unit": "L",
                "norm_value": Decimal("8000"), "norm_unit": "L",
                "co2e": Decimal("21426.4"),
                "date": date(2024, 2, 3),
                "plant": "IN01", "plant_name": "Mumbai Facility", "country": "IN",
                "metadata": {"po_number": "4500001290", "vendor_id": "5000045", "vendor_name": "Bharat Petroleum Ltd", "plant_code": "IN01", "material_code": "10001234", "material_group": "Diesel"},
                "suspicious": False,
            },
            {
                "category": "fuel_natural_gas",
                "scope": "1",
                "description": "Natural gas purchase, Plant DE-01, Vendor 4000078 (E.ON Energie)",
                "raw_value": Decimal("2500"), "raw_unit": "M3",
                "norm_value": Decimal("2500"), "norm_unit": "m3",
                "co2e": Decimal("5110"),
                "date": date(2024, 1, 31),
                "plant": "DE01", "plant_name": "Frankfurt Plant 1", "country": "DE",
                "metadata": {"po_number": "4500001241", "vendor_id": "4000078", "vendor_name": "E.ON Energie AG", "plant_code": "DE01", "material_code": "20003456", "material_group": "Erdgas"},
                "suspicious": False,
            },
            {
                "category": "fuel_petrol",
                "scope": "1",
                "description": "Petrol (gasoline) purchase, Plant GB-01, Vendor 4000200 (Shell UK)",
                "raw_value": Decimal("1200"), "raw_unit": "L",
                "norm_value": Decimal("1200"), "norm_unit": "L",
                "co2e": Decimal("2603.4"),
                "date": date(2024, 3, 10),
                "plant": "GB01", "plant_name": "London Office", "country": "GB",
                "metadata": {"po_number": "4500001310", "vendor_id": "4000200", "vendor_name": "Shell UK Ltd", "plant_code": "GB01", "material_code": "10001567", "material_group": "Petrol"},
                "suspicious": False,
            },
            {
                "category": "fuel_diesel",
                "scope": "1",
                "description": "Diesel fuel purchase, Plant DE-01 — UNUSUALLY HIGH VOLUME, verify PO",
                "raw_value": Decimal("85000"), "raw_unit": "L",
                "norm_value": Decimal("85000"), "norm_unit": "L",
                "co2e": Decimal("227655.5"),
                "date": date(2024, 2, 20),
                "plant": "DE01", "plant_name": "Frankfurt Plant 1", "country": "DE",
                "metadata": {"po_number": "4500001255", "vendor_id": "4000123", "vendor_name": "Petronas GmbH", "plant_code": "DE01", "material_code": "10001234", "material_group": "Dieselkraftstoff"},
                "suspicious": True,
                "suspicion_reason": "Volume 17x the average quarterly purchase for this plant. Verify PO 4500001255.",
            },
        ]

        for rec_data in sap_records:
            raw_row = RawRow.objects.create(
                ingestion_run=run,
                row_index=sap_records.index(rec_data),
                raw_data=rec_data["metadata"],
            )
            EmissionRecord.objects.get_or_create(
                source_row=raw_row,
                defaults={
                    "tenant": tenant,
                    "ingestion_run": run,
                    "source_type": "sap",
                    "scope": rec_data["scope"],
                    "category": rec_data["category"],
                    "activity_description": rec_data["description"],
                    "raw_value": rec_data["raw_value"],
                    "raw_unit": rec_data["raw_unit"],
                    "normalized_value": rec_data["norm_value"],
                    "normalized_unit": rec_data["norm_unit"],
                    "unit_conversion_factor": Decimal("1.0"),
                    "emission_factor": ef_diesel,
                    "emission_factor_value_used": Decimal("2.6783"),
                    "normalized_value_kg_co2e": rec_data["co2e"],
                    "activity_date": rec_data["date"],
                    "reporting_period_start": date(2024, 1, 1),
                    "reporting_period_end": date(2024, 12, 31),
                    "location_code": rec_data["plant"],
                    "location_name": rec_data["plant_name"],
                    "country_code": rec_data["country"],
                    "source_metadata": rec_data["metadata"],
                    "is_suspicious": rec_data.get("suspicious", False),
                    "suspicion_reason": rec_data.get("suspicion_reason", ""),
                    "status": EmissionRecord.STATUS_PENDING,
                }
            )
        self.stdout.write(f"  SAP records seeded: {len(sap_records)}")

    def _seed_utility_records(self, tenant, user):
        run = IngestionRun.objects.create(
            tenant=tenant,
            source_type="utility",
            status=IngestionRun.STATUS_NORMALIZED,
            original_filename="electricity_Q1_2024_greenbutton.csv",
            uploaded_by=user,
            uploaded_at=timezone.now(),
            started_at=timezone.now(),
            completed_at=timezone.now(),
            row_count_total=6,
            row_count_parsed=6,
            row_count_failed=0,
            notes="Q1 2024 electricity data from BESCOM portal CSV export (Bangalore)",
        )

        ef_elec = EmissionFactor.objects.filter(category="electricity_in").first()

        utility_records = [
            {"meter": "MTR-BLR-001", "site": "Bangalore Office A", "month": "January 2024",
             "kwh": Decimal("18500"), "period_start": date(2024, 1, 1), "period_end": date(2024, 1, 31),
             "co2e": Decimal("13190.5"), "date": date(2024, 1, 15)},
            {"meter": "MTR-BLR-001", "site": "Bangalore Office A", "month": "February 2024",
             "kwh": Decimal("17200"), "period_start": date(2024, 2, 1), "period_end": date(2024, 2, 29),
             "co2e": Decimal("12263.6"), "date": date(2024, 2, 15)},
            {"meter": "MTR-BLR-001", "site": "Bangalore Office A", "month": "March 2024",
             "kwh": Decimal("19100"), "period_start": date(2024, 3, 1), "period_end": date(2024, 3, 31),
             "co2e": Decimal("13618.3"), "date": date(2024, 3, 15)},
            {"meter": "MTR-BLR-002", "site": "Bangalore Warehouse B", "month": "January 2024",
             "kwh": Decimal("42000"), "period_start": date(2024, 1, 1), "period_end": date(2024, 1, 31),
             "co2e": Decimal("29946.0"), "date": date(2024, 1, 15)},
            {"meter": "MTR-BLR-002", "site": "Bangalore Warehouse B", "month": "February 2024",
             "kwh": Decimal("39500"), "period_start": date(2024, 2, 1), "period_end": date(2024, 2, 29),
             "co2e": Decimal("28163.5"), "date": date(2024, 2, 15)},
            {"meter": "MTR-MUM-001", "site": "Mumbai HQ", "month": "January 2024",
             "kwh": Decimal("55000"), "period_start": date(2024, 1, 1), "period_end": date(2024, 1, 31),
             "co2e": Decimal("39215.0"), "date": date(2024, 1, 15),
             "suspicious": True, "suspicion_reason": "Usage 55,000 kWh for single meter - verify this is not a multi-site aggregation"},
        ]

        for i, rec_data in enumerate(utility_records):
            raw_row = RawRow.objects.create(
                ingestion_run=run,
                row_index=i,
                raw_data={
                    "Meter ID": rec_data["meter"],
                    "Billing Period": f"{rec_data['period_start']} - {rec_data['period_end']}",
                    "Usage (kWh)": str(rec_data["kwh"]),
                    "Site": rec_data["site"],
                },
            )
            EmissionRecord.objects.get_or_create(
                source_row=raw_row,
                defaults={
                    "tenant": tenant,
                    "ingestion_run": run,
                    "source_type": "utility",
                    "scope": "2",
                    "category": "electricity",
                    "activity_description": f"Electricity - {rec_data['site']}, Meter {rec_data['meter']}, {rec_data['month']}",
                    "raw_value": rec_data["kwh"],
                    "raw_unit": "kWh",
                    "normalized_value": rec_data["kwh"],
                    "normalized_unit": "kWh",
                    "unit_conversion_factor": Decimal("1.0"),
                    "emission_factor": ef_elec,
                    "emission_factor_value_used": Decimal("0.713"),
                    "normalized_value_kg_co2e": rec_data["co2e"],
                    "activity_date": rec_data["date"],
                    "reporting_period_start": date(2024, 1, 1),
                    "reporting_period_end": date(2024, 12, 31),
                    "location_code": rec_data["meter"],
                    "location_name": rec_data["site"],
                    "country_code": "IN",
                    "source_metadata": {
                        "meter_id": rec_data["meter"],
                        "tariff": "HT-Commercial",
                        "billing_period_start": str(rec_data["period_start"]),
                        "billing_period_end": str(rec_data["period_end"]),
                        "emission_factor_source": "IEA 2023 / CEA 2022",
                        "emission_factor_country": "IN",
                    },
                    "is_suspicious": rec_data.get("suspicious", False),
                    "suspicion_reason": rec_data.get("suspicion_reason", ""),
                    "status": EmissionRecord.STATUS_PENDING,
                }
            )
        self.stdout.write(f"  Utility records seeded: {len(utility_records)}")

    def _seed_travel_records(self, tenant, user):
        run = IngestionRun.objects.create(
            tenant=tenant,
            source_type="travel",
            status=IngestionRun.STATUS_NORMALIZED,
            original_filename="concur_travel_export_Q1_2024.csv",
            uploaded_by=user,
            uploaded_at=timezone.now(),
            started_at=timezone.now(),
            completed_at=timezone.now(),
            row_count_total=8,
            row_count_parsed=8,
            row_count_failed=0,
            notes="Q1 2024 Concur expense export, all approved travel reports",
        )

        ef_flight = EmissionFactor.objects.filter(category="flight_economy").first()
        ef_hotel = EmissionFactor.objects.filter(category="hotel").first()

        travel_records = [
            {
                "category": "travel_flight", "scope": "3",
                "description": "Flight BOM→LHR (long-haul), economy, Priya Sharma",
                "raw_value": Decimal("7190"), "raw_unit": "km",
                "co2e": Decimal("1115.1"), "ef": Decimal("0.1551"),
                "date": date(2024, 1, 20),
                "location": "BOM", "location_name": "BOM to LHR",
                "metadata": {"origin_iata": "BOM", "destination_iata": "LHR", "cabin_class": "economy", "distance_km": "7190", "haul_type": "long-haul", "traveler_name": "Priya Sharma", "distance_source": "calculated_haversine"},
            },
            {
                "category": "travel_flight", "scope": "3",
                "description": "Flight LHR→FRA (short-haul), business class, Rajesh Kumar",
                "raw_value": Decimal("932"), "raw_unit": "km",
                "co2e": Decimal("399.5"), "ef": Decimal("0.4286"),
                "date": date(2024, 2, 5),
                "location": "LHR", "location_name": "LHR to FRA",
                "metadata": {"origin_iata": "LHR", "destination_iata": "FRA", "cabin_class": "business", "distance_km": "932", "haul_type": "short-haul", "traveler_name": "Rajesh Kumar", "distance_source": "calculated_haversine"},
            },
            {
                "category": "travel_flight", "scope": "3",
                "description": "Flight DEL→DXB (medium-haul), economy, Ananya Singh",
                "raw_value": Decimal("2194"), "raw_unit": "km",
                "co2e": Decimal("340.3"), "ef": Decimal("0.1551"),
                "date": date(2024, 3, 12),
                "location": "DEL", "location_name": "DEL to DXB",
                "metadata": {"origin_iata": "DEL", "destination_iata": "DXB", "cabin_class": "economy", "distance_km": "2194", "haul_type": "medium-haul", "traveler_name": "Ananya Singh", "distance_source": "calculated_haversine"},
            },
            {
                "category": "travel_hotel", "scope": "3",
                "description": "Hotel stay: Premier Inn Heathrow, 3 nights, London, Priya Sharma",
                "raw_value": Decimal("3"), "raw_unit": "night",
                "co2e": Decimal("61.8"), "ef": Decimal("20.6"),
                "date": date(2024, 1, 20),
                "location": "London", "location_name": "Premier Inn Heathrow",
                "metadata": {"hotel_name": "Premier Inn Heathrow", "city": "London", "country": "GB", "nights": 3, "traveler_name": "Priya Sharma"},
            },
            {
                "category": "travel_hotel", "scope": "3",
                "description": "Hotel stay: Marriott Frankfurt, 2 nights, Frankfurt, Rajesh Kumar",
                "raw_value": Decimal("2"), "raw_unit": "night",
                "co2e": Decimal("41.2"), "ef": Decimal("20.6"),
                "date": date(2024, 2, 5),
                "location": "Frankfurt", "location_name": "Marriott Frankfurt",
                "metadata": {"hotel_name": "Marriott Frankfurt", "city": "Frankfurt", "country": "DE", "nights": 2, "traveler_name": "Rajesh Kumar"},
            },
            {
                "category": "travel_ground", "scope": "3",
                "description": "Ground transport: Uber, Mumbai, Ananya Singh",
                "raw_value": Decimal("20"), "raw_unit": "km",
                "co2e": Decimal("2.98"), "ef": Decimal("0.1491"),
                "date": date(2024, 1, 8),
                "location": "Mumbai", "location_name": "Mumbai",
                "metadata": {"vendor": "Uber", "city": "Mumbai", "country": "IN", "distance_km": "20", "distance_source": "estimated_default_20km", "traveler_name": "Ananya Singh"},
            },
        ]

        for i, rec_data in enumerate(travel_records):
            ef = ef_flight if rec_data["category"] == "travel_flight" else ef_hotel
            raw_row = RawRow.objects.create(
                ingestion_run=run,
                row_index=i,
                raw_data=rec_data["metadata"],
            )
            EmissionRecord.objects.get_or_create(
                source_row=raw_row,
                defaults={
                    "tenant": tenant,
                    "ingestion_run": run,
                    "source_type": "travel",
                    "scope": "3",
                    "category": rec_data["category"],
                    "activity_description": rec_data["description"],
                    "raw_value": rec_data["raw_value"],
                    "raw_unit": rec_data["raw_unit"],
                    "normalized_value": rec_data["raw_value"],
                    "normalized_unit": rec_data["raw_unit"],
                    "unit_conversion_factor": Decimal("1.0"),
                    "emission_factor": ef,
                    "emission_factor_value_used": rec_data["ef"],
                    "normalized_value_kg_co2e": rec_data["co2e"],
                    "activity_date": rec_data["date"],
                    "reporting_period_start": date(2024, 1, 1),
                    "reporting_period_end": date(2024, 12, 31),
                    "location_code": rec_data["location"],
                    "location_name": rec_data["location_name"],
                    "country_code": "",
                    "source_metadata": rec_data["metadata"],
                    "is_suspicious": False,
                    "suspicion_reason": "",
                    "status": EmissionRecord.STATUS_PENDING,
                }
            )
        self.stdout.write(f"  Travel records seeded: {len(travel_records)}")

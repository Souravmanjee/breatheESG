# MODEL.md — Data Model & Design

## Overview

The data model has four layers:

```
Tenant
  └── IngestionRun (one per file upload)
        └── RawRow (one per row in the original file)
              └── EmissionRecord (normalized, one-to-one with RawRow)
                    └── EmissionRecordEdit (append-only audit log)
```

Supporting:
- `TenantMembership` (user ↔ tenant with role)
- `EmissionFactor` (lookup table, versioned by source and year)

---

## Multi-tenancy

We use **row-level tenancy**: every `EmissionRecord`, `IngestionRun`, and `RawRow` has a `tenant` foreign key. All querysets are filtered by tenant at the view level before any data is returned.

We chose this over schema-per-tenant because:
- A single-schema approach is far simpler to deploy on Railway/Render (no dynamic schema creation)
- Our data volume per tenant in the prototype is low (thousands of rows per year, not millions)
- Django's ORM doesn't have first-class multi-schema support

**Tradeoff**: If we have thousands of tenants with large datasets, row-level tenancy puts all data in one table and requires that every query include `WHERE tenant_id = ?`. We enforce this in `get_tenant_or_403()` in every view. A future improvement would be a custom manager that enforces this automatically.

---

## Scope 1/2/3 Categorisation

Scope is stored as a single character field on `EmissionRecord`:

| Scope | When assigned | Source types |
|-------|--------------|--------------|
| 1 | At parse time, based on fuel type | SAP fuel purchases (diesel, petrol, natural gas, LPG) |
| 2 | At parse time | All utility electricity records |
| 3 | At parse time | All travel records (flights, hotels, ground) |

Scope is set by the parser, not by the analyst. The analyst can reject a record if the scope is wrong, but cannot change scope directly in v1 (see TRADEOFFS.md).

Procurement records from SAP that can't be classified as fuel are skipped (not given a scope) — this is an explicit decision described in DECISIONS.md.

---

## Source-of-Truth Tracking

Every `EmissionRecord` links back to:

1. `ingestion_run` — which upload produced this record, when, and by whom
2. `source_row` — the specific raw row from the original file (stored as JSON in `raw_data`)

This means: given any CO₂e figure in the final report, you can trace it back to:
- The exact byte in the original file
- Who uploaded it
- When

**Why we store `RawRow` at all**: if our SAP parser improves (e.g., we add support for additional fuel material groups), we can re-run the parser against stored raw rows without requiring the client to re-upload the file.

**Why `raw_data` is JSON, not separate columns**: SAP, utility, and travel files have completely different schemas. A single table with 40 nullable source-specific columns would be unmaintainable. JSON gives us full fidelity of the original row without schema contortion.

---

## Unit Normalisation

We store **both** raw and normalized values on every record:

```
raw_value + raw_unit         → what the source said
normalized_value + normalized_unit  → standard unit for EF lookup
unit_conversion_factor       → the multiplier applied
emission_factor_value_used   → snapshot of EF at calculation time
normalized_value_kg_co2e     → final CO₂e (what goes to the report)
```

**Why snapshot the emission factor value?** Emission factors are updated annually (DEFRA 2023 → DEFRA 2024). A record locked in 2023 with DEFRA 2023 factors should not be silently recalculated if we update factors for 2024. We store the factor value used at the time, as well as a FK to the `EmissionFactor` row itself for reference.

**Unit conversion chain (example)**:
```
SAP says: 500 GAL (US gallons) of diesel
raw_value = 500, raw_unit = "GAL"
unit_conversion_factor = 3.78541 (GAL → L)
normalized_value = 1892.7, normalized_unit = "L"
emission_factor_value_used = 2.6783 (kgCO2e/L, DEFRA 2023)
normalized_value_kg_co2e = 1892.7 × 2.6783 = 5069.7 kgCO2e
```

---

## Audit Trail

The `EmissionRecordEdit` table is **append-only**. Every change to a record's status, or any field edit, writes a row here with:
- Who changed it
- When
- What field
- Old value → new value
- Reason

Records in `locked` status cannot be modified at all — the API returns 400 if you try. This is enforced in both the view (state machine check) and business logic.

**State machine:**
```
pending → approved | flagged | rejected
flagged → pending | approved | rejected
approved → locked   (admin only)
locked → (no transitions allowed)
```

---

## EmissionFactor Table

Rather than hardcoding factors in the parser, we store them in the database. Each factor has:
- `category` (e.g., "diesel", "electricity_in")
- `unit` (what unit the factor is per)
- `kg_co2e_per_unit`
- `source` (e.g., "DEFRA 2023")
- `valid_from` / `valid_to` dates

This allows:
- Updating factors annually without code changes
- Showing analysts which factor version was used
- Supporting different factors by country/region (electricity has different factors per country grid)

---

## Key Design Decisions

**`activity_date` vs `ingestion date`**: We always store the date of the activity (when the fuel was used, when the billing period ended, when the flight departed), not when we ingested the record. This is what determines which reporting year a record belongs to. A record uploaded in April 2024 covering January electricity still belongs to 2024-Q1.

**`reporting_period_start` / `reporting_period_end`**: Stored on each record. Most clients report Jan–Dec, but some have fiscal years (Apr–Mar in India). Storing these explicitly lets us handle non-calendar reporting periods.

**`source_metadata` JSON**: Source-specific fields (PO number, meter ID, IATA codes) go here. We don't promote them to top-level columns because they don't apply across source types. Analysts can see them in the detail view and in the raw data viewer.

---

## What This Model Doesn't Handle (yet)

- Scope 3 categories beyond travel (supply chain, waste, water) — we'd need a different category taxonomy
- Market-based Scope 2 (RECs, PPAs) vs location-based — we only implement location-based in v1
- Multiple reporting standards (GHG Protocol, ISO 14064, CDP) — the model stores raw numbers; which standard applies is a reporting-layer concern
- Sub-annual reporting periods — activity is bucketed to full years

These are elaborated in TRADEOFFS.md.

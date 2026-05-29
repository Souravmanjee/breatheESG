# TRADEOFFS.md — What We Deliberately Didn't Build

## 1. Async ingestion (Celery / background tasks)

**What we built instead**: Synchronous file parsing inside the HTTP request.

**Why we skipped it**: Celery requires a message broker (Redis or RabbitMQ), a separate worker process, and deployment configuration — effectively doubling the operational complexity of the deployment. For a prototype with files under 1,000 rows (typical for a quarterly fuel or travel export), synchronous parsing completes in under 2 seconds. The UX is simpler: upload, get a result, done.

**What breaks in production**: A Q1 SAP export from a large enterprise might have 50,000 line items. Parsing that synchronously will hit Gunicorn's 30-second timeout and the request will fail. The right fix is a Celery task queue where the upload endpoint creates the `IngestionRun` and returns immediately (with a `pending` status), and a worker processes the file in the background. The frontend would poll `/ingestion-runs/{id}/` for status. We designed the `IngestionRun` model specifically to support this — it has `status`, `started_at`, `completed_at`, and `error_message` fields. The async wrapper is a day's work on top of what's here.

---

## 2. PDF bill parsing for utility data

**What we built instead**: CSV portal export parsing (Green Button format).

**Why we skipped it**: PDF parsing for utility bills requires:
1. OCR (Tesseract or a paid service like AWS Textract)
2. Layout-aware extraction (utility bills have tables, headers, totals in inconsistent positions)
3. Per-utility template configuration (National Grid's bill looks nothing like BESCOM's)
4. Confidence scoring (OCR can misread numbers — a missed digit in a kWh figure causes a 10x error in CO₂e)

This is a significant sub-product. Companies like Arcadia and UtilityAPI have built entire businesses around it. For a 4-day prototype, we focus on the path that works for the majority of enterprise clients: their facilities team exports a CSV from the utility portal.

**The right v2 approach**: Integrate with a document extraction API (AWS Textract, Google Document AI, or a specialist like Sensible). Template the extraction per utility, with human-in-the-loop review for low-confidence extractions. The `IngestionRun` model already has an `original_file` field that would store the PDF.

---

## 3. Market-based Scope 2 (RECs and PPAs)

**What we built instead**: Location-based Scope 2 only (grid average emission factors by country).

**Why we skipped it**: Market-based Scope 2 accounting requires:
1. Tracking Renewable Energy Certificates (RECs) or Guarantee of Origin (GoO) certificates purchased by the client
2. Matching those certificates to specific electricity consumption periods and locations
3. Computing a "market-based" emission factor that may be zero (if the client bought RECs for all consumption) rather than the grid average
4. Maintaining a separate certificate registry with validity periods

This is a substantial data model extension (new `EnergyCertificate` model, certificate-to-meter mapping, market vs location factor selection logic). It also requires the client to actually provide their certificate data, which many can't do easily.

**The right v2 approach**: Add a `scope_2_method` field to `EmissionRecord` (location | market). Add an `EnergyCertificate` model. During review, allow analysts to apply certificates to reduce market-based figures. The GHG Protocol requires companies to report both methods — so we'd eventually need both.

**Why this matters for the client**: If Acme Corp has signed a PPA for their Bangalore warehouse, their Scope 2 under market-based accounting could be near-zero for that site, versus ~30 tCO₂e/year under location-based. This is a material difference in their reported footprint.

---

## Honourable mentions (things we almost cut but kept)

- **Bulk review**: almost cut it for simplicity, but it's essential for analyst UX. A quarterly upload of 200 travel records that all look fine shouldn't require 200 individual approvals.
- **Suspicion flags**: almost cut it as an AI-features-for-its-own-sake risk, but the SAP demo data has a record that's 17x the average purchase volume — this is exactly the kind of thing that causes restatements if it goes unreviewed. It's a rule (>X standard deviations or >absolute threshold), not a model.
- **Audit trail (`EmissionRecordEdit`)**: tempting to skip for MVP, but auditors will ask "who approved this and when?" on day one. The incremental cost of writing one row per status change is negligible.

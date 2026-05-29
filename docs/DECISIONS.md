# DECISIONS.md — Ambiguities Resolved & Choices Justified

## SAP: Format Choice

**Decision**: SAP ME2M flat file export (tab/semicolon separated).

**Why not IDoc (ORDERS05)?** IDoc is SAP's native EDI format for inter-system communication. Receiving an IDoc requires an SAP XI/PI/Integration Suite middleware endpoint that can receive port-level connections. No enterprise client's IT team is going to open that up to a startup in the first month of onboarding. The ME2M flat file export is something a procurement coordinator can do from the SAP GUI in 2 minutes, without IT involvement.

**Why not OData (SAP Fiori)?** Requires exposing an RFC endpoint externally with OAuth2. Security review at most enterprises takes 6–12 weeks. Also, some clients are still on SAP R/3 which doesn't have Fiori at all.

**Why not BAPI?** BAPIs require programmatic SAP access — a service account with specific authorisation objects. Again, weeks of IT involvement.

**Subset we handle**: Only fuel-related procurement (diesel, petrol, natural gas, LPG). We detect these by string matching on the material description and material group fields. We skip service procurement (no quantity/unit), office supplies, and anything we can't classify. This is logged as a parse skip, not a failure.

**What I'd ask the PM**: Does the client have a standard material group code for fuel? If they do, we can switch from fuzzy string matching to exact code lookup, which is far more reliable. "Diesel" in German is "Dieselkraftstoff" but some SAP configs just use "01" for fuel.

**German headers**: SAP uses the language set in the user's SAP logon. European clients often have German-locale SAP. We map both German and English column names to our canonical fields. We tested against real SAP community documentation for EKKO/EKPO field names.

---

## Utility: Format Choice

**Decision**: Portal CSV export — specifically the Green Button "Download My Data" format, plus a billing summary variant.

**Why not PDF bills?** PDF parsing requires layout-aware OCR. Every utility has a different bill template. We'd need to train or configure a separate parser per utility provider. This is a product in itself, not a feature. Fragile in production (any billing template change breaks it).

**Why not utility APIs (ESPI/Green Button Connect My Data)?** Each of the 3,000+ US electric utilities and hundreds of EU providers has a different OAuth2 implementation. ESPI is the standard but adoption is inconsistent. Real-world timeline: 2–3 months of integration work per major utility. We'd ship nothing for the prototype.

**The portal CSV** is what facilities teams already use for internal reporting. The Green Button standard (used by PG&E, ConEd, National Grid, and via Oracle CC&B by many EU utilities) produces a consistent CSV. We handle both interval data (15-min/hourly readings, aggregated to monthly) and billing summary rows (one row per billing period).

**Billing period misalignment**: Utility billing periods don't align with calendar months. A bill might run Jan 15–Feb 14. We store `billing_period_start` and `billing_period_end` in `source_metadata`, and use the period midpoint as `activity_date`. The record is assigned to the reporting year of `billing_period_start`.

**Emission factor**: We apply country-level grid factors (IEA 2023 / national authority sources). The user specifies the country at upload time. In production, this would be derived from the meter's service territory automatically.

**What I'd ask the PM**: Does the client have multiple meters at different locations with different grid factors (e.g., one site in India, one in Germany)? If so, we need per-meter country tagging, not per-upload.

---

## Travel: Format Choice

**Decision**: Concur Analytics / Navan admin CSV export.

**Why not Concur API (v4)?** Requires OAuth2 client credentials from each enterprise Concur instance, plus SAP Concur's partner program approval. Each client's IT/security team must whitelist our OAuth app. Realistically 4–8 weeks per client.

**Why not Navan API?** Same problem — per-client OAuth credential setup, and Navan's enterprise API requires a reseller agreement.

**The CSV export** is available to any Concur Expense Processor or Navan admin from the dashboard, no IT involvement. Sustainability leads already use this for manual carbon calculations in spreadsheets.

**Distance calculation for flights**: Concur expense reports often have origin/destination as city names or airport codes, but rarely give distance. We compute great-circle (haversine) distance from IATA airport coordinates for ~25 major business travel hubs. For unknown airports, the row fails with a clear error message. In production: use the full OurAirports.com dataset (~7,500 airports, freely licensed).

**Cabin class**: We apply DEFRA 2023 emission factors by cabin class (economy, premium economy, business, first). If not specified, we default to economy — the conservative choice.

**What we don't calculate**: Radiative forcing multiplier (RF). IPCC suggests flights have ~2x the warming effect of CO₂ alone due to contrails and NOx. DEFRA includes RF in its "with RF" factors. We use "without RF" factors because it's contested and many reporting frameworks (GHG Protocol Scope 3) don't require it. This is disclosed in SOURCES.md.

**What I'd ask the PM**: Should we apply the radiative forcing multiplier? This is a methodological choice that affects all flight figures by ~2x and must be consistent across all reporting periods. Also: does the client want per-traveler breakdowns or just aggregate?

---

## Review Workflow

**Decision**: Pending → Approved → Locked (three-stage), with Flagged and Rejected as side states.

**Why three stages?** 
- `pending`: ingested but not yet reviewed
- `approved`: analyst has reviewed and signed off
- `locked`: admin has frozen the record for audit submission — cannot be changed

The distinction between approved and locked matters because analysts may approve records incrementally, but the final lock should be a deliberate admin action before sending to auditors.

**Who can do what**:
- Analysts: approve, flag, reject, unflag
- Admins: all of the above + lock
- Auditors: read-only (can view records and audit trail, cannot take actions)

**Bulk review**: analysts can select multiple records and approve/flag/reject them in one action. This is essential for usability — a quarterly SAP export might produce 200 rows, most of which are straightforward.

---

## Multi-tenancy Approach

**Decision**: Row-level tenancy with FK + mandatory filter in every view.

**Alternative considered**: Schema-per-tenant (PostgreSQL schemas). Pros: complete data isolation, simpler queries (no tenant filter needed). Cons: requires dynamic schema creation, migrations must run per-schema, Django doesn't support this out of the box, and Railway/Render don't make it easy to manage many schemas.

Row-level with strict view-level enforcement is the right tradeoff for a prototype with a small number of enterprise clients.

---

## What I'd Ask the PM If I Could

1. **Material group codes for fuel**: Does each client have their own material group taxonomy, or is there a standard we can rely on?
2. **Radiative forcing**: Do clients need the RF multiplier for flights? Many corporate targets (SBTi) use it; CDP doesn't require it.
3. **Scope 2 method**: Market-based (RECs/PPAs) or location-based only? Market-based is more complex (requires RE certificate tracking).
4. **Fiscal year**: Do clients report Jan–Dec or a non-calendar year (e.g., Apr–Mar for India)?
5. **Re-ingestion**: If a client re-uploads a corrected file for the same period, how do we handle de-duplication? By PO number? By date range?
6. **Async ingestion**: For large files (10,000+ rows), synchronous parsing in the HTTP request will timeout. Do we need Celery for background processing in v1?

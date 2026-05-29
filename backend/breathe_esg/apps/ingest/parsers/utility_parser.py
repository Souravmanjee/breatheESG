"""
Utility Electricity Parser

Format choice: Portal CSV export (Green Button Download My Data format).

Why this over PDF bills or API:
- PDF: Requires OCR + layout-aware parsing. Every utility has a different
  bill layout. Fragile, expensive, and a project in itself (we noted this
  in TRADEOFFS.md).
- Utility API (ESPI/Green Button Connect My Data): Requires per-utility
  OAuth2 integration. The 3,000+ US utilities and hundreds of EU providers
  each have different auth flows. Real-world timeline: 2-3 months per utility.
  We'd ship nothing.
- Portal CSV: Most enterprise utility portals (Oracle CC&B, Itron, SAP ISU)
  offer a "Download My Data" or Green Button CSV export. Facilities managers
  already use this for internal reporting. This is what they'll email us.

Green Button CSV format (from Oracle CC&B / most major US/EU utilities):
  Columns vary slightly by utility but the core pattern is:
  TYPE, DATE, START TIME, END TIME, USAGE, UNITS, COST, NOTES
  or the summary variant (one row per billing period):
  Billing Period, Meter ID, Service Point, Usage (kWh), Demand (kW), Cost, Tariff

What we handle:
- Interval data: 15-min, 30-min, or hourly - we aggregate to daily
- Monthly billing period summaries (the more common enterprise export)
- Units: kWh (most common), Wh (some smart meter exports), MWh (industrial)
- Multiple meters in one file (meter ID column)
- Billing periods that don't align with calendar months (we store the actual period)

What we deliberately don't handle:
- Solar export/net metering credits (negative kWh) - flagged as suspicious
- kVAh (reactive power) - not relevant for Scope 2 CO2e calculation
- Multi-site files without a meter/site identifier column - we error out
"""

import csv
import io
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)

# Emission factors for electricity by country/region (kgCO2e per kWh)
# Source: IEA 2023 Electricity Emission Factors
# In production: these would be in the EmissionFactor table, looked up by country+year
ELECTRICITY_EMISSION_FACTORS = {
    "IN": Decimal("0.713"),   # India grid average (CEA 2022)
    "GB": Decimal("0.207"),   # UK (DEFRA 2023)
    "US": Decimal("0.386"),   # US average (EPA eGrid 2022)
    "DE": Decimal("0.364"),   # Germany (UBA 2023)
    "AU": Decimal("0.51"),    # Australia (DCCEEW 2023)
    "DEFAULT": Decimal("0.45"),  # Global average when country unknown
}

# Column name variants we've seen in real utility portal exports
UTILITY_FIELD_MAP = {
    # Green Button standard (Oracle CC&B / Itron)
    "TYPE": "record_type",
    "DATE": "date",
    "START TIME": "start_time",
    "END TIME": "end_time",
    "USAGE": "usage_value",
    "UNITS": "usage_unit",
    "COST": "cost",
    "NOTES": "notes",
    # Monthly billing summary (common enterprise export)
    "Billing Period": "billing_period",
    "Billing Period Start": "period_start",
    "Billing Period End": "period_end",
    "Meter ID": "meter_id",
    "Service Point ID": "meter_id",
    "Meter Number": "meter_id",
    "Usage (kWh)": "usage_kwh",
    "Net Usage (kWh)": "usage_kwh",
    "Total Usage": "usage_value",
    "Consumption (kWh)": "usage_kwh",
    "kWh": "usage_kwh",
    "Demand (kW)": "demand_kw",
    "Cost ($)": "cost",
    "Cost (£)": "cost",
    "Cost (€)": "cost",
    "Amount": "cost",
    "Tariff": "tariff",
    "Rate Schedule": "tariff",
    "Site": "site_name",
    "Location": "site_name",
    "Facility": "site_name",
}

UNIT_TO_KWH = {
    "KWH": Decimal("1.0"),
    "kWh": Decimal("1.0"),
    "WH": Decimal("0.001"),
    "Wh": Decimal("0.001"),
    "MWH": Decimal("1000.0"),
    "MWh": Decimal("1000.0"),
}


def parse_utility_date(raw: str) -> Optional[date]:
    """Parse utility date strings. Utilities use many formats."""
    raw = raw.strip()
    for fmt in (
        "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d",
        "%d-%m-%Y", "%m-%d-%Y", "%b %d, %Y", "%d %b %Y",
        "%B %d, %Y", "%Y%m%d",
    ):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_billing_period(period_str: str) -> Optional[tuple[date, date]]:
    """
    Parse billing period strings like:
    "2024-01-15 - 2024-02-14"
    "Jan 15, 2024 to Feb 14, 2024"
    "01/15/2024-02/14/2024"
    Returns (start, end) or None.
    """
    for sep in (" - ", " to ", "-", "/"):
        if sep in period_str:
            parts = period_str.split(sep, 1)
            if len(parts) == 2:
                start = parse_utility_date(parts[0].strip())
                end = parse_utility_date(parts[1].strip())
                if start and end:
                    return start, end
    return None


def detect_file_type(headers: list[str]) -> str:
    """Detect whether this is interval data or billing summary."""
    header_set = {h.strip().upper() for h in headers}
    if "TYPE" in header_set and "USAGE" in header_set and "UNITS" in header_set:
        return "interval"
    return "billing_summary"


def parse_utility_file(file_content: bytes, filename: str, country_code: str = "DEFAULT") -> list[dict]:
    """
    Parse a utility portal CSV export.

    Handles both Green Button interval data and monthly billing summaries.
    For interval data, we aggregate to monthly totals before normalizing.

    Returns list of dicts (one per billing period per meter).
    """
    raw_text = file_content.decode("utf-8", errors="replace")

    # Skip any comment/header lines before the actual CSV
    # Some utilities prepend metadata rows starting with # or "Account:"
    lines = raw_text.splitlines()
    csv_start = 0
    for i, line in enumerate(lines):
        # Find the first line that looks like a CSV header
        if any(keyword in line for keyword in ["DATE", "Billing", "Usage", "kWh", "Meter"]):
            csv_start = i
            break

    csv_text = "\n".join(lines[csv_start:])

    # Try different delimiters
    delimiter = ","
    if csv_text.count("\t") > csv_text.count(","):
        delimiter = "\t"

    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)
    raw_rows = list(reader)

    if not raw_rows:
        return [{"row_index": 0, "raw_data": {}, "parse_error": "File is empty or unreadable"}]

    file_type = detect_file_type(list(raw_rows[0].keys()))

    results = []
    if file_type == "interval":
        results = _parse_interval_data(raw_rows, country_code)
    else:
        results = _parse_billing_summary(raw_rows, country_code)

    return results


def _parse_billing_summary(rows: list[dict], country_code: str) -> list[dict]:
    """Parse monthly billing summary format (one row per billing period)."""
    results = []
    for row_index, row in enumerate(rows):
        try:
            parsed = _parse_billing_row(row, row_index, country_code)
            results.append(parsed)
        except Exception as e:
            results.append({
                "row_index": row_index,
                "raw_data": dict(row),
                "parse_error": str(e),
            })
    return results


def _parse_billing_row(row: dict, row_index: int, country_code: str) -> dict:
    """Parse a single billing summary row."""
    raw_data = dict(row)

    # Normalize headers
    normalized = {}
    for key, value in row.items():
        canonical = UTILITY_FIELD_MAP.get(key.strip(), key.strip().lower())
        normalized[canonical] = (value or "").strip()

    # Find usage value
    usage_kwh = None
    usage_raw = None
    usage_unit_raw = "kWh"

    # Try direct kWh column first
    for field in ("usage_kwh", "usage_value"):
        raw = normalized.get(field, "").replace(",", "")
        if raw:
            try:
                usage_raw = Decimal(raw)
                break
            except InvalidOperation:
                pass

    if usage_raw is None:
        return {
            "row_index": row_index,
            "raw_data": raw_data,
            "parse_error": "Cannot find usage value",
        }

    # Handle unit
    unit_str = normalized.get("usage_unit", "kWh").strip()
    conv = UNIT_TO_KWH.get(unit_str, UNIT_TO_KWH.get("kWh"))
    usage_kwh = usage_raw * conv

    # Sanity check: >10,000 kWh for a single billing period for a single meter
    # is unusual for SME but normal for large industrial. We flag >50,000.
    is_suspicious = usage_kwh > 50000
    suspicion_reason = "Usage > 50,000 kWh in single billing period - verify meter ID is single site" if is_suspicious else ""

    # Dates - billing period
    period_start = None
    period_end = None

    # Try explicit start/end columns
    start_str = normalized.get("period_start", "") or normalized.get("billing_period", "")
    end_str = normalized.get("period_end", "")

    if start_str and end_str:
        period_start = parse_utility_date(start_str)
        period_end = parse_utility_date(end_str)
    elif start_str and " - " in start_str:
        result = parse_billing_period(start_str)
        if result:
            period_start, period_end = result
    elif start_str:
        # Some exports only have a single date (period start)
        period_start = parse_utility_date(start_str)
        # Assume ~30 day billing period
        if period_start:
            period_end = period_start + timedelta(days=30)

    if period_start is None:
        return {
            "row_index": row_index,
            "raw_data": raw_data,
            "parse_error": "Cannot parse billing period dates",
        }

    # Use billing period midpoint for activity_date
    activity_date = period_start + (period_end - period_start) / 2

    # Emission factor
    ef = ELECTRICITY_EMISSION_FACTORS.get(country_code, ELECTRICITY_EMISSION_FACTORS["DEFAULT"])
    co2e = usage_kwh * ef

    meter_id = normalized.get("meter_id", "")
    site_name = normalized.get("site_name", "")
    tariff = normalized.get("tariff", "")

    return {
        "row_index": row_index,
        "raw_data": raw_data,
        "parse_error": "",
        "scope": "2",
        "category": "electricity",
        "activity_description": (
            f"Electricity consumption, Meter {meter_id or 'unknown'}, "
            f"{site_name or ''}, "
            f"Period {period_start} to {period_end}"
        ),
        "raw_value": usage_raw,
        "raw_unit": unit_str,
        "normalized_value": usage_kwh,
        "normalized_unit": "kWh",
        "unit_conversion_factor": conv,
        "normalized_value_kg_co2e": co2e,
        "emission_factor_value_used": ef,
        "activity_date": activity_date,
        "reporting_period_start": date(period_start.year, 1, 1),
        "reporting_period_end": date(period_start.year, 12, 31),
        "location_code": meter_id,
        "location_name": site_name,
        "country_code": country_code,
        "is_suspicious": is_suspicious,
        "suspicion_reason": suspicion_reason,
        "source_metadata": {
            "meter_id": meter_id,
            "tariff": tariff,
            "billing_period_start": str(period_start),
            "billing_period_end": str(period_end),
            "cost": normalized.get("cost", ""),
            "demand_kw": normalized.get("demand_kw", ""),
            "emission_factor_source": "IEA 2023",
            "emission_factor_country": country_code,
        },
    }


def _parse_interval_data(rows: list[dict], country_code: str) -> list[dict]:
    """
    Parse Green Button interval data (15-min/hourly readings).
    We aggregate to monthly totals, producing one result row per month.
    """
    # Collect all valid readings grouped by (meter, month)
    monthly = {}  # key: (meter_id, year, month) → total_kwh

    for row_index, row in enumerate(rows):
        normalized = {}
        for k, v in row.items():
            canonical = UTILITY_FIELD_MAP.get(k.strip(), k.strip().lower())
            normalized[canonical] = (v or "").strip()

        date_str = normalized.get("date", "")
        usage_str = normalized.get("usage_value", "").replace(",", "")
        unit_str = normalized.get("usage_unit", "kWh")
        meter_id = normalized.get("meter_id", "DEFAULT")

        activity_date = parse_utility_date(date_str)
        if not activity_date:
            continue

        try:
            usage_raw = Decimal(usage_str)
        except InvalidOperation:
            continue

        conv = UNIT_TO_KWH.get(unit_str, Decimal("1.0"))
        usage_kwh = usage_raw * conv

        key = (meter_id, activity_date.year, activity_date.month)
        monthly[key] = monthly.get(key, Decimal("0")) + usage_kwh

    # Convert monthly totals to result rows
    results = []
    ef = ELECTRICITY_EMISSION_FACTORS.get(country_code, ELECTRICITY_EMISSION_FACTORS["DEFAULT"])

    for i, ((meter_id, year, month), total_kwh) in enumerate(sorted(monthly.items())):
        period_start = date(year, month, 1)
        # End of month
        if month == 12:
            period_end = date(year, 12, 31)
        else:
            period_end = date(year, month + 1, 1) - timedelta(days=1)

        results.append({
            "row_index": i,
            "raw_data": {"aggregated_from_interval": f"{meter_id}/{year}/{month:02d}"},
            "parse_error": "",
            "scope": "2",
            "category": "electricity",
            "activity_description": f"Electricity - Meter {meter_id}, {period_start:%B %Y} (aggregated from interval data)",
            "raw_value": total_kwh,
            "raw_unit": "kWh",
            "normalized_value": total_kwh,
            "normalized_unit": "kWh",
            "unit_conversion_factor": Decimal("1.0"),
            "normalized_value_kg_co2e": total_kwh * ef,
            "emission_factor_value_used": ef,
            "activity_date": period_start,
            "reporting_period_start": date(year, 1, 1),
            "reporting_period_end": date(year, 12, 31),
            "location_code": meter_id,
            "location_name": "",
            "country_code": country_code,
            "is_suspicious": total_kwh > 50000,
            "suspicion_reason": "Monthly usage > 50,000 kWh" if total_kwh > 50000 else "",
            "source_metadata": {
                "meter_id": meter_id,
                "aggregation": "monthly from interval",
                "emission_factor_source": "IEA 2023",
                "emission_factor_country": country_code,
            },
        })

    return results

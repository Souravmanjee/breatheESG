"""
SAP Fuel & Procurement Parser

Format choice: SAP "Local File" flat export from ME2M transaction.
This is a tab-separated or semicolon-separated file that procurement teams
can generate without IT involvement (Menu > List > Export > Local File).

Why this over IDoc or OData:
- IDoc requires SAP XI/PI middleware to receive. Not present in a prototype,
  and the client IT team would need to configure an outbound port - weeks of work.
- OData (SAP Fiori) requires the client to expose an RFC endpoint externally.
  Security approval alone takes months at enterprise clients.
- The ME2M flat file export is what sustainability leads actually email over.
  We've seen this in practice. It's messy, but it's real.

What we handle:
- German column headers (SAP's default in EU deployments): Werk, Menge, Meins,
  Nettopreis, Währung, Bestelldatum
- English column headers in US/UK SAP installations
- Dates as YYYYMMDD (SAP standard) and DD.MM.YYYY (German locale)
- Units: L (Litre), KG, M3, ST (Stück = piece), GAL (US gallon)
- Plant codes that need lookup (we ship a sample lookup table)

What we deliberately DON'T handle:
- Multi-currency POs (we take the base currency value only)
- Scheduling agreements (EKEH table) - different structure entirely
- Service procurement (no quantity/unit, just cost) - no emission factor applies
- IDoc ORDERS05 format - different assignment entirely, logged in DECISIONS.md
"""

import csv
import io
import logging
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)

# Maps SAP German field names → our canonical field names
# SAP exports can have either German or English headers depending on SAP language config
SAP_FIELD_MAP = {
    # German → canonical
    "Werk": "plant_code",
    "Lieferant": "vendor_id",
    "Name 1": "vendor_name",
    "Bestelldatum": "posting_date",
    "Bestellnummer": "po_number",
    "Pos.": "line_item",
    "Kurztext": "material_description",
    "Materialnummer": "material_code",
    "Menge": "quantity",
    "Meins": "unit",
    "Nettopreis": "net_price",
    "Währung": "currency",
    "Warengruppe": "material_group",
    # English SAP headers (US/UK deployments)
    "Plant": "plant_code",
    "Vendor": "vendor_id",
    "Vendor Name": "vendor_name",
    "Posting Date": "posting_date",
    "PO Number": "po_number",
    "Document Date": "posting_date",
    "Item": "line_item",
    "Short Text": "material_description",
    "Material": "material_code",
    "Quantity": "quantity",
    "UoM": "unit",
    "Order Quantity": "quantity",
    "Order Unit": "unit",
    "Net Price": "net_price",
    "Currency": "currency",
    "Material Group": "material_group",
    "Purch. Doc.": "po_number",
}

# SAP unit codes → standard units we use
UNIT_NORMALISATION = {
    "L": ("L", Decimal("1.0")),          # Litre → Litre (no conversion)
    "LT": ("L", Decimal("1.0")),         # SAP alias for Litre
    "GAL": ("L", Decimal("3.78541")),    # US Gallon → Litre
    "KG": ("kg", Decimal("1.0")),        # Kilogram → Kilogram
    "G": ("kg", Decimal("0.001")),       # Gram → Kilogram
    "T": ("kg", Decimal("1000.0")),      # Metric tonne → Kilogram
    "M3": ("m3", Decimal("1.0")),        # Cubic metre → Cubic metre
    "FT3": ("m3", Decimal("0.0283168")), # Cubic foot → Cubic metre
    "ST": None,                          # Stück (piece) - no emission factor, skip
    "EA": None,                          # Each - skip
    "PC": None,                          # Piece - skip
}

# Material groups / descriptions that indicate fuel purchases
# SAP material group codes vary by client. These are common patterns.
FUEL_INDICATORS = {
    "diesel": ("fuel_diesel", "1"),
    "dieselkraftstoff": ("fuel_diesel", "1"),
    "petrol": ("fuel_petrol", "1"),
    "benzin": ("fuel_petrol", "1"),         # German
    "gasoline": ("fuel_petrol", "1"),
    "natural gas": ("fuel_natural_gas", "1"),
    "erdgas": ("fuel_natural_gas", "1"),    # German
    "lpg": ("fuel_lpg", "1"),
    "flüssiggas": ("fuel_lpg", "1"),        # German
}

# Plant code → location lookup (client would provide this; we ship a sample)
# In real deployment: loaded from a config file or database table per tenant
PLANT_LOOKUP = {
    "DE01": {"name": "Frankfurt Plant 1", "country": "DE"},
    "DE02": {"name": "Munich Warehouse", "country": "DE"},
    "GB01": {"name": "London Office", "country": "GB"},
    "IN01": {"name": "Mumbai Facility", "country": "IN"},
    "US01": {"name": "Chicago Distribution", "country": "US"},
}


def parse_sap_date(raw: str) -> Optional[date]:
    """
    SAP exports dates in multiple formats depending on locale settings.
    YYYYMMDD is the SAP-native format.
    DD.MM.YYYY is common in German-locale SAP.
    We try both.
    """
    raw = raw.strip()
    for fmt in ("%Y%m%d", "%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def detect_fuel_category(material_description: str, material_group: str) -> Optional[tuple]:
    """
    Returns (category, scope) if this line item looks like a fuel purchase.
    Returns None if we can't classify it (we skip non-fuel procurement for now).

    Real deployment: the client would provide a mapping of their material codes
    to fuel types. We'd use that instead of string matching.
    """
    text = (material_description + " " + material_group).lower()
    for keyword, result in FUEL_INDICATORS.items():
        if keyword in text:
            return result
    return None


def parse_sap_file(file_content: bytes, filename: str) -> list[dict]:
    """
    Parse a SAP ME2M flat file export.

    Returns a list of dicts, each being a parsed row. Rows that couldn't
    be parsed have a 'parse_error' key. Good rows have all the canonical
    fields populated.

    We try tab-separated first (SAP default), then semicolon, then comma.
    """
    raw_text = file_content.decode("utf-8", errors="replace")

    # Detect delimiter
    delimiter = "\t"
    if raw_text.count(";") > raw_text.count("\t"):
        delimiter = ";"
    elif raw_text.count(",") > raw_text.count("\t"):
        delimiter = ","

    reader = csv.DictReader(io.StringIO(raw_text), delimiter=delimiter)

    results = []
    for row_index, row in enumerate(reader):
        try:
            parsed = _parse_sap_row(row, row_index)
            results.append(parsed)
        except Exception as e:
            results.append({
                "row_index": row_index,
                "raw_data": dict(row),
                "parse_error": str(e),
            })

    return results


def _parse_sap_row(row: dict, row_index: int) -> dict:
    """Parse a single SAP row dict."""
    # Normalize headers: strip whitespace, map German→English
    normalized = {}
    for key, value in row.items():
        canonical_key = SAP_FIELD_MAP.get(key.strip(), key.strip().lower())
        normalized[canonical_key] = (value or "").strip()

    raw_data = dict(row)

    # Required fields
    quantity_str = normalized.get("quantity", "").replace(",", ".")  # German decimal comma
    if not quantity_str:
        return {"row_index": row_index, "raw_data": raw_data, "parse_error": "Missing quantity"}

    try:
        quantity = Decimal(quantity_str)
    except InvalidOperation:
        return {
            "row_index": row_index,
            "raw_data": raw_data,
            "parse_error": f"Cannot parse quantity: {quantity_str!r}",
        }

    if quantity <= 0:
        return {
            "row_index": row_index,
            "raw_data": raw_data,
            "parse_error": "Quantity is zero or negative",
        }

    unit_raw = normalized.get("unit", "").upper()
    unit_info = UNIT_NORMALISATION.get(unit_raw)
    if unit_info is None:
        # If unit not in map at all (not even mappable), skip
        return {
            "row_index": row_index,
            "raw_data": raw_data,
            "parse_error": f"Unknown or non-fuel unit: {unit_raw!r}",
        }

    norm_unit, conv_factor = unit_info

    # Classify: is this a fuel purchase?
    material_desc = normalized.get("material_description", "")
    material_group = normalized.get("material_group", "")
    classification = detect_fuel_category(material_desc, material_group)
    if classification is None:
        return {
            "row_index": row_index,
            "raw_data": raw_data,
            "parse_error": "Cannot classify as fuel - skipping (non-fuel procurement not in scope)",
        }

    category, scope = classification

    # Date
    date_str = normalized.get("posting_date", "")
    activity_date = parse_sap_date(date_str)
    if activity_date is None:
        return {
            "row_index": row_index,
            "raw_data": raw_data,
            "parse_error": f"Cannot parse date: {date_str!r}",
        }

    # Plant lookup
    plant_code = normalized.get("plant_code", "")
    plant_info = PLANT_LOOKUP.get(plant_code, {})

    # Build the canonical parsed row
    return {
        "row_index": row_index,
        "raw_data": raw_data,
        "parse_error": "",
        # Core fields
        "scope": scope,
        "category": category,
        "activity_description": (
            f"{material_desc or 'Fuel purchase'}, "
            f"Plant {plant_code}, "
            f"Vendor {normalized.get('vendor_id', 'unknown')}"
        ),
        "raw_value": quantity,
        "raw_unit": unit_raw,
        "normalized_value": quantity * conv_factor,
        "normalized_unit": norm_unit,
        "unit_conversion_factor": conv_factor,
        "activity_date": activity_date,
        "reporting_period_start": date(activity_date.year, 1, 1),
        "reporting_period_end": date(activity_date.year, 12, 31),
        "location_code": plant_code,
        "location_name": plant_info.get("name", ""),
        "country_code": plant_info.get("country", ""),
        "source_metadata": {
            "po_number": normalized.get("po_number", ""),
            "line_item": normalized.get("line_item", ""),
            "vendor_id": normalized.get("vendor_id", ""),
            "vendor_name": normalized.get("vendor_name", ""),
            "material_code": normalized.get("material_code", ""),
            "material_group": material_group,
            "net_price": normalized.get("net_price", ""),
            "currency": normalized.get("currency", ""),
            "plant_code": plant_code,
        },
    }

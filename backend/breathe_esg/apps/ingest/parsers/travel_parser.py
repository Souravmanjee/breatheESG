"""
Corporate Travel Parser

Format choice: Concur Analytics / Navan expense report CSV export.

Why CSV export over API:
- Concur API (v4): Requires OAuth2 client credentials from the enterprise
  client's SAP Concur instance. Each client's IT security team must whitelist
  our app and issue credentials. This is weeks of procurement + security review.
- Navan API: Similar OAuth2 flow, and Navan's API is better documented,
  but again requires per-client credential setup.
- The CSV export: Concur Expense Processors and Navan admins can export
  all approved expenses as CSV from their dashboard without IT involvement.
  This is how sustainability teams actually get this data today.

Concur expense export fields we use:
  Report Name, Report Date, Employee ID, Employee Name, Expense Type,
  Transaction Date, Vendor, City, Country, Amount, Currency,
  Origin City, Destination City, Distance, Distance Unit,
  Departure Date, Return Date, Hotel Name, Check-in, Check-out, Nights

Navan export fields (slightly different naming):
  Trip ID, Traveler Name, Traveler Email, Booking Type,
  Departure Date, Origin, Destination, Fare Class,
  Hotel Name, Check-in Date, Check-out Date, Nights,
  Amount, Currency, Carbon (kg) [sometimes, not always]

Emission factor approach:
- Flights: We calculate distance from IATA codes using great-circle distance,
  then apply DEFRA/ICAO emission factors per km by cabin class.
  If distance is given directly, we use that.
- Hotels: DEFRA 2023 average hotel night factor (20.6 kgCO2e/night)
- Ground: DEFRA taxi/rental car factors by type if given; default taxi otherwise.

What we don't handle:
- Rail travel (not in the typical Concur export we've modeled)
- Per-airline emission factors (ICAO provides these; too granular for v1)
- Radiative forcing multiplier (contested; we note this in TRADEOFFS.md)
"""

import csv
import io
import math
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# IATA airport coordinates for great-circle distance calculation
# Subset of common business travel airports
# In production: full IATA DB (~7,500 airports) from OurAirports.com free dataset
AIRPORT_COORDS = {
    "BOM": (19.0887, 72.8679),  # Mumbai
    "DEL": (28.5561, 77.1000),  # Delhi
    "BLR": (13.1986, 77.7066),  # Bangalore
    "MAA": (12.9941, 80.1709),  # Chennai
    "HYD": (17.2313, 78.4298),  # Hyderabad
    "CCU": (22.6547, 88.4467),  # Kolkata
    "LHR": (51.4775, -0.4614),  # London Heathrow
    "LGW": (51.1537, -0.1821),  # London Gatwick
    "CDG": (49.0097, 2.5479),   # Paris
    "FRA": (50.0379, 8.5622),   # Frankfurt
    "AMS": (52.3086, 4.7639),   # Amsterdam
    "DXB": (25.2532, 55.3657),  # Dubai
    "SIN": (1.3592, 103.9894),  # Singapore
    "HKG": (22.3080, 113.9185), # Hong Kong
    "NRT": (35.7719, 140.3929), # Tokyo Narita
    "SYD": (33.9461, 151.1772), # Sydney
    "JFK": (40.6398, -73.7789), # New York JFK
    "EWR": (40.6895, -74.1745), # New York Newark
    "LAX": (33.9425, -118.4081),# Los Angeles
    "ORD": (41.9742, -87.9073), # Chicago O'Hare
    "SFO": (37.6188, -122.3750),# San Francisco
    "DFW": (32.8998, -97.0403), # Dallas/Fort Worth
    "MIA": (25.7959, -80.2870), # Miami
    "YYZ": (43.6772, -79.6306), # Toronto
    "GRU": (-23.4356, -46.4731),# São Paulo
    "MEX": (19.4361, -99.0719), # Mexico City
}

# Emission factors (kgCO2e per passenger-km) by cabin class
# Source: DEFRA 2023 Business Travel
FLIGHT_EF_BY_CLASS = {
    "economy": Decimal("0.1551"),
    "economy class": Decimal("0.1551"),
    "coach": Decimal("0.1551"),
    "premium economy": Decimal("0.2337"),
    "premium economy class": Decimal("0.2337"),
    "business": Decimal("0.4286"),
    "business class": Decimal("0.4286"),
    "first": Decimal("0.6083"),
    "first class": Decimal("0.6083"),
    "unknown": Decimal("0.1551"),  # default to economy
}

# Hotel: DEFRA 2023 average (UK-based study; best available)
HOTEL_EF_PER_NIGHT = Decimal("20.6")  # kgCO2e per room-night

# Ground transport emission factors (kgCO2e per km)
GROUND_EF = {
    "taxi": Decimal("0.1491"),
    "cab": Decimal("0.1491"),
    "uber": Decimal("0.1491"),
    "lyft": Decimal("0.1491"),
    "rental car": Decimal("0.1713"),
    "car rental": Decimal("0.1713"),
    "bus": Decimal("0.0892"),
    "train": Decimal("0.0410"),
    "rail": Decimal("0.0410"),
    "metro": Decimal("0.0280"),
    "subway": Decimal("0.0280"),
    "default": Decimal("0.1491"),
}

# Concur expense type → our category
EXPENSE_TYPE_MAP = {
    "airfare": "travel_flight",
    "air": "travel_flight",
    "flight": "travel_flight",
    "airline": "travel_flight",
    "hotel": "travel_hotel",
    "lodging": "travel_hotel",
    "accommodation": "travel_hotel",
    "taxi": "travel_ground",
    "ground transportation": "travel_ground",
    "ground transport": "travel_ground",
    "car rental": "travel_ground",
    "rental car": "travel_ground",
    "uber": "travel_ground",
    "lyft": "travel_ground",
    "bus": "travel_ground",
    "train": "travel_ground",
    "rail": "travel_ground",
}

# Concur/Navan field name variants
TRAVEL_FIELD_MAP = {
    # Concur standard
    "Expense Type": "expense_type",
    "Transaction Date": "transaction_date",
    "Report Date": "transaction_date",
    "Departure Date": "departure_date",
    "Return Date": "return_date",
    "Employee ID": "employee_id",
    "Employee Name": "traveler_name",
    "Vendor": "vendor",
    "City of Purchase": "city",
    "Country": "country",
    "Amount": "amount",
    "Currency": "currency",
    "Origin": "origin",
    "Destination": "destination",
    "Distance": "distance",
    "Distance Unit": "distance_unit",
    "Hotel Name": "hotel_name",
    "Check-in": "checkin_date",
    "Check-out": "checkout_date",
    "Nights": "nights",
    "Cabin Class": "cabin_class",
    "Class of Service": "cabin_class",
    "Fare Class": "cabin_class",
    # Navan
    "Booking Type": "expense_type",
    "Traveler Name": "traveler_name",
    "Traveler Email": "traveler_email",
    "Check-in Date": "checkin_date",
    "Check-out Date": "checkout_date",
    "Trip ID": "trip_id",
    "Carbon (kg)": "provided_carbon_kg",  # Navan sometimes includes this
}


def haversine_km(coord1: tuple, coord2: tuple) -> Decimal:
    """
    Great-circle distance between two (lat, lon) pairs in km.
    This is how we compute flight distances from IATA codes when
    the export doesn't include distance.
    """
    R = 6371  # Earth radius in km
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return Decimal(str(round(R * c, 1)))


def get_flight_distance_km(origin_iata: str, dest_iata: str) -> Optional[Decimal]:
    """Look up airport coords and compute distance. Returns None if either airport unknown."""
    o = AIRPORT_COORDS.get(origin_iata.upper())
    d = AIRPORT_COORDS.get(dest_iata.upper())
    if o and d:
        return haversine_km(o, d)
    return None


def parse_travel_date(raw: str) -> Optional[date]:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_travel_file(file_content: bytes, filename: str) -> list[dict]:
    """Parse a Concur or Navan travel expense CSV export."""
    raw_text = file_content.decode("utf-8", errors="replace")

    delimiter = ","
    if raw_text.count("\t") > raw_text.count(","):
        delimiter = "\t"

    reader = csv.DictReader(io.StringIO(raw_text), delimiter=delimiter)

    results = []
    for row_index, row in enumerate(reader):
        try:
            parsed = _parse_travel_row(row, row_index)
            results.append(parsed)
        except Exception as e:
            results.append({
                "row_index": row_index,
                "raw_data": dict(row),
                "parse_error": str(e),
            })

    return results


def _parse_travel_row(row: dict, row_index: int) -> dict:
    raw_data = dict(row)

    # Normalize headers
    normalized = {}
    for key, value in row.items():
        canonical = TRAVEL_FIELD_MAP.get(key.strip(), key.strip().lower())
        normalized[canonical] = (value or "").strip()

    # Classify
    expense_type_raw = normalized.get("expense_type", "").lower()
    category = None
    for keyword, cat in EXPENSE_TYPE_MAP.items():
        if keyword in expense_type_raw:
            category = cat
            break

    if category is None:
        return {
            "row_index": row_index,
            "raw_data": raw_data,
            "parse_error": f"Unrecognised expense type: {expense_type_raw!r}",
        }

    # Date
    date_str = (
        normalized.get("departure_date")
        or normalized.get("transaction_date")
        or normalized.get("checkin_date")
        or ""
    )
    activity_date = parse_travel_date(date_str)
    if not activity_date:
        return {
            "row_index": row_index,
            "raw_data": raw_data,
            "parse_error": f"Cannot parse date: {date_str!r}",
        }

    if category == "travel_flight":
        return _calc_flight(normalized, raw_data, row_index, activity_date)
    elif category == "travel_hotel":
        return _calc_hotel(normalized, raw_data, row_index, activity_date)
    else:
        return _calc_ground(normalized, raw_data, row_index, activity_date)


def _calc_flight(normalized: dict, raw_data: dict, row_index: int, activity_date: date) -> dict:
    origin = normalized.get("origin", "").upper().strip()[:3]
    destination = normalized.get("destination", "").upper().strip()[:3]

    # Try to get distance
    distance_km = None
    if normalized.get("distance"):
        try:
            dist_val = Decimal(normalized["distance"].replace(",", ""))
            dist_unit = normalized.get("distance_unit", "km").lower()
            if "mi" in dist_unit:
                dist_val = dist_val * Decimal("1.60934")
            distance_km = dist_val
        except Exception:
            pass

    if distance_km is None and origin and destination:
        distance_km = get_flight_distance_km(origin, destination)

    if distance_km is None:
        return {
            "row_index": row_index,
            "raw_data": raw_data,
            "parse_error": f"Cannot compute distance for {origin}→{destination} (airports not in lookup table)",
        }

    cabin_class = normalized.get("cabin_class", "economy").lower()
    ef = FLIGHT_EF_BY_CLASS.get(cabin_class, FLIGHT_EF_BY_CLASS["unknown"])
    co2e = distance_km * ef

    # Haul type for description
    if distance_km < 500:
        haul = "short-haul"
    elif distance_km < 3700:
        haul = "medium-haul"
    else:
        haul = "long-haul"

    return {
        "row_index": row_index,
        "raw_data": raw_data,
        "parse_error": "",
        "scope": "3",
        "category": "travel_flight",
        "activity_description": (
            f"Flight {origin}→{destination} ({haul}), "
            f"{cabin_class}, "
            f"{normalized.get('traveler_name', 'unknown traveler')}"
        ),
        "raw_value": distance_km,
        "raw_unit": "km",
        "normalized_value": distance_km,
        "normalized_unit": "km",
        "unit_conversion_factor": Decimal("1.0"),
        "normalized_value_kg_co2e": co2e,
        "emission_factor_value_used": ef,
        "activity_date": activity_date,
        "reporting_period_start": date(activity_date.year, 1, 1),
        "reporting_period_end": date(activity_date.year, 12, 31),
        "location_code": origin,
        "location_name": f"{origin} to {destination}",
        "country_code": "",
        "is_suspicious": distance_km > 20000,
        "suspicion_reason": "Distance > 20,000 km - verify route" if distance_km > 20000 else "",
        "source_metadata": {
            "origin_iata": origin,
            "destination_iata": destination,
            "cabin_class": cabin_class,
            "distance_km": str(distance_km),
            "haul_type": haul,
            "traveler_id": normalized.get("employee_id", ""),
            "traveler_name": normalized.get("traveler_name", ""),
            "trip_id": normalized.get("trip_id", ""),
            "emission_factor_source": "DEFRA 2023",
            "distance_source": "provided" if normalized.get("distance") else "calculated_haversine",
        },
    }


def _calc_hotel(normalized: dict, raw_data: dict, row_index: int, activity_date: date) -> dict:
    nights_str = normalized.get("nights", "1").replace(",", "")
    try:
        nights = int(Decimal(nights_str))
    except Exception:
        nights = 1

    if nights <= 0:
        nights = 1

    co2e = HOTEL_EF_PER_NIGHT * nights

    return {
        "row_index": row_index,
        "raw_data": raw_data,
        "parse_error": "",
        "scope": "3",
        "category": "travel_hotel",
        "activity_description": (
            f"Hotel stay: {normalized.get('hotel_name', 'unknown hotel')}, "
            f"{nights} night(s), "
            f"{normalized.get('city', '')}, "
            f"{normalized.get('country', '')}"
        ),
        "raw_value": Decimal(str(nights)),
        "raw_unit": "night",
        "normalized_value": Decimal(str(nights)),
        "normalized_unit": "night",
        "unit_conversion_factor": Decimal("1.0"),
        "normalized_value_kg_co2e": co2e,
        "emission_factor_value_used": HOTEL_EF_PER_NIGHT,
        "activity_date": activity_date,
        "reporting_period_start": date(activity_date.year, 1, 1),
        "reporting_period_end": date(activity_date.year, 12, 31),
        "location_code": normalized.get("city", ""),
        "location_name": normalized.get("hotel_name", ""),
        "country_code": normalized.get("country", "")[:2].upper() if normalized.get("country") else "",
        "is_suspicious": nights > 30,
        "suspicion_reason": "Hotel stay > 30 nights - verify" if nights > 30 else "",
        "source_metadata": {
            "hotel_name": normalized.get("hotel_name", ""),
            "city": normalized.get("city", ""),
            "country": normalized.get("country", ""),
            "checkin": normalized.get("checkin_date", ""),
            "checkout": normalized.get("checkout_date", ""),
            "nights": nights,
            "traveler_name": normalized.get("traveler_name", ""),
            "emission_factor_source": "DEFRA 2023",
        },
    }


def _calc_ground(normalized: dict, raw_data: dict, row_index: int, activity_date: date) -> dict:
    vendor = normalized.get("vendor", "").lower()
    ef = GROUND_EF.get("default")
    for k, v in GROUND_EF.items():
        if k in vendor:
            ef = v
            break

    # Ground often has no distance - use amount as proxy or just estimate
    distance_km = None
    if normalized.get("distance"):
        try:
            distance_km = Decimal(normalized["distance"].replace(",", ""))
        except Exception:
            pass

    if distance_km is None:
        distance_km = Decimal("20")  # conservative default: 20km urban trip

    co2e = distance_km * ef

    return {
        "row_index": row_index,
        "raw_data": raw_data,
        "parse_error": "",
        "scope": "3",
        "category": "travel_ground",
        "activity_description": (
            f"Ground transport: {normalized.get('vendor', 'unknown')}, "
            f"{normalized.get('city', '')}, "
            f"{normalized.get('traveler_name', '')}"
        ),
        "raw_value": distance_km,
        "raw_unit": "km",
        "normalized_value": distance_km,
        "normalized_unit": "km",
        "unit_conversion_factor": Decimal("1.0"),
        "normalized_value_kg_co2e": co2e,
        "emission_factor_value_used": ef,
        "activity_date": activity_date,
        "reporting_period_start": date(activity_date.year, 1, 1),
        "reporting_period_end": date(activity_date.year, 12, 31),
        "location_code": normalized.get("city", ""),
        "location_name": normalized.get("city", ""),
        "country_code": normalized.get("country", "")[:2].upper() if normalized.get("country") else "",
        "is_suspicious": False,
        "suspicion_reason": "",
        "source_metadata": {
            "vendor": normalized.get("vendor", ""),
            "city": normalized.get("city", ""),
            "distance_km": str(distance_km),
            "distance_source": "provided" if normalized.get("distance") else "estimated_default_20km",
            "amount": normalized.get("amount", ""),
            "currency": normalized.get("currency", ""),
            "traveler_name": normalized.get("traveler_name", ""),
            "emission_factor_source": "DEFRA 2023",
        },
    }

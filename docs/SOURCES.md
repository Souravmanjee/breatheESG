# SOURCES.md — Research, Sample Data, and Real-World Gaps

## Source 1: SAP Fuel & Procurement

### What we researched

SAP has multiple ways to export purchase order data. We researched:

- **Transaction ME2M** ("Purchase Orders by Material"): generates a list of POs filterable by material, plant, date range, vendor. The export goes to a tab-separated local file via Menu → List → Export → Local File. This is documented in SAP Help and confirmed by real SAP community discussions.
- **Tables EKKO + EKPO**: EKKO is the PO header (document number, vendor, date, company code). EKPO is the PO line item (material, quantity, unit of measure, plant code). These are the underlying tables ME2M reads from. Field names like `WERKS` (plant), `MATNR` (material number), `MENGE` (quantity), `MEINS` (unit of measure) are stable across SAP versions.
- **German locale headers**: SAP's column labels in the export reflect the user's SAP language. German installations export `Werk` (plant), `Lieferant` (vendor), `Menge` (quantity), `Meins` (unit), `Bestelldatum` (order date). We map both sets.
- **Unit codes**: SAP uses internal unit codes — `L` (litre), `LT` (another SAP litre variant), `KG`, `M3`, `ST` (Stück = piece), `GAL` (US gallon). These are in the `T006` table in SAP.
- **Date format**: SAP-native date storage is `YYYYMMDD`. German locale exports sometimes produce `DD.MM.YYYY`.

### What our sample data looks like

`sample_data/sap_fuel_export.txt`: A tab-separated file with German headers mimicking an ME2M export from a German-language SAP installation. Contains:
- 5 fuel purchase line items: diesel (DE plant, IN plant), natural gas, petrol
- 1 anomalous diesel purchase (85,000 L instead of typical 5,000–8,000 L) — to demonstrate suspicion flagging
- Mixed date formats
- A plant code (DE01, IN01, GB01) that requires the lookup table to resolve to a location name

**Why it looks this way**: A German manufacturing company running SAP in German locale, with plants in Germany, India, and the UK. The Indian plant uses higher fuel volumes (diesel generators common in India due to grid instability). The anomalous record simulates a data entry error (extra zero) that our suspicion flagging catches.

### What would break in real deployment

1. **Material group taxonomy is client-specific**: We match "diesel" as a keyword in material description. In practice, clients use material group codes like "R001" for fuel, and these codes have no meaning without the client's own material group table. We'd need the client's `T023T` table export to do proper lookups.
2. **Multi-currency POs**: A DE plant paying for fuel in EUR is straightforward. A UK plant paying in GBP for a Euro-priced contract is not — we'd need currency conversion at the PO date.
3. **Scheduling agreements**: Long-term fuel contracts in SAP use `EKEH` (scheduling agreement releases), not standard POs. Different table structure entirely.
4. **Goods receipts vs purchase orders**: We parse what was ordered, not what was received. For accurate Scope 1, we should use `EKBE` (goods receipt history) to get actual delivery quantities. PO quantities can differ from delivered quantities.

---

## Source 2: Utility Electricity

### What we researched

- **Green Button standard**: An ESPI-based XML and CSV standard for utility data exchange, managed by the Green Button Alliance. Used by PG&E, ConEd, Pacific Gas, and implemented via Oracle CC&B and Itron billing systems. The Oracle CC&B documentation shows the CSV configuration options: columns include TYPE, DATE, START TIME, END TIME, USAGE, UNITS, COST.
- **Billing summary format**: Many enterprise utility portals offer a "billing summary" view — one row per billing period per meter. This is what facilities managers use. Common columns: Billing Period, Meter ID, Usage (kWh), Demand (kW), Cost, Tariff.
- **Indian utility portals** (BESCOM, MSEDCL, Tata Power): These use custom web portals but generally offer CSV exports with similar structure. BESCOM (Bangalore) issues bills in units of kWh on a bi-monthly cycle for high-tension commercial connections.
- **Grid emission factors**: 
  - India: CEA (Central Electricity Authority) publishes CO2 Baseline Database annually. 2022 figure: 0.713 kgCO2e/kWh (national grid average)
  - UK: DEFRA 2023 conversion factors: 0.207 kgCO2e/kWh
  - Germany: UBA (Umweltbundesamt) 2023: 0.364 kgCO2e/kWh
  - USA: EPA eGrid 2022 national average: 0.386 kgCO2e/kWh

### What our sample data looks like

`sample_data/electricity_greenbutton.csv`: A billing summary CSV for two meters at a Bangalore office and warehouse, Q1 2024. Contains:
- Monthly billing periods (not calendar months — they run slightly offset as is typical)
- Two meters: MTR-BLR-001 (office, ~18,000 kWh/month) and MTR-BLR-002 (warehouse, ~40,000 kWh/month)
- One record for Mumbai HQ at 55,000 kWh — flagged as suspicious (above our 50,000 kWh single-meter threshold)
- Tariff noted as "HT-Commercial" (High Tension commercial — the appropriate tariff for large commercial buildings in India)

**Why it looks this way**: A real BESCOM HT connection for a commercial building in Bangalore would draw 15,000–20,000 kWh/month for a medium-sized office. A warehouse with heavy equipment is higher. We chose values consistent with BESCOM published consumption data for similar building categories.

### What would break in real deployment

1. **Tariff structure complexity**: HT commercial connections have demand charges (kVA) in addition to energy charges (kWh). Our emission calculation only uses kWh. For completeness we'd want demand data too (though it doesn't change CO2e calculation).
2. **Solar net metering**: Facilities with rooftop solar export power back to the grid. Green Button exports for net-metered accounts show both import and export. We don't handle negative kWh values — our suspicion flag would fire incorrectly.
3. **Multi-state India emission factors**: India's grid is divided into 5 regions with different emission factors (Southern grid: ~0.69, Northern grid: ~0.75). We use the national average. A client with sites in different regions should use regional factors.
4. **Currency in cost fields**: Utility CSVs from India show cost in INR, from UK in GBP. We parse but don't use cost for emission calculation — it's stored in `source_metadata` only.

---

## Source 3: Corporate Travel

### What we researched

- **Concur Expense export**: Concur Expense Processors can export approved expense reports as CSV from the Concur Analytics module. Fields available include: Report Name, Employee ID, Expense Type, Transaction Date, Vendor, City, Country, Amount, Currency. Custom fields (Origin, Destination, Cabin Class) are configured per company — not all Concur installations have them.
- **Navan (formerly TripActions) export**: Navan admins can export trip data as CSV. Fields include: Booking Type, Traveler Name, Departure Date, Origin, Destination, Fare Class, Nights, Amount.
- **IATA airport codes**: 3-letter codes managed by IATA. OurAirports.com provides a free, licensed CSV of all ~7,500 IATA airports with latitude/longitude — our production implementation would load this. We ship a subset of 25 major business travel hubs in the parser.
- **Emission factors — flights**: DEFRA 2023 Greenhouse Gas Reporting provides emission factors per passenger-km by cabin class and haul type. Economy short-haul: 0.1551 kgCO2e/pkm, business class: 0.4286 kgCO2e/pkm.
- **Radiative forcing**: DEFRA publishes factors both "with RF" and "without RF". "With RF" approximately doubles the climate impact to account for contrail warming. We use "without RF" because (a) GHG Protocol Scope 3 doesn't require it, (b) it's methodologically contested, (c) consistency across reporting periods matters more than precision here.
- **Hotels**: DEFRA 2023 average hotel night: 20.6 kgCO2e/room-night. This is a UK average — in practice, a five-star London hotel has a very different footprint from a budget hotel in Pune.
- **Ground transport**: DEFRA 2023 taxi: 0.1491 kgCO2e/km. We estimate 20km for ground trips where no distance is given — a conservative urban assumption.

### What our sample data looks like

`sample_data/concur_travel_export.csv`: A Concur-style CSV for Q1 2024. Contains:
- 3 flights: BOM→LHR (long-haul economy), LHR→FRA (short-haul business), DEL→DXB (medium-haul economy)
- 2 hotel stays: Premier Inn Heathrow (3 nights), Marriott Frankfurt (2 nights)
- 1 ground transport: Uber Mumbai

**Why it looks this way**: An Indian technology company with European clients. Mumbai and Delhi are natural origin airports. The BOM→LHR route is a major long-haul business route (~7,190 km). LHR→FRA is a frequent short-hop for continental meetings (~932 km), often taken in business class. The DEL→DXB route (~2,194 km) covers the India–Gulf corridor.

### What would break in real deployment

1. **Origin/destination not always in IATA format**: Concur sometimes stores "London, United Kingdom" rather than "LHR". We'd need a geocoding step or a city→IATA mapping.
2. **Shared rides and multi-segment flights**: Concur records each booking. A LHR→FRA→ZRH itinerary might appear as one expense or two. We treat each row independently.
3. **Hotel category emission factors**: DEFRA's 20.6 kgCO2e/night is a UK average across all hotel categories. A 5-star hotel has roughly 2x the footprint of a budget property. Without hotel category data, we can't be more precise.
4. **Currency conversion**: Amounts appear in transaction currency (EUR, GBP, USD, INR). We store but don't convert — cost isn't used for CO2e calculation.
5. **Personal travel mixed in**: Some companies run personal expense reimbursements through Concur. We'd need expense category filtering rules to exclude non-business travel.

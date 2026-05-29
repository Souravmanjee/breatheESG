# Breathe ESG — Activity Data Ingestion & Analyst Review Platform

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2-green?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![React](https://img.shields.io/badge/React-18-blue?logo=react&logoColor=white)](https://reactjs.org/)
[![Vite](https://img.shields.io/badge/Vite-5.0-purple?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Database](https://img.shields.io/badge/PostgreSQL-15-blue?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Hosting](https://img.shields.io/badge/Railway-Deploys-black?logo=railway&logoColor=white)](https://railway.app)
[![Hosting](https://img.shields.io/badge/Vercel-Live-black?logo=vercel&logoColor=white)](https://vercel.com)

A robust Django + React prototype built to ingest, normalize, and review raw activity and emissions data from enterprise corporate sources (SAP, Utility Portals, Corporate Travel Platforms). 

This platform acts as the bridge between messy corporate activity logs and audit-ready ESG reporting, complete with a structured analyst workflow, automated carbon calculations, manual correction handling, and rigorous audit trail logging.

---

## 🔗 Live Demo URLs

The application is deployed and fully operational:

*   **Live Application (React Frontend)**: [https://breathe-esg-henna.vercel.app](https://breathe-esg-henna.vercel.app)
*   **Live API Engine (Django Backend)**: [https://breatheesg-production-83a0.up.railway.app](https://breatheesg-production-83a0.up.railway.app)
*   **API Health & Database Status**: [https://breatheesg-production-83a0.up.railway.app/api/health/](https://breatheesg-production-83a0.up.railway.app/api/health/)

### Demo Credentials
Use the pre-seeded tenant administrator credentials:
*   **Username**: `breatheEsgAdmin`
*   **Password**: `Thanksforthetest`
*   **Tenant Slug**: `acme`

---

## 🏗️ System Architecture & Data Flow

Below is the directory structure outlining the separation of concerns:

```text
├── backend/                  # Django REST Framework Service
│   ├── breathe_esg/
│   │   ├── apps/
│   │   │   ├── tenants/      # Row-level multi-tenancy & Auth (analyst/admin)
│   │   │   ├── ingest/       # IngestionRun, RawRow tracking & parser engines
│   │   │   ├── emissions/    # EmissionRecord schema & CO₂e calculations
│   │   │   └── review/       # State machine, approvals & edit audit trails
│   │   └── settings/         # Unified environment settings (SQLite / PG fallback)
│   ├── manage.py
│   ├── requirements.txt
│   ├── railway.toml          # Release pipeline configuration
│   └── Procfile              # Heroku-compatible service runner
│
├── frontend/                 # React + Vite Client (Vanilla CSS & Glassmorphism UI)
│   ├── src/
│   │   ├── components/       # Premium layout, navigation & alert components
│   │   ├── hooks/            # useAuth (JWT context manager)
│   │   ├── pages/            # Login, Dashboard, Upload, Records & RecordDetail
│   │   ├── utils/            # api.js (Axios engine with dynamic endpoint matching)
│   │   └── index.css         # Modern, dark-mode design styling system
│   └── vite.config.js
│
├── docs/                     # Engineering design files
│   ├── MODEL.md              # Rationale behind row-level multi-tenancy
│   ├── DECISIONS.md          # Real-world data quirks resolved & documented
│   ├── TRADEOFFS.md          # Short-term architectural trade-offs made
│   └── SOURCES.md            # Reference data formats & emission factors used
└── sample_data/              # Raw data exports for end-to-end testing
```

---

## ⚡ Core Engineering Features

### 1. Robust Multi-Tenant Parser Engines
Handles raw files of highly varied formats, safely discarding header noise, mapping inconsistent keys, and extracting required metrics:
*   **SAP Procurement Parser**: Reads tab-separated German-header files (`ME2M`), automatically skips irrelevant inventory codes, and parses fuel/quantity records.
*   **Utility Billing Parser**: Extracts billing records from custom summaries, converting variable-length units (kWh, Therms) into standardized metrics.
*   **Corporate Travel Parser**: Parses corporate CSV exports (Concur/Navan style) mapping flights, hotel stays, and ground transport to active carbon categories.

### 2. Strict State Machine
All emissions records adhere to a rigorous lifecycle tracking framework:
`pending` ➔ `flagged` ➔ `approved` ➔ `locked`

### 3. Smart Manual Correction & Recalculation Engine
Analysts can correct human entry errors or OCR/scraping discrepancies directly through the dashboard. The backend:
1.  Intercepts corrections via `PATCH`.
2.  Performs automated unit conversions and fetches updated emission factors.
3.  Recalculates raw activity to accurate `kgCO₂e`.
4.  Persists the correction to an immutable `EmissionRecordEdit` history log (acting as an audit trail).
5.  Prevents changes to `locked` or `approved` data once signed off.

### 4. Health & Liveness Monitoring
A dedicated database-aware endpoint at `/api/health/` runs constant connection checks to ensure database stability and prevent faulty deployment routing.

---

## 💻 Local Development Setup

### Backend (Django)

**1. Set up your virtual environment:**
```bash
cd backend
python -m venv venv

# On macOS/Linux:
source venv/bin/activate
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On Windows (CMD):
.\venv\Scripts\activate.bat
```

**2. Install dependencies:**
```bash
pip install -r requirements.txt
```

**3. Configure environment variables:**
Create a `.env` file in the `backend/` folder or set them in your terminal:
```bash
SECRET_KEY="dev-secret-key-change-in-production"
DEBUG=True
ALLOWED_HOSTS="*"
```

**4. Run database setup & seed demo data:**
```bash
python manage.py migrate
python manage.py seed_demo
```
*(The `seed_demo` command seeds EPA/DEFRA emission factors, tenant memberships, users, and 17 raw parsed activity records).*

**5. Start Django REST API:**
```bash
python manage.py runserver 8000
```

---

### Frontend (React + Vite)

**1. Install packages:**
```bash
cd frontend
npm install
```

**2. Run client server:**
```bash
npm run dev
```
*(The React application runs at `http://localhost:5173` and automatically proxies backend API calls to `http://localhost:8000`).*

---

## 🧪 Running Unit Tests

The backend includes a comprehensive unit testing suite verifying parser edge cases, row-level multi-tenant isolation, calculations, and the correction edit states.

To run the tests locally:
```bash
cd backend
python manage.py test
```

---

## 🔌 API Documentation Reference

All endpoints (except auth and healthcheck) require authentication. Supply the token in the request header: `Authorization: Token <your_token_key>`.

| Method | Endpoint | Description |
|:---|:---|:---|
| **GET** | `/api/health/` | Liveness indicator & DB connection check (Public) |
| **POST** | `/api/auth/login/` | User authentication. Returns API Token (Public) |
| **GET** | `/api/auth/me/` | Retrieves authenticated user profile & tenant roles |
| **POST** | `/api/tenants/{slug}/upload/` | Multipart file upload (SAP, Utility, Travel) |
| **GET** | `/api/tenants/{slug}/ingestion-runs/` | Lists file upload history |
| **GET** | `/api/tenants/{slug}/records/` | Filterable list of tenant emission records |
| **GET** | `/api/tenants/{slug}/records/{id}/` | Retrieves record details & audit logs |
| **PATCH** | `/api/tenants/{slug}/records/{id}/` | Updates record quantity/unit & triggers recalculation |
| **POST** | `/api/tenants/{slug}/records/{id}/review/` | Transition record state (approve, reject, flag, lock) |
| **POST** | `/api/tenants/{slug}/bulk-review/` | Multi-select bulk state approval/flagging |
| **GET** | `/api/tenants/{slug}/stats/` | Aggregated dashboard charts & carbon metrics |

---

## 📈 Deployment Specifications

### Railway (Backend & PostgreSQL)
*   **Release Command**: `python manage.py migrate && python manage.py seed_demo` runs before start to guarantee schema alignment and seed fallback datasets.
*   **Start Command**: Launches high-performance `gunicorn` workers.
*   **Build Environment**: Automatically handled by Nixpacks.

### Vercel (React Frontend)
*   **Vite Configuration**: Statically injects the Railway backend engine URL using `VITE_API_URL`.
*   **Asset Bundling**: Optimizes React files into modular chunked outputs.

# Breathe ESG — Emissions Ingestion & Review Prototype

A Django + React application that ingests fuel/procurement data from SAP, electricity data from utility portals, and business travel data from Concur/Navan, normalizes it to kgCO₂e, and surfaces a review dashboard where analysts can approve records before they're locked for audit.

## Live Demo

- **App**: [deployed URL]
- **Credentials**: analyst / demo1234 · admin_acme / demo1234
- **Tenant slug**: acme

## Architecture

```
backend/          Django REST API
  breathe_esg/
    apps/
      tenants/    Auth, tenant, membership models
      ingest/     IngestionRun, RawRow, three parsers
      emissions/  EmissionRecord, EmissionFactor
      review/     Approve/reject/flag/lock workflow

frontend/         React + Vite
  src/
    pages/        Login, Dashboard, Upload, Records, RecordDetail
    hooks/        useAuth (AuthContext)
    utils/        api.js (axios instance)

docs/             MODEL.md · DECISIONS.md · TRADEOFFS.md · SOURCES.md
sample_data/      Test files for all three source types
```

## Local Setup

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set env vars (or create .env)
export DJANGO_SETTINGS_MODULE=breathe_esg.settings.settings
export SECRET_KEY=your-secret-key
export DEBUG=True

python manage.py migrate
python manage.py seed_demo   # creates tenant, users, sample records

python manage.py runserver   # runs on :8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev    # runs on :5173 with proxy to :8000
```

### Environment Variables (production)

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Django secret key |
| `DATABASE_URL` | PostgreSQL connection string (Railway sets this automatically) |
| `DEBUG` | `False` in production |
| `ALLOWED_HOSTS` | comma-separated, e.g. `myapp.railway.app` |
| `CORS_ALLOWED_ORIGINS` | frontend URL, e.g. `https://myapp.vercel.app` |

## Deploying to Railway

1. Push this repo to GitHub
2. Create a new Railway project, connect the repo
3. Add a PostgreSQL plugin
4. Set environment variables above
5. Railway auto-detects `railway.toml` and runs migrations + seed on release

## Deploying frontend to Vercel

```bash
cd frontend
npm run build
# Deploy dist/ to Vercel
# Set VITE_API_URL env var to your Railway backend URL
```

Or serve the React build from Django (set `VITE_BUILD_DIR` and add a catch-all URL).

## Sample Data Files

All in `sample_data/`:

| File | Source type | Description |
|------|-------------|-------------|
| `sap_fuel_export.txt` | SAP | ME2M tab-separated, German headers, 7 rows (5 fuel + 2 non-fuel to test skipping) |
| `electricity_greenbutton.csv` | Utility | Billing summary, 2 meters, 6 months, 1 suspicious record |
| `concur_travel_export.csv` | Travel | 3 flights, 2 hotels, 1 ground transport |

## Documents

- `docs/MODEL.md` — data model, design decisions, schema rationale
- `docs/DECISIONS.md` — every ambiguity resolved with justification
- `docs/TRADEOFFS.md` — three things deliberately not built and why
- `docs/SOURCES.md` — real-world format research, sample data rationale, what would break

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login/` | Returns token |
| GET | `/api/auth/me/` | Current user + tenants |
| POST | `/api/tenants/{slug}/upload/` | Upload file (multipart) |
| GET | `/api/tenants/{slug}/ingestion-runs/` | List uploads |
| GET | `/api/tenants/{slug}/records/` | List emission records (filterable) |
| GET | `/api/tenants/{slug}/records/{id}/` | Record detail + audit trail |
| POST | `/api/tenants/{slug}/records/{id}/review/` | Approve/reject/flag/lock |
| POST | `/api/tenants/{slug}/bulk-review/` | Bulk approve/reject/flag |
| GET | `/api/tenants/{slug}/stats/` | Dashboard statistics |

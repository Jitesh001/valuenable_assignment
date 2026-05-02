# Benefit Illustration — Valuenable Assignment

A scalable, secure backend (Django + DRF + Postgres) and a minimal React UI
that generates **insurance benefit illustrations**. The focus is domain
modeling, calculation accuracy, security, and a path to bulk-scale processing.

> Companion docs: [`project_details.md`](./project_details.md) (architecture,
> security, scalability) and [`api_details.md`](./api_details.md) (per-endpoint
> contract).

---

## Stack

- **Backend**: Python 3.12, Django 5, Django REST Framework
- **Auth**: JWT (SimpleJWT), with PII (name/DOB/mobile) encrypted at rest
- **DB**: PostgreSQL
- **Frontend**: React 18 + Vite (minimal UI)
- **Tests**: `pytest` + `pytest-django` (calculator + validators)

## Repository layout

```
valuenable_assignment/
├── backend/
│   ├── core/                # Django project (settings, urls, wsgi)
│   ├── accounts/            # User model + JWT auth + PII encryption
│   ├── policies/
│   │   ├── domain/          # Pure-python calculator + validators (no Django)
│   │   ├── repositories.py  # Data-access layer
│   │   ├── services.py      # Application service (orchestration)
│   │   ├── serializers.py   # DRF request/response shapes
│   │   ├── views.py         # API endpoints (transport only)
│   │   └── tests/           # Unit tests for the calculation engine
│   ├── manage.py
│   ├── requirements.txt
│   ├── pytest.ini
│   └── .env.example
├── frontend/                # Vite + React minimal UI
├── README.md
├── project_details.md
└── api_details.md
```

---

## Prerequisites

Install these once before cloning:

| Tool       | Required version | Verify with                |
| ---------- | ---------------- | -------------------------- |
| Python     | **3.12.x**       | `python3.12 --version`     |
| Node.js    | **20+** (24 ok)  | `node --version`           |
| npm        | **9+** (11 ok)   | `npm --version`            |
| PostgreSQL | **14+**          | `psql --version`           |
| git        | any              | `git --version`            |

A working Postgres instance must be reachable on `localhost:5432` (or whatever
host/port you put in `backend/.env`).

> **Note on Python**: The repo pins `3.12` via `.python-version` (read by
> `pyenv`). If you don't use `pyenv`, just make sure `python3.12` is on your
> PATH.

---

## 1) Clone the repository

```bash
git clone https://github.com/Jitesh001/valuenable_assignment.git
cd valuenable_assignment
```

---

## 2) Create the Postgres database

The repo's defaults expect a database named `valuenable` owned by the OS user.
Two common ways:

**A. Use your existing OS user as the DB role** (simplest on macOS/Linux):

```bash
createdb valuenable
```

**B. Create a dedicated role** (matching the committed `.env.example`):

```bash
createuser -s jitesh                       # only if the role doesn't exist
createdb -O jitesh valuenable
```

Either way, you'll set the actual user/host/password in `backend/.env` below.

---

## 3) Backend setup

### 3a. Create the virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate                  # or:  .venv/bin/activate.fish, etc.
```

> If you prefer to keep using the venv without activating, every command below
> can also be run as `./.venv/bin/python …`.

### 3b. Install Python dependencies

```bash
pip install -r backend/requirements.txt
```

### 3c. Configure environment variables

The real `.env` is **gitignored** — copy the template and fill it in:

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and set at least:

```
DJANGO_SECRET_KEY=<any long random string>
POSTGRES_DB=valuenable
POSTGRES_USER=<your-postgres-username>
POSTGRES_PASSWORD=<your-postgres-password-or-empty>
DB_HOST=localhost
DB_PORT=5432
FIELD_ENCRYPTION_KEY=<generated below>
```

Generate `FIELD_ENCRYPTION_KEY` (used to encrypt PII at rest):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output into `FIELD_ENCRYPTION_KEY=` in `backend/.env`.

> **Important**: keep this key safe. Losing it means losing access to every
> encrypted PII column in the database. In production it should come from a
> secrets manager (AWS Secrets Manager / Vault / SSM).

### 3d. Run migrations and seed reference data

```bash
cd backend
python manage.py migrate
python manage.py seed_reference   # dummy PolicyTypes (ENDOW/TERM/ULIP) and Riders
python manage.py createsuperuser  # optional, for /admin/
```

### 3e. Start the API

```bash
python manage.py runserver 0.0.0.0:8000
```

- API root:      http://localhost:8000/api/
- Swagger UI:    http://localhost:8000/api/docs/
- OpenAPI JSON:  http://localhost:8000/api/schema/
- Django admin:  http://localhost:8000/admin/

### 3f. Run the unit tests

```bash
# from backend/, with the venv active
python -m pytest -v
```

27 tests cover the calculator and the 5 spec validators. They don't need a DB.

---

## 4) Frontend setup

In a **new terminal** (leave the backend running):

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The Vite dev server proxies `/api/*` → `http://localhost:8000`, so the backend
must be running.

Production build:

```bash
npm run build        # output in frontend/dist/
```

---

## 5) Smoke test (curl)

```bash
# Register
curl -s -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "email":"demo@example.com","password":"DemoPass123!",
    "full_name":"Demo User","dob":"1990-01-01","mobile":"9876543210"
  }' | python -m json.tool

# Login
ACCESS=$(curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"DemoPass123!"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['access'])")

# Generate an illustration (no DB write)
curl -s -X POST http://localhost:8000/api/policies/illustrate/ \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{
    "policy_type":"ENDOW","dob":"1990-01-01","gender":"M",
    "premium":"25000","premium_frequency":"annual",
    "premium_term":7,"policy_term":15,"sum_assured":"500000"
  }' | python -m json.tool
```

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `psql: FATAL: role "<user>" does not exist` | Create the role: `createuser -s <user>`, or set the right user in `backend/.env`. |
| `django.db.utils.OperationalError: connection refused` | Postgres isn't running, or `DB_HOST`/`DB_PORT` are wrong. |
| `RuntimeError: FIELD_ENCRYPTION_KEY is not configured` | You skipped step 3c — generate the key and paste it into `.env`. |
| `Invalid token` after login | Old key in `localStorage`. Logout in the UI or `localStorage.clear()` in DevTools. |
| CORS errors in the browser | Backend must be on `:8000` and frontend on `:5173`; both are the defaults. |

---

## What's implemented

- Layered backend (transport / service / domain / repository).
- Calculation engine isolated from Django, deterministic, fully unit-tested.
- All **5 input validations** from the spec, errors collected and returned together.
- **Age Completed Birthday (ACB)** age computation, leap-day safe.
- JWT auth (access + rotating refresh).
- **PII encryption at rest** with Fernet; per-row HMAC fingerprint for
  indexed lookups; masked outputs in API responses.
- Idempotency via `Idempotency-Key` header.
- Throttling via DRF default rate limits (`anon=30/min`, `user=120/min`).
- React UI with Login / Register / Illustration / History pages.
- OpenAPI schema + Swagger UI.
- Seed command for dummy reference data.

See [`project_details.md`](./project_details.md) for the deeper architecture
and scalability story, and [`api_details.md`](./api_details.md) for the
per-endpoint reference.

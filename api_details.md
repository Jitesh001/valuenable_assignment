# API Details

Base URL: `http://localhost:8000/api`

All non-auth endpoints require `Authorization: Bearer <access_token>`.
Live OpenAPI / Swagger UI is served at `/api/docs/`.

---

## Conventions

- Content type is **JSON** in/out.
- Times are ISO-8601, monetary values are decimal strings (no float drift).
- Validation failures return **HTTP 400** with `{ "detail": "...", "errors": [...] }`.
- Auth failures return **HTTP 401**.
- Resource-not-found returns **HTTP 404**.
- All endpoints are throttled (`anon=30/min`, `user=120/min`).

---

## Authentication

### `POST /auth/register/`
Create a new user. Stores `full_name`, `dob`, and `mobile` **encrypted at rest**
(Fernet) and computes a deterministic HMAC for `mobile` to support indexed
lookups without decrypting.

**Body**
```json
{
  "email": "demo@example.com",
  "password": "DemoPass123!",
  "full_name": "Demo User",
  "dob": "1990-01-01",
  "mobile": "9876543210"
}
```

**Response 201**
```json
{
  "user": {
    "id": 1,
    "email": "demo@example.com",
    "full_name": "D*** U***",
    "mobile": "******3210",
    "dob": "****-**-**",
    "created_at": "2026-05-02T10:11:12Z"
  },
  "access": "...",
  "refresh": "..."
}
```

**Errors**
- `400` — invalid email, weak password, mobile not 10-digit Indian, DOB in future.

---

### `POST /auth/login/`
Standard SimpleJWT obtain-pair.

**Body**
```json
{ "email": "demo@example.com", "password": "DemoPass123!" }
```

**Response 200**
```json
{ "access": "...", "refresh": "..." }
```

---

### `POST /auth/refresh/`
Rotate the access token. Refresh tokens rotate too (see SimpleJWT settings).

**Body**
```json
{ "refresh": "..." }
```

**Response 200**
```json
{ "access": "...", "refresh": "..." }
```

---

### `GET /auth/me/`
Returns the current user (PII fields **masked**).

**Response 200**
```json
{
  "id": 1,
  "email": "demo@example.com",
  "full_name": "D*** U***",
  "mobile": "******3210",
  "dob": "****-**-**",
  "created_at": "2026-05-02T10:11:12Z"
}
```

---

## Policy reference data

### `GET /policies/types/`
List active policy types (seeded via `manage.py seed_reference`).

**Response 200**
```json
[
  { "code": "ENDOW", "name": "Endowment Plan", "description": "..." },
  { "code": "TERM",  "name": "Term Plan",      "description": "..." },
  { "code": "ULIP",  "name": "Unit-Linked Plan","description": "..." }
]
```

---

## Illustration

There are **two** illustration endpoints with the same input shape but
different persistence semantics:

| Endpoint | Persists? | When to use |
| --- | --- | --- |
| `POST /policies/illustrate/` | **No** | Live what-if previews from the UI. Cheap. |
| `POST /policies/calculate/`  | **Yes** (creates a `PolicyQuote` row) | When the user explicitly wants the quote saved. Honours `Idempotency-Key`. |

### Common request body

```json
{
  "policy_type": "ENDOW",
  "dob": "1990-01-01",
  "quote_date": "2026-05-02",          // optional, defaults to today
  "gender": "M",                       // "M" | "F" | "O"
  "premium": "25000",
  "premium_frequency": "annual",       // annual | semi | quarterly | monthly
  "premium_term": 7,                   // 5–10
  "policy_term": 15,                   // 10–20, must be > premium_term
  "sum_assured": "500000",             // ≥ max(10× premium, ₹5,00,000)
  "riders": ["ADB", "WOP"]             // optional rider codes
}
```

### Validation error shape (HTTP 400)

```json
{
  "detail": "Validation failed.",
  "errors": [
    "Age at entry must be between 23 and 56 (got 13).",
    "Annual premium must be between ₹10,000 and ₹50,000.",
    "Premium payment term must be between 5 and 10 years.",
    "Policy term must be strictly greater than premium term.",
    "Sum assured must be at least ₹5,00,000 (max of 10× premium and ₹5,00,000)."
  ]
}
```

The five business validations come from `policies/domain/validators.py`
and are returned **all at once** rather than one-at-a-time.

---

### `POST /policies/illustrate/` — stateless calculation

**Response 200** (illustration body — does **not** create a `PolicyQuote`):

```json
{
  "policy_type": "ENDOW",
  "result": {
    "age_at_entry": 36,
    "annualized_premium": "25000",
    "sum_assured": "500000",
    "policy_term": 15,
    "premium_term": 7,
    "assumed_return_lower": "0.04",
    "assumed_return_higher": "0.08",
    "rows": [
      {
        "policy_year": 1,
        "age": 36,
        "annualized_premium": "25000",
        "cumulative_premium": "25000",
        "death_benefit": "500000",
        "accrued_bonus_lower": "15000",
        "accrued_bonus_higher": "27500",
        "surrender_value_lower": "2250",
        "surrender_value_higher": "4125",
        "maturity_benefit_lower": "0",
        "maturity_benefit_higher": "0"
      }
    ]
  }
}
```

---

### `POST /policies/calculate/` — persisted

Same input shape. Optional header:

```
Idempotency-Key: <client-generated UUID v4>
```

If two requests arrive with the same `(user, Idempotency-Key)` pair, the
second one returns the **original** persisted quote — never recomputes,
never duplicates. Implemented via a partial unique index in Postgres.

**Response 201**
```json
{
  "id": 7,
  "policy_type": "ENDOW",
  "age_at_entry": 36,
  "gender": "M",
  "premium": "25000.00",
  "premium_frequency": "annual",
  "premium_term": 7,
  "policy_term": 15,
  "sum_assured": "500000.00",
  "result": { ...same shape as /illustrate/ response... },
  "created_at": "2026-05-02T10:30:00Z"
}
```

**Errors**
- `400` — input or business validation failed.
- `404` — `policy_type` code unknown.
- `401` — missing / expired access token.

---

## Quote history

### `GET /policies/quotes/`
Paginated list of the **caller's** persisted quotes, newest first.

**Response 200**: array of `PolicyQuote` records (see `/calculate/` response).

### `GET /policies/quotes/{id}/`
Retrieve one quote by id. **Scoped to the authenticated user** (a different
user's id returns 404, never 200).

---

## OpenAPI / docs

- Schema (JSON):  `GET /api/schema/`
- Swagger UI:      `GET /api/docs/`

---

## Status code reference

| Code | Meaning |
| --- | --- |
| 200 | OK (read / stateless calc) |
| 201 | Created (register / persisted calculate) |
| 400 | Validation failure (DRF or domain) |
| 401 | Missing/expired/invalid token |
| 403 | Authenticated but not allowed |
| 404 | Resource not found / not yours |
| 429 | Throttled (`Retry-After` returned) |
| 500 | Server error (we log; never include PII) |

---

## Notes on bulk processing

The same calculator is reused inside the bulk worker (Celery task). The
public REST API is intentionally per-policy because:

- Per-call latency is microseconds; HTTP overhead would dominate at scale.
- A bulk endpoint that *blocks* on millions of rows is hostile to clients.

The recommended bulk shape (not implemented in this assignment, but the
foundation is laid) is:

```
POST /api/policies/bulk/         body: {"input_url":"s3://.../in.csv"}
   → 202 Accepted { "job_id": "..." }

GET  /api/policies/bulk/{job_id}/
   → 200 { "status":"running","completed":420131,"total":1000000 }
   → 200 { "status":"done","output_url":"s3://.../out.parquet" }
```

See [`project_details.md`](./project_details.md) → **Scalability** for the
full pipeline diagram.

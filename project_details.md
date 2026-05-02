# Project Details — Architecture, Security, and Scalability

This document explains *how* the system is built and *why*. The companion
[`api_details.md`](./api_details.md) covers the per-endpoint contract.

---

## 1. Architecture

The backend is intentionally split into four layers so each can be tested,
swapped, or scaled independently.

```
┌─────────────────────────────────────────┐
│  HTTP / DRF (Transport)                 │  views.py, serializers.py, urls.py
│  - request validation, auth, throttling │
└──────────────┬──────────────────────────┘
               │ DTO (validated_data)
┌──────────────▼──────────────────────────┐
│  Application Service                    │  services.py
│  - orchestrates use-cases               │
│  - idempotency, transactions            │
└──────────────┬──────────────────────────┘
               │ PolicyInput (pure-python value object)
┌──────────────▼──────────────────────────┐
│  Domain                                 │  domain/validators.py, domain/calculator.py
│  - business rules (5 validations)       │  NO Django imports.
│  - benefit illustration math            │
└──────────────┬──────────────────────────┘
               │ ORM model objects
┌──────────────▼──────────────────────────┐
│  Repositories (Data Access)             │  repositories.py
│  - all queries live here                │
│  - perfect place for query optimisation │
└─────────────────────────────────────────┘
```

**Why this matters for the assignment:**

- The calculator (`policies/domain/calculator.py`) and the 5 validations
  (`policies/domain/validators.py`) are **plain Python** — they don't import
  Django, DRF, or models. That makes them trivially unit-testable
  (`pytest policies/tests/`) and reusable from a Celery worker, a CLI tool,
  or a CSV batch job — see Scalability below.
- Views are thin: parse → DTO → service → response. Easy to add a v2 or a
  GraphQL gateway without touching business logic.

### Key files

| File | Purpose |
| --- | --- |
| `policies/domain/validators.py` | `PolicyInput` value object, `age_acb`, all 5 validations |
| `policies/domain/calculator.py` | `IllustrationCalculator.run(input) → IllustrationResult` |
| `policies/services.py`          | `IllustrationService.illustrate(cmd)` (idempotency, persistence) |
| `policies/repositories.py`      | All ORM queries |
| `policies/views.py`             | DRF API endpoints |
| `accounts/crypto.py`            | Fernet helpers + `EncryptedCharField` |

---

## 2. Domain modeling

The domain is modeled to absorb new policy types and riders **without
touching the calculator core**:

| Model | Role |
| --- | --- |
| `PolicyType`        | Reference data — `ENDOW`, `TERM`, `ULIP`, etc. New product = a row. |
| `Rider`             | Optional add-ons (ADB, CI, WOP). |
| `PolicyVersion`     | Versioned assumption set per `PolicyType`. Lets us evolve calculator factor tables (bonus rates, GSV factors) over time while keeping historical illustrations reproducible. |
| `PolicyQuote`       | Snapshot of inputs **plus** the computed `result` JSON. Indexed on `(user, -created_at)` and `(policy_type, -created_at)`. |
| `User` (accounts)   | Email login. PII (`full_name_enc`, `dob_enc`, `mobile_enc`) stored as ciphertext. `mobile_fp` is a deterministic HMAC for indexed lookups. |

**Extensibility patterns**:

- Adding a new policy type: insert a `PolicyType` row + a new
  `PolicyVersion` (no code change needed if the existing factor tables apply).
- Adding new bonus / surrender logic: introduce a strategy (`BonusStrategy`,
  `SurrenderStrategy`) keyed off `PolicyType.code` inside `domain/`. The
  calculator stays a single orchestrator that delegates per scenario.
- Versioning calculation logic: every `PolicyQuote` records
  `policy_version`. To roll out v2, deploy code that picks the strategy per
  version — old quotes recompute using their original version, new quotes
  use v2.

---

## 3. Calculation engine

`IllustrationCalculator.run(PolicyInput)` produces an `IllustrationResult`
whose rows match what an IRDAI benefit-illustration sheet contains:

For each policy year `t`:
- `annualized_premium_t` = `P` if `t ≤ PPT` else `0`
- `cumulative_premium_t` = Σ premiums paid through year `t`
- `death_benefit_t` = `max(SA, 10·P, 1.05·cumulative_premium_t)`
- `accrued_bonus_t[scen]` = `t · (bonus_rate[scen] · SA / 1000)`
- `surrender_value_t[scen]` =
    `gsv_factor[t] · cumulative_premium + gsv_bonus_factor[t] · accrued_bonus[scen]`
- `maturity_t[scen]` (only when `t == PT`) = `SA + accrued_bonus + terminal_bonus`

Two scenarios are produced (`lower` ≈ 4 % gross, `higher` ≈ 8 % gross), per
the IRDAI two-scenario rule. The factor tables and rates are documented
constants in `calculator.py`; in production they'd live in a versioned
`PolicyVersion` row so historical reproducibility is preserved.

**Determinism** is verified by a unit test: same input → identical output.
This is essential for caching, idempotency, and replay.

### Validations (the five)

Lives in `domain/validators.py::validate_inputs`. Errors are **collected**,
not short-circuited, so the API surfaces every problem in a single response.

| # | Rule |
| --- | --- |
| 1 | `23 ≤ age_at_entry ≤ 56` (computed via ACB) |
| 2 | `₹10,000 ≤ premium ≤ ₹50,000` |
| 3 | `5 ≤ premium_term ≤ 10` |
| 4 | `10 ≤ policy_term ≤ 20` and `policy_term > premium_term` |
| 5 | `sum_assured ≥ max(10 × premium, ₹5,00,000)` |

Age uses **Age Completed Birthday (ACB)**: integer years fully elapsed since
DOB on `quote_date`; defaults to today if not supplied.

---

## 4. Security & data protection

### PII encryption at rest

`accounts/crypto.py` provides:

- `EncryptedCharField` — a Django model field that calls Fernet on every
  save / load. The DB only sees ciphertext.
- A **deterministic HMAC fingerprint** (`mobile_fp`) so we can do
  exact-match lookups (e.g. login by mobile, prevent duplicate signups)
  **without** decrypting the whole table.
- Masking helpers (`mask_name`, `mask_mobile`, `mask_dob`). All API
  read serializers emit masked values — never raw PII.

**Key management**: `FIELD_ENCRYPTION_KEY` is loaded from env via
`python-decouple`. There is **no key in source**. Rotation is a future
extension: tag ciphertext with key-id (`v1:…`, `v2:…`), maintain a
small registry, decrypt with old key, re-encrypt with new key offline.

### Logging

`LOGGING` in `settings.py` formats logs without bodies, and routes
`django.request` at `WARNING` so request payloads aren't leaked at INFO.
The `User.__str__` method deliberately includes only the email — never the
encrypted blob — so it's safe in admin listings and exception messages.

### Secrets

Every secret (`DJANGO_SECRET_KEY`, DB password, `FIELD_ENCRYPTION_KEY`,
JWT TTLs) is in env. `.env.example` documents the contract; `.env` is
intended to be local-only and excluded from real-world git. In production
they'd be served from Vault / AWS Secrets Manager / SSM Parameter Store.

### Threat surface

| Concern | Mitigation |
| --- | --- |
| Input validation | DRF serializers (types, ranges) + domain `validate_inputs` (5 business rules). |
| AuthN | JWT (SimpleJWT). 30-min access, 7-day rotating refresh. |
| AuthZ | All policy endpoints require `IsAuthenticated`; quotes filtered by `user_id`. |
| Rate limiting | DRF throttles: `anon=30/min`, `user=120/min`. In prod, push to API-gateway / WAF. |
| CSRF | API is JWT-authenticated and CORS-restricted; CSRF middleware kept enabled for the admin. |
| CORS | `CORS_ALLOWED_ORIGINS` is env-driven, defaults to `http://localhost:5173` only. |
| Mass-assignment | Serializers explicitly enumerate writable fields. |
| Replay / dupe | `Idempotency-Key` header → `unique(user, key)` partial index. |
| SQL-injection | Django ORM, no raw SQL. |
| Password storage | Django's PBKDF2 default; min 8 chars + similarity / common-pwd validators. |

---

## 5. Database design

### Schema

- `accounts_user` — `email UNIQUE`, encrypted PII columns + indexed `mobile_fp`.
- `policies_policytype` — small reference table.
- `policies_rider` — small reference table.
- `policies_policyversion` — composite unique on `(policy_type, version)`,
  index on `(policy_type, effective_from)`.
- `policies_policyquote` — heavy table. Indexes:
  - `(user_id, -created_at)` — user history pagination
  - `(policy_type_id, -created_at)` — analytics by product
  - **Partial unique** `(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL`
    — drops storage cost while still preventing replay.

### Why Postgres (vs NoSQL)

We're storing **strongly relational** data: users → quotes → policy types,
audit-trail style writes, and we want transactional integrity on the
"register a quote" flow. Postgres also gives us:

- `JSONB` for the `result` column — best of both worlds (relational
  inputs, document outputs, with GIN-indexable querying if we ever need it).
- Partial / composite indexes for cheap idempotency.
- Mature replication for read scaling.

NoSQL trade-offs we *would* accept:
- A document store (Mongo, DynamoDB) is attractive **only** for raw write
  throughput on the `policy_quote` table at extreme scale (≥ tens of millions
  per day).
- The cost: weaker referential integrity (we'd need an outbox pattern), no
  transactions across users + quotes, more app-side joins. For the read paths
  we have (history + per-quote detail), Postgres is the cleaner default.

### Sensitive-data masking strategy

| Field | At rest | In API responses | In logs |
| --- | --- | --- | --- |
| `email` | plaintext (login key) | plaintext | plaintext |
| `full_name` | Fernet ciphertext | masked (`J*** D**`) | never |
| `dob` | Fernet ciphertext | `****-**-**` | never |
| `mobile` | Fernet ciphertext + HMAC fingerprint | `******1234` | never |
| `password` | PBKDF2 hash | never | never |

---

## 6. Scalability — single policy → millions

The single-policy path goes through `views → service → calculator`. To
process millions of records per run, the path becomes:

```
[CSV / S3 / Kafka producer]
            │
            ▼
   ┌──────────────────┐  (idempotency-keyed jobs)
   │  Job queue       │  Redis Streams / RabbitMQ / SQS
   └─────────┬────────┘
             │ pulled in batches
   ┌─────────▼──────────────────────┐
   │  Worker fleet (horizontally    │
   │  scaled — N pods)              │
   │  - reuses domain/calculator.py │
   │  - writes via COPY / bulk_create│
   └─────────┬──────────────────────┘
             │
   ┌─────────▼─────────────────┐
   │  Postgres (writer)        │
   │  partitioned by month or  │
   │  hash(user_id) for hot    │
   │  tables                   │
   └───────────────────────────┘
```

**Why this works in this codebase:**

- `IllustrationCalculator` is **stateless** and pure-Python, so a worker
  process can call `.run()` in a tight loop. No DB round-trip per record.
- `IllustrationService` already supports `persist=False`, useful when the
  result is being streamed to S3 instead of the DB.
- `Idempotency-Key` already prevents double-insertion if a worker retries.

**Practical levers**:

- **Bulk write**: `Model.objects.bulk_create(quotes, batch_size=1000)` —
  ~50× faster than per-row `.save()`. Even faster: drop to `psycopg2.copy_from`
  for true millions/run loads.
- **Async ingestion**: Celery with Redis broker; one task per shard
  (e.g. 10k records per task). Tasks are idempotent (each carries its
  shard's `idempotency_key`), so retries are safe.
- **Streaming vs batch**: a Kafka topic + a Python consumer using
  `aiokafka` lets us add `IllustrationCalculator` calls inline. Throughput
  scales by adding partitions + consumer pods.
- **Horizontal scaling**: stateless workers behind a queue → trivially
  scaled (HPA on CPU). The DB becomes the bottleneck before the engine does.
- **DB read scaling**: history endpoints read `(user_id, -created_at)`;
  send those to a read replica. Use cursor pagination on `created_at` to
  avoid `OFFSET` blow-up.
- **Caching**: `(input_hash, policy_version)` is a perfect cache key.
  Lookup → Redis (1ms) before running the calculator. Hot what-if previews
  on the UI become free after the first hit.
- **Idempotency + retries**: every endpoint that mutates accepts
  `Idempotency-Key`, enforced by partial unique index. Workers retry on
  failure; duplicate inserts are no-ops.
- **Backpressure**: queue depth + worker concurrency are the natural knobs.
  Add DLQ for poison messages; surface them in an admin dashboard.

### Why DRF + sync views are still fine for the public API

The user-facing API is bound by **per-request latency**, not throughput.
A single illustration is microseconds of CPU; the surface that needs to go
async is the **bulk pipeline**, which lives outside the request/response
cycle. Keeping the public API synchronous avoids the operational complexity
of `asgi` while letting workers absorb the heavy traffic.

---

## 7. What I'd add next

- **Bulk endpoint**: `POST /api/policies/bulk/` accepting an S3 URL or an
  inline CSV; returns a `job_id` immediately, status + signed-URL output
  once done. The calculator already supports this — only the queue plumbing
  is missing.
- **Calculation versioning**: actually load factor tables from
  `PolicyVersion` rather than module constants.
- **Audit log**: a separate write-only table that records every
  illustration request hashed (no PII), for compliance.
- **End-to-end Cypress test** of the React flow.
- **Refresh-token rotation + blacklist** (already partially configured).

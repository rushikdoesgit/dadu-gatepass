# Advanced Gatepass System
**DADU Inductions Hackathon — Backend Submission**

A robust, role-based campus gate pass management system built with FastAPI, SQLAlchemy 2.0 (async), and SQLite. Supports student outpasses, visitor day passes, faculty RFID vehicle passes, conference passes, rotating TOTP QR codes, OTP verification, and full SWD app integration.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Database | SQLite (via aiosqlite) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Auth | JWT (HS256 local + RS256 SWD) |
| Password hashing | bcrypt (passlib) |
| QR generation | qrcode + pyotp (TOTP, 45s window) |
| Validation | Pydantic v2 |

---

## Project Structure

```
src/
├── main.py                  # FastAPI app entry point
├── config.py                # Settings (DATABASE_URL, JWT keys, SWD config)
├── security.py              # bcrypt, JWT creation and decoding
├── api/
│   ├── dependencies.py      # get_current_user (dual HS256/RS256), RoleChecker
│   └── v1/
│       ├── auth.py          # POST /login, POST /swd-login
│       ├── passes.py        # Pass CRUD, QR, OTP endpoints
│       ├── warden.py        # Warden approval queue
│       ├── gate.py          # Gate scan verification
│       ├── admin.py         # RFID blacklisting
│       └── swd.py           # Mock SWD JWKS + token issuer
├── db/
│   ├── session.py           # Async engine + session factory
│   └── models/
│       ├── base.py          # Base + TimestampMixin
│       ├── enums.py         # Role, PassStatus, ResidencyStatus, StudentTier
│       ├── identity.py      # User, Hostel, StudentProfile
│       ├── passes.py        # Pass, PassType, PassBatch, PassOTP, PassVehicle, PassApproval, BlacklistedRFID
│       └── logging.py       # AccessLog
└── services/
    ├── auth_service.py      # SWD RS256 token verification
    ├── pass_service.py      # Pass + vehicle pass creation logic
    ├── gate_service.py      # RFID verification, anti-passback, access logging
    └── qr_service.py        # TOTP QR generation and verification
scripts/
└── seed_db.py               # Seeds test users and pass types
migrations/                  # Alembic migration files
```

---

## Setup Instructions

### 1. Prerequisites
- Python 3.12
- pip

### 2. Create and activate virtual environment

**Windows (cmd):**
```cmd
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt --prefer-binary
```

### 4. Set up the database
```bash
# Delete old database if it exists
del gatepass.db        # Windows
rm gatepass.db         # Linux/Mac

# Run migrations to create all tables
alembic upgrade head

# Seed test users and pass types
python -m scripts.seed_db
```

### 5. Start the server
```bash
uvicorn src.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`  
Interactive Swagger UI at `http://127.0.0.1:8000/docs`

---

## Environment Variables

Create a `.env` file in the project root (all have safe defaults for local dev):

```env
# Database
DATABASE_URL=sqlite+aiosqlite:///gatepass.db

# JWT secret for local HS256 tokens
AES_ENCRYPTION_KEY=32_byte_secret_key_for_aes_encryption_here_!!!!

# QR code rotation interval in seconds
QR_STEP_INTERVAL_SECONDS=45

# SWD Integration
SWD_ISSUER=https://swd.campus.edu
SWD_CLIENT_ID=gatepass_system_client
SWD_JWKS_URL=http://localhost:8000/api/v1/mock-swd/.well-known/jwks.json
```

---

## Seeded Test Users

All accounts use password: **`password123`**

| Role | Email | Description |
|---|---|---|
| `STUDENT` | `test_student@example.com` | Can apply for passes, view own QR |
| `WARDEN` | `test_warden@example.com` | Approves/rejects student passes, blacklists RFID |
| `GUARD` | `test_guard@example.com` | Scans QR and RFID at the gate |
| `FACULTY` | `test_faculty@example.com` | Requests RFID vehicle passes |

**Seeded Pass Types:**

| Name | Requires Approval |
|---|---|
| `DAY_PASS` | No (auto-approved) |
| `OUTSTATION` | Yes (warden approval) |
| `VACATION` | Yes (warden approval) |
| `VEHICLE` | Yes (warden approval) |

---

## API Reference

All endpoints are documented interactively at `/docs`. Below is a summary:

### Auth
| Method | Endpoint | Description | Auth |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Login with email/password, get JWT | None |
| POST | `/api/v1/auth/swd-login` | Exchange SWD RS256 token for local JWT | None |

### Passes
| Method | Endpoint | Description | Role |
|---|---|---|---|
| POST | `/api/v1/passes/request` | Apply for a new pass | STUDENT |
| POST | `/api/v1/passes/vehicle-request` | Request RFID vehicle pass | FACULTY |
| GET | `/api/v1/passes/` | List passes (scoped by role) | Any |
| PATCH | `/api/v1/passes/{id}/status` | Approve or reject a pass | WARDEN |
| POST | `/api/v1/passes/{id}/revoke` | Revoke an active pass | WARDEN |
| GET | `/api/v1/passes/{id}/qr` | Get rotating QR code (PNG) | Owner / GUARD |
| GET | `/api/v1/passes/{id}/qr/view` | View QR code in browser | Owner / GUARD |
| POST | `/api/v1/passes/{id}/send-otp` | Send OTP for visitor verification | Any |
| POST | `/api/v1/passes/{id}/verify-otp` | Verify visitor OTP at gate | GUARD |

### Warden
| Method | Endpoint | Description | Role |
|---|---|---|---|
| GET | `/api/v1/warden/pending` | List all pending passes | WARDEN |

### Gate Operations
| Method | Endpoint | Description | Role |
|---|---|---|---|
| POST | `/api/v1/gate/verify` | Verify QR scan at gate | GUARD |

### Admin
| Method | Endpoint | Description | Role |
|---|---|---|---|
| POST | `/api/v1/admin/blacklist-rfid` | Blacklist RFID tag + revoke linked passes | WARDEN |

### SWD Mock (Integration Testing)
| Method | Endpoint | Description | Auth |
|---|---|---|---|
| GET | `/api/v1/mock-swd/.well-known/jwks.json` | Public JWKS endpoint | None |
| GET | `/api/v1/mock-swd/token` | Issue a signed RS256 student token | None |

---

## Testing the Full Student Outpass Flow

### Step 1 — Login as student
In Swagger (`/docs`), click **Authorize** → enter:
- Username: `test_student@example.com`
- Password: `password123`

### Step 2 — Create a pass (requires warden approval)
`POST /api/v1/passes/request`
```json
{
  "pass_type": "OUTSTATION",
  "purpose": "Going home for the weekend",
  "valid_from": "2026-06-08T10:00:00Z",
  "valid_until": "2026-06-09T20:00:00Z"
}
```
Copy the `pass_id` from the response.

### Step 3 — Approve as warden
Log out, log in as `test_warden@example.com`.

`GET /api/v1/warden/pending` — verify the pass appears.

`PATCH /api/v1/passes/{pass_id}/status`
```json
{
  "status": "APPROVED",
  "warden_comment": "Approved"
}
```

### Step 4 — Get the QR code
Log back in as student. Open in browser:
```
http://127.0.0.1:8000/api/v1/passes/{pass_id}/qr/view
```
The QR rotates every 45 seconds.

### Step 5 — Scan at gate
Log in as `test_guard@example.com`.

Get the raw QR payload from:
```
http://127.0.0.1:8000/api/v1/passes/{pass_id}/qr
```

`POST /api/v1/gate/verify`
```json
{
  "scanned_payload": "v1:{pass_id}:{token}",
  "gate_id": "00000000-0000-0000-0000-000000000001",
  "direction": "OUT"
}
```

---

## Testing the RFID Vehicle Flow

### Step 1 — Faculty requests vehicle pass
Login as `test_faculty@example.com`.

`POST /api/v1/passes/vehicle-request`
```json
{
  "vehicle_number": "TS09AB1234",
  "vehicle_model": "Honda City",
  "rfid_tag_id": "RFID_TAG_001",
  "purpose": "Daily commute",
  "valid_until": "2026-12-31T23:59:59Z"
}
```

### Step 2 — Warden approves the vehicle pass
Login as warden. Use `PATCH /api/v1/passes/{pass_id}/status` with `"status": "APPROVED"`.

### Step 3 — Simulate RFID scan at gate
Login as guard. `POST /api/v1/gate/verify` with RFID payload — handled via `gate_service.verify_rfid_access()`.

### Step 4 — Blacklist a stolen tag
As warden, `POST /api/v1/admin/blacklist-rfid`:
```json
{
  "rfid_tag_id": "RFID_TAG_001",
  "reason": "Tag reported stolen"
}
```
All linked passes are automatically revoked.

---

## Testing the SWD Integration Flow

This simulates how the existing SWD student app integrates with this system.

### Step 1 — Get a mock RS256 token from SWD
```
GET /api/v1/mock-swd/token?student_id=2021A7PS001H&name=John+Doe&email=john@example.com&role=STUDENT
```

### Step 2 — Exchange for a local JWT
`POST /api/v1/auth/swd-login`
```json
{
  "swd_token": "<token from step 1>"
}
```
Response includes `"provisioned": true` if the user was auto-created.

### Step 3 — Use the local token
Use the returned `access_token` as a Bearer token to call any student endpoint. The auto-provisioned user has full STUDENT access.

---

## Innovative Features

### 1. Rotating TOTP QR Codes
QR codes use `pyotp.TOTP` with a 45-second interval. The payload format is `v1:{pass_id}:{totp_token}`. Screenshots become invalid within 45 seconds. The gate accepts the current and immediately preceding window (`valid_window=1`) to tolerate scanning lag.

### 2. Anti-Passback State Machine
Each pass tracks `has_exited` and `has_entered` boolean flags. The system prevents:
- Exiting without an approved pass
- Exiting twice without re-entering
- Entering without having exited first

This prevents pass sharing — one person exits, another can't use the same pass to enter.

### 3. Late Entry Detection
If a student scans IN after their `valid_until` time, the system logs the scan with `status: LATE_ENTRY` and records `late_duration_seconds`. Access is still granted but the event is flagged for review.

### 4. Dual JWT Authentication Path
The `get_current_user` dependency tries HS256 local tokens first, then falls back to SWD RS256 verification. This means the system works standalone and also as a plugin to the existing SWD infrastructure without any code changes.

### 5. OTP Visitor Verification
Visitor passes can trigger an OTP (simulated SMS) that is SHA-256 hashed before storage. The guard verifies the OTP at the gate before granting entry, ensuring the physical visitor matches the pass applicant.

### 6. RFID Blacklist with Cascade Revocation
Blacklisting an RFID tag immediately sets all linked passes to `EXPIRED` and marks `PassVehicle.is_active = False`. Any subsequent scan attempt with that tag is denied before any pass lookup.

---

## Health Check

```
GET /health
```
Returns `{"status": "ok", "message": "Gatepass System Backend is running"}`

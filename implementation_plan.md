# Advanced Gatepass System: Implementation Plan & Project Scaffolding

This document outlines the tech stack selection, clean architecture directory layout, milestone execution plan, and external integration strategy for the backend development of the **Advanced Gatepass System**.

---

## 1. Tech Stack Selection

The stack is optimized for high concurrency, low latency, and robust type safety.

*   **Web Framework: FastAPI**
    *   *Rationale*: Fully asynchronous natively, integrates Pydantic v2 for parsing/validation, auto-generates interactive Swagger/OpenAPI documentation, and has minimal overhead.
*   **Database Toolkit: SQLAlchemy 2.0 (Async Engine) + Alembic**
    *   *Rationale*: Supports modern Python type hints, provides clean async mapping (via `asyncio` extension), and `asyncpg` as the database driver for PostgreSQL. Alembic handles declarative, version-controlled migrations.
*   **Validation & Serialization: Pydantic v2**
    *   *Rationale*: Rewritten in Rust for superior performance. Used for strict input validation, data sanitization, and serialization of responses.
*   **Auth & Security: PyJWT (with Cryptography support) & PyOTP**
    *   *Rationale*: `PyJWT` handles JWKS token decoding, claims validation, and signature checks using public keys. `PyOTP` generates and validates RFC-6238 TOTP tokens for dynamic QR codes.
*   **Task Queue: FastAPI BackgroundTasks**
    *   *Rationale*: Standard lightweight task executer running inside the server process loop. Perfect for queuing access log insertion without needing the overhead of Celery or Redis brokers in the initial MVP phase. Can be scaled to `Arq` (Redis-based async queue) for production loads.

---

## 2. Project Directory Layout

We follow a **Clean Architecture (Service Layer Pattern)** to maintain strict separation of concerns and maximize readability.

```
d:/Rushik/DADU Inuductions/
├── alembic/                    # Database migration files
├── alembic.ini                 # Alembic configuration
├── pyproject.toml              # Dependency and package configuration (Poetry/Pipenv)
├── src/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entry point
│   ├── config.py               # Global environment settings & configurations
│   │
│   ├── api/                    # API Route Controllers (Routing & Serialization)
│   │   ├── __init__.py
│   │   ├── dependencies.py     # FastAPI dependencies (DB sessions, current user auth)
│   │   ├── v1/
│   │   │   ├── auth.py         # Login, token exchange, and SWD handshake endpoints
│   │   │   ├── passes.py       # Outpass, single-day visitor, and bulk pass actions
│   │   │   ├── gate.py         # RFID and QR scan validation endpoints (Guard view)
│   │   │   └── admin.py        # Hostels, blacklists, and manual overrides
│   │
│   ├── core/                   # Security, cryptography, and core algorithms
│   │   ├── __init__.py
│   │   ├── security.py         # JWT/JWKS token parsing and signature validation
│   │   └── dynamic_qr.py       # HMAC-SHA256 based TOTP generation & drift checking
│   │
│   ├── db/                     # Data Access Layer
│   │   ├── __init__.py
│   │   ├── session.py          # Database engine and session pool managers (async)
│   │   └── models/             # SQLAlchemy declarative models
│   │       ├── base.py         # Shared base model with timestamp triggers
│   │       ├── identity.py     # Users, Roles, Student/Faculty/Visitor profiles
│   │       ├── passes.py       # Passes, PassTypes, Batches, OTPs, and Vehicles
│   │       └── logging.py      # Immutable AccessLogs and Blacklisted RFIDs
│   │
│   ├── schemas/                # Pydantic validation schemas
│   │   ├── __init__.py
│   │   ├── identity.py         # User & Profile validators
│   │   ├── passes.py           # Pass creation, bulk upload, and OTP validations
│   │   └── gate.py             # RFID payload and access check schemas
│   │
│   └── services/               # Business Logic Layer (The Validation Engine)
│       ├── __init__.py
│       ├── user_service.py     # Auto-provisioning and transaction flows
│       ├── pass_service.py     # Pass lifecycle transitions, bulk creation
│       └── gate_service.py     # Scanning logic, APB verification, SQLite edge sync
│
└── tests/                      # Automated test suite
    ├── __init__.py
    ├── conftest.py             # Pytest database fixtures and clients
    ├── test_auth.py            # SWD Mock verification and provisioning tests
    ├── test_passes.py          # State transitions and bulk issuance tests
    └── test_gate.py            # QR and RFID scan engine verification tests
```

---

## 3. First Milestone Coding Plan (The Golden Path)

To demonstrate a functional system to the hackathon judges quickly, we prioritize a simplified integration flow representing a full student outpass lifecycle.

### Execution Sequence Checklist
- [ ] **Phase 1: Database Setup & Scaffolding**
  - Define all SQLAlchemy models inside `src/db/models/`.
  - Set up Alembic and run the initial migration to build the PostgreSQL database schema.
  - Create seed scripts for roles (Student, Faculty, Security Guard, Superintendent) and mock hostels.
- [ ] **Phase 2: Authentication & SWD Provisioning**
  - Implement SWD JWKS mock endpoints.
  - Create the authentication route (`POST /api/v1/auth/swd-login`) to auto-provision user profiles in a serializable transaction.
- [ ] **Phase 3: Pass Creation & Lifecycle Engine**
  - Implement pass request endpoint (`POST /api/v1/passes/request`).
    - **Enforce the Strict Sequential Trip Constraint**: Query `passes` for active trip before creating. If found, raise `409 Conflict`.
  - Implement supervisor routing and approval (`POST /api/v1/passes/{pass_id}/approve`).
  - Generate encrypted QR seeds and output dynamic verification tokens.
- [ ] **Phase 4: Gate Scan Validation Engine**
  - Implement QR verification endpoint (`POST /api/v1/gate/verify-qr`) verifying TOTP tokens and single round-trip status.
  - Implement RFID verification endpoint (`POST /api/v1/gate/verify-rfid`) checking resident categorization rules (including PhD logic) and logging events asynchronously in the background.

---

## 4. SWD JWKS Integration Mocking Strategy

To test asymmetric token verification without an active SWD identity service, we deploy a localized mock authorization server inside our test suite or as a toggleable path in `src/main.py`.

### Mock Scaffolding Flow
1. **Key Generation**: Upon startup in `development` mode, the app generates a temporary RSA 2048-bit key pair (Private + Public) using the `cryptography` library.
2. **JWKS Mock Endpoint**: A route `GET /api/v1/mock-swd/.well-known/jwks.json` is exposed, serving the public key formatted as a JWKS.
3. **Token Issuer Route**: We build a helper endpoint `GET /api/v1/mock-swd/token` that generates a signed JWT using the RSA private key containing the student payloads (roll number, name, hostel, etc.).
4. **Validation Test**: During authentication, our verification function hits this local endpoint to download the keys, confirming that signature validation, parsing, and auto-provisioning workflows operate successfully.

---

## 5. Verification Plan

### Automated Tests
*   Run unit and integration tests using `pytest` to validate database serialization, validation engines, and authentication loops:
    ```bash
    pytest tests/
    ```

### Manual Verification
*   We will use the FastAPI interactive Swagger UI (`http://127.0.0.1:8000/docs`) to simulate:
    1. Exchanging a mocked SWD token for a local session.
    2. Requesting a student outpass.
    3. Attempting to request a second outpass (must result in `409 Conflict` due to the active trip check).
    4. Simulating superintendent approval.
    5. Simulating a security guard scanning a dynamic QR code within the 15-second epoch window.

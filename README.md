# Lumi — local salon-wallet vertical slice

A dependency-free, web-first development prototype. Python 3.11+ recommended.
Modern responsive customer and staff screens, CSS motion, SQLite persistence.
THIS IS NOT PRODUCTION SOFTWARE. USE TEST FUNDS AND FICTIONAL CUSTOMER DATA ONLY.

## Run

Extract the ZIP, open a terminal in this folder, then:

Windows:
    py server.py
macOS/Linux:
    python3 server.py

Open http://localhost:8000 in your browser. Keep the terminal running.
No pip install, npm install, API key, or paid service is needed.
Stop with Ctrl+C. Delete salon.db only if you want to erase local demo data.
Use localhost, not your LAN address; the server binds to loopback only.

## Accounts

All seeded accounts use password: DemoPass123!

Salon A staff: owner@lumiere.test
Salon B staff: owner@velvet.test
Customer: jane@example.test
Customer phone: +14085550123

Seed balances: Salon A $80 paid + $10 bonus; Salon B $40 paid.
Sessions are stored per browser tab in sessionStorage. Open separate tabs and sign
in independently. A newly duplicated tab may inherit sessionStorage; sign out in
that tab before changing users. Do not share browser profiles with other people.

## Test the main flow

1. Sign in as Salon A staff in one tab.
2. In another tab, sign in as Jane.
3. Staff: Find customer with +14085550123.
4. Add funds: $100, Cash or Card, eligible promotion checked, confirm collection.
5. Jane: the wallet increases by $110; receipt appears locally.
6. Staff: Find customer again if needed; choose Charge service.
7. Enter Gel manicure and $45. Request deduction code.
8. Jane: authorization inbox displays the exact charge and six-digit code.
9. Staff: enter that code and verify. One $45 deduction is recorded.
10. Sign in as Salon B staff to see separate transactions and funds.

SMS fallback: wait 30 seconds after the initial request, then choose Send
simulated SMS. The customer inbox shows a replacement code. The old code is
invalid. Expiry remains three minutes from the ORIGINAL request; SMS does not
extend it or reset failed attempts. Neither push nor SMS is actually sent.

## Implemented

- Customer signup and password login; seeded business staff accounts
- Password hashing with scrypt; server-side expiring bearer sessions
- Separate business wallets and server-side business authorization
- Phone/token lookup; server-calculated $10 bonus on reloads of $100+
- Cash/card collection labels; no card processing or card-number storage
- Integer-cent append-only credits/debits; promotion-first spending policy
- Database transactions; one active authorization per wallet
- Six-digit transaction-bound codes, three-minute expiry, five-attempt lock
- SMS simulation replaces prior code; resend cooldown; customer rejection
- Idempotent reload keys and single-use deduction completion
- Customer history/service descriptions; staff recent-100 activity view
- Audit records, receipt inbox, responsive layout, reduced-motion support
- Six backend integration tests

## Deliberately not implemented yet

- Native Expo iOS/Android apps; this build is a responsive WEBSITE
- QR image generation/camera scanning: use exact phone or copied lookup token
- Actual APNs/FCM push, SMS provider, delivery callbacks or consent verification
- Real phone/email verification, password recovery, account deletion
- Business onboarding, invitations, manager/owner role granularity
- Multiple locations within a business (each demo business has one location)
- Promotion management; only the fixed demo offer is implemented
- Date-filtered reports, CSV exports, full accounting, taxes, tips, credit lots
- Refunds, California cash-outs, expiration or legal-policy engine
- Persisting staff pending-request UI after a page reload: the backend request
  survives but the screen does not recover it; wait for three-minute expiry
- Production-grade rate limits for login/search, abuse monitoring, backups
- Production secure-cookie auth/CSRF strategy, hardened hosting, security review
- PostgreSQL migrations or cloud deployment

Do not expose this development HTTP server publicly. Demo credentials and local
notification codes are intentionally available for testing. The inbox contains
plaintext demo codes; production should retrieve protected authorization data
through a dedicated customer-only flow, minimize exposure/retention, and use a
proper notification provider. Do not store real SMS secrets in frontend code.
The server does basic Origin/Host checks but is not a production security boundary.

## Files

server.py      HTTP API, authentication, SQLite schema and financial workflows
app.js         Customer and staff frontend; no external JS dependencies
style.css      Responsive design, subtle entry/hover animations, reduced motion
index.html     Application entry point
 test_server.py Backend tests (run as described below)

## Run tests

Windows:       py test_server.py
macOS/Linux:   python3 test_server.py

Tests use temporary databases and cover signup, role isolation, business isolation,
reload idempotency, successful checkout, duplicate deduction, wrong-code lockout,
SMS replacement and customer rejection. They do not replace browser, concurrency,
accessibility, performance or security testing.

## API map

POST /api/login, /api/signup, /api/logout
GET  /api/me, /api/customer, /api/staff
POST /api/lookup, /api/reload, /api/request
POST /api/verify, /api/sms, /api/cancel, /api/reject

Amounts are integer cents. Authorization: Bearer <session-token>.
The staff API never returns a raw approval code. The customer-only demo inbox does.
Database writes use BEGIN IMMEDIATE, serializing concurrent writers in SQLite.

## Next implementation stages

1. Validate design and the full local cashier/customer flow.
2. Add QR scanning, recoverable pending requests, configurable promotions/reports.
3. Add real verification, account recovery, permission granularity, legal cash-outs.
4. Move the API/ledger to a maintained backend framework and PostgreSQL.
5. Add real notification adapters, rate limits, backups and deployment automation.
6. Build Expo native clients against the same secured API contracts.
7. Perform security/legal review and staged deployment before handling real money.

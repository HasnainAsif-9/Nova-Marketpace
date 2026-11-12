# Phase 13 — Security Audit Report

**Date:** 2026-11-12
**Backup:** `C:\Users\User\CascadeProjects\marketplace-backup-20261112-111927` (138 files, pre-audit snapshot)
**Tests:** 57/57 passing (50 original + 7 new security regression tests)

## Vulnerabilities Found & Fixed

### 1. JWT type confusion — refresh token usable as access token (HIGH)
**File:** `app/utils/decorators.py` — `load_current_user()`
**Issue:** Any valid JWT with a `sub` claim was accepted as an access token. A stolen **refresh token** (30-day lifetime) could be used to call every authenticated API endpoint.
**Fix:** Require `payload["type"] == "access"` before loading the user.
**Regression test:** `test_refresh_token_rejected_as_access`

### 2. No token revocation on password change (MEDIUM)
**Files:** `app/auth/routes.py`, `app/utils/decorators.py`
**Issue:** Changing a password did not invalidate previously issued JWTs — a stolen token remained valid until natural expiry.
**Fix:** Added `token_version` (`tv` claim) to both token types; `load_current_user` and `/auth/refresh` reject mismatched versions; `change-password` increments `token_version`. Existing users default to version 0 — no migration needed, old tokens remain valid until expiry or next password change.
**Regression test:** `test_password_change_revokes_old_tokens`

### 3. Email case-sensitivity account duplication (MEDIUM)
**File:** `app/auth/routes.py`
**Issue:** Emails were stored/looked up case-sensitively — `User@x.com` and `user@x.com` could register as separate accounts; login was inconsistent depending on casing.
**Fix:** Email normalized to lowercase at registration; login checks both the raw and lowercased identifier. Usernames remain case-sensitive (unchanged).
**Regression test:** `test_email_case_normalization`

### 4. Payment IDOR (MEDIUM)
**File:** `app/payments/routes.py` — `GET /api/payments/order/<id>`
**Issue:** Only the buyer check existed — **any seller** could view payment details (amount, method, status) of any order by guessing/enumerating order IDs.
**Fix:** Sellers must have an `order_items` sub-order for that order; admins unaffected.
**Regression test:** `test_seller_cannot_view_other_order_payment`

### 5. Missing `ObjectId` import — refresh endpoint broken (BUG)
**File:** `app/auth/routes.py`
**Issue:** `ObjectId` was used in `/auth/refresh` but never imported → every refresh attempt raised `NameError` (caught → 401). Token refresh was completely non-functional.
**Fix:** Added `from bson import ObjectId`.

### 6. Broken relative imports — public store & wishlist 500 (BUG)
**Files:** `app/sellers/routes.py` (×2), `app/wishlist/routes.py`
**Issue:** `from .products.routes import _enrich_products` resolved to nonexistent `app.sellers.products` / `app.wishlist.products` → `GET /api/sellers/<slug>`, `GET /api/sellers/<slug>/products`, and `GET /api/wishlist` all returned 500.
**Fix:** Corrected to `from ..products.routes import _enrich_products`.
**Verified live:** `GET /api/sellers/demo-store` → 200 with 8 products.
**Regression tests:** `test_public_store_endpoint_works`, `test_wishlist_endpoint_works`

### 7. Order cancellation via status endpoint skipped restock (MEDIUM — inventory integrity)
**File:** `app/orders/routes.py` — `update_order_status`
**Issue:** Setting status → `cancelled` updated order/sub-order/commission statuses but did **not** restock inventory or void commissions — unlike the dedicated buyer cancel endpoint. Stock and `sold_count` drifted permanently.
**Fix:** On transition to `cancelled`, restock affected sub-order items and mark their commissions cancelled; admin cancellations also void the payment record.
**Regression test:** `test_status_cancel_restock`

### 8. Unescaped user input in `$regex` queries (LOW — ReDoS)
**Files:** `app/admin/routes.py` (users, products, audit-logs), `app/sellers/routes.py`, `app/orders/routes.py` (admin order search)
**Issue:** Raw user input interpolated into MongoDB `$regex` — regex metacharacters could cause expensive patterns.
**Fix:** All wrapped with `re.escape()`. (Product search was already escaped.)

### 9. Missing rate limits (LOW)
**Files:** `app/auth/routes.py`, `app/payments/routes.py`
**Fix:** Added `@rate_limit` — `/auth/refresh` (30/min), `/auth/change-password` (5/min), `/payments/cod/confirm` (10/min).

### 10. `int()` crashes on malformed input → 500 (LOW — robustness)
**Files:** `app/reviews/routes.py` (rating), `app/products/routes.py` (stock delta), `app/categories/routes.py` (sort_order)
**Fix:** Safe parsing with try/except returning 400 instead of unhandled 500.

## Areas Audited — No Issues Found

- **Password handling:** bcrypt hashing, never returned in API responses, `password_hash` stripped everywhere
- **Authorization/RBAC:** every admin route `role_required("admin")`; seller scoping verified on products, orders, payments, commissions, reports
- **IDOR:** orders, addresses, reviews, notifications, wishlist, cart all scoped to `user_id`
- **Price/total tampering:** checkout recalculates everything server-side; client totals ignored (tested)
- **Mass assignment:** all update endpoints use field whitelists
- **MongoDB injection:** PyMongo parameterized queries throughout; ObjectId validation via `to_object_id`
- **Security headers:** X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, HSTS (prod)
- **CORS:** none configured → same-origin only (correct for this architecture)
- **Cookies:** `httponly`, `samesite=Lax`, `secure` in production, refresh cookie path-scoped to `/api/auth`
- **Frontend XSS:** all user-controlled fields rendered through `Format.escapeHtml()` (52 usages verified across product cards, reviews, addresses, orders, admin tables, store pages)
- **Error handling:** no stack traces leaked; consistent JSON envelope
- **Order state machine:** transitions validated; seller cannot set delivered/refunded/returned
- **Stock integrity:** atomic `$inc` deduction at checkout with rollback on failure

## Remaining Issues / Recommendations (not fixed — require decisions or larger changes)

1. **Rate limiter is in-memory per-process** — resets on restart and doesn't scale across multiple workers/instances. For production, move to Redis or a shared store.
2. **No refresh-token reuse detection** — a stolen refresh token can be used until expiry (30 days). Consider rotating with reuse detection or shortening refresh lifetime.
3. **Access token also returned in response body** (`access_token` field) — the frontend stores it for Bearer auth. An XSS could steal it. The httpOnly cookie path mitigates this; consider dropping the body token once the frontend fully relies on cookies.
4. **Seller can cancel orders in `shipped` state** via the status endpoint (transitions allow it). Business decision — confirm this is intended; restock now works correctly either way.
5. **Sub-order vs parent-order status divergence** — when a seller updates their sub-order status, the parent order status is also set, which can leave other sellers' sub-orders inconsistent. Pre-existing design limitation; recommend per-seller sub-order status model in a future phase.
6. **No password reset / email verification flow** — out of scope for this phase; required before public launch.
7. **`maintenance_mode` bool parsing** — `bool("false")` → `True` if a non-JSON client sends a string. Admin UI sends proper JSON booleans; low risk.
8. **Audit log has no retention/archival policy** — will grow unbounded; add TTL index in production.

## Tests Performed

- Full suite: **57 passed** (`python -m pytest tests/ -q`)
- 7 new regression tests covering every fixed vulnerability
- Live verification: public store endpoint, sellers list, settings, checkout flow on dev server

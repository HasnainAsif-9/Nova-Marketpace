# NovaMarket — Multi-Vendor E-Commerce Marketplace

A complete, production-ready multi-vendor marketplace with Buyer, Seller, and Admin roles.
Built with Flask + MongoDB (PyMongo) backend and a dependency-free HTML/CSS/JS frontend.

## Features

- **Three roles**: Buyer, Seller, Admin — strict server-side RBAC on every endpoint
- **Catalog**: categories, products with variants/options, search, filters, sorting, pagination
- **Cart & Checkout**: server-side price recalculation, multi-seller order splitting, delivery options, free-delivery threshold
- **Orders**: full status state machine, stock deduction/restock, notifications at every step
- **Commissions**: configurable rate, per-order commission records, seller earnings dashboard
- **Reviews**: only verified buyers with delivered orders can review; admin moderation
- **Admin panel**: stats, user/seller/product/category/order management, commissions, settings, audit logs, analytics
- **Security**: JWT auth, bcrypt password hashing, rate limiting, input validation, IDOR protection, security headers, audit logging
- **Payments**: Cash on Delivery (COD) with payment records; architecture ready for gateway integration

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, Flask, PyMongo, JWT, bcrypt |
| Database | MongoDB |
| Frontend | HTML5, CSS3 (custom design system), JavaScript ES6+ |
| Deployment | Docker + docker-compose, Gunicorn |

## Project Structure

```
marketplace/
├── backend/
│   ├── app/
│   │   ├── __init__.py          # App factory, error handlers, security headers
│   │   ├── config.py            # Environment-based configuration
│   │   ├── extensions.py        # MongoDB connection + indexes
│   │   ├── auth/                # Register, login, logout, JWT
│   │   ├── users/               # Profile management
│   │   ├── buyers/              # Addresses
│   │   ├── sellers/             # Store profiles, earnings
│   │   ├── admin/               # Dashboard, moderation, analytics
│   │   ├── products/            # Catalog + seller product management
│   │   ├── categories/
│   │   ├── cart/
│   │   ├── wishlist/
│   │   ├── orders/              # Checkout, status flow, sub-orders
│   │   ├── payments/            # COD records
│   │   ├── commissions/
│   │   ├── reviews/
│   │   ├── notifications/
│   │   ├── reports/             # Sales + inventory reports
│   │   ├── settings/            # Marketplace settings
│   │   └── utils/               # Auth decorators, validation, audit, responses
│   ├── tests/test_marketplace.py  # 50 automated tests
│   ├── run.py
│   └── requirements.txt
├── frontend/
│   ├── index.html, shop.html, product.html, cart.html, checkout.html
│   ├── login.html, register.html, seller-store.html, 404.html
│   ├── buyer/index.html, seller/index.html, admin/index.html
│   └── assets/{css,js,images}/
├── scripts/
│   ├── seed_admin.py            # Create initial admin user
│   └── seed_demo_data.py        # Demo categories, seller, products
├── Dockerfile
├── docker-compose.yml
└── PROGRESS.md
```

## Quick Start (Local Development)

### Prerequisites
- Python 3.12+
- MongoDB running locally (or set `MONGODB_URI`)

### Setup

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

# 2. Environment
copy .env.example .env          # Windows (cp on macOS/Linux)
# Edit .env — set SECRET_KEY, JWT_SECRET_KEY, ADMIN_PASSWORD

# 3. Seed admin + demo data
python ../scripts/seed_admin.py
python ../scripts/seed_demo_data.py

# 4. Run
python run.py                   # http://localhost:5000
```

The frontend is served by Flask at `/` — no separate frontend server needed.

### Default Admin
- Username: `husnain` (configurable via `ADMIN_USERNAME`)
- Password: whatever you set in `ADMIN_PASSWORD` env var

## Running Tests

```bash
cd backend
python -m pytest tests/ -v       # 50 tests, uses mongomock (no DB needed)
```

Tests cover: authentication, authorization/IDOR, business logic (commission,
delivery, multi-seller orders, stock), catalog, seller flows, reviews,
security, and settings.

## Docker Deployment

```bash
# Create .env with secrets (SECRET_KEY, JWT_SECRET_KEY, MONGO_PASSWORD required), then:
docker compose up --build
```

Includes an authenticated MongoDB container with healthchecks. For production,
use a managed MongoDB Atlas cluster and set `MONGODB_URI` accordingly (the
compose `mongo` service can then be removed). The app refuses to start in
production mode with default secret keys.

## API Overview

All endpoints return a consistent JSON envelope:

```json
{ "success": true, "data": { ... }, "message": "..." }
{ "success": false, "error": "...", "error_code": "..." }
```

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register`, `/login`, `/logout`, `/change-password`, `GET /api/users/me` |
| Catalog | `GET /api/products`, `GET /api/products/:id`, `GET /api/categories` |
| Cart | `GET/POST/PUT/DELETE /api/cart/items`, `DELETE /api/cart` |
| Orders | `POST /api/orders/checkout`, `GET /api/orders`, `GET /api/orders/:id`, `POST /api/orders/:id/status`, `POST /api/orders/:id/cancel` |
| Seller | `GET/PUT /api/sellers/me`, `GET /api/sellers/me/earnings`, `POST /api/products` |
| Admin | `GET /api/admin/stats`, user/seller/product/order management, `GET/PUT /api/settings` |
| Reviews | `GET /api/products/:id/reviews`, `POST /api/reviews` |

## Business Rules

- **Commission**: `order_subtotal × commission_rate%` per seller sub-order (default 10%, admin-configurable)
- **Delivery**: standard Rs. 20, express Rs. 50; free above configurable threshold
- **Stock**: deducted atomically at checkout; restored on cancellation
- **Reviews**: only buyers with delivered orders, one per product
- **Seller approval**: new sellers are `pending` until admin approves

## Security

- Passwords hashed with bcrypt (12 rounds) — never stored or returned in plaintext
- JWT access tokens (Bearer) + httpOnly refresh cookies
- Rate limiting on auth and write endpoints
- Server-side validation on every input; client values never trusted for prices/totals
- IDOR protection: users can only access their own resources
- Security headers: X-Content-Type-Options, X-Frame-Options, CSP, HSTS (production)
- Audit log for all critical admin/seller actions
- MongoDB injection prevention via PyMongo parameterized queries

## Environment Variables

See `.env.example` for the full list. Key ones:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask secret |
| `JWT_SECRET_KEY` | JWT signing |
| `MONGODB_URI` | MongoDB connection string |
| `ADMIN_PASSWORD` | Initial admin password (seed only) |
| `DEFAULT_COMMISSION_RATE` | Marketplace commission % |
| `DELIVERY_FEE_STANDARD` / `DELIVERY_FEE_EXPRESS` | Delivery fees |
| `FREE_DELIVERY_THRESHOLD` | Free delivery above this subtotal |
| `CURRENCY` / `CURRENCY_SYMBOL` | PKR / Rs. |

## License

Private project — all rights reserved.

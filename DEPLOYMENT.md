# NovaMarket — Production Deployment Guide

## Prerequisites

- Docker + Docker Compose **or** a server with Python 3.12+ and MongoDB 7
- A domain name (recommended) with TLS termination (reverse proxy)

## 1. Configure environment

Copy `backend/.env.example` to `.env` (project root for compose, or `backend/.env` for bare-metal) and set:

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | ✅ | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_SECRET_KEY` | ✅ | Different random value, same method |
| `MONGO_PASSWORD` | ✅ (compose) | Strong password for the mongo container |
| `MONGO_USER` | optional | Defaults to `marketplace` |
| `SMTP_HOST/PORT/USER/PASSWORD/FROM` | ✅ for email | Without SMTP, reset/verification emails are only logged (dev mode). In production the app logs an error and does not send. |
| `FRONTEND_BASE_URL` | ✅ | Public URL, e.g. `https://market.example.com` — used in emailed links |
| `FLASK_ENV` | ✅ | `production` |
| `PAYMENT_METHODS_ENABLED` | optional | Comma-separated: `cod` (default). Add `stripe`/`jazzcash`/`easypaisa` only after implementing the adapter in `app/payments/gateway.py` and setting its credentials |
| `STRIPE_*` / `JAZZCASH_*` / `EASYPAISA_*` | when enabling | Provider credentials — see `.env.example` |
| `ADMIN_USERNAME/PASSWORD/EMAIL` | ✅ | Used once by `scripts/seed_admin.py` |

The app **refuses to start** in production with default secret keys.

## 2. Deploy with Docker Compose (recommended)

```bash
docker compose up --build -d
docker compose ps          # both services should be healthy
docker compose logs -f app
```

- App: `http://<host>:5000` (put behind nginx/Caddy for TLS)
- MongoDB: internal only, authenticated, persistent volume `mongo_data`
- Health checks: `GET /api/health`

> `MONGO_INITDB_*` credentials apply only on first volume init. To change them later, update the `marketplace` user via `mongosh`.

## 3. Deploy bare-metal

```bash
cd backend
pip install -r requirements.txt
# set MONGODB_URI to your MongoDB (Atlas or self-hosted), FLASK_ENV=production
python ../scripts/seed_admin.py     # creates initial admin
python ../scripts/seed_demo_data.py # optional demo data
python -m gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 60 run:app
```

## 4. Post-deploy checklist

- [ ] `GET /api/health` returns 200
- [ ] Register a buyer, place a COD order, confirm it appears in admin
- [ ] Register a seller, approve it in admin, add a product
- [ ] Request a password reset and confirm the email arrives (SMTP configured)
- [ ] Verify a new account's email link works
- [ ] Confirm `Secure` cookies work (requires HTTPS — set `SESSION_COOKIE_SECURE` via `FLASK_ENV=production`)

## Architecture notes

- Auth: JWT access (1h) + refresh (30d) tokens in httpOnly cookies; `SameSite=Lax` mitigates CSRF; Bearer header also supported for API clients
- Rate limiting: in-memory per process — **move to Redis if running multiple gunicorn workers behind a load balancer** (each worker keeps its own counters)
- All prices/commissions recalculated server-side at checkout; stock deducted atomically
- Audit log written for auth, admin, and order actions

## Remaining limitations

See `SECURITY_AUDIT.md` § "Remaining Issues" — notably: no payment gateway (COD only), no refresh-token reuse detection, in-memory rate limiter, no email-verification enforcement gate (flag is set but login is not blocked).

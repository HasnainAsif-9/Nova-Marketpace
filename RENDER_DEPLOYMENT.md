# NovaMarket — Render Deployment Guide (Free Tier)

Deploys the Flask backend + static frontend as a single Render web service,
with MongoDB Atlas (free M0) as the database. No Docker needed on Render —
the existing Dockerfile/docker-compose remain for local development only.

## Architecture on Render

- **Web service**: `render.yaml` blueprint → Python runtime, `rootDir: backend`
- **Build**: `pip install -r requirements.txt` (includes gunicorn)
- **Start**: `gunicorn run:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60`
- **Health check**: `GET /api/health`
- **Database**: MongoDB Atlas free cluster (external, persists across deploys)

## Step 1 — Push code to GitHub

The repo must be on GitHub (private recommended). `.env`, `.venv`,
`cloudflared.exe`, and `START-SERVER.bat` are git-ignored — verify with
`git status` that `backend/.env` does **not** appear before pushing.

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

## Step 2 — MongoDB Atlas (free)

1. Create a free account at https://www.mongodb.com/atlas → **Build a Database** →
   choose the **Free M0** tier (AWS region closest to your Render region).
2. **Database Access → Add New Database User**: username e.g. `novamarket`,
   password = a strong generated password (save it).
3. **Network Access → Add IP Address → Allow Access from Anywhere**
   (`0.0.0.0/0`). Required because Render outbound IPs are dynamic.
   (Atlas free tier shows a security warning for this — acceptable for a
   marketplace demo; the DB user still requires auth.)
4. **Connect → Drivers → Python**: copy the connection string, it looks like:
   ```
   mongodb+srv://novamarket:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   Replace `<password>` with the URL-encoded database user password.

## Step 3 — Deploy on Render

1. Sign up at https://render.com (free) → **New → Blueprint** → connect the
   GitHub repo. Render reads `render.yaml` automatically.
2. When prompted, fill in the `sync: false` env vars:

   | Variable | Value |
   |---|---|
   | `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
   | `JWT_SECRET_KEY` | different random value, same command |
   | `MONGODB_URI` | Atlas connection string from Step 2 |
   | `FRONTEND_BASE_URL` | `https://<your-app>.onrender.com` (after first deploy) |
   | `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_EMAIL` | initial admin seed |
   | `SMTP_*` | optional — leave empty until you configure email |

3. Deploy. First build takes ~3–5 min. Check logs if it fails.
4. After deploy, open `https://<app>.onrender.com` — the site should load.

## Step 4 — Seed admin + demo data

The app does **not** auto-seed on Render (scripts run locally). Either:

- **Option A (recommended)**: run seed scripts locally pointed at Atlas:
  ```powershell
  cd backend
  # temporarily set MONGODB_URI to the Atlas string in backend/.env
  .venv\Scripts\python.exe ..\scripts\seed_admin.py
  .venv\Scripts\python.exe ..\scripts\seed_demo_data.py
  # revert MONGODB_URI to mongodb://localhost:27017 afterwards
  ```
- **Option B**: register the admin via the normal register flow, then set
  `role: "admin"` directly in Atlas (Database → Browse Collections → users).

## Post-deploy checklist

- [ ] `GET /api/health` returns 200 (Render dashboard health check)
- [ ] Homepage loads products/categories
- [ ] Register buyer → place COD order → visible in admin dashboard
- [ ] Admin login works (`ADMIN_*` seeded account)
- [ ] Set `FRONTEND_BASE_URL` to the real `https://...onrender.com` URL and
      redeploy (needed for correct links in emails)

## Free-tier caveats

- **Cold starts**: free web services sleep after ~15 min idle; first request
  after sleep takes ~30–60 s. Acceptable for demos.
- **Ephemeral filesystem**: any file written to disk is lost on redeploy/restart.
  NovaMarket stores **no uploads on disk** — product images are URL strings
  only — so this does not affect the app. If image uploads are added later,
  use Cloudinary/S3, not local disk.
- **In-memory rate limiting**: counters reset on restart and are per-worker.
  Fine at this scale; move to Redis only if needed.
- **MongoDB Atlas M0**: 512 MB storage, shared CPU — fine for launch.

## Keeping local dev working

Local setup is unchanged:

```powershell
cd backend
.venv\Scripts\python.exe ..\scripts\dev_server.py   # or run.py
# MongoDB: docker start novamarket-mongo
```

`docker-compose.yml` + `Dockerfile` still work exactly as before — Render
deployment does not use them.

## If deploy fails

- `RuntimeError: Production startup blocked` → a `sync:false` secret still has
  the dev default. Set `SECRET_KEY`/`JWT_SECRET_KEY` in the Render dashboard.
- Mongo connection timeout → check Atlas Network Access allows `0.0.0.0/0` and
  the URI password is URL-encoded.
- `ModuleNotFoundError` → check `rootDir: backend` in `render.yaml`; the build
  must run `pip install -r requirements.txt` inside `backend/`.

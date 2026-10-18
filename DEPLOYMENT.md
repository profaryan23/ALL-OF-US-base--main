# Deploy on Render + Supabase

Render runs FastAPI, templates, CSS, JavaScript, and the bundled video. Supabase
stores application data in PostgreSQL. A Render persistent disk stores uploaded
product photos. This setup uses a **paid Render Starter web service plus disk**;
check current pricing before confirming. Supabase billing is separate.

## 1. Create the Supabase database

1. In <https://supabase.com/dashboard>, create a project in your organization.
2. Choose a region near the Render region you intend to use. Save the database
   password in a password manager and wait for provisioning to finish.
3. Open the project's **Connect** dialog. Select the **Session pooler** connection
   string (port **5432**). This is suitable for this long-running application and
   avoids relying on IPv6 support for a direct connection. Do not select the
   transaction pooler on port 6543 for this guide.
4. Replace the password placeholder with your database password. URL-encode the
   password only if it contains characters such as `@`, `#`, `/`, `:` or `%`.
   Do not encode the entire connection string. Keep the host and username from
   your dashboard; the pooler username normally includes the project reference.
5. Add `?sslmode=require` (or `&sslmode=require` if other query parameters exist).
   The result has this shape, not literal credentials:

   ```text
   postgresql://postgres.PROJECT_REF:ENCODED_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
   ```

6. **Secure API exposure before deployment.** This app connects directly with
   SQLAlchemy and does not use Supabase's browser Data API. Disable the project's
   Data API in its API settings if the project is dedicated to this app. If you
   need the Data API for something else, remove the app's schema from exposed
   schemas or explicitly configure grants/RLS so anonymous/authenticated API
   clients cannot read the app's users, orders, or contact messages. Tables
   created by SQLAlchemy do not automatically receive browser-safe RLS policies.
7. No Supabase Auth, Storage bucket, publishable/anon key, service-role key, or
   Edge Function is needed for this deployment. Existing app login stays in use.

The first successful app startup creates tables and starter content. You do not
need to paste table-creation SQL into Supabase.

## 2. Push the prepared code

Review your existing local changes as well as the deployment files. In PowerShell:

```powershell
Set-Location 'C:\Users\aryan\Downloads\ALL-OF-US-base--main'
git status
git add main.py requirements.txt .gitignore .env.example render.yaml DEPLOYMENT.md README.md tests/test_deployment.py
git commit -m "Prepare Render and Supabase deployment"
git push origin main
```

Commit other intended UI changes separately. Do not commit credentials, `.env`,
your virtual environment, or `allofus.db`.

## 3. Deploy using the Render Blueprint (recommended)

1. Open <https://dashboard.render.com>, select **New > Blueprint**, connect your
   GitHub account, and select `profaryan23/ALL-OF-US-base--main`, branch `main`.
2. Render reads `render.yaml`. Review the paid Starter service and 1 GB disk.
   Choose a region near Supabase if the setup screen allows it; otherwise adjust
   the Blueprint's region before provisioning.
3. Fill in the prompted secrets:
   - `DATABASE_URL`: the session-pooler URI from step 1, with SSL enabled.
   - `ADMIN_EMAIL`: the email you want for the initial admin account.
   - `ADMIN_PASSWORD`: a unique password of at least 16 characters, not `admin123`.
4. Apply/create the Blueprint. `SECRET_KEY` is generated automatically. The file
   also sets production mode, HTTPS cookies, Python version, and image directory.
5. Wait for build and startup. Inspect **Logs** for errors. Render supplies `PORT`;
   do not manually set it or put `--reload` in the start command.
6. Open the assigned `https://...onrender.com` URL.

### Alternative: create a Web Service manually

Do this **instead of**, not in addition to, the Blueprint:

| Setting | Value |
| --- | --- |
| Service type | Web Service, not Static Site |
| Repository / branch | Your repository / `main` |
| Root directory | Leave blank (repository root) |
| Runtime | Python 3 |
| Instance | Paid Starter or higher |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'` |
| Health check path | `/healthz` |
| Persistent disk | Mount `/var/data`, size 1 GB |

Set these environment variables before the first successful deployment:

| Variable | Value |
| --- | --- |
| `PYTHON_VERSION` | `3.13.14` |
| `APP_ENV` | `production` |
| `DATABASE_URL` | Supabase session pooler URI including `sslmode=require` |
| `SECRET_KEY` | A random secret of at least 32 characters |
| `ADMIN_EMAIL` | Your initial admin email |
| `ADMIN_PASSWORD` | A unique password of at least 16 characters |
| `COOKIE_SECURE` | `true` |
| `PRODUCT_IMAGE_DIR` | `/var/data/product-images` |

Generate a session secret locally with:

```powershell
.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Render's start command uses Linux shell syntax (`$PORT`), even though local
development uses Windows. Proxy trust here assumes requests reach Uvicorn only
through Render's proxy; do not reuse that wildcard on a directly exposed server.

## 4. Verify the deployment

1. Visit `/healthz`: expect `{"status":"ok"}`. It checks database connectivity.
2. Visit `/`, `/shop`, `/about`, `/contact`, and `/admin/login`.
3. Sign in using `ADMIN_EMAIL` / `ADMIN_PASSWORD`, not the local demo credentials.
4. In Studio > Inventory, create a product with a photo. Confirm it appears in
   the shop, redeploy once, and confirm its data and photo still exist.
5. Test customer registration, bag, mock checkout, and the contact inbox.
6. In Supabase Table Editor, verify application tables and test records exist.

## Important data and security notes

- This starts a **new database**. Changing `DATABASE_URL` does not copy your local
  SQLite products, customers, orders, or content. Back up `allofus.db` first.
  Existing-data migration requires a separate reviewed import; do not upload a
  SQLite file into PostgreSQL or assume it will be imported automatically.
- Bundled product-image files are copied to the disk on startup if missing, but
  their database product records are not imported from SQLite.
- Admin environment variables create an account only if that email is absent.
  Changing `ADMIN_PASSWORD` later does **not** reset an existing account. Never
  import an account that still uses the demo password into production.
- A persistent disk supports one instance and prevents zero-downtime deploys.
  Keep this deployment to one instance/worker. For a free Render instance or
  horizontal scaling, implement Supabase Storage uploads first; this code does
  not currently store photos in Supabase Storage.
- `.env.example` documents settings; the app does not automatically load `.env`.
- Keep `SECRET_KEY` stable across deployments; changing it invalidates sessions.
- Startup creates tables and applies a few existing additive schema updates; it
  is not a general migration system. Back up and review future schema changes.
- Restrict DB network access where practical, keep secrets server-side, and
  configure backups appropriate to your Supabase plan. Disk snapshots are not
  PostgreSQL backups.
- Checkout is still a mock flow, not a live payment integration.

## Common failures

- **Connection timeout / network unreachable:** use the session pooler host and
  port 5432 from Connect, check network restrictions and project availability.
- **Password authentication failed:** check the database password (not account
  password/API key), URL encoding, and full pooler username.
- **Missing PostgreSQL driver:** ensure the deployed `requirements.txt` includes
  `psycopg2-binary`. The app normalizes `postgres://` and `postgresql://` URLs to
  `postgresql+psycopg2://` so SQLAlchemy uses that installed driver even when its
  default changes. If the logs show `No module named 'psycopg'`, deploy the updated
  `main.py` as well as `requirements.txt`, then use Render's **Clear build cache &
  deploy** option. An explicitly configured URL should use `postgresql+psycopg2://`,
  not `postgresql+psycopg://` (which requires a different package).
- **Startup rejects production settings:** supply all required secrets; short
  session/admin secrets and SQLite production URLs are intentionally rejected.
- **Login loops or HTTP asset URLs:** use the HTTPS site and the documented proxy
  flags; keep secure cookies enabled in production.
- **Photos disappear:** confirm the disk is mounted at `/var/data` and
  `PRODUCT_IMAGE_DIR=/var/data/product-images`; only disk-backed files persist.

References: [Render FastAPI](https://render.com/docs/deploy-fastapi),
[Render disks](https://render.com/docs/disks),
[Supabase database connections](https://supabase.com/docs/guides/database/connecting-to-postgres).
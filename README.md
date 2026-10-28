# All of Us

A local e-commerce storefront and CRM built with FastAPI, SQLAlchemy, SQLite, and Jinja templates.

## Deploy on Render + Supabase

See [DEPLOYMENT.md](./DEPLOYMENT.md) for Supabase setup, Render dashboard steps,
environment variables, persistent product photos, and deployment verification.
The included `render.yaml` provisions a paid Render web service and image disk;
Supabase provides PostgreSQL. No live cloud deployment is performed by these files.

## Run locally

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

On Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\python -m pip install -r requirements.txt
.\venv\Scripts\uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

Open <http://127.0.0.1:8001> (or port 8000). The SQLite database (`allofus.db`) and sample catalog are created automatically on first startup.

## Admin modules

Open <http://127.0.0.1:8000/admin/login> and sign in with `admin@allofus.com` / `admin123`. The overview is at <http://127.0.0.1:8000/admin>; each workspace is separate:

- CRM: <http://127.0.0.1:8000/admin/crm>
- Inventory: <http://127.0.0.1:8000/admin/inventory>
- Sales: <http://127.0.0.1:8000/admin/sales>
- Orders: <http://127.0.0.1:8000/admin/orders>
- Content management: <http://127.0.0.1:8000/admin/content>
- Website analytics: <http://127.0.0.1:8000/admin/analytics>
- Combined reports: <http://127.0.0.1:8000/admin/reports>

The public site includes the Home page at `/`, the dedicated collection at `/shop`, product details at `/shop/product/{id}`, About at `/about`, and Contact at `/contact`. Select a product from Home or Shop to see its full inventory description, photo, price, size choices, and availability before adding it to the bag. In Studio > Content, edit each page's headings, copy, SEO description, and publishing state. The Home editor also manages the site announcement, video caption, shop-section copy, closing message, and footer tagline. Contact form submissions are saved in the Studio inbox and can be marked read/unread; the form does not send email.

Studio > Inventory contains a product form for product name, category, shop category, photo, price, size variations, description, stock, and storefront visibility. Saving an active product opens its Shop category so the new listing is easy to find. Active products with zero stock remain visible as sold out; inactive products stay hidden. Product photos accept JPEG, PNG, or WebP up to 10 MB and appear on the Shop listing after save. Shoppers can browse by shop category, view the photo and product details, select a size variation when available, and retain that selection through their bag and order record. Size choices share the product's stock count; per-size inventory is not implemented.

Change the starter password and set a random `SECRET_KEY` before using this beyond a local demo.

Checkout is intentionally a mock flow and does not collect payment details.

The storefront hero directly below the navigation features the provided full-screen video. It is served as a muted, looping 540p H.264 MP4 (`static/videos/shop-hero-540p.mp4`) with a glassmorphism text panel and a play/pause control. The video was converted using macOS `avconvert`; no Python or JavaScript package is required.

The Overview and Reports pages summarize database-backed data across the existing modules. Reports are available at `/admin/reports`; use the period selector to adjust sales/order/product/website metrics. The report calls out requested modules whose data is not tracked yet rather than implying they are fully implemented. The Sales dashboard ranks products by units sold as well as revenue. Customers can request shipment help or an exchange from order history; admins review these in Orders and can leave status/response notes. Carrier tracking and company exchange terms are not configured. Website Analytics includes first-party activity and local technical SEO checks; it is not an external uptime, search-ranking, or performance-monitoring service. Notification delivery/scheduling, expanded customer lifecycle, inventory movements/vendors, and manual daily sales are specified in [system_specifications.md](./system_specifications.md) but are not yet implemented. Django-Q is not part of this FastAPI project.

The platform supports four access tiers in the product specification: `super_admin`/`developer`, `admin`, `agent`, and `customer`. Super admins and admins share broad operational privileges, agents can be created and monitored from the admin panel, customers can self-register and manage their own orders/profile, and the system records staff changes in the new Activities module. The accounting layer includes a chart of accounts, journal entry posting with validation, and balanced double-entry posting for revenue, fees, COGS, and operating expenses.

Run from the project directory with the `--reload` command above. If the server was started without reload, restart it after code changes; refresh the browser at `/admin` and use the Reports link in the admin navigation.
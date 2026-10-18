# Agent One-Prompt Execution Document

> **Role:** You are an expert Full-Stack Python Developer and Software Architect.
> **Task:** Build a monolithic web application for **All of Us** using Python, HTML, CSS, JavaScript, and Jinja2 templates (or a similar templating engine) following the architecture and system specifications outlined below.

---

## Project Specification Brief

### Tech Stack
* **Backend:** Python (Flask or FastAPI)
* **Database:** SQLite (using SQLAlchemy ORM)
* **Frontend:** HTML5, CSS3, Vanilla JavaScript (ES6+)

---

## Core System Modules to Implement

### 1. Database Schema & ORM setup
Create models for:
* `User`: ID, name, email, password_hash, phone, marketing_opt_in (boolean), role (`customer`/`admin`), created_at.
* `Product`: ID, name, description, price, stock_quantity, is_active (boolean), created_at.
* `Order`: ID, user_id, total_amount, status, created_at.
* `OrderItem`: ID, order_id, product_id, quantity, price_at_purchase.

### 2. Public User Portal (E-Commerce Storefront)
* Home/Catalog page displaying all active products (`is_active=True` and `stock_quantity > 0`).
* User registration page capturing contact details and a marketing opt-in checkbox.
* Login/Logout functionality.
* Shopping cart logic (session-based) and checkout route.

### 3. Admin Control Panel & Inventory System
* Protected route `/admin` accessible only to users with `role='admin'`.
* Product Management Dashboard: Form to add new products, edit price/stock, or update active status.
* Order Overview: Page listing all submitted user orders.

### 4. Embedded CRM & Data Export Module
* Integrated into the `/admin` dashboard.
* Analytics Overview: Total customers, opt-in lead count, total revenue generated.
* Customer Data Table displaying spend history and contact details.
* Export feature: A route `/admin/crm/export` that outputs a downloadable CSV of all marketing opt-in customers.

---

## Directives & Execution Instructions
1. **Single Project Setup:** Create a functional layout containing the main application file (`app.py`), database setup, templates directory, and static assets directory.
2. **Sample Data Seeding:** Provide an automated seed script or function that populates initial dummy products and an admin account (`admin@allofus.com` / `admin123`).
3. **Clean UX/UI:** Apply standard responsive modern CSS styling with clean UI elements. Ensure zero dynamic frontend reliance on heavy external frameworks.
4. **Execution Command:** Begin generating the complete application structure and full code implementations now.

---

## Expanded Operations Requirements (2026-10)

Keep the existing FastAPI, SQLAlchemy, SQLite/PostgreSQL, Jinja2, and vanilla JavaScript stack. Do not introduce a Django migration solely to use Django-Q; Django-Q and scheduled notification delivery require a separate architecture decision and must not be represented as working integrations until configured.

### Order, shipment, and customer experience
* Admin order pipeline: pending, processing, sold/completed, and cancelled; keep line-item specifications and fulfillment notes.
* Add shipment requests/status/tracking to orders and show a customer's shipment/order details only to that customer.
* Publish and enforce the company exchange policy; retain exchange requests and outcomes.

### Website analytics
* Track storefront leads/visits, web-originated purchases, product purchase counts, and cart events separately.
* Show the best-selling product(s) ranked by units purchased (the requested business meaning of “MVP”), as well as revenue ranking.
* Add technical website health and SEO checks. Label these as local checks; do not claim external uptime, rankings, or performance measurements without an integration.

### CRM
* Customer/lead profile: name, phone, email, location, lead source, qualified/non-qualified status, lifecycle onboarding/offboarding, feedback, orders/purchases, and activity timeline.
* Provide explicit hot/high-engagement and spam classifications, lead-source reporting, and customer interactivity reporting.
* Preserve consent and role-based data access.

### Sales, inventory, and reporting
* Support daily sales entry, company exchange policy, and exchange tracking.
* Add stock-in/stock-out movement records, damaged stock and recovery/disposition, stock purchase orders, SKU, HSN code, and vendor specifications.
* Identify dead/slow-moving stock from actual movement/sale history.
* Provide an aggregate analytics report across website, CRM, orders/sales, and inventory; show date ranges and metric definitions.

### Notification and audit trail
* Track notification attempts and delivery status, scheduled job state/results, and stakeholder/admin activity.
* Surface failed jobs and deliveries. Do not silently swallow integration errors or display unsent notifications as sent.
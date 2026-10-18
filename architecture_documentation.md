# Technical Architecture Document: All of Us E-Commerce, CRM & Operations Platform

## 1. Executive Overview
**All of Us** is an integrated e-commerce platform designed to combine customer-facing retail capabilities with a lightweight Customer Relationship Management (CRM) system, Admin Control Panel, order/sales operations, inventory management, and website analytics. The core objective is to connect customer and product activity to operational decisions and sales.

## 2. Technology Stack
To maintain simplicity, reliability, and ease of deployment, the platform utilizes a lightweight Python stack:

*   **Backend Framework:** Python FastAPI
*   **Database:** SQLite (Development/MVP) or PostgreSQL (Production) with SQLAlchemy ORM
*   **Frontend:** HTML5, CSS3, Vanilla JavaScript (ES6+)
*   **Authentication:** Session-based authentication with password hashing (`werkzeug.security` or `passlib`)
*   **Data Processing:** Python (`pandas` or standard libraries) for customer segment exports and marketing analytics

---

## 3. System Components & Module Interaction

```
[ Customer/User Portal ] <---> [ Flask/FastAPI App Core ] <---> [ Database (PostgreSQL/SQLite) ]
                                         ^
[ Admin Control Panel  ] ----------------|
  ├── Inventory System
  ├── Orders, Sales & Reporting
  ├── Website Analytics & Technical SEO
  └── CRM, Notifications & Stakeholder Activity
```

### 3.1 User Portal (E-Commerce Storefront)
* **Product Browsing:** Home product cards link to the dedicated `/shop` collection and `/shop/product/{id}` detail routes. Collection pages filter by shop category; product details show the full inventory description, photo, category, price, stock availability, and size selector where configured. Size selection happens on the detail page and carries through to the cart and order.
*   **User Registration & Checkout:** Captures customer profiles, purchase history, and marketing preferences (opt-in newsletter).
*   **Session Management:** Maintains shopping carts and customer preferences.
*   **Public Content:** Serves Home, About, and Contact pages. The Contact form stores validated submissions for Studio review; no email provider is configured.

### 3.2 Admin Control Panel & Inventory System
*   **Inventory Management:** Protected product forms manage product name, category, shop category, JPEG/PNG/WebP photo uploads (10 MB limit), price, size variations, description, stock, and active status. Available active products and photos appear on Shop; selected sizes are retained on cart and order items.
*   **Content Management:** Protected Studio editors manage page copy, metadata, publishing state for About/Contact, homepage sections, announcement, video caption, and footer tagline.
*   **Inventory operations:** The target workflow adds SKU/HSN and vendor details, stock-in/stock-out movement history, damaged-stock recovery, purchase orders, and dead-stock analysis.
*   **Order Management:** Tracks order pipeline, order specifications, shipment requests, and status (Pending, Processing, Completed/Sold, Cancelled).
*   **Sales:** Supports daily sales, best-selling products by units purchased, and an auditable exchange workflow governed by company policy.

### 3.3 Integrated CRM & Marketing Engine
*   **Customer Profiling:** Centralized database capturing customer contact details and location, lead source/qualification, lifecycle status, feedback, total spend, order count, and interaction history.
*   **Segmentation & Export:** Filter customers based on purchase behavior, recency, and spend; export data (CSV) for email/SMS marketing platforms.
*   **Engagement:** Support explicit hot/high-engagement and spam classifications, onboarding/offboarding, and customer purchase/activity views.

### 3.4 Website Analytics, Notifications & Reports
* **Website Analytics:** Retain first-party visit, cart, and purchase events; distinguish conversion and purchase-ranked products from cart interest. Technical SEO checks are local checks, not external ranking or uptime monitoring.
* **Notifications:** The requested delivery tracing and scheduled jobs need a provider and a scheduler. Django-Q is Django-specific and is not directly compatible with the current FastAPI stack; do not imply that it is installed or running.
* **Stakeholder activity:** Operational changes should be written to an auditable activity record.
* **Reports:** A unified report should cover website, leads/customers, sales/orders, and inventory with clear date ranges and metric definitions.

### 3.5 Implementation Boundaries
The current implementation uses FastAPI and SQLAlchemy. Existing working features include the storefront and editable Home/About/Contact pages, a Studio content editor and contact inbox, session-based cart and mock checkout, customer shipment/exchange request submission and admin review, protected admin modules, a database-backed overview, a period-filtered cross-module report, basic CRM filtering/export, product stock editing, sales aggregation with a units-based best-seller, local technical SEO checks, and first-party website event analytics. New page-content and contact-message data are stored in additive tables created at startup. Contact form messages are saved for manual follow-up; delivery and reply tracking are not configured. Additional data models and workflows listed above must be implemented with additive database migrations before they can be presented as operational. Do not migrate to Django solely to obtain Django-Q without an explicit architecture decision.

---

## 4. Data Architecture & Schema

### `users`
* `id` (INTEGER, PK)
* `email` (VARCHAR, Unique)
* `password_hash` (VARCHAR)
* `first_name` (VARCHAR)
* `last_name` (VARCHAR)
* `phone` (VARCHAR)
* `marketing_opt_in` (BOOLEAN)
* `created_at` (TIMESTAMP)

### `products`
* `id` (INTEGER, PK)
* `name` (VARCHAR)
* `category` and `shop_category` (VARCHAR)
* `photo_path` (VARCHAR; validated image stored under static product images)
* `size_variations` (TEXT; comma-separated labels)
* `sku` (VARCHAR, unique per catalog)
* `hsn_code` (VARCHAR)
* `vendor_id` (FK -> vendors.id, when vendor management is implemented)
* `description` (TEXT)
* `price` (DECIMAL)
* `stock_quantity` (INTEGER)
* `is_active` (BOOLEAN)
* `created_at` (TIMESTAMP)

### `orders`
* `id` (INTEGER, PK)
* `user_id` (FK -> users.id)
* `total_amount` (DECIMAL)
* `status` (VARCHAR)
* `shipment_status`, `tracking_reference`, and fulfillment specification (target schema)
* `created_at` (TIMESTAMP)

### `order_items`
* `id` (INTEGER, PK)
* `order_id` (FK -> orders.id)
* `product_id` (FK -> products.id)
* `quantity` (INTEGER)
* `size_variation` (VARCHAR)
* `price_at_purchase` (DECIMAL)

### `page_content` and `contact_messages`
* `page_content` stores editable content, metadata, and publishing state for the home, About, and Contact pages.
* `contact_messages` stores validated contact form submissions and their read/unread state for the Studio inbox.

### Target operational records
* `leads`/customer lifecycle data: lead source, qualification, location, onboarding/offboarding, feedback, and explicit client classification.
* `inventory_movements`: product, movement type, quantity, reason, timestamp, and related stock/purchase order.
* `vendors` and `stock_orders`: vendor contact/specification and purchase/receipt workflow.
* `notification_events` and `scheduled_jobs`: recipient/template, delivery/job status, timestamps, references, and surfaced failures.
* `stakeholder_activity`: actor, action, affected record, and timestamp.
* `exchange_requests` and daily sales records: customer/order link, policy/outcome, business date, items, and amounts.
* A reporting layer should aggregate these records rather than duplicate mutable totals.

---

## 5. Security & Data Privacy
1. **Password Security:** Mandatory salt and hash hashing algorithm (e.g., bcrypt / pbkdf2:sha256).
2. **Access Control:** Role-Based Access Control (RBAC) enforcing separation between standard customers and administrative users.
3. **Data Compliance:** GDPR/CAN-SPAM compliance support with explicit marketing consent opt-in flags.
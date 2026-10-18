# System Specification & Requirements Document: All of Us

## 1. Functional Requirements

### 1.1 Customer Storefront (User Portal)
* **FR-UP-01:** Users must be able to browse catalog items in real-time based on active database inventory on a dedicated Shop page and open each product's detail page.
* **FR-UP-02:** Users must be able to create an account, providing name, email, phone number, and explicit marketing consent choices.
* **FR-UP-03:** Users must be able to add items to a shopping cart and process mock or real purchases.
* **FR-UP-04:** Returning users must be able to log in and view their past orders.

### 1.2 Admin Control Panel & Inventory Management
* **FR-AP-01:** Admins must log in through a secure, non-public administrative authentication route.
* **FR-AP-02:** Admins must be able to create and edit products with name, category, shop category, product photo, price, size variations, description, and inventory stock.
* **FR-AP-03:** Any product added or set to active status must immediately reflect on the public storefront, including active products that are currently out of stock.
* **FR-AP-04:** Admins must be able to mark items as out-of-stock or soft-delete products.
* **FR-AP-05:** Shoppers must be able to browse published items by shop category, open a product detail page with its full description and photo, and choose a size there where provided.
* **FR-AP-06:** A selected size variation must remain associated with the cart line and resulting order item.

### 1.3 CRM & Data Collection Engine
* **FR-CRM-01:** The system must record customer interactions, registration timestamps, order counts, and total monetary value spent.
* **FR-CRM-02:** The system must provide a dedicated CRM dashboard summarizing key metrics:
  * Total Customers
  * Marketing Opt-in Percentage
  * Customer Lifetime Value (CLV) distribution
* **FR-CRM-03:** Admins must be able to filter customer lists by spending thresholds, opt-in flags, or purchase history.
* **FR-CRM-04:** Admins must be able to export filtered customer data into CSV format for external marketing software integration.

### 1.4 Order Management & Fulfillment
* **FR-ORD-01:** Admins must be able to review orders and manage their lifecycle from pending through fulfillment and sale, while retaining cancellation history.
* **FR-ORD-02:** Each order must retain an order specification: customer, line items, quantities, prices at purchase, total, timestamps, and fulfillment notes.
* **FR-ORD-03:** Customers and admins must be able to see shipment-request and shipment-status information associated with an order.
* **FR-ORD-04:** Customers must be able to review their own order and shipment history; customer data must not be exposed to other customers.

### 1.5 Website Analytics & Quality
* **FR-WEB-01:** Record storefront visits and product/cart/purchase events, and attribute web-originated orders to website activity where consent and available identifiers permit.
* **FR-WEB-02:** Report visits, distinct visitors, cart activity, conversion, and products with the most purchases; distinguish purchase counts from add-to-cart interest.
* **FR-WEB-03:** Provide an on-site health view and a technical SEO checklist covering page titles, descriptions, mobile viewport, and primary page headings.
* **FR-WEB-04:** Clearly distinguish local technical checks from external search-engine ranking, uptime, or performance services that have not been integrated.

### 1.6 Email & Notification Tracking
* **FR-NOT-01:** Keep notification delivery records with recipient, channel/template, related customer or order, status, timestamps, and provider/job reference where available.
* **FR-NOT-02:** Track queued, sent, failed, and retried notifications; failures must remain visible to an administrator.
* **FR-NOT-03:** Support scheduled notification jobs and expose their next run, last run, and result to administrators.
* **FR-NOT-04:** Record stakeholder/admin activity for important operational changes.
* **FR-NOT-05:** Email delivery and a Django-Q scheduler are integration requirements, not capabilities of the current FastAPI application; they require a deliberate scheduler/provider decision before implementation.

### 1.7 CRM & Customer Lifecycle
* **FR-CRM-05:** Customer profiles must support name, phone, email, and location, plus lead source and lead qualification (qualified or non-qualified).
* **FR-CRM-06:** Admins must be able to distinguish prospects from customers and record customer onboarding/offboarding dates and status.
* **FR-CRM-07:** Customer profiles must support feedback, purchase details, and a chronological activity history.
* **FR-CRM-08:** Admins must be able to identify hot/high-engagement and spam clients using explicit, reviewable classifications rather than inferred or hidden labels.
* **FR-CRM-09:** Lead-generation source and customer interactivity must be reportable and filterable.

### 1.8 Sales Management
* **FR-SALES-01:** Admins must be able to review sales by day and record a daily sale with its date, items, quantities, amount, and source.
* **FR-SALES-02:** Sales reports must identify the best-selling product by units purchased, with revenue available as a separate ranking.
* **FR-SALES-03:** Exchange requests and outcomes must follow a published company exchange policy and retain an auditable record.
* **FR-SALES-04:** “MVP” in this business request means the product or products selling most often; it does not mean a reduced product scope.

### 1.9 Inventory & Vendors
* **FR-INV-01:** Track stock-in and stock-out changes as auditable movements, including adjustment reason and timestamp.
* **FR-INV-02:** Product specifications must include SKU and HSN code; products must be associable with vendor specifications.
* **FR-INV-03:** Record damaged stock and recovery/disposition separately from sellable inventory.
* **FR-INV-04:** Support stock orders/purchase orders with vendor, items, quantities, and order/receipt status.
* **FR-INV-05:** Report dead/slow-moving stock using the last-sale date and current quantity; do not treat missing history as a confirmed dead-stock finding.

### 1.10 Reports
* **FR-REP-01:** Provide an admin report covering order pipeline, sales, best sellers, customer/lead activity, website performance, and inventory movement/health.
* **FR-REP-02:** Reports must state their date range and definitions, and must not present unavailable integrations or incomplete data as verified results.

### 1.11 Website Content Management
* **FR-CMS-01:** Administrators must be able to edit the Home, About, and Contact page copy and SEO descriptions from the protected Studio.
* **FR-CMS-02:** Administrators must be able to publish or unpublish the About and Contact pages; the Home page remains available.
* **FR-CMS-03:** The Home editor must support the hero, shop-section, announcement, video caption, closing message, and footer tagline content.
* **FR-CMS-04:** Contact form submissions must be validated, stored, and reviewable in the protected Studio inbox.
* **FR-CMS-05:** Contact submissions must not be represented as email-delivered unless a delivery provider is configured.

### 1.12 Current Delivery Status
The current application already provides a storefront, an admin product form for name/category/shop category/photo/price/size variations/description/stock/visibility, shop-category browsing, product photo and details display, size-aware cart/order items, editable Home/About/Contact pages in Studio, contact message storage and an admin inbox, account registration/login, session cart and mock checkout, customer order history, admin-protected CRM/inventory/sales/orders/website-analytics pages, customer CSV export, storefront event tracking, sales-by-product totals, an operational admin overview, and a combined date-filtered report across the currently available data. Product image uploads accept JPEG, PNG, or WebP up to 10 MB and are served on the Shop listing after save. Customers can submit shipment or exchange requests against their own orders; admins can approve, decline, complete, and add response/tracking notes to those requests. This is request handling only: carrier integration and company exchange terms are not configured. Website health/SEO template checks and a units-based best-seller indicator are available in the admin surfaces.

The following items in this expanded request are **not yet implemented** and remain requirements: lead qualification/source lifecycle, location and feedback capture, hot/spam/interactivity classifications, manual daily sales, enforced exchange-policy terms, stock movement and damaged-stock recovery, vendor/purchase orders, dead-stock reporting, contact email delivery/reply tracking, notification delivery/job tracking, and stakeholder audit history. The combined report presents tracked metrics and explicitly identifies these untracked data areas.

---

## 2. Non-Functional Requirements

### 2.1 Performance & Usability
* **NFR-01:** Storefront page load times must remain under 2 seconds on standard internet connections.
* **NFR-02:** Interface must be clean, responsive, and mobile-friendly using clean HTML5/CSS3.

### 2.2 Security
* **NFR-03:** All administrative endpoints must be guarded by session/token checks.
* **NFR-04:** Input validation must be strictly enforced on all form fields to prevent SQL Injection (SQLi) and Cross-Site Scripting (XSS).

### 2.3 Simplicity & Maintainability
* **NFR-05:** Codebase must follow standard Python PEP 8 style guides.
* **NFR-06:** No complex heavy JavaScript framework dependencies; plain ES6 JavaScript and HTML templates (e.g., Jinja2) must be preferred.
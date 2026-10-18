# Change Log & Future Work

This file records implemented changes and practical follow-up work for the All of Us application. A feature listed as future work is not yet available in the web app.

## 2026-10-07 — Dedicated Shop & Product Detail Pages

### Completed
- Added a dedicated `/shop` collection page with shop-category filters and product links.
- Added `/shop/product/{id}` pages with the full inventory description, product photo, category, price, available sizes, and stock state.
- Updated Home product cards so they link to product details instead of showing size selectors or adding directly to the bag.
- Updated the site Shop navigation and product-save destination to lead to the dedicated collection.
- Documented the new shopper flow in the README and system specification.

## 2026-10-07 — Product Photo Upload Limit

### Completed
- Raised the product photo upload limit from 5 MB to 10 MB for both new products and photo replacements.
- Updated the inventory form guidance and documented that accepted product images display in Shop after saving.

## 2026-10-07 — Product Catalog Form & Shop Display

### Completed
- Expanded Studio > Inventory create/edit forms with product name, category, shop category, product photo, price, size variations, description, stock quantity, and active status.
- Added image upload validation for JPEG, PNG, and WebP files up to 10 MB; generated server-side filenames and stored the product photo with the catalog record. Verified the exact 10 MiB boundary is accepted and the next byte is rejected.
- Added additive product/order schema migration to preserve the existing catalog and order data while adding category, shop category, image, size variation, and purchased size fields.
- Published active, stocked products in Shop with photo, category labels, description, and price; added shop-category filters.
- Added size selection to product cards and carried the selected size from the bag into customer/admin order details. Variant sizes share the product's total stock quantity; size-specific stock counts are not configured.
- Changed successful active-product saves to open Shop at the saved product's category, added explicit "saved as hidden" feedback for inactive products, and kept active zero-stock listings visible with a Sold out state.
- Updated README, system requirements, and architecture notes.

### Future Work
- Add a managed media library, image resizing/thumbnail generation, and per-size inventory counts if needed.

## 2026-10-07 — Studio Content Management & Public Pages

### Completed
- Added protected Studio > Content editors for Home, About, and Contact, with persisted page copy, SEO descriptions, and publishing controls for About and Contact. The Home page remains published.
- Made the Home hero copy/button, shop-section heading, video caption, site announcement, closing message, and footer tagline editable from Studio.
- Added public About and Contact pages to the main navigation and footer.
- Kept published-page links in sync with each page's publishing state and tuned the header layout to fit the added navigation at tablet widths.
- Added a validated Contact form that saves submissions to the database and exposes a read/unread inbox in Studio. Messages are not emailed.
- Added the `page_content` and `contact_messages` tables plus an additive migration for the evolving page schema; existing site content is initialized only when missing, preserving later edits.
- Documented the CMS, routes, data storage, and email-delivery limitation in the README, system requirements, and architecture notes.

### Future Work
- Configure an email provider and reply workflow if contact messages should trigger email notifications.
- Add reusable media uploads and additional custom page creation if content needs expand beyond these three pages.

## 2026-10-07 — Shop Video & Glassmorphism

### Completed
- Replaced the earlier Shop-only feature video with the newly provided `IMG_5478.MP4`.
- Converted the supplied 4K HEVC video to a 960×540 H.264/AAC MP4 using macOS `avconvert`: 4.13 seconds and approximately 3 MB instead of the 43 MB source.
- Moved the video into the existing `.hero` section, directly after the site navigation; the hero now fills the remaining viewport height and uses the footage as a full-bleed background.
- Kept the hero headline, added a translucent glassmorphism text panel, and added an accessible play/pause control. The muted film loops inline; reduced-motion preference pauses it by default.
- Removed the separate video panel from the Shop product section so the product grid follows the hero directly.
- Bumped asset cache versions and updated the local video instructions in [README.md](./README.md).

### Future Work
- Consider adding a custom poster image or transcript/audio track if requested.

## 2026-10-03 — Admin Overview, Reports & Web App Updates

### Completed
- Updated the local run command to launch the actual FastAPI app module (`main:app`) with Uvicorn reload enabled.
- Restarted the local app at `http://127.0.0.1:8000` with reload enabled so Python route changes appear without a manual restart.
- Fixed the Admin Overview to show customer, product, order, and non-cancelled net sales metrics, plus pending/processing counts and low-stock count.
- Updated Overview module cards to link to current workspaces, including the new Reports module.
- Added `/admin/reports`, reachable from the admin navigation and Overview.
- Added report-period filtering (7, 30, 90 days, or all time) for orders, net sales, product rankings, daily sales, and website events.
- Added combined report sections for order status, units-based best sellers, current stock totals/low stock, registered customers/marketing opt-ins, first-party visits/cart/purchase activity, and open shipment/exchange requests.
- Excluded cancelled orders from net sales and product-unit rankings. Updated Sales product ordering to rank by units sold, with revenue as a separate value.
- Fixed product and order form redirects so actions return to the corresponding admin module rather than the Overview page.
- Added CSS cache-busting query parameters so browsers fetch the updated admin styles.
- Updated [README.md](./README.md) with the app command, admin module routes, Reports route, and limitations.
- Validated the updated Overview and Reports pages in the browser and at localhost. Checked that sample report data excludes cancelled orders and ranks products by units sold. Python syntax and diagnostics passed.

### Future Work — Recommended Order

#### 1. Customer and lead CRM
- Add customer location fields and a separate lead workflow.
- Record lead source, qualification state (qualified/non-qualified), onboarding/offboarding dates, and lifecycle status.
- Add feedback records and a chronological customer activity view.
- Add explicit, admin-editable hot/high-engagement and spam classifications; avoid silently inferring these labels.
- Add lead-source and customer-interactivity reports.

#### 2. Inventory controls
- Add SKU, HSN code, and vendor information to products.
- Record stock-in and stock-out as dated, reasoned inventory movements rather than only overwriting a stock number.
- Add damaged-stock records and recovery/disposition history.
- Add vendor stock orders/purchase orders with order and received quantities/status.
- Add slow/dead-stock reporting based on actual movement and sale history. Do not label products dead when there is not enough history.

#### 3. Notifications and stakeholder audit
- Select an email/SMS provider and record each notification attempt and its queued/sent/failed status.
- Choose a scheduler compatible with the existing FastAPI stack, or explicitly decide to migrate to Django before using Django-Q.
- Add visible scheduled-job status, failures, retry history, and last/next run.
- Record admin/stakeholder actions such as order status updates, stock changes, customer classification, and request decisions.

#### 4. Sales, exchange policy, and fulfillment
- Define the company's exchange terms before enforcing eligibility, deadlines, or refund/exchange outcomes.
- Add exchange request outcomes and audit history under that policy.
- Configure a shipping carrier/provider if live tracking numbers and delivery status are required; current shipment requests and admin notes are not carrier tracking.
- Add manual daily sales only if sales outside online checkout must be entered. Define how these entries relate to customers, products, inventory, and reports to prevent double counting.

#### 5. Reports and analytics expansion
- Extend Reports when the relevant lead, feedback, notification, stakeholder, and inventory-movement data is implemented.
- Add report download/export formats and explicit date/time-zone definitions if needed.
- Add external website health, speed, SEO ranking, or traffic integrations only after selecting providers and granting/configuring credentials.
- Preserve the current distinction between first-party page/cart/purchase events and independently verified sales/traffic.

#### 6. Production readiness
- Replace the default local admin password and development `SECRET_KEY`; configure deployment-only secrets securely.
- Add database migrations before changing existing production schema; current startup table creation does not migrate existing databases.
- Add automated regression tests for admin authentication, reports and date filters, inventory/order workflows, and customer data isolation.
- Decide on backups, production database hosting, monitoring, and retention/privacy rules for customer activity data.

## 2026-10-03 — Initial Requirements & Module Work

### Completed
- Expanded the system requirements, architecture notes, and implementation prompt to include order pipeline/shipment requests, website analytics and technical SEO checks, CRM/customer lifecycle, sales, inventory/vendor operations, notifications, and reporting.
- Added customer shipment and exchange request submission to their own order history and admin review/status/response handling in Orders.
- Added a units-sold best-seller indicator to Sales and local storefront technical SEO checks to Website Analytics.
- Added a storefront meta description.
- Clarified in documentation that carrier delivery, company exchange policy, Django-Q scheduling, and unimplemented CRM/inventory workflows are not live integrations.

### Future Work
- Implement lead source/qualification and customer lifecycle/profile features.
- Implement stock movement, vendor/purchase-order, damaged stock, and dead-stock workflows.
- Implement notification delivery/job tracking and stakeholder audit history.
- Define and implement daily manual sales and the actual company exchange policy.
- Expand combined reports as the above workflows produce reliable stored data.

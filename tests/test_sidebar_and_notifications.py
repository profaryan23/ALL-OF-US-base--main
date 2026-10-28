import unittest
from decimal import Decimal
from datetime import datetime
from starlette.requests import Request

import main


class SidebarAndOrderNotificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.Base.metadata.create_all(main.engine)
        main.migrate_catalog_schema()
        main.migrate_accounting_schema()
        main.migrate_page_content()
        main.seed_database()

    def test_admin_sidebar_layout_and_modules(self):
        with main.SessionLocal() as db:
            admin = db.query(main.User).filter_by(role="admin").first()
            if not admin:
                admin = main.User(
                    email="admin-unit-test@allofus.com",
                    password_hash=main.generate_password_hash("pass123"),
                    first_name="Admin",
                    last_name="Test",
                    role="admin"
                )
                db.add(admin)
                db.commit()

            scope = {
                "type": "http",
                "method": "GET",
                "path": "/admin",
                "headers": [],
                "session": {"user_id": admin.id},
                "app": main.app,
                "query_string": b"",
            }
            req = Request(scope)
            res = main.admin_dashboard(req, admin, db)
            body = res.body.decode("utf-8")

            # Verify Task 1: Left navigation sidebar contains all 12 modules
            self.assertIn("admin-sidebar", body)
            self.assertIn("sidebar-nav", body)
            self.assertIn("module-nav", body)
            self.assertIn("module-nav-search-area", body)
            self.assertIn("nav-search-button", body)

            # All 12 modules present
            for mod_name in [
                "Overview", "Content", "CRM", "RBAC", "Inventory",
                "Agents", "Sales", "Orders", "Accounts",
                "Website analytics", "Activities", "Reports"
            ]:
                self.assertIn(mod_name, body)

            # Overview is active
            self.assertIn('class="nav-item active"', body)

    def test_all_admin_module_routes_render_left_sidebar_and_active_state(self):
        with main.SessionLocal() as db:
            admin = db.query(main.User).filter_by(role="admin").first()

            modules_to_test = [
                ("/admin", main.admin_dashboard, "Overview"),
                ("/admin/content", main.admin_content, "Content"),
                ("/admin/crm", main.admin_crm, "CRM"),
                ("/admin/rbac", main.admin_rbac, "RBAC"),
                ("/admin/inventory", main.admin_inventory, "Inventory"),
                ("/admin/agents", main.admin_agents, "Agents"),
                ("/admin/sales", main.admin_sales, "Sales"),
                ("/admin/orders", main.admin_orders, "Orders"),
                ("/admin/accounts", main.admin_accounts, "Accounts"),
                ("/admin/analytics", main.admin_analytics, "Website analytics"),
                ("/admin/activities", main.admin_activities, "Activities"),
                ("/admin/reports", main.admin_reports, "Reports"),
            ]

            for path, route_fn, label in modules_to_test:
                with self.subTest(module=label):
                    scope = {
                        "type": "http",
                        "method": "GET",
                        "path": path,
                        "headers": [],
                        "session": {"user_id": admin.id},
                        "app": main.app,
                        "query_string": b"",
                    }
                    req = Request(scope)
                    import inspect
                    sig = inspect.signature(route_fn)
                    if len(sig.parameters) == 2:
                        res = route_fn(req, db)
                    else:
                        res = route_fn(req, admin, db)
                    self.assertEqual(res.status_code, 200)
                    html = res.body.decode("utf-8")
                    self.assertIn("admin-sidebar", html)
                    self.assertIn("sidebar-nav", html)
                    self.assertIn("notif-bell-button", html)
                    # Verify active class is applied to this module's item
                    self.assertIn(f'class="nav-item active"', html)

    def test_admin_not_see_your_orders_and_redirect(self):
        with main.SessionLocal() as db:
            admin = db.query(main.User).filter_by(role="admin").first()
            customer = db.query(main.User).filter_by(role="customer").first()
            if not customer:
                customer = main.User(
                    email="shopper@test.com",
                    password_hash=main.generate_password_hash("pass123"),
                    first_name="Shopper",
                    last_name="Test",
                    role="customer"
                )
                db.add(customer)
                db.commit()

            # Render storefront for customer
            scope_cust = {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [],
                "session": {"user_id": customer.id},
                "app": main.app,
                "query_string": b"",
            }
            req_cust = Request(scope_cust)
            res_cust = main.storefront(req_cust, db)
            body_cust = res_cust.body.decode("utf-8")

            # Customer sees "Your orders" and does not see "Studio"
            self.assertIn("Your orders", body_cust)
            self.assertNotIn(">Studio<", body_cust)

            # Render storefront for admin
            scope_adm = {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [],
                "session": {"user_id": admin.id},
                "app": main.app,
                "query_string": b"",
            }
            req_adm = Request(scope_adm)
            res_adm = main.storefront(req_adm, db)
            body_adm = res_adm.body.decode("utf-8")

            # Admin sees Studio and does NOT see Your orders
            self.assertIn(">Studio<", body_adm)
            self.assertNotIn("Your orders", body_adm)

            # Admin accessing order_history_page directly gets redirected to admin_orders
            scope_orders = {
                "type": "http",
                "method": "GET",
                "path": "/account/orders",
                "headers": [],
                "session": {"user_id": admin.id},
                "app": main.app,
                "query_string": b"",
            }
            req_orders = Request(scope_orders)
            res_redirect = main.order_history_page(req_orders, admin, db)
            self.assertEqual(res_redirect.status_code, 303)
            self.assertIn("/admin/orders", res_redirect.headers.get("location", ""))

    def test_order_placed_notification_flow(self):
        with main.SessionLocal() as db:
            admin = db.query(main.User).filter_by(role="admin").first()
            customer = db.query(main.User).filter_by(role="customer").first()
            product = db.query(main.Product).filter(main.Product.stock_quantity > 0).first()
            if not product:
                product = main.Product(
                    name="Test Artisan Bowl",
                    category="Home",
                    shop_category="Kitchen",
                    price=Decimal("85.00"),
                    stock_quantity=20,
                    is_active=True
                )
                db.add(product)
                db.commit()

            # Place an order as customer
            order = main.Order(
                user_id=customer.id,
                total_amount=Decimal("85.00"),
                status="Pending",
                channel="Online delivery"
            )
            db.add(order)
            db.flush()
            order.items.append(main.OrderItem(
                product_id=product.id,
                quantity=1,
                price_at_purchase=Decimal("85.00")
            ))
            main.create_activity_log(
                db,
                actor=customer,
                module="orders",
                action="order_placed",
                entity_type="order",
                entity_id=order.id,
                details=f"New order #{order.id:04d} placed by visitor {customer.first_name} {customer.last_name} ({customer.email}) for Rs 85.00."
            )
            db.commit()

            # Verify ActivityLog created
            log = db.query(main.ActivityLog).filter_by(action="order_placed", entity_id=order.id).first()
            self.assertIsNotNone(log)
            self.assertIn(f"#{order.id:04d}", log.details)

            # Check admin page render contains order placed notifications
            scope_adm = {
                "type": "http",
                "method": "GET",
                "path": "/admin",
                "headers": [],
                "session": {"user_id": admin.id},
                "app": main.app,
                "query_string": b"",
            }
            req_adm = Request(scope_adm)
            res_adm = main.admin_dashboard(req_adm, admin, db)
            body_adm = res_adm.body.decode("utf-8")

            # Notification bell and dropdown present
            self.assertIn("notif-bell-button", body_adm)
            self.assertIn("notif-dropdown-panel", body_adm)
            self.assertIn("Order Placed Notifications", body_adm)
            self.assertIn(f"#{order.id:04d}", body_adm)

            # Sidebar Orders badge present
            self.assertIn("sidebar-order-badge", body_adm)

            # Check Orders page has pending orders alert banner
            scope_orders = {
                "type": "http",
                "method": "GET",
                "path": "/admin/orders",
                "headers": [],
                "session": {"user_id": admin.id},
                "app": main.app,
                "query_string": b"",
            }
            req_orders = Request(scope_orders)
            res_orders = main.admin_orders(req_orders, admin, db)
            body_orders = res_orders.body.decode("utf-8")
            self.assertIn("orders-pending-alert", body_orders)
            self.assertIn("Order Placed Notifications", body_orders)


if __name__ == "__main__":
    unittest.main()

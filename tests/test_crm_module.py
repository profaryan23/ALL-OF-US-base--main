import json
import unittest
from datetime import datetime
from decimal import Decimal

from starlette.requests import Request

import crm_service
import main


def run_coro(coro):
    """Executes a coroutine synchronously without initializing OS loopback sockets."""
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value


class CRMModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.Base.metadata.create_all(main.engine)
        crm_service.migrate_crm_schema(main.engine, main.Base, main.SessionLocal, False)

    def setUp(self):
        with main.SessionLocal() as db:
            self.admin = db.query(main.User).filter_by(role="admin").first()
            if not self.admin:
                self.admin = main.User(
                    first_name="Studio",
                    last_name="Admin",
                    email="studio-admin-crm@example.com",
                    password_hash=main.generate_password_hash("admin-pass-1234"),
                    role="admin",
                )
                db.add(self.admin)
                db.commit()
            self.admin_id = self.admin.id

    def make_request(self, method="GET", path="/admin/crm", query_string=b"", session=None, json_data=None, form_data=None):
        sess = {"user_id": self.admin_id, "csrf_token": "valid_token"}
        if session:
            sess.update(session)
        headers = [
            (b"x-csrf-token", b"valid_token"),
        ]
        if json_data is not None:
            headers.append((b"content-type", b"application/json"))
        elif form_data is not None:
            headers.append((b"content-type", b"application/x-www-form-urlencoded"))
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query_string,
            "headers": headers,
            "session": sess,
            "app": main.app,
        }
        req = Request(scope)
        if json_data is not None:
            async def _json():
                return json_data
            req.json = _json
        if form_data is not None:
            async def _form():
                return form_data
            req.form = _form
        return req

    def test_admin_crm_page_renders_with_kpi_and_ux_components(self):
        req = self.make_request(path="/admin/crm")
        with main.SessionLocal() as db:
            response = main.admin_crm(req, self.admin, db)
            self.assertEqual(response.status_code, 200)
            html = response.body.decode("utf-8")

            # Top Actions & Add Customer Modal
            self.assertIn("+ Add Customer", html)
            self.assertIn("showAddModal", html)
            self.assertIn("crm-add-customer-modal", html)
            self.assertIn("First Name", html)
            self.assertIn("Acquisition Channel", html)
            self.assertIn("Marketing & Email Bulletins Consent", html)

            # A. Global KPI & Filter Bar
            self.assertIn("Total Customers", html)
            self.assertIn("Period Revenue", html)
            self.assertIn("Average Customer Value (LTV)", html)
            self.assertIn("crm-time-pill", html)
            self.assertIn("Subscribed", html)

            # B. Cross-Filtering & Insights Area
            self.assertIn("Retention Progression", html)
            self.assertIn("Retention Rate", html)
            self.assertIn("Acquisition Type", html)
            self.assertIn("Client Channels", html)

            # C. Smart Segment Tabs & Builder
            self.assertIn("All Customers", html)
            self.assertIn("High Value (LTV Rs 200+)", html)
            self.assertIn("+ Smart segment", html)
            self.assertIn("Smart Segment Builder", html)

            # D. Head-to-Head Compare
            self.assertIn("Compare Segments", html)
            self.assertIn("Head-to-Head Segment Comparison", html)

            # E. Ledger & Bulk Actions
            self.assertIn("crm-sticky-bulk-bar", html)
            self.assertIn("Dispatch Bulk Email", html)
            self.assertIn("crm-table", html)

            # F. Slide-Over Profile Detail Panel
            self.assertIn("crm-slide-panel", html)

    def test_analytics_api_returns_kpis_and_breakdowns(self):
        req = self.make_request(path="/admin/crm/api/analytics", query_string=b"window=30D")
        with main.SessionLocal() as db:
            analytics = main.crm_api_analytics(req, self.admin, db)
            self.assertIn("kpi", analytics)
            self.assertIn("donuts", analytics)
            self.assertIn("timeline", analytics)
            self.assertGreater(analytics["kpi"]["total_customers"], 0)
            self.assertIn("opt_in_breakdown", analytics["kpi"])
            self.assertIn("ltv_brackets", analytics["kpi"])

    def test_customers_api_search_and_pagination(self):
        with main.SessionLocal() as db:
            first = db.query(main.User).filter_by(role="customer").first()
            self.assertIsNotNone(first)
            name_query = first.first_name.encode()

            req = self.make_request(path="/admin/crm/api/customers", query_string=b"q=" + name_query + b"&page=1&per_page=12")
            res = main.crm_api_customers(req, self.admin, db)
            self.assertGreaterEqual(res["total_matching"], 1)
            self.assertEqual(res["customers"][0]["id"], first.id)

    def test_customer_detail_and_timeline_logging(self):
        with main.SessionLocal() as db:
            customer = db.query(main.User).filter_by(role="customer").first()
            self.assertIsNotNone(customer)
            cid = customer.id

            detail = main.crm_api_customer_detail(cid, self.admin, db)
            self.assertEqual(detail["id"], cid)
            self.assertIn("spend_history", detail)
            self.assertIn("timeline_groups", detail)
            self.assertIn("category_counts", detail)

            # Test adding an interaction
            req_int = self.make_request(
                method="POST",
                path=f"/admin/crm/api/customer/{cid}/interaction",
                json_data={"type": "call", "title": "Check-in Call", "content": "Customer asked about upcoming sale."}
            )
            int_res = run_coro(main.crm_api_add_interaction(cid, req_int, self.admin, db))
            self.assertTrue(int_res["success"])

            # Verify logged
            updated_detail = main.crm_api_customer_detail(cid, self.admin, db)
            found = False
            for grp in updated_detail["timeline_groups"]:
                for item in grp["items"]:
                    if "Check-in Call" in item["title"]:
                        found = True
                        break
            self.assertTrue(found)

    def test_tag_addition_and_removal(self):
        with main.SessionLocal() as db:
            customer = db.query(main.User).filter_by(role="customer").first()
            cid = customer.id

            req_add = self.make_request(
                method="POST",
                path=f"/admin/crm/api/customer/{cid}/tags",
                json_data={"action": "add", "tag": "TestVIPTag"}
            )
            res_add = run_coro(main.crm_api_update_tags(cid, req_add, self.admin, db))
            self.assertIn("TestVIPTag", res_add["tags"])

            req_rem = self.make_request(
                method="POST",
                path=f"/admin/crm/api/customer/{cid}/tags",
                json_data={"action": "remove", "tag": "TestVIPTag"}
            )
            res_rem = run_coro(main.crm_api_update_tags(cid, req_rem, self.admin, db))
            self.assertNotIn("TestVIPTag", res_rem["tags"])

    def test_compare_segments_venn_and_overlap_warning(self):
        with main.SessionLocal() as db:
            segs = db.query(main.SmartSegment).all()
            self.assertGreaterEqual(len(segs), 2)
            seg_a = str(segs[0].id)
            seg_b = str(segs[1].id)

            req = self.make_request(path="/admin/crm/api/compare", query_string=f"seg_a={seg_a}&seg_b={seg_b}".encode())
            res = main.crm_api_compare(req, self.admin, db)
            self.assertIn("venn", res)
            self.assertIn("stats_a", res)
            self.assertIn("stats_b", res)
            self.assertIn("shared_revenue", res["venn"])
            self.assertIn("intersection_rules", res)

    def test_bulk_actions_and_undo(self):
        with main.SessionLocal() as db:
            customers = db.query(main.User).filter_by(role="customer").limit(2).all()
            cids = [c.id for c in customers]
            self.assertGreaterEqual(len(cids), 1)

            # 1. Bulk tag
            req_bulk_tag = self.make_request(
                method="POST",
                path="/admin/crm/api/bulk/tags",
                json_data={"customer_ids": cids, "action": "add", "tag": "BulkCohortA"}
            )
            res_tag = run_coro(main.crm_api_bulk_tags(req_bulk_tag, self.admin, db))
            self.assertTrue(res_tag["success"])
            undo_token = res_tag["undo_token"]

            # 2. Undo bulk tag
            req_undo = self.make_request(
                method="POST",
                path="/admin/crm/api/bulk/undo",
                json_data={"undo_token": undo_token}
            )
            res_undo = run_coro(main.crm_api_bulk_undo(req_undo, self.admin, db))
            self.assertTrue(res_undo["success"])

            # 3. Bulk consent update
            req_bulk_consent = self.make_request(
                method="POST",
                path="/admin/crm/api/bulk/consent",
                json_data={"customer_ids": cids, "marketing_status": "subscribed"}
            )
            res_consent = run_coro(main.crm_api_bulk_consent(req_bulk_consent, self.admin, db))
            self.assertTrue(res_consent["success"])

            # 4. Bulk Email Dispatcher
            req_bulk_email = self.make_request(
                method="POST",
                path="/admin/crm/api/bulk/email",
                json_data={
                    "customer_ids": cids,
                    "template_type": "marketing",
                    "subject": "Studio Drop Welcome",
                    "body": "Hello {{first_name}}, thank you for supporting All of Us.",
                    "schedule": "immediate",
                }
            )
            res_email = run_coro(main.crm_api_bulk_email(req_bulk_email, self.admin, db))
            self.assertTrue(res_email["success"])
            self.assertGreaterEqual(res_email["sent_count"], 1)

    def test_smart_segment_crud_and_preview(self):
        with main.SessionLocal() as db:
            # 1. Live preview
            req_prev = self.make_request(
                method="POST",
                path="/admin/crm/api/segments/preview",
                json_data={"rules": {"min_spend": 100}, "match_type": "all"}
            )
            res_prev = run_coro(main.crm_api_preview_segment(req_prev, self.admin, db))
            self.assertIn("matching_count", res_prev)
            self.assertIn("share_percentage", res_prev)
            self.assertIn("channel_mix", res_prev)

            # 2. Create segment
            req_create = self.make_request(
                method="POST",
                path="/admin/crm/api/segments",
                json_data={
                    "name": "High Spenders Test",
                    "color": "#7c3aed",
                    "match_type": "all",
                    "rules": {"min_spend": 100},
                    "is_pinned": True,
                    "daily_digest": True,
                    "digest_time": "09:00 NPT",
                }
            )
            res_create = run_coro(main.crm_api_create_segment(req_create, self.admin, db))
            self.assertTrue(res_create["success"])
            seg_id = res_create["id"]

            # 3. Update segment
            req_update = self.make_request(
                method="PUT",
                path=f"/admin/crm/api/segments/{seg_id}",
                json_data={"name": "High Spenders Updated"}
            )
            res_update = run_coro(main.crm_api_update_segment(seg_id, req_update, self.admin, db))
            self.assertTrue(res_update["success"])

            # 4. Delete segment
            req_del = self.make_request(
                method="DELETE",
                path=f"/admin/crm/api/segments/{seg_id}",
                json_data={}
            )
            res_del = run_coro(main.crm_api_delete_segment(seg_id, req_del, self.admin, db))
            self.assertTrue(res_del["success"])

    def test_export_customers_csv(self):
        req = self.make_request(path="/admin/crm/export", query_string=b"")
        with main.SessionLocal() as db:
            res = main.export_customers(req, self.admin, db)
            self.assertEqual(res.status_code, 200)
            self.assertIn("text/csv", res.headers.get("content-type", ""))
            csv_text = res.body.decode("utf-8")
            self.assertIn("First name", csv_text)
            self.assertIn("Total spend", csv_text)
            self.assertIn("Rank", csv_text)
            self.assertIn("Channel", csv_text)

    def test_add_customer_view_creates_customer_and_sets_flash(self):
        with main.SessionLocal() as db:
            test_email = "dipesh.malla@example.com"
            # Cleanup if existed previously
            db.query(main.User).filter_by(email=test_email).delete()
            db.commit()

            form_payload = {
                "first_name": "Dipesh",
                "last_name": "Malla",
                "email": test_email,
                "phone": "+977-9812345678",
                "channel": "Store Agent Portal",
                "marketing_consent": "on",
            }
            req = self.make_request(
                method="POST",
                path="/admin/crm/customers/add",
                form_data=form_payload,
            )

            res = run_coro(main.add_customer_view(req, self.admin, db))
            self.assertEqual(res.status_code, 303)
            self.assertEqual(req.session.get("flash"), ["success", "Customer Dipesh Malla added successfully."])

            # Verify saved in db
            created = db.query(main.User).filter_by(email=test_email).first()
            self.assertIsNotNone(created)
            self.assertEqual(created.first_name, "Dipesh")
            self.assertEqual(created.last_name, "Malla")
            self.assertEqual(created.role, "customer")
            self.assertEqual(created.acquisition_channel, "Store Agent Portal")
            self.assertTrue(created.marketing_opt_in)
            self.assertEqual(created.resolved_marketing_status, "subscribed")

    def test_add_customer_view_duplicate_detection(self):
        with main.SessionLocal() as db:
            existing = db.query(main.User).filter_by(role="customer").first()
            self.assertIsNotNone(existing)

            form_payload = {
                "first_name": "Duplicate",
                "last_name": "User",
                "email": existing.email,
                "phone": "+977-9800000000",
                "channel": "Direct Web",
            }
            req = self.make_request(
                method="POST",
                path="/admin/crm/customers/add",
                form_data=form_payload,
            )

            res = run_coro(main.add_customer_view(req, self.admin, db))
            self.assertEqual(res.status_code, 303)
            self.assertEqual(req.session.get("flash")[0], "error")
            self.assertIn("already exists", req.session.get("flash")[1])

    def test_add_customer_view_require_post_enforcement(self):
        with main.SessionLocal() as db:
            req_get = self.make_request(method="GET", path="/admin/crm/customers/add")
            with self.assertRaises(main.HTTPException) as ctx:
                run_coro(main.add_customer_view(req_get, self.admin, db))
            self.assertEqual(ctx.exception.status_code, 405)

    def test_views_and_urls_django_compatibility(self):
        import views
        import urls

        self.assertIs(views.Customer, main.User)
        self.assertTrue(hasattr(views, "add_customer_view"))
        self.assertTrue(hasattr(views, "require_POST"))
        self.assertTrue(hasattr(urls, "urlpatterns"))
        self.assertGreaterEqual(len(urls.urlpatterns), 1)

    def test_import_legacy_customers_utility(self):
        import io
        import import_legacy_customers

        csv_content = """email,first_name,last_name,phone,joined_date,total_spend,orders,channel,marketing_consent
aarav.sharma@example.com,Aarav,Sharma,+977-9801234567,2025-01-10,350.00,4,Direct Web,yes
test.migrated.user@example.com,Pooja,Rana,+977-9844445555,2025-04-12,220.00,3,Guest Checkout,yes
"""
        with main.SessionLocal() as db:
            # Clean up prior test user if present
            db.query(main.User).filter_by(email="test.migrated.user@example.com").delete()
            db.commit()

            # First run: 1 existing, 1 new
            report = import_legacy_customers.import_legacy_customers(io.StringIO(csv_content), db=db)
            self.assertEqual(report["total_rows"], 2)
            self.assertEqual(report["created_count"], 1)
            self.assertEqual(report["updated_count"], 1)

            # Verify created user
            migrated = db.query(main.User).filter_by(email="test.migrated.user@example.com").first()
            self.assertIsNotNone(migrated)
            self.assertEqual(migrated.first_name, "Pooja")
            self.assertEqual(migrated.last_name, "Rana")
            self.assertEqual(migrated.acquisition_channel, "Guest Checkout")
            self.assertTrue(migrated.marketing_opt_in)
            self.assertGreaterEqual(len(migrated.orders), 1)

            # Second run: 0 created, 2 updated/existing (get_or_create deduplication check)
            report_second = import_legacy_customers.import_legacy_customers(io.StringIO(csv_content), db=db)
            self.assertEqual(report_second["created_count"], 0)
            self.assertEqual(report_second["updated_count"], 2)


if __name__ == "__main__":
    unittest.main()

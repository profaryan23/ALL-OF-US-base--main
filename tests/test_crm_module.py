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

    def make_request(self, method="GET", path="/admin/crm", query_string=b"", session=None, json_data=None):
        sess = {"user_id": self.admin_id, "csrf_token": "valid_token"}
        if session:
            sess.update(session)
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query_string,
            "headers": [
                (b"x-csrf-token", b"valid_token"),
                (b"content-type", b"application/json"),
            ],
            "session": sess,
            "app": main.app,
        }
        req = Request(scope)
        if json_data is not None:
            async def _json():
                return json_data
            req.json = _json
        return req

    def test_admin_crm_page_renders_with_kpi_and_ux_components(self):
        req = self.make_request(path="/admin/crm")
        with main.SessionLocal() as db:
            response = main.admin_crm(req, self.admin, db)
            self.assertEqual(response.status_code, 200)
            html = response.body.decode("utf-8")

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


if __name__ == "__main__":
    unittest.main()

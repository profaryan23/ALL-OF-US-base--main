import unittest
from decimal import Decimal
from fastapi.testclient import TestClient

import main


class OrderAndSalesManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.migrate_catalog_schema()
        cls.client = TestClient(main.app)

        # Login as admin
        login_res = cls.client.post(
            "/login",
            data={"email": "team@allofus.internal", "password": "changethisnow"},
            follow_redirects=True,
        )
        assert login_res.status_code == 200

    def test_admin_orders_page_and_drawer_triggers(self):
        res = self.client.get("/admin/orders")
        self.assertEqual(res.status_code, 200)
        # Check drawer triggers exist in the table
        self.assertIn("order-drawer-trigger", res.text)
        self.assertIn("order-slide-drawer", res.text)
        self.assertIn("Audit Trail &amp; Status Progression", res.text)
        self.assertIn("Line Item Variant Breakdown", res.text)
        self.assertIn("Operational Fulfillment &amp; Vendor Production Tracking", res.text)
        self.assertIn("vendor_batch_id", res.text)
        self.assertIn("tracking_number", res.text)

    def test_update_order_fulfillment_and_batch_details(self):
        # Retrieve CSRF token and first order
        orders_page = self.client.get("/admin/orders")
        self.assertEqual(orders_page.status_code, 200)
        csrf_token = orders_page.text.split('name="csrf_token" value="')[1].split('"')[0]

        with main.SessionLocal() as db:
            first_order = db.query(main.Order).first()
            self.assertIsNotNone(first_order)
            order_id = first_order.id

        update_res = self.client.post(
            f"/admin/orders/{order_id}/fulfillment",
            data={
                "csrf_token": csrf_token,
                "status": "Processing",
                "carrier": "DHL Express",
                "tracking_number": "DHL-9948201",
                "vendor_batch_id": "BATCH-STREET-TEE-2026",
                "shipping_address": "450 Broadway Apt 4B, New York, NY 10013",
                "gateway_ref": "ch_3N82b8Klw0P",
                "promo_code": "STREETWEAR10",
                "tax_amount": "8.50",
                "discount_amount": "15.00",
            },
            follow_redirects=True,
        )
        self.assertEqual(update_res.status_code, 200)
        self.assertIn(f"Fulfillment &amp; vendor production batch details saved for Order #{order_id:04d}", update_res.text)

        # Verify persisted fields in database
        with main.SessionLocal() as db:
            saved_order = db.get(main.Order, order_id)
            self.assertEqual(saved_order.status, "Processing")
            self.assertEqual(saved_order.carrier, "DHL Express")
            self.assertEqual(saved_order.tracking_number, "DHL-9948201")
            self.assertEqual(saved_order.vendor_batch_id, "BATCH-STREET-TEE-2026")
            self.assertEqual(saved_order.shipping_address, "450 Broadway Apt 4B, New York, NY 10013")
            self.assertEqual(saved_order.gateway_ref, "ch_3N82b8Klw0P")
            self.assertEqual(saved_order.promo_code, "STREETWEAR10")
            self.assertEqual(saved_order.tax_amount, Decimal("8.50"))
            self.assertEqual(saved_order.discount_amount, Decimal("15.00"))

    def test_admin_sales_executive_kpis_and_variant_margins(self):
        # Test default period (30 days)
        res30 = self.client.get("/admin/sales?period=30")
        self.assertEqual(res30.status_code, 200)
        self.assertIn("Gross Revenue", res30.text)
        self.assertIn("Net Revenue", res30.text)
        self.assertIn("Average Order Value (AOV)", res30.text)
        self.assertIn("Total Units Sold", res30.text)
        self.assertIn("Est. Manufacturing Margin", res30.text)
        self.assertIn("Product &amp; Variant Performance", res30.text)
        self.assertIn("Vendor COGS (Unit)", res30.text)
        self.assertIn("Gross Margin (%)", res30.text)
        self.assertIn("Transaction Ledger", res30.text)

        # Test other date ranges (today, 7, 90, all)
        for p in ["today", "7", "90", "all"]:
            resp = self.client.get(f"/admin/sales?period={p}")
            self.assertEqual(resp.status_code, 200)

    def test_sales_ledger_csv_export(self):
        export_res = self.client.get("/admin/sales/export?period=30")
        self.assertEqual(export_res.status_code, 200)
        self.assertIn("text/csv", export_res.headers.get("content-type", ""))
        self.assertIn("all-of-us-sales-ledger-30.csv", export_res.headers.get("content-disposition", ""))
        
        # Verify CSV column headers
        csv_content = export_res.text
        self.assertIn("Transaction ID", csv_content)
        self.assertIn("Order Date (UTC)", csv_content)
        self.assertIn("Customer Name", csv_content)
        self.assertIn("Gross Subtotal ($)", csv_content)
        self.assertIn("Estimated COGS ($)", csv_content)
        self.assertIn("Gross Profit ($)", csv_content)
        self.assertIn("Carrier", csv_content)
        self.assertIn("Tracking Number", csv_content)
        self.assertIn("Vendor Batch ID", csv_content)


if __name__ == "__main__":
    unittest.main()

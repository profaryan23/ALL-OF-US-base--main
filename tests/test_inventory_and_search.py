import os
import tempfile
import unittest
from pathlib import Path

_temp_dir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_ENV"] = "development"
os.environ["PRODUCT_IMAGE_DIR"] = str(Path(_temp_dir.name) / "images")
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "admin-secret-password-123"
os.environ["COOKIE_SECURE"] = "false"

from fastapi.testclient import TestClient
import main


class InventoryAndSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(main.app)
        cls.client = cls.client_context.__enter__()
        main.seed_database()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        main.engine.dispose()
        _temp_dir.cleanup()

    def _login_admin(self):
        email = "test-inventory-admin@example.com"
        password = "strong-admin-password-xyz"
        with main.SessionLocal() as db:
            admin = db.query(main.User).filter_by(email=email).first()
            if not admin:
                admin = main.User(
                    email=email,
                    password_hash=main.generate_password_hash(password),
                    first_name="Admin",
                    last_name="Tester",
                    role="admin",
                )
                db.add(admin)
                db.commit()

        login_res = self.client.get("/admin/login")
        import re
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_res.text)
        csrf_token = match.group(1) if match else ""
        response = self.client.post(
            "/admin/login",
            data={
                "email": email,
                "password": password,
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        return csrf_token

    def test_admin_search_page_and_querying(self):
        self._login_admin()

        # Search overview
        res = self.client.get("/admin/search?module=overview&q=Inventory")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Search Overview", res.text)
        self.assertIn("Inventory", res.text)

        # Search inventory module
        res = self.client.get("/admin/search?module=inventory&q=")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Search Inventory", res.text)

        # Search all modules
        res = self.client.get("/admin/search?module=all&q=Ceramic")
        self.assertEqual(res.status_code, 200)
        self.assertIn("All modules", res.text)

    def test_inventory_has_add_button_and_product_elements(self):
        self._login_admin()
        res = self.client.get("/admin/inventory")
        self.assertEqual(res.status_code, 200)

        # Check for Add Product button
        self.assertIn("btn-open-add-product", res.text)
        self.assertIn("Add Product", res.text)

        # Check for add-product-panel form
        self.assertIn("add-product-panel", res.text)

        # Check for search bar at top right
        self.assertIn("module-nav-search-area", res.text)
        self.assertIn("nav-search-button", res.text)

        # Check for product table rows and View in shop buttons
        self.assertIn('product-row-', res.text)
        self.assertIn("View in shop ↗", res.text)
        self.assertIn("Delete product", res.text)

    def test_delete_product_flow(self):
        self._login_admin()
        # Create a new test product to delete
        with main.SessionLocal() as db:
            prod = main.Product(
                name="Ephemeral Test Mug",
                category="Kitchen",
                shop_category="Specials",
                price=25.00,
                stock_quantity=5,
                is_active=True,
            )
            db.add(prod)
            db.commit()
            db.refresh(prod)
            test_prod_id = prod.id

        # Verify it exists in inventory page
        inv_res = self.client.get("/admin/inventory")
        self.assertIn(f"product-{test_prod_id}", inv_res.text)

        # Get csrf token from session
        import re
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', inv_res.text)
        csrf_token = match.group(1) if match else ""

        # Delete the product
        del_res = self.client.post(
            f"/admin/products/{test_prod_id}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertIn("Product deleted from inventory", del_res.text)

        # Verify it is no longer in database
        with main.SessionLocal() as db:
            deleted_prod = db.get(main.Product, test_prod_id)
            self.assertIsNone(deleted_prod)


if __name__ == "__main__":
    unittest.main()

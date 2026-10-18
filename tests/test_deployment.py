import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Run against isolated data, never the developer's SQLite database.
_temporary_directory = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_ENV"] = "development"
os.environ["PRODUCT_IMAGE_DIR"] = str(Path(_temporary_directory.name) / "images")
os.environ["ADMIN_EMAIL"] = "deploy-test@example.com"
os.environ["ADMIN_PASSWORD"] = "test-admin-password-unique"
os.environ["COOKIE_SECURE"] = "false"

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import main


class DeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(main.app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        main.engine.dispose()
        _temporary_directory.cleanup()

    def test_health_check(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_check_database_failure(self):
        with patch.object(main.engine, "connect", side_effect=OperationalError("SELECT 1", {}, Exception("private details"))):
            response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private details", response.text)

    def test_configured_admin_is_seeded_once(self):
        main.seed_database()
        with main.SessionLocal() as db:
            admins = db.query(main.User).filter_by(role="admin").all()
            self.assertEqual(len(admins), 1)
            self.assertEqual(admins[0].email, "deploy-test@example.com")
            self.assertTrue(main.check_password_hash(admins[0].password_hash, "test-admin-password-unique"))

    def test_pages_and_static_files(self):
        for path in ("/", "/shop", "/about", "/contact", "/admin/login", "/static/styles.css"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_uploaded_image_is_served_from_configured_directory(self):
        content = b"\x89PNG\r\n\x1a\nexample"
        image_path = main.save_product_image((".png", content))
        self.assertTrue((main.PRODUCT_IMAGE_DIR / Path(image_path).name).exists())
        response = self.client.get(f"/static/{image_path}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, content)

    def test_bundled_images_are_copied(self):
        for image in Path("static/product-images").iterdir():
            if image.is_file():
                self.assertEqual((main.PRODUCT_IMAGE_DIR / image.name).read_bytes(), image.read_bytes())

    def test_production_rejects_sqlite(self):
        environment = dict(os.environ, APP_ENV="production")
        result = subprocess.run([sys.executable, "-c", "import main"], env=environment, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Production requires a PostgreSQL DATABASE_URL", result.stderr)

    def test_production_rejects_weak_secrets(self):
        base_environment = dict(
            os.environ,
            APP_ENV="production",
            DATABASE_URL="postgresql://postgres:unused@localhost/postgres",
            SECRET_KEY="s" * 48,
        )
        for overrides, expected in (
            ({"SECRET_KEY": "short"}, "Set SECRET_KEY"),
            ({"ADMIN_PASSWORD": "admin123"}, "Set ADMIN_EMAIL"),
        ):
            with self.subTest(overrides=overrides):
                result = subprocess.run(
                    [sys.executable, "-c", "import main"],
                    env=dict(base_environment, **overrides),
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)


if __name__ == "__main__":
    unittest.main()
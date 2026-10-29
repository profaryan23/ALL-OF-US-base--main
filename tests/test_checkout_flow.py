import json
import re
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import main


class CheckoutFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'store.db'}", connect_args={"check_same_thread": False})
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.patches = [patch.object(main, 'engine', self.engine), patch.object(main, 'SessionLocal', self.sessions),
                        patch.object(main, 'PRODUCT_IMAGE_DIR', Path(self.directory.name) / 'images')]
        for item in self.patches:
            item.start()
        self.client = TestClient(main.app).__enter__()
        with self.sessions() as db:
            product = main.Product(name='Inventory-only shirt', description='Saved inventory description',
                                   price=Decimal('1250.50'), stock_quantity=5, size_variations='S, M',
                                   color_variations=json.dumps([{'name': 'Blue', 'hex': '#123456', 'photo_path': ''}]))
            db.add(product)
            settings = main.CheckoutSettings(id=1, whatsapp='https://wa.me/9779812345678')
            db.add(settings)
            db.commit()
            self.product_id = product.id
        self.token = self.csrf('/shop')

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.engine.dispose()
        for item in reversed(self.patches):
            item.stop()
        main.product_image_files.directory = str(main.PRODUCT_IMAGE_DIR)
        self.directory.cleanup()

    def csrf(self, path):
        html = self.client.get(path).text
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        if match:
            return match.group(1)
        return json.loads(re.search(r'var csrfToken = ("[^"]+");', html).group(1))

    def add(self, **overrides):
        data = dict(product_id=self.product_id, quantity=2, size='M', color='Blue')
        data.update(overrides)
        return self.client.post('/api/cart/add', json=data, headers={'X-CSRF-Token': self.token})

    def place(self, **overrides):
        data = dict(csrf_token=self.token, name='Actual Buyer', phone='9812345678',
                    address='Street 1, Kathmandu', notes='Call on arrival', payment_method='WhatsApp')
        data.update(overrides)
        return self.client.post('/checkout', data=data, follow_redirects=False)

    def login_admin(self):
        with self.sessions() as db:
            user = main.User(first_name='Test', last_name='Admin', email='checkout-admin@example.com',
                             password_hash=main.generate_password_hash('secure-test-password'), role='admin')
            db.add(user)
            db.commit()
        token = self.csrf('/admin/login')
        response = self.client.post('/admin/login', data=dict(csrf_token=token, email='checkout-admin@example.com', password='secure-test-password'))
        self.assertEqual(response.status_code, 200)
        self.token = self.csrf('/admin/orders')

    def test_inventory_data_is_published_and_edits_are_immediate(self):
        self.login_admin()
        response = self.client.post(f'/admin/products/{self.product_id}', data=dict(
            csrf_token=self.token, name='Updated inventory shirt', description='Updated live description',
            category='Apparel', shop_category='Essentials', price='1500.75', stock_quantity='4',
            size_variations='S, M', is_active='on'))
        self.assertEqual(response.status_code, 200)
        html = self.client.get('/shop').text
        products = json.loads(re.search(r'<script id="shopProductsJson" type="application/json">(.*?)</script>', html, re.S).group(1))
        product = next(p for p in products if p['id'] == self.product_id)
        self.assertEqual(product['name'], 'Updated inventory shirt')
        self.assertEqual(product['description'], 'Updated live description')
        self.assertEqual(product['price'], 1500.75)
        self.assertEqual(product['sizes'], ['S', 'M'])
        self.assertEqual(product['stock'], 4)
        self.assertNotIn('Demo total', html)

    def test_guest_order_persists_total_variants_and_stock(self):
        self.assertEqual(self.add(price=1).status_code, 200)
        self.assertIn('2501.00', self.client.get('/cart').text)
        self.assertIn('Choose payment', self.client.get('/checkout').text)
        response = self.place()
        self.assertEqual(response.status_code, 303)
        confirmation = self.client.get(response.headers['location'])
        self.assertEqual(confirmation.status_code, 200)
        self.assertIn('Awaiting verification', confirmation.text)
        self.assertIn('https://wa.me/9779812345678', confirmation.text)
        self.engine.dispose()  # Reload via a fresh connection to the on-disk database.
        with self.sessions() as db:
            order = db.query(main.Order).one()
            self.assertEqual(order.total_amount, Decimal('2501.00'))
            self.assertEqual(order.customer_phone, '9812345678')
            self.assertEqual(order.customer_notes, 'Call on arrival')
            self.assertEqual(order.payment_method, 'WhatsApp')
            self.assertEqual(order.items[0].color_variation, 'Blue')
            self.assertEqual(order.items[0].size_variation, 'M')
            self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 3)
            movement = db.query(main.StockMovement).filter_by(product_id=self.product_id, reason='Customer order').one()
            self.assertEqual(movement.quantity, -2)
            self.assertEqual(movement.balance_after, 3)
            self.assertEqual(movement.reference, f'Order #{order.id:04d}')
        self.assertIn('Your bag is empty', self.client.get('/cart').text)
        self.assertIn('Your bag is empty', self.client.get(self.place().headers['location']).text)
        with TestClient(main.app) as other:
            self.assertEqual(other.get(response.headers['location']).status_code, 404)

    def test_cart_rejects_unknown_products_variants_and_stock(self):
        for overrides, status in [({'product_id': 999999}, 404), ({'size': 'XL'}, 400),
                                  ({'color': 'Red'}, 400), ({'quantity': -1}, 400),
                                  ({'quantity': 6}, 400), ({'quantity': 1.5}, 400)]:
            with self.subTest(overrides=overrides):
                self.assertEqual(self.add(**overrides).status_code, status)
        self.assertEqual(self.client.post('/api/cart/add', json={'product_id': self.product_id}).status_code, 400)
        self.assertEqual(self.add().status_code, 200)
        self.assertEqual(self.add(size='S', quantity=4).status_code, 400)

    def test_checkout_rejects_missing_details_and_changed_stock_without_writes(self):
        self.add()
        self.assertEqual(self.place(phone='').status_code, 400)
        self.assertEqual(self.place(payment_method='QR payment').status_code, 400)
        with self.sessions() as db:
            db.get(main.Product, self.product_id).stock_quantity = 1
            db.commit()
        self.assertEqual(self.place().status_code, 400)
        with self.sessions() as db:
            self.assertEqual(db.query(main.Order).count(), 0)
            self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 1)

    def test_admin_settings_qr_order_page_and_payment_verification(self):
        self.assertEqual(self.client.get('/admin/orders/1').status_code, 403)
        self.login_admin()
        response = self.client.post('/admin/checkout-settings', data=dict(csrf_token=self.token,
            whatsapp='https://wa.me/9779812345678', instagram='https://www.instagram.com/store',
            payment_instructions='Send the receipt with your order number'),
            files={'photo': ('qr.png', b'\x89PNG\r\n\x1a\nqr-test', 'image/png')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post('/admin/checkout-settings', data=dict(csrf_token=self.token,
                         instagram='https://evil.example')).status_code, 400)
        self.add()
        response = self.place(payment_method='QR payment')
        self.assertEqual(response.status_code, 303)
        self.assertIn('Store payment QR code', self.client.get(response.headers['location']).text)
        with self.sessions() as db:
            order = db.query(main.Order).one()
            order_id = order.id
        self.assertIn('Actual Buyer', self.client.get(f'/admin/orders/{order_id}').text)
        response = self.client.post(f'/admin/orders/{order_id}/payment', data=dict(
            csrf_token=self.token, payment_status='Paid', gateway_ref='RECEIPT-123'))
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.get(main.Order, order_id).payment_status, 'Paid')
            self.assertEqual(db.get(main.Order, order_id).gateway_ref, 'RECEIPT-123')
        self.assertEqual(self.client.get('/admin/orders/999999').status_code, 404)

    def test_unconfigured_checkout_disables_ordering_without_none_values(self):
        with self.sessions() as db:
            db.delete(db.get(main.CheckoutSettings, 1))
            db.commit()
        self.add()
        response = self.client.get('/checkout')
        self.assertEqual(response.status_code, 200)
        self.assertIn('has not configured payment or contact options', response.text)
        self.assertNotIn('<p>None</p>', response.text)
        self.assertEqual(self.place().status_code, 400)
        self.login_admin()
        self.assertNotIn('value="None"', self.client.get('/admin/checkout-settings').text)

    def test_order_inventory_and_settings_survive_database_reconnect(self):
        self.add()
        response = self.place()
        self.assertEqual(response.status_code, 303)
        self.engine.dispose()
        with TestClient(main.app) as restarted:
            self.assertIn('Inventory-only shirt', restarted.get('/shop').text)
            with self.sessions() as db:
                order = db.query(main.Order).one()
                self.assertEqual(order.total_amount, Decimal('2501.00'))
                self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 3)
                self.assertEqual(db.get(main.CheckoutSettings, 1).whatsapp, 'https://wa.me/9779812345678')
                self.assertEqual(db.query(main.AnalyticsEvent).filter_by(event_type='purchase').count(), 1)

    def test_checkout_uses_latest_database_price_not_browser_price(self):
        self.add(price=1)
        with self.sessions() as db:
            db.get(main.Product, self.product_id).price = Decimal('1400.00')
            db.commit()
        self.assertEqual(self.place().status_code, 303)
        with self.sessions() as db:
            self.assertEqual(db.query(main.Order).one().total_amount, Decimal('2800.00'))

    def test_additive_checkout_migration_preserves_legacy_orders(self):
        legacy = create_engine('sqlite:///:memory:')
        try:
            with legacy.begin() as connection:
                connection.execute(text('CREATE TABLE orders (id INTEGER PRIMARY KEY, total_amount NUMERIC)'))
                connection.execute(text('INSERT INTO orders VALUES (2, 1250.50)'))
            with patch.object(main, 'engine', legacy):
                main.migrate_catalog_schema()
                main.migrate_catalog_schema()  # Repeat deployments must be safe.
            columns = {column['name'] for column in inspect(legacy).get_columns('orders')}
            self.assertTrue({'payment_method', 'payment_status', 'customer_name', 'customer_phone'} <= columns)
            with legacy.connect() as connection:
                row = connection.execute(text('SELECT total_amount, payment_status FROM orders WHERE id = 2')).one()
                self.assertEqual(Decimal(str(row[0])), Decimal('1250.50'))
                self.assertEqual(row[1], 'Awaiting verification')
        finally:
            legacy.dispose()


if __name__ == '__main__':
    unittest.main()

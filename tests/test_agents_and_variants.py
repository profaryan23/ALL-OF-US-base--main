import json
import os
import re
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

_storage = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['APP_ENV'] = 'development'
os.environ['PRODUCT_IMAGE_DIR'] = str(Path(_storage.name) / 'images')
os.environ['ADMIN_EMAIL'] = 'deploy-test@example.com'
os.environ['ADMIN_PASSWORD'] = 'test-admin-password-unique'
os.environ['COOKIE_SECURE'] = 'false'

from fastapi.testclient import TestClient
import main


class AgentAndVariantTests(unittest.TestCase):
    def setUp(self):
        main.Base.metadata.drop_all(main.engine)
        main.Base.metadata.create_all(main.engine)
        main.seed_database()
        self.context = TestClient(main.app)
        self.client = self.context.__enter__()
        with main.SessionLocal() as db:
            admin = db.query(main.User).filter_by(role='admin').first()
            if not admin:
                admin = main.User(email=main.ADMIN_EMAIL, password_hash=main.generate_password_hash(main.ADMIN_PASSWORD), role='admin')
                db.add(admin)
            else:
                admin.password_hash = main.generate_password_hash(main.ADMIN_PASSWORD)
            db.commit()
        response = self.client.get('/admin/login')
        self.token = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text).group(1)
        self.client.post('/admin/login', data={'csrf_token': self.token, 'email': main.ADMIN_EMAIL, 'password': main.ADMIN_PASSWORD})
        response = self.client.get('/admin/agents')
        self.token = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text).group(1)
        with main.SessionLocal() as db:
            product = main.Product(name='Variant trousers', category='Clothing', shop_category='Everyday',
                                   price=Decimal('1000'), stock_quantity=20, size_variations='28, M, L, XL',
                                   color_variations=json.dumps([{'name': 'Red', 'photo_path': 'red.png'}, {'name': 'Blue', 'photo_path': 'blue.png'}]))
            agent = main.Agent(name='Top Agent', phone='9800000000')
            db.add_all([product, agent])
            db.commit()
            self.product_id, self.agent_id = product.id, agent.id

    def tearDown(self):
        self.context.__exit__(None, None, None)
        main.Base.metadata.create_all(main.engine)
        main.seed_database()

    def post(self, url, **data):
        return self.client.post(url, data={'csrf_token': self.token, **data}, follow_redirects=True)

    def sale(self, **extra):
        return self.post('/admin/sales/record', product_id=self.product_id, quantity=2, price='950',
                         agent_id=self.agent_id, size_variation='M', color_variation='Red',
                         company_discount_percent='10', commission_percent='10', **extra)

    def test_agent_sale_cost_commission_filters_and_export(self):
        self.assertEqual(self.sale().status_code, 200)
        with main.SessionLocal() as db:
            order = db.query(main.Order).filter_by(agent_id=self.agent_id).one()
            item = order.items[0]
            self.assertEqual(order.total_amount, Decimal('1900.00'))
            self.assertEqual(item.agent_unit_cost, Decimal('900.00'))
            self.assertEqual(item.commission_amount, Decimal('190.00'))
            self.assertEqual(item.color_variation, 'Red')
            self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 18)
        for endpoint in ('agents', 'sales', 'orders', 'crm', 'reports'):
            response = self.client.get(f'/admin/{endpoint}?agent_id={self.agent_id}')
            self.assertEqual(response.status_code, 200, endpoint)
            self.assertIn('Top Agent', response.text)
        response = self.client.get(f'/admin/sales/export?agent_id={self.agent_id}')
        self.assertIn('Agent Commission (Rs)', response.text)
        self.assertIn('190.00', response.text)
        self.assertIn('Red', response.text)
        direct = self.client.get('/admin/sales?agent_id=direct')
        self.assertNotIn('1900.00', direct.text)

    def test_allocation_and_sale_do_not_double_deduct(self):
        response = self.post('/admin/agents/allocate', agent_id=self.agent_id, product_id=self.product_id,
                             quantity=5, size_variation='M', color_variation='Red', company_discount_percent='10')
        self.assertEqual(response.status_code, 200)
        with main.SessionLocal() as db:
            allocation = db.query(main.AgentAllocation).one()
            allocation_id = allocation.id
            self.assertEqual(allocation.unit_cost, Decimal('900.00'))
            self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 15)
        self.sale(allocation_id=allocation_id)
        with main.SessionLocal() as db:
            self.assertEqual(db.get(main.AgentAllocation, allocation_id).remaining, 3)
            self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 15)

    def test_invalid_sale_does_not_change_stock(self):
        for extra in ({'quantity': 100}, {'commission_percent': 'NaN'}, {'company_discount_percent': '101'}, {'color_variation': 'Green'}, {'price': 'Infinity'}):
            data = dict(product_id=self.product_id, quantity=1, price='950', agent_id=self.agent_id,
                        size_variation='M', color_variation='Red', commission_percent='10', company_discount_percent='10')
            data.update(extra)
            response = self.post('/admin/sales/record', **data)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Check price', response.text)
        with main.SessionLocal() as db:
            self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 20)
            self.assertEqual(db.query(main.Order).filter_by(agent_id=self.agent_id).count(), 0)

    def test_color_cart_and_checkout_preserve_variants(self):
        for color in ('Red', 'Blue'):
            response = self.post(f'/cart/add/{self.product_id}', size_variation='M', color_variation=color)
            self.assertEqual(response.status_code, 200)
        cart = self.client.get('/cart')
        self.assertIn('Color: Red', cart.text)
        self.assertIn('Color: Blue', cart.text)
        self.assertIn('red.png', cart.text)
        self.post('/checkout')
        with main.SessionLocal() as db:
            order = db.query(main.Order).order_by(main.Order.id.desc()).first()
            self.assertEqual({i.color_variation for i in order.items}, {'Red', 'Blue'})
            self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 18)
        response = self.post(f'/cart/add/{self.product_id}', size_variation='M', color_variation='Green')
        self.assertEqual(response.status_code, 400)

    def test_create_product_with_size_buttons_and_color_upload(self):
        response = self.client.post('/admin/products', data={
            'csrf_token': self.token, 'name': 'New color shirt', 'category': 'Clothing', 'shop_category': 'Everyday',
            'price': '1200', 'stock_quantity': '5', 'size_choices_present': '1', 'sizes': ['28', 'M', 'XL'],
            'colors_present': '1', 'color_name': ['Red', 'Blue'], 'is_active': 'on',
        }, files={'color_photo_0': ('red.png', b'\x89PNG\r\n\x1a\nred', 'image/png'),
                  'color_photo_1': ('blue.png', b'\x89PNG\r\n\x1a\nblue', 'image/png')}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with main.SessionLocal() as db:
            product = db.query(main.Product).filter_by(name='New color shirt').one()
            self.assertEqual(product.size_variations, '28, M, XL')
            self.assertEqual(len(main.product_colors(product)), 2)
            detail = self.client.get(f'/shop/product/{product.id}')
            self.assertIn('data-color-photo=', detail.text)
            self.assertIn('name="color_variation"', detail.text)
        inventory = self.client.get('/admin/inventory')
        for size in ('28', '29', '30', '31', '32', '33', '34', 'M', 'L', 'XL'):
            self.assertIn(f'name="sizes" value="{size}"', inventory.text)

    def test_percentages_editable_and_cancelled_sales_excluded_from_rank(self):
        self.post('/admin/sales/record', product_id=self.product_id, quantity=1, price='955.55',
                  agent_id=self.agent_id, size_variation='M', color_variation='Blue',
                  company_discount_percent='15', commission_percent='12.5')
        with main.SessionLocal() as db:
            order = db.query(main.Order).filter_by(agent_id=self.agent_id).one()
            self.assertEqual(order.items[0].agent_unit_cost, Decimal('850.00'))
            self.assertEqual(order.items[0].commission_amount, Decimal('119.44'))
            order_id = order.id
        self.post(f'/admin/orders/{order_id}', status='Cancelled')
        agents = self.client.get('/admin/agents')
        self.assertIn('Rs 0.00', agents.text)
        self.assertIn('(not earned)', agents.text)

    def test_agent_routes_require_admin_and_csrf(self):
        self.assertEqual(self.client.post('/admin/agents', data={'name': 'No CSRF'}).status_code, 400)
        with TestClient(main.app) as anonymous:
            self.assertEqual(anonymous.get('/admin/agents').status_code, 403)


if __name__ == '__main__':
    unittest.main()
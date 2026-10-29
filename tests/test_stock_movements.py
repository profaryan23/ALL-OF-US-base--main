import re
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

import main


class StockMovementTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'stock.db'}",
                                    connect_args={"check_same_thread": False})
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.patches = [patch.object(main, 'engine', self.engine),
                        patch.object(main, 'SessionLocal', self.sessions),
                        patch.object(main, 'PRODUCT_IMAGE_DIR', Path(self.directory.name) / 'images')]
        for item in self.patches:
            item.start()
        self.context = TestClient(main.app)
        self.client = self.context.__enter__()
        with self.sessions() as db:
            admin = main.User(email='stock-admin@example.com', first_name='Stock', last_name='Admin',
                              role='admin', password_hash=main.generate_password_hash('stock-test-password'))
            product = main.Product(name='Movement shirt', price=Decimal('1250.00'), stock_quantity=10)
            db.add_all([admin, product])
            db.commit()
            self.product_id = product.id
        token = self.token('/admin/login')
        self.client.post('/admin/login', data=dict(csrf_token=token, email='stock-admin@example.com',
                                                   password='stock-test-password'))
        self.csrf = self.token('/admin/inventory')

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.engine.dispose()
        for item in reversed(self.patches):
            item.stop()
        main.product_image_files.directory = str(main.PRODUCT_IMAGE_DIR)
        self.directory.cleanup()

    def token(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text).group(1)

    def movement(self, **overrides):
        data = dict(csrf_token=self.csrf, product_id=self.product_id, quantity=5,
                    reason='Vendor receipt', vendor='Kathmandu Apparel', reference='INV-001', notes='Delivery')
        data.update(overrides)
        return self.client.post('/admin/inventory/movements', data=data, follow_redirects=False)

    def report(self, **overrides):
        from urllib.parse import urlencode
        query = dict(start='2026-01-01', end='2026-03-31', group='daily', product_id=self.product_id)
        query.update(overrides)
        request = Request(dict(type='http', query_string=urlencode(query).encode()))
        with self.sessions() as db:
            return main.stock_movement_report(db, request)

    def test_vendor_receipt_stock_out_and_persistence(self):
        self.assertEqual(self.movement().status_code, 303)
        self.assertEqual(self.movement(reason='Damaged stock', quantity=2, vendor='').status_code, 303)
        self.engine.dispose()
        with self.sessions() as db:
            rows = db.query(main.StockMovement).filter_by(product_id=self.product_id).order_by(main.StockMovement.id).all()
            self.assertEqual([row.quantity for row in rows], [10, 5, -2])
            self.assertEqual([row.balance_after for row in rows], [10, 15, 13])
            self.assertEqual(rows[1].vendor, 'Kathmandu Apparel')
            self.assertEqual(rows[1].actor_name, 'stock-admin@example.com')
            self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 13)
        page = self.client.get('/admin/inventory')
        self.assertEqual(page.status_code, 200)
        self.assertIn('INV-001', page.text)
        self.assertIn('Stock movement details', page.text)

    def test_invalid_movements_are_atomic_and_routes_are_protected(self):
        for data in [dict(quantity=0), dict(quantity=-2), dict(quantity='1.5'), dict(vendor=''),
                     dict(reason='unknown'), dict(reason='Damaged stock', quantity=11), dict(notes='x' * 1001)]:
            with self.subTest(data=data):
                self.assertEqual(self.movement(**data).status_code, 400)
        self.assertEqual(self.movement(product_id=999999).status_code, 404)
        self.assertEqual(self.movement(csrf_token='wrong').status_code, 400)
        with TestClient(main.app) as other:
            token = re.search(r'name="csrf_token"\s+value="([^"]+)"', other.get('/admin/login').text).group(1)
            response = other.post('/admin/inventory/movements', data=dict(csrf_token=token))
            self.assertEqual(response.status_code, 403)
        with self.sessions() as db:
            self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 10)
            self.assertEqual(db.query(main.StockMovement).filter_by(product_id=self.product_id).count(), 1)

    def test_daily_weekly_monthly_reports_and_product_filter(self):
        with self.sessions() as db:
            db.add_all([
                main.StockMovement(product_id=self.product_id, product_name='Movement shirt', quantity=10,
                                   balance_after=10, reason='Opening balance', created_at=datetime(2025, 12, 31)),
                main.StockMovement(product_id=self.product_id, product_name='Movement shirt', quantity=5,
                                   balance_after=15, reason='Vendor receipt', vendor='Vendor A', created_at=datetime(2026, 1, 31)),
                main.StockMovement(product_id=self.product_id, product_name='Movement shirt', quantity=-2,
                                   balance_after=13, reason='Recorded sale', created_at=datetime(2026, 2, 1)),
                main.StockMovement(product_id=self.product_id, product_name='Movement shirt', quantity=4,
                                   balance_after=17, reason='Vendor receipt', vendor='Vendor B', created_at=datetime(2026, 2, 2)),
                main.StockMovement(product_id=None, product_name='Other', quantity=99,
                                   balance_after=99, reason='Vendor receipt', vendor='Other', created_at=datetime(2026, 2, 2)),
            ])
            db.commit()
        report = self.report()
        self.assertEqual(report['movement_opening'], 10)
        self.assertEqual(report['movement_closing'], 17)
        self.assertEqual(report['movement_totals'], dict(stock_in=9, stock_out=2, vendor_in=9, opening_added=0))
        self.assertEqual(len(report['movement_rows']), 3)
        self.assertEqual(report['vendor_total'], 9)
        weekly = self.report(group='weekly')['movement_rows']
        self.assertEqual([str(row['period']) for row in weekly], ['2026-01-26', '2026-02-02'])
        self.assertEqual(weekly[0]['closing'], 13)
        monthly = self.report(group='monthly')['movement_rows']
        self.assertEqual([str(row['period']) for row in monthly], ['2026-01-01', '2026-02-01'])
        self.assertEqual(monthly[1]['closing'], 17)
        for query in ['group=bad', 'start=bad', 'start=2026-03-01&end=2026-01-01', 'movement_page=0']:
            self.assertEqual(self.client.get('/admin/inventory?' + query).status_code, 400)

    def test_opening_balance_is_idempotent_and_not_vendor_stock(self):
        main.initialize_stock_movements()
        main.initialize_stock_movements()
        with self.sessions() as db:
            self.assertEqual(db.query(main.StockMovement).filter_by(product_id=self.product_id).count(), 1)
        today = str(datetime.utcnow().date())
        report = self.report(start=today, end=today)
        self.assertEqual(report['movement_totals']['stock_in'], 0)
        self.assertEqual(report['movement_totals']['opening_added'], 10)
        self.assertEqual(report['vendor_total'], 0)

    def test_product_edit_and_delete_preserve_ledger(self):
        response = self.client.post(f'/admin/products/{self.product_id}', data=dict(
            csrf_token=self.csrf, name='Movement shirt', price='1250', category='Apparel', shop_category='Everyday',
            stock_quantity=7, is_active='on'), follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with self.sessions() as db:
            movement = db.query(main.StockMovement).filter_by(product_id=self.product_id, reason='Inventory adjustment').one()
            self.assertEqual(movement.quantity, -3)
        self.assertEqual(self.movement().status_code, 303)
        response = self.client.post(f'/admin/products/{self.product_id}/delete', data=dict(csrf_token=self.csrf), follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with self.sessions() as db:
            self.assertIsNone(db.get(main.Product, self.product_id))
            rows = db.query(main.StockMovement).filter_by(product_name='Movement shirt').all()
            self.assertTrue(all(row.product_id is None for row in rows))
            self.assertEqual(sum(row.quantity for row in rows), 0)
            self.assertEqual(sum(row.quantity for row in rows if row.reason == 'Vendor receipt'), 5)

    def test_history_pagination_does_not_truncate_totals(self):
        with self.sessions() as db:
            for index in range(55):
                db.add(main.StockMovement(product_id=self.product_id, product_name='Movement shirt',
                                         quantity=1, balance_after=11 + index, reason='Vendor receipt',
                                         vendor='Bulk vendor', created_at=datetime(2026, 2, 1)))
            db.commit()
        first = self.report()
        second = self.report(movement_page=2)
        self.assertEqual(first['movement_totals']['vendor_in'], 55)
        self.assertEqual(second['movement_totals']['vendor_in'], 55)
        self.assertEqual(len(first['movements']), 50)
        self.assertEqual(len(second['movements']), 5)
        self.assertEqual(first['movement_page_count'], 2)
        self.assertFalse({row.id for row in first['movements']} & {row.id for row in second['movements']})

    def test_database_failure_rolls_back_balance_and_movement_together(self):
        with patch.object(main, 'create_activity_log', side_effect=RuntimeError('Simulated failure')):
            with self.assertRaisesRegex(RuntimeError, 'Simulated failure'):
                self.movement()
        with self.sessions() as db:
            self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 10)
            self.assertEqual(db.query(main.StockMovement).filter_by(product_id=self.product_id).count(), 0)


if __name__ == '__main__':
    unittest.main()
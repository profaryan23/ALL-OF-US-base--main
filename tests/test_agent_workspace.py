from decimal import Decimal
import unittest

from fastapi.testclient import TestClient

import main
import test_stock_movements


class AgentWorkspaceTests(unittest.TestCase):
    token = test_stock_movements.StockMovementTests.token

    def tearDown(self):
        self.agent_client.close()
        test_stock_movements.StockMovementTests.tearDown(self)

    def setUp(self):
        test_stock_movements.StockMovementTests.setUp(self)
        with self.sessions() as db:
            user = main.User(first_name='Private', last_name='Agent', email='own-agent@example.com',
                             password_hash=main.generate_password_hash('agent-password'), role='agent')
            other = main.Agent(name='Other agent', email='other-agent@example.com')
            db.add_all([user, other])
            db.flush()
            agent = main.Agent(name='Private Agent', email=user.email, user_id=user.id)
            db.add(agent)
            db.flush()
            self.user_id, self.agent_id = user.id, agent.id
            for owner in [agent, other]:
                allocation = main.AgentAllocation(agent_id=owner.id, product_id=self.product_id, quantity=5,
                    remaining=5, list_price=Decimal('1250'), unit_cost=Decimal('1125'), company_discount_percent=10)
                db.add(allocation)
                db.flush()
                if owner.id == agent.id:
                    self.allocation_id = allocation.id
                else:
                    self.other_allocation_id = allocation.id
            db.commit()
        self.agent_client = TestClient(main.app)
        token = self.agent_token('/login')
        response = self.agent_client.post('/login', data=dict(csrf_token=token, email='own-agent@example.com',
                                                              password='agent-password'), follow_redirects=False)
        self.assertEqual(response.headers['location'], '/agent/dashboard')
        self.agent_csrf = self.agent_token('/agent/profile')

    def agent_token(self, path):
        import re
        response = self.agent_client.get(path)
        self.assertEqual(response.status_code, 200)
        return re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text).group(1)

    def sale(self, **overrides):
        data = dict(csrf_token=self.agent_csrf, allocation_id=self.allocation_id, quantity=2, price='1450.50',
                    name='Own Customer', phone='9812345678', email='own-customer@example.com', address='Kathmandu')
        data.update(overrides)
        return self.agent_client.post('/agent/sales/record', data=data, follow_redirects=False)

    def test_agent_scoping_and_read_only_inventory(self):
        self.assertEqual(self.sale().status_code, 303)
        with self.sessions() as db:
            other_id = db.get(main.AgentAllocation, self.other_allocation_id).agent_id
            customer = main.User(first_name='Hidden', last_name='Customer', email='hidden-customer@example.com',
                                 password_hash=main.generate_password_hash('customer-password'), role='customer')
            db.add(customer)
            db.flush()
            db.add(main.Order(user_id=customer.id, agent_id=other_id, total_amount=Decimal('9999.00')))
            db.commit()
        for module in ['dashboard', 'crm', 'sales', 'reports']:
            response = self.agent_client.get('/agent/' + module + '?agent_id=999')
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('Other agent', response.text)
            self.assertNotIn('hidden-customer@example.com', response.text)
            self.assertNotIn('9999.00', response.text)
        self.assertIn('1450.50', self.agent_client.get('/agent/sales').text)
        self.assertIn('Own Customer', self.agent_client.get('/agent/crm').text)
        for path in ['/admin/crm', '/admin/inventory', '/admin/sales', '/admin/rbac', '/admin/agents']:
            self.assertEqual(self.agent_client.get(path).status_code, 403)
        response = self.agent_client.post(f'/admin/products/{self.product_id}/delete', data=dict(csrf_token=self.agent_csrf))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.sale(allocation_id=self.other_allocation_id).status_code, 404)
        self.assertEqual(self.sale(quantity=99).status_code, 400)
        self.assertEqual(self.sale(csrf_token='wrong').status_code, 400)
        with self.sessions() as db:
            order = db.query(main.Order).filter_by(agent_id=self.agent_id).one()
            self.assertEqual(order.total_amount, Decimal('2901.00'))
            self.assertEqual(db.get(main.AgentAllocation, self.allocation_id).remaining, 3)
            self.assertEqual(db.get(main.Product, self.product_id).stock_quantity, 10)
        self.assertIn('Own Customer', self.client.get('/admin/crm').text)
        self.assertIn('1450.50', self.client.get('/admin/sales').text)

    def test_profile_picture_email_details_and_stable_agent_link(self):
        response = self.agent_client.post('/agent/profile', data=dict(csrf_token=self.agent_csrf,
            first_name='Updated', last_name='Agent', email='updated-agent@example.com', phone='9801234567',
            current_password='agent-password', address='Pokhara', bio='Regional sales'),
            files={'profile_image': ('avatar.png', b'\x89PNG\r\n\x1a\nprofile', 'image/png')})
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            user = db.get(main.User, self.user_id)
            agent = db.get(main.Agent, self.agent_id)
            self.assertEqual(agent.user_id, user.id)
            self.assertEqual(agent.email, 'updated-agent@example.com')
            self.assertEqual(user.bio, 'Regional sales')
            self.assertEqual(user.address, 'Pokhara')
            self.assertEqual(self.agent_client.get('/static/' + user.profile_image).status_code, 200)
        self.assertEqual(self.agent_client.get('/agent/sales').status_code, 200)
        response = self.agent_client.post('/agent/profile', data=dict(csrf_token=self.agent_csrf,
            email='stolen@example.com', first_name='Updated', last_name='Agent'))
        self.assertEqual(response.status_code, 400)

    def test_admin_can_reset_credentials_revoke_sessions_and_remove_access(self):
        self.sale()
        response = self.client.post(f'/admin/users/{self.user_id}/update', data=dict(csrf_token=self.csrf,
            first_name='Managed', last_name='Agent', email='managed@example.com', phone='9801111111',
            password='replacement-password', is_active='on'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.agent_client.get('/agent/crm', follow_redirects=False).status_code, 303)
        token = self.agent_token('/login')
        response = self.agent_client.post('/login', data=dict(csrf_token=token, email='managed@example.com', password='replacement-password'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.agent_client.get('/agent/crm').status_code, 200)
        response = self.client.post(f'/admin/users/{self.user_id}/delete', data=dict(csrf_token=self.csrf))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.agent_client.get('/agent/sales', follow_redirects=False).status_code, 303)
        with self.sessions() as db:
            self.assertFalse(db.get(main.User, self.user_id).is_active)
            self.assertFalse(db.get(main.Agent, self.agent_id).is_active)
            self.assertEqual(db.query(main.Order).filter_by(agent_id=self.agent_id).count(), 1)

    def test_navigation_placement_and_admin_profile(self):
        html = self.client.get('/admin/rbac').text
        studio = html.split('aria-label="Studio Back-Office Modules"')[1].split('</nav>')[0]
        access = html.split('aria-label="Access management"')[1].split('</nav>')[0]
        self.assertIn('Agents', studio)
        self.assertNotIn('Agents', access)
        self.assertIn('RBACM', access)
        self.assertIn('Edit profile & picture', html)
        response = self.client.post('/admin/profile', data=dict(csrf_token=self.csrf,
            first_name='Studio', last_name='Admin', phone='9800000000', bio='Store manager', address='Kathmandu'),
            files={'profile_image': ('admin.png', b'\x89PNG\r\n\x1a\nadmin', 'image/png')})
        self.assertEqual(response.status_code, 200)
        html = self.client.get('/admin').text
        self.assertIn('/static/product-images/', html)

    def test_legacy_agent_link_migrates_once(self):
        with self.sessions() as db:
            db.get(main.Agent, self.agent_id).user_id = None
            db.commit()
        main.link_agent_accounts()
        main.link_agent_accounts()
        with self.sessions() as db:
            self.assertEqual(db.get(main.Agent, self.agent_id).user_id, self.user_id)

    def test_role_specific_profiles_and_agent_modules(self):
        for client, destination in [(self.client, '/admin/profile'), (self.agent_client, '/agent/profile')]:
            response = client.get('/account/profile', follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertTrue(response.headers['location'].endswith(destination))
            html = client.get(destination).text
            self.assertIn('admin-sidebar', html)
            self.assertIn(f'action="http://testserver{destination}"', html)
        self.assertEqual(self.agent_client.get('/admin/profile').status_code, 403)
        self.assertEqual(self.client.get('/agent/profile').status_code, 403)
        self.assertEqual(self.agent_client.get('/agent/inventory').status_code, 404)
        self.assertEqual(self.agent_client.get('/agent', follow_redirects=False).headers['location'], '/agent/dashboard')
        html = self.agent_client.get('/agent/dashboard').text
        nav = html.split('aria-label="Agent modules"')[1].split('</nav>')[0]
        for label in ['Dashboard', 'Sales', 'CRM', 'Reports']:
            self.assertIn(label, nav)
        for label in ['Inventory', 'RBAC', 'Accounts', 'Content']:
            self.assertNotIn(label, nav)
        self.assertIn('aria-label="Public Store Links"', html)
        with self.sessions() as db:
            db.add(main.User(first_name='Web', last_name='Customer', email='profile-customer@example.com',
                            password_hash=main.generate_password_hash('customer-password'), role='customer'))
            db.commit()
        with TestClient(main.app) as customer:
            import re
            token = re.search(r'name="csrf_token"\s+value="([^"]+)"', customer.get('/login').text).group(1)
            customer.post('/login', data=dict(csrf_token=token, email='profile-customer@example.com', password='customer-password'))
            html = customer.get('/account/profile').text
            self.assertIn('action="http://testserver/account/profile"', html)
            self.assertNotIn('admin-sidebar', html)
            self.assertEqual(customer.get('/admin/profile').status_code, 403)
            self.assertEqual(customer.get('/agent/dashboard').status_code, 403)

    def test_profile_validation_and_account_management_permissions(self):
        response = self.agent_client.post('/agent/profile', data=dict(csrf_token=self.agent_csrf,
            first_name='Private', last_name='Agent'), files={'profile_image': ('bad.png', b'not an image', 'image/png')})
        self.assertEqual(response.status_code, 400)
        for action in ['update', 'delete']:
            response = self.agent_client.post(f'/admin/users/{self.user_id}/{action}', data=dict(csrf_token=self.agent_csrf))
            self.assertEqual(response.status_code, 403)
        with self.sessions() as db:
            admin = db.query(main.User).filter_by(email='stock-admin@example.com').one()
            admin_id = admin.id
        response = self.client.post(f'/admin/users/{admin_id}/update', data=dict(csrf_token=self.csrf))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(f'/admin/users/{self.user_id}/update', data=dict(csrf_token='wrong'))
        self.assertEqual(response.status_code, 400)

import unittest

from fastapi.testclient import TestClient

import main


class SiteAnnouncementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.Base.metadata.create_all(main.engine)
        main.migrate_page_content()
        main.seed_database()

    def setUp(self):
        with main.SessionLocal() as db:
            self.originals = {
                page.page_key: page.site_announcement
                for page in db.query(main.PageContent).all()
            }

    def tearDown(self):
        with main.SessionLocal() as db:
            for page in db.query(main.PageContent).all():
                page.site_announcement = self.originals[page.page_key]
            db.commit()

    def test_defaults_leave_announcement_empty(self):
        for content in main.PAGE_DEFAULTS.values():
            self.assertEqual(content['site_announcement'], '')

    def test_seed_removes_only_legacy_promotion(self):
        with main.SessionLocal() as db:
            db.query(main.PageContent).filter_by(page_key='home').first().site_announcement = main.LEGACY_SITE_ANNOUNCEMENT
            db.query(main.PageContent).filter_by(page_key='shop').first().site_announcement = 'ALL OF US — Together, every day.'
            db.commit()
        main.seed_database()
        main.seed_database()
        with main.SessionLocal() as db:
            self.assertEqual(db.query(main.PageContent).filter_by(page_key='home').first().site_announcement, '')
            self.assertEqual(db.query(main.PageContent).filter_by(page_key='shop').first().site_announcement, 'ALL OF US — Together, every day.')

    def test_empty_banner_hidden_and_future_slogan_visible(self):
        with main.SessionLocal() as db:
            db.query(main.PageContent).filter_by(page_key='home').first().site_announcement = ''
            db.commit()
        with TestClient(main.app) as client:
            html = client.get('/').text
            self.assertNotIn('class="announcement"', html)
            self.assertNotIn(main.LEGACY_SITE_ANNOUNCEMENT, html)
            with main.SessionLocal() as db:
                db.query(main.PageContent).filter_by(page_key='home').first().site_announcement = 'ALL OF US, together.'
                db.commit()
            html = client.get('/').text
            self.assertIn('class="announcement"', html)
            self.assertIn('ALL OF US, together.', html)
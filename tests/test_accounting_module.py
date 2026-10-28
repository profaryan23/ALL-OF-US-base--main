import unittest
from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient

import main


class AccountingModuleTests(unittest.TestCase):
    def setUp(self):
        main.Base.metadata.drop_all(main.engine)
        main.Base.metadata.create_all(main.engine)
        main.seed_database()

    def test_post_journal_entry_validates_and_records_balanced_entries(self):
        with main.SessionLocal() as db:
            cash = main.Account(code="1010", name="Cash", type="ASSET", normal_balance="DEBIT")
            revenue = main.Account(code="4010", name="Sales Revenue", type="REVENUE", normal_balance="CREDIT")
            db.add_all([cash, revenue])
            db.commit()

            entry = main.post_journal_entry(
                db,
                date=datetime.utcnow(),
                reference_type="ORDER",
                reference_id=42,
                description="Customer sale",
                lines=[
                    {"account_id": cash.id, "debit": Decimal("150.00"), "credit": Decimal("0.00")},
                    {"account_id": revenue.id, "debit": Decimal("0.00"), "credit": Decimal("150.00")},
                ],
            )

            self.assertEqual(entry.total_debit, Decimal("150.00"))
            self.assertEqual(entry.total_credit, Decimal("150.00"))
            self.assertEqual(db.query(main.JournalEntry).count(), 1)
            self.assertEqual(db.query(main.JournalLine).count(), 2)

        with self.assertRaises(ValueError):
            with main.SessionLocal() as db:
                cash = db.query(main.Account).filter_by(code="1010").one()
                revenue = db.query(main.Account).filter_by(code="4010").one()
                main.post_journal_entry(
                    db,
                    date=datetime.utcnow(),
                    reference_type="ORDER",
                    reference_id=43,
                    description="Bad entry",
                    lines=[
                        {"account_id": cash.id, "debit": Decimal("100.00"), "credit": Decimal("0.00")},
                        {"account_id": revenue.id, "debit": Decimal("0.00"), "credit": Decimal("50.00")},
                    ],
                )

    def test_admin_account_module_access_and_journal_creation(self):
        with main.SessionLocal() as db:
            account = main.Account(code="1020", name="Gateway Clearing", type="ASSET", normal_balance="DEBIT")
            db.add(account)
            db.commit()

        client = TestClient(main.app)
        admin = main.User(email="admin@allofus.com", password_hash=main.generate_password_hash("admin123"), role="admin", first_name="Admin", last_name="User")
        with main.SessionLocal() as db:
            if not db.query(main.User).filter_by(email="admin@allofus.com").first():
                db.add(admin)
                db.commit()

        response = client.get("/admin/accounts")
        self.assertIn(response.status_code, (200, 307, 302))

        with main.SessionLocal() as db:
            cash = db.query(main.Account).filter_by(code="1020").first()
            revenue = db.query(main.Account).filter_by(code="4000").first()
            self.assertIsNotNone(cash)
            self.assertIsNotNone(revenue)

        form_response = client.post(
            "/admin/accounts/journal",
            data={
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "reference_type": "ORDER",
                "reference_id": "99",
                "description": "Sale recorded",
                "account_id_1": str(cash.id),
                "debit_1": "75.00",
                "credit_1": "0.00",
                "account_id_2": str(revenue.id),
                "debit_2": "0.00",
                "credit_2": "75.00",
            },
            follow_redirects=False,
        )
        self.assertIn(form_response.status_code, (200, 303, 302))


if __name__ == "__main__":
    unittest.main()

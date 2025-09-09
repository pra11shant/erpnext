import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch
from erpnext.accounts.report.billed_items_to_be_received import billed_items_to_be_received as report


class TestBilledItemsToBeReceived(FrappeTestCase):
    def test_execute_triggers_all(self):
        filters = {
            "company": "Test Co",
            "posting_date": "2024-12-31",
            "purchase_invoice": "PINV-0001"
        }

        fake_row = {
            "name": "PINV-0001",
            "supplier": "SUP-1",
            "company": "Test Co",
            "posting_date": "2024-12-01",
            "currency": "INR",
            "item_code": "ITEM-1",
            "item_name": "Test Item",
            "uom": "Nos",
            "qty": 5,
            "received_qty": 2,
            "rate": 100,
            "amount": 500,
        }

        with patch(
            "erpnext.accounts.report.billed_items_to_be_received.billed_items_to_be_received.frappe.get_all",
            return_value=[fake_row]
        ) as mock_get_all:
            columns, data = report.execute(filters)

            # frappe.get_all should be called with fields + filters
            args, kwargs = mock_get_all.call_args
            self.assertEqual(args[0], "Purchase Invoice")
            self.assertIn("fields", kwargs)
            self.assertIn("filters", kwargs)

            # columns should include expected keys
            labels = [col["label"] for col in columns]
            self.assertIn("Purchase Invoice", labels)
            self.assertIn("Supplier", labels)
            self.assertIn("Amount", labels)

            # data should be the mocked row
            self.assertEqual(data[0]["name"], "PINV-0001")

    def test_execute_without_purchase_invoice(self):
        filters = {
            "company": "Test Co",
            "posting_date": "2024-12-31",
        }
        with patch(
            "erpnext.accounts.report.billed_items_to_be_received.billed_items_to_be_received.frappe.get_all",
            return_value=[]
        ):
            cols, data = report.execute(filters)
            self.assertIsInstance(cols, list)
            self.assertEqual(data, [])

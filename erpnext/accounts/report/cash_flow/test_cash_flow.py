import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch
from datetime import date
from erpnext.accounts.report.cash_flow import cash_flow


class TestCashFlow(FrappeTestCase):
    def test_execute_full_paths(self):
        filters = frappe._dict({
            "company": "_Test Company",
            "from_date": "2024-01-01",
            "to_date": "2024-12-31",
            "periodicity": "Monthly",
            "from_fiscal_year": "2024",
            "to_fiscal_year": "2024",
        })

        fake_period_list = [
            frappe._dict({
                "key": "2024-01",
                "from_date": date(2024, 1, 1),
                "to_date": date(2024, 1, 31),
                "year_start_date": date(2024, 1, 1),
                "year_end_date": date(2024, 12, 31),
            })
        ]

        with patch("erpnext.accounts.report.cash_flow.cash_flow.get_period_list", return_value=fake_period_list):
            result = cash_flow.execute(filters)

        # --- Handle ERPNext execute() return signatures ---
        cols = data = chart = summary = message = None

        if isinstance(result, tuple):
            if len(result) == 2:
                cols, data = result
            elif len(result) == 4:
                cols, data, chart, summary = result
            elif len(result) == 5:
                cols, data, message, chart, summary = result
            else:
                self.fail(f"Unexpected execute() return length: {len(result)}")
        else:
            cols, data = [], result

        # --- Assertions ---
        self.assertIsInstance(cols, list)
        self.assertIsInstance(data, list)
        if chart:
            self.assertIsInstance(chart, dict)
        if summary:
            self.assertIsInstance(summary, list)
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe import _dict
from unittest.mock import patch, MagicMock
from erpnext.accounts.report.open_item import open_item


class TestOpenItem(FrappeTestCase):
    def get_filters(self):
        return _dict({
            "company": "Test Co",
            "from_date": "2024-01-01",
            "to_date": "2024-12-31",
        })

    # ---------------- execute ----------------
    def test_execute_without_filters(self):
        cols, res = open_item.execute(None)
        self.assertEqual(cols, [])
        self.assertEqual(res, [])

    def test_execute_with_account_currency(self):
        f = self.get_filters()
        f.print_in_account_currency = 1
        f.account = None
        with self.assertRaises(Exception):
            open_item.execute(f)

    # ---------------- validate_filters ----------------
    def test_validate_filters_variants(self):
        # company missing
        with self.assertRaises(Exception):
            open_item.validate_filters(_dict({}), {})

        # invalid account -> stringified list
        f = self.get_filters()
        f.account = '["NonExisting"]'
        with self.assertRaises(Exception):
            open_item.validate_filters(f, {})

        # child account with group by
        f = self.get_filters()
        f.account = '["Acc1"]'
        f.group_by = "Group by Account"
        with self.assertRaises(Exception):
            open_item.validate_filters(f, {"Acc1": _dict(is_group=0)})

        # voucher conflict
        f = self.get_filters()
        f.voucher_no = "VN1"
        f.group_by = "Group by Voucher"
        with self.assertRaises(Exception):
            open_item.validate_filters(f, {})

        # invalid date range
        f = self.get_filters()
        f.from_date = "2025-01-01"
        f.to_date = "2024-01-01"
        with self.assertRaises(Exception):
            open_item.validate_filters(f, {})

        # valid project & cost_center
        f = self.get_filters()
        f.project = '["P1"]'
        f.cost_center = '["CC1"]'
        open_item.validate_filters(f, {})

    # ---------------- validate_party ----------------
    def test_validate_party_variants(self):
        f = self.get_filters()
        f.party_type = "Customer"
        f.party = ["X1"]

        frappe.db.exists = MagicMock(return_value=False)
        with self.assertRaises(Exception):
            open_item.validate_party(f)

        frappe.db.exists = MagicMock(return_value=True)
        open_item.validate_party(f)

    # ---------------- set_account_currency ----------------
    def test_set_account_currency_variants(self):
        # multiple accounts same currency
        f = self.get_filters()
        f.account = ["A1", "A2"]
        with patch("erpnext.accounts.report.open_item.open_item.get_account_currency", return_value="USD"):
            with patch("frappe.get_cached_value", return_value="INR"):
                res = open_item.set_account_currency(f)
                self.assertIn("account_currency", res)

        # party_type branch
        f = self.get_filters()
        f.party = ["C1"]
        f.party_type = "Customer"
        with patch("frappe.get_cached_value", return_value="INR"):
            with patch("frappe.db.get_value", return_value=None):
                res = open_item.set_account_currency(f)
                self.assertIn("account_currency", res)

    # ---------------- unreconciled totals ----------------
    def test_get_unreconciled_reconciled_totals(self):
        gle = [
            {"is_reconciled": 1, "credit": 1, "credit_in_account_currency": 10, "debit": 1, "debit_in_account_currency": 5},
            {"is_reconciled": 0, "credit": 1, "credit_in_account_currency": 2, "debit": 1, "debit_in_account_currency": 3},
        ]
        res = open_item.get_unreconciled_reconciled_totals(gle)
        self.assertEqual(res[0]["credit"], 10)
        self.assertEqual(res[1]["debit"], 3)

        r1 = _dict(is_reconciled=1, credit=1, debit=1, credit_in_account_currency=5, debit_in_account_currency=4)
        r2 = _dict(is_reconciled=0, credit=1, debit=1, credit_in_account_currency=2, debit_in_account_currency=1)
        rr1 = open_item.get_unreconciled_reconciled_totals_other(r1)
        rr2 = open_item.get_unreconciled_reconciled_totals_other(r2)
        self.assertEqual(rr1[0]["credit"], 5)
        self.assertEqual(rr2[1]["credit"], 2)

    # ---------------- get_conditions ----------------
    def test_get_conditions_and_gl_entries(self):
        f = self.get_filters()
        f.account = "Acc1,Acc2"
        f.cost_center = ["CC1"]
        f.voucher_no, f.against_voucher_no = "VN1", "AV1"
        f.ignore_err = 1
        f.voucher_no_not_in = ["X1"]
        f.group_by, f.party, f.party_type = "Group by Party", ["C1"], "Customer"
        f.show_unreconciled_entries, f.show_reconciled_entries = 1, 1
        f.finance_book, f.company_fb = "FB1", "CFB1"
        f.include_default_book_entries = 0
        f.include_dimensions = 1
        f.add_values_in_transaction_currency = 1
        f.show_remarks = 1
        f.presentation_currency = "USD"

        fake_gl_row = {
            "name": "GL1",
            "posting_date": "2024-06-01",
            "account": "Acc1",
            "debit": 100,
            "credit": 0,
            "remarks": "ok",
        }

        with patch("erpnext.accounts.report.open_item.open_item.get_accounts_with_children", return_value=["Acc1", "Acc2"]), \
            patch("erpnext.accounts.report.open_item.open_item.get_cost_centers_with_children", return_value=["CC1"]), \
            patch("erpnext.accounts.report.open_item.open_item.get_accounting_dimensions",
                return_value=[_dict(fieldname="dim1", disabled=0, document_type="Cost Center")]), \
            patch("frappe.db.get_all", return_value=[["JV-1"]]), \
            patch("frappe.db.get_value", return_value="INR"), \
            patch("frappe.get_cached_value", return_value=0), \
            patch("frappe.desk.reportview.build_match_conditions", return_value="(company='Test Co')"), \
            patch("erpnext.accounts.report.open_item.open_item.convert_to_presentation_currency",
                side_effect=lambda f, rows: rows), \
            patch("frappe.db.get_single_value", side_effect=[500, None]), \
            patch("frappe.db.sql", side_effect=[
                [fake_gl_row],                  # first call → gl_entries
                [{"remarks": "X"*600}],         # second call → remarks (long string truncated)
                [{"remarks": "ok"}],            # third call → remarks ok
                []                              # fourth call → tax rows empty
            ]):

            cond = open_item.get_conditions(f, 0)
            self.assertIn("account", cond)

            rows = open_item.get_gl_entries(
                f, accounting_dimensions=["dim1"]
            )
            self.assertIsInstance(rows, dict)
        

    # ---------------- group_by_field, balance, columns ----------------
    def test_group_by_field_balance_columns(self):
        self.assertEqual(open_item.group_by_field("Group by Party"), "party")
        self.assertEqual(open_item.group_by_field("Group by Account"), "account")
        self.assertEqual(open_item.group_by_field("X"), "voucher_no")

        bal = open_item.get_balance({"debit": 5, "credit": 2}, 0, "debit", "credit")
        self.assertEqual(bal, 3)

        f = self.get_filters()
        f.add_values_in_transaction_currency = 1
        f.include_dimensions = 0
        f.show_remarks = 1
        with patch("erpnext.accounts.report.open_item.open_item.get_company_currency", return_value="USD"):
            cols = open_item.get_columns(f)
            self.assertTrue(any("Debit (Transaction)" in c.get("label", "") for c in cols))
            self.assertTrue(any("Remarks" in c.get("label", "") for c in cols))
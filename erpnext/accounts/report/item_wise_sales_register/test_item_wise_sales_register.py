import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, today

from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.accounts.report.item_wise_sales_register.item_wise_sales_register import execute
from erpnext.accounts.report.item_wise_sales_register import item_wise_sales_register as report # < = Cange
from unittest.mock import patch # < = Cange
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin


class TestItemWiseSalesRegister(AccountsTestMixin, FrappeTestCase):
	def setUp(self):
		self.create_company()
		self.create_customer()
		self.create_item()
		self.clear_old_entries()

	def tearDown(self):
		frappe.db.rollback()

	def create_sales_invoice(self, do_not_submit=False):
		si = create_sales_invoice(
			item=self.item,
			company=self.company,
			customer=self.customer,
			debit_to=self.debit_to,
			posting_date=today(),
			parent_cost_center=self.cost_center,
			cost_center=self.cost_center,
			rate=100,
			price_list_rate=100,
			do_not_save=1,
		)
		si = si.save()
		if not do_not_submit:
			si = si.submit()
		return si

	def test_basic_report_output(self):
		si = self.create_sales_invoice()

		filters = frappe._dict({"from_date": today(), "to_date": today(), "company": self.company})
		report = execute(filters)

		self.assertEqual(len(report[1]), 1)

		expected_result = {
			"item_code": si.items[0].item_code,
			"invoice": si.name,
			"posting_date": getdate(),
			"customer": si.customer,
			"debit_to": si.debit_to,
			"company": self.company,
			"income_account": si.items[0].income_account,
			"stock_qty": 1.0,
			"stock_uom": si.items[0].stock_uom,
			"rate": 100.0,
			"amount": 100.0,
			"total_tax": 18.0,
			"total_other_charges": 0,
			"total": 118.0,
			"currency": "INR",
		}

		report_output = {k: v for k, v in report[1][0].items() if k in expected_result}
		self.assertDictEqual(report_output, expected_result)

	def test_group_by_item_flow(self):
		"""Covers: group_by, add_total_row, add_sub_total_row, get_display_value, get_group_by_and_display_fields"""
		# Create an invoice to ensure data exists
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		si = create_sales_invoice(
			item=frappe.get_doc("Item", {"item_code": "Test Item"}),  # fallback item
			company=self.company,
			customer=self.customer,
			debit_to="Debtors - _TC",
			posting_date=today(),
			rate=100,
			do_not_save=0,
		)
		si.submit()

		filters = frappe._dict({
			"from_date": today(),
			"to_date": today(),
			"company": si.company,
			"group_by": "Item"
		})
		columns, data, *_ = report.execute(filters)

		assert isinstance(data, list) and len(data) > 0
		assert any(isinstance(row, dict) and "Total" in str(row.values()) for row in data)

	def test_apply_conditions_filters(self):
		"""Covers: mode_of_payment, warehouse, brand, item_code, item_group, income_account, additional_conditions"""
		si = frappe.qb.DocType("Sales Invoice")
		sii = frappe.qb.DocType("Sales Invoice Item")

		class DummyQuery:
			def __init__(self): self.where_clauses = []
			def where(self, cond): self.where_clauses.append(str(cond)); return self

		query = DummyQuery()
		filters = frappe._dict({
			"mode_of_payment": "Cash",
			"warehouse": "Main Warehouse",
			"brand": "Nike",
			"item_code": "ITEM-001",
			"item_group": "All Item Groups",
			"income_account": "Sales - T",
		})
		additional_conditions = {"remarks": "Test"}

		with patch("frappe.db.get_all") as mock_get_all, patch("frappe.db.get_value") as mock_get_value:
			mock_get_all.side_effect = lambda *a, **k: ["INV-001"] if "Sales Invoice Payment" in a else []
			mock_get_value.return_value = None

			q = report.apply_conditions(query, si, sii, filters, additional_conditions)

		clause_text = " ".join(q.where_clauses)
		assert len(q.where_clauses) >= 5

	def test_apply_order_by_conditions_variants(self):
		"""Covers: different group_by order clauses"""
		si = frappe.qb.DocType("Sales Invoice")
		sii = frappe.qb.DocType("Sales Invoice Item")
		base_query = "select * from tabSalesInvoice"

		assert "posting_date" in report.apply_order_by_conditions(base_query, si, sii, frappe._dict())
		assert "parent" in report.apply_order_by_conditions(base_query, si, sii, frappe._dict({"group_by": "Invoice"}))
		assert "item_code" in report.apply_order_by_conditions(base_query, si, sii, frappe._dict({"group_by": "Item"}))
		assert "item_group" in report.apply_order_by_conditions(base_query, si, sii, frappe._dict({"group_by": "Item Group"}))
		assert "customer" in report.apply_order_by_conditions(base_query, si, sii, frappe._dict({"group_by": "Customer"}))

	def test_get_display_value_variants(self):
		"""Covers: Item, Customer, Supplier branches"""
		item = {"item_code": "ITM-1", "item_name": "Item 1"}
		assert "ITM-1" in report.get_display_value({"group_by": "Item"}, "item_code", item)

		cust_item = {"customer": "CUST-1", "customer_name": "Customer 1"}
		assert "Customer 1" in report.get_display_value({"group_by": "Customer"}, "customer", cust_item)

		supp_item = {"supplier": "SUP-1", "supplier_name": "Supplier 1"}
		assert "Supplier 1" in report.get_display_value({"group_by": "Supplier"}, "supplier", supp_item)

	def test_get_group_by_and_display_fields(self):
		"""Covers: Item, Invoice, generic group_by"""
		assert report.get_group_by_and_display_fields({"group_by": "Item"}) == ("item_code", "invoice")
		assert report.get_group_by_and_display_fields({"group_by": "Invoice"}) == ("parent", "item_code")
		assert report.get_group_by_and_display_fields({"group_by": "Customer"}) == ("customer", "item_code")

	def test_add_sub_total_row_accumulates(self):
		"""Covers: add_sub_total_row calculations"""
		total_row_map = {"grp": {"stock_qty": 0, "amount": 0, "total_tax": 0, "total": 0, "percent_gt": 0}}
		row = {"stock_qty": 2, "amount": 100, "total_tax": 10, "total": 110, "percent_gt": 20, "vat_amount": 5}
		report.add_sub_total_row(row, total_row_map, "grp", ["VAT"])
		assert total_row_map["grp"]["stock_qty"] == 2
		assert total_row_map["grp"]["total_tax"] == 10

	def test_apply_order_by_conditions_all_branches(self):
		si = frappe.qb.DocType("Sales Invoice")
		sii = frappe.qb.DocType("Sales Invoice Item")
		base = "select * from tabSalesInvoice"

		q1 = report.apply_order_by_conditions(base, si, sii, {})
		assert "posting_date" in q1

		q2 = report.apply_order_by_conditions(base, si, sii, {"group_by": "Invoice"})
		assert "parent" in q2

		q3 = report.apply_order_by_conditions(base, si, sii, {"group_by": "Item"})
		assert "item_code" in q3

		q4 = report.apply_order_by_conditions(base, si, sii, {"group_by": "Item Group"})
		assert "item_group" in q4

		q5 = report.apply_order_by_conditions(base, si, sii, {"group_by": "Customer"})
		assert "customer" in q5

	def test_get_display_value_else_branch(self):
		# Covers "else" branch (not Item, Customer, Supplier)
		item = {"territory": "India"}
		val = report.get_display_value({"group_by": "Territory"}, "territory", item)
		assert val == "India"

	def test_get_group_by_and_display_fields_else_branch(self):
		group_by_field, subtotal_display_field = report.get_group_by_and_display_fields({"group_by": "Territory"})
		assert group_by_field == "territory"
		assert subtotal_display_field == "item_code"
	
	def test_get_grand_total_runs(self):
		from unittest.mock import patch
		filters = {"from_date": today(), "to_date": today()}

		with patch("frappe.db.sql", return_value=[[123]]):
			val = report.get_grand_total(filters, "Sales Invoice")
			assert val == 123.0
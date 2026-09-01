"""Tests for the Timesheet guardrails.

Run with:  bench --site <site> run-tests --app itchamps_timesheet
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate


def make_timesheet(employee, project, entries):
	"""entries is a list of (date, hours) tuples."""
	doc = frappe.new_doc("Timesheet")
	doc.employee = employee
	doc.parent_project = project
	for day, hours in entries:
		doc.append(
			"time_logs",
			{
				"custom_from_date": day,
				"custom_to_date": day,
				"hours": hours,
				"project": project,
				"activity_type": "Execution",
			},
		)
	return doc


class TestTimesheetRules(FrappeTestCase):
	def setUp(self):
		self.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		self.project = frappe.db.get_value("Project", {}, "name")
		self.today = nowdate()

	def test_row_spanning_multiple_days_is_rejected(self):
		doc = make_timesheet(self.employee, self.project, [(self.today, 4)])
		doc.time_logs[0].custom_to_date = add_days(self.today, 4)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_zero_hours_is_rejected(self):
		doc = make_timesheet(self.employee, self.project, [(self.today, 0)])
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_single_document_over_twelve_hours_is_rejected(self):
		doc = make_timesheet(self.employee, self.project, [(self.today, 8), (self.today, 5)])
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_twelve_hours_across_two_timesheets_is_rejected(self):
		first = make_timesheet(self.employee, self.project, [(self.today, 8)])
		first.insert()
		first.submit()

		second = make_timesheet(self.employee, self.project, [(self.today, 5)])
		second.insert()
		self.assertRaises(frappe.ValidationError, second.submit)

	def test_rows_do_not_overlap_across_timesheets(self):
		first = make_timesheet(self.employee, self.project, [(self.today, 4)])
		first.insert()
		first.submit()

		second = make_timesheet(self.employee, self.project, [(self.today, 4)])
		second.insert()
		# first occupies 09:00 to 13:00, second should start at 13:00
		self.assertEqual(str(second.time_logs[0].from_time)[11:16], "13:00")

	def test_amendment_is_blocked(self):
		doc = make_timesheet(self.employee, self.project, [(self.today, 4)])
		doc.insert()
		doc.submit()
		doc.cancel()

		amended = frappe.copy_doc(doc)
		amended.amended_from = doc.name
		self.assertRaises(frappe.ValidationError, amended.insert)

	def test_total_hours_is_computed_server_side(self):
		doc = make_timesheet(self.employee, self.project, [(self.today, 4), (add_days(self.today, 1), 3)])
		doc.total_hours = 999
		doc.insert()
		self.assertEqual(doc.total_hours, 7)

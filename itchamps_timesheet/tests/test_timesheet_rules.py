"""Tests for the Timesheet guardrails.

Run with:  bench --site <site> run-tests --app itchamps_timesheet
"""

from unittest.mock import patch

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


class TestGuardrailSettings(FrappeTestCase):
	def setUp(self):
		self.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		self.project = frappe.db.get_value("Project", {}, "name")
		self.today = nowdate()
		self.settings = frappe.get_single("Timesheet Guardrail Settings")

	def tearDown(self):
		self.settings.bypass_until = None
		self.settings.bypass_reason = None
		self.settings.enforce_from_date = None
		self.settings.enforce_daily_limit = 1
		self.settings.max_daily_hours = 12
		self.settings.save(ignore_permissions=True)

	def set(self, **kwargs):
		self.settings.update(kwargs)
		self.settings.save(ignore_permissions=True)

	def test_daily_limit_can_be_switched_off(self):
		self.set(enforce_daily_limit=0)
		doc = make_timesheet(self.employee, self.project, [(self.today, 8), (self.today, 8)])
		doc.insert()
		self.assertEqual(doc.total_hours, 16)

	def test_raising_the_cap_admits_more_hours(self):
		self.set(max_daily_hours=16)
		doc = make_timesheet(self.employee, self.project, [(self.today, 8), (self.today, 8)])
		doc.insert()
		self.assertEqual(doc.total_hours, 16)

	def test_enforce_from_date_exempts_older_rows(self):
		self.set(enforce_from_date=add_days(self.today, 1))
		doc = make_timesheet(self.employee, self.project, [(self.today, 8), (self.today, 8)])
		doc.insert()
		self.assertEqual(doc.total_hours, 16)

	def test_enforce_from_date_still_covers_newer_rows(self):
		self.set(enforce_from_date=add_days(self.today, -30))
		doc = make_timesheet(self.employee, self.project, [(self.today, 8), (self.today, 8)])
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_expired_bypass_does_not_apply(self):
		self.set(bypass_until=add_days(nowdate(), -1), bypass_reason="test")
		doc = make_timesheet(self.employee, self.project, [(self.today, 8), (self.today, 8)])
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_bypass_window_is_capped(self):
		self.settings.bypass_until = add_days(nowdate(), 7)
		self.settings.bypass_reason = "too long"
		self.assertRaises(frappe.ValidationError, self.settings.save)


PERMISSIONS = "itchamps_timesheet.overrides.timesheet_permissions"


class TestLockedTimesheetPermissions(FrappeTestCase):
	"""Exercises the has_permission hook directly, with the role, role profile
	and reporting line lookups patched so no users have to be created."""

	def check(self, ptype, state="Approved", privileged=False, manager=False, reports_to_user=False):
		from itchamps_timesheet.overrides.timesheet_permissions import has_permission

		doc = frappe._dict(workflow_state=state, employee="EMP-1")
		with (
			patch(f"{PERMISSIONS}.is_privileged", return_value=privileged),
			patch(f"{PERMISSIONS}.is_timesheet_manager", return_value=manager),
			patch(f"{PERMISSIONS}.is_reporting_manager", return_value=reports_to_user),
		):
			return has_permission(doc, ptype, "someone@example.com")

	def test_manager_can_cancel_and_delete_direct_reports_locked_timesheets(self):
		for state in ("Approved", "Rejected"):
			for ptype in ("cancel", "delete"):
				self.assertTrue(self.check(ptype, state, manager=True, reports_to_user=True), (state, ptype))

	def test_manager_cannot_cancel_or_delete_other_teams_locked_timesheets(self):
		for ptype in ("cancel", "delete"):
			self.assertFalse(self.check(ptype, manager=True), ptype)

	def test_reporting_manager_without_profile_cannot_cancel_or_delete(self):
		for ptype in ("cancel", "delete"):
			self.assertFalse(self.check(ptype, reports_to_user=True), ptype)

	def test_manager_still_cannot_edit_or_amend_locked_timesheets(self):
		for ptype in ("write", "submit", "amend"):
			self.assertFalse(self.check(ptype, manager=True, reports_to_user=True), ptype)

	def test_other_users_cannot_cancel_or_delete_locked_timesheets(self):
		for ptype in ("cancel", "delete"):
			self.assertFalse(self.check(ptype), ptype)

	def test_system_manager_keeps_full_access(self):
		for ptype in ("write", "cancel", "delete", "amend"):
			self.assertTrue(self.check(ptype, privileged=True), ptype)


EMPLOYEES = {
	"EMP-1": {"reports_to": "EMP-2"},
	"EMP-2": {"user_id": "boss@example.com"},
	"EMP-3": {"reports_to": "EMP-4"},
	"EMP-4": {"user_id": None},
	"EMP-5": {"reports_to": None},
}


class TestIsReportingManager(FrappeTestCase):
	"""Runs is_reporting_manager against a patched Employee lookup."""

	def check(self, employee, user):
		from itchamps_timesheet.overrides.timesheet_rules import is_reporting_manager

		def get_value(doctype, name, field):
			return EMPLOYEES[name].get(field)

		with patch("frappe.db.get_value", side_effect=get_value):
			return is_reporting_manager(employee, user)

	def test_direct_manager_matches(self):
		self.assertTrue(self.check("EMP-1", "boss@example.com"))

	def test_someone_else_does_not_match(self):
		self.assertFalse(self.check("EMP-1", "other@example.com"))

	def test_manager_without_a_linked_user_matches_nobody(self):
		self.assertFalse(self.check("EMP-3", "boss@example.com"))

	def test_employee_without_a_manager_matches_nobody(self):
		self.assertFalse(self.check("EMP-5", "boss@example.com"))

	def test_timesheet_without_an_employee_matches_nobody(self):
		self.assertFalse(self.check(None, "boss@example.com"))

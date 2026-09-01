import frappe

from itchamps_timesheet.patches.v0_1.add_timesheet_detail_index import execute as add_index


def after_install():
	"""Anything the app needs that is not a fixture."""
	add_index()
	frappe.db.commit()

"""Index Timesheet Detail.custom_from_date.

The daily hour cap filters child rows on this column on every save. Without an
index the check degrades badly once the table has a year of data in it.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
	if not frappe.db.has_column("Timesheet Detail", "custom_from_date"):
		# custom field not created yet, the fixture install will bring it in
		return

	make_property_setter(
		"Timesheet Detail",
		"custom_from_date",
		"search_index",
		1,
		"Check",
		validate_fields_for_doctype=False,
	)

	frappe.db.add_index("Timesheet Detail", ["custom_from_date"])

app_name = "itchamps_timesheet"
app_title = "ITChamps Timesheet"
app_publisher = "ITChamps Software Private Limited"
app_description = "Timesheet guardrails: daily hour caps, one day per row, approver lockdown"
app_email = "support@itchamps.com"
app_license = "MIT"

required_apps = ["frappe/erpnext", "frappe/hrms"]

# ---------------------------------------------------------------------------
# Document events
# ---------------------------------------------------------------------------
# One function registered across the draft path and the submitted path. Frappe
# skips before_validate and validate on update_after_submit, which is why the
# guards are also wired to before_update_after_submit.

RULES = "itchamps_timesheet.overrides.timesheet_rules"

doc_events = {
	"Timesheet": {
		"before_validate": f"{RULES}.before_validate",
		"validate": f"{RULES}.validate",
		"before_update_after_submit": f"{RULES}.before_update_after_submit",
		"on_update": f"{RULES}.share_with_approver",
		"on_submit": f"{RULES}.share_with_approver",
		"on_update_after_submit": f"{RULES}.share_with_approver",
	}
}

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

has_permission = {
	"Timesheet": "itchamps_timesheet.overrides.timesheet_permissions.has_permission",
}

# ---------------------------------------------------------------------------
# Client script
# ---------------------------------------------------------------------------

doctype_js = {"Timesheet": "public/js/timesheet.js"}

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

after_install = "itchamps_timesheet.install.after_install"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
# Ship the customisations with the code so a new site is one install away.
# Export with:  bench --site <site> export-fixtures --app itchamps_timesheet

fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"Timesheet Detail-custom_from_date",
					"Timesheet Detail-custom_to_date",
					"Timesheet-custom_project_manager",
					"Timesheet-custom_project_manager_name",
					"Project-custom_project_manager",
				],
			]
		],
	},
	{
		"dt": "Property Setter",
		"filters": [["doc_type", "in", ["Timesheet", "Timesheet Detail"]]],
	},
	{"dt": "Workflow", "filters": [["document_type", "=", "Timesheet"]]},
	{"dt": "Workflow State"},
	{"dt": "Workflow Action Master"},
]

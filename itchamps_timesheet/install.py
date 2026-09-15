import frappe

from itchamps_timesheet.patches.v0_1.add_timesheet_detail_index import execute as add_index

DEFAULTS = {
	"enforce_daily_limit": 1,
	"max_daily_hours": 12,
	"enforce_single_day_rows": 1,
	"enforce_single_project": 1,
	"enforce_approver_lockdown": 1,
	"lock_terminal_states": 1,
	"block_amendment": 1,
}


def after_install():
	"""Anything the app needs that is not a fixture."""
	add_index()
	seed_settings()
	frappe.db.commit()


def seed_settings():
	"""Write the Singles row so the settings form opens with everything on.

	The rules treat an unset Check as on regardless, so this is about the form
	looking right rather than about enforcement.
	"""
	settings = frappe.get_single("Timesheet Guardrail Settings")
	if settings.get("max_daily_hours"):
		return

	settings.update(DEFAULTS)
	settings.save(ignore_permissions=True)

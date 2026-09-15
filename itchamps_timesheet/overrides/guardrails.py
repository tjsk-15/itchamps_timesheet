"""Resolves which Timesheet guardrails apply to a given document.

Kept apart from timesheet_rules so the rules stay readable: each rule asks one
question of this module and gets a boolean, rather than carrying settings
lookups around with it.
"""

import frappe
from frappe.utils import flt, get_datetime, getdate, now_datetime

SETTINGS = "Timesheet Guardrail Settings"
DEFAULT_MAX_DAILY_HOURS = 12.0

#: settings fieldname -> the name the rules use
RULE_FIELDS = {
	"block_amendment": "block_amendment",
	"lock_terminal_states": "lock_terminal_states",
	"enforce_approver_lockdown": "approver_lockdown",
	"enforce_single_day_rows": "single_day_rows",
	"enforce_single_project": "single_project",
	"enforce_daily_limit": "daily_limit",
}


def guardrails(doc):
	"""Resolved flags for this document. Computed once per save and cached on
	doc.flags, which survives from before_validate through to validate."""
	if not doc.flags.get("guardrails"):
		doc.flags.guardrails = resolve(doc)
	return doc.flags.guardrails


def resolve(doc):
	settings = get_settings()
	bypassed = bypass_active(settings)
	active = not bypassed and in_scope(doc, settings)

	flags = frappe._dict(
		bypassed=bypassed,
		max_daily_hours=flt(settings.get("max_daily_hours")) or DEFAULT_MAX_DAILY_HOURS,
	)
	for field, name in RULE_FIELDS.items():
		flags[name] = active and is_enabled(settings, field)

	return flags


def get_settings():
	try:
		return frappe.get_cached_doc(SETTINGS)
	except frappe.DoesNotExistError:
		# The app is installed but not migrated yet. Everything on is the safe
		# default: a missing settings record must never mean unenforced.
		return frappe._dict()


def is_enabled(settings, field):
	"""Unset means on.

	A Check field only reads 0 once somebody has saved it off. Before the
	Singles row exists it reads None, which must not be treated as disabled.
	"""
	value = settings.get(field)
	return True if value is None else bool(value)


def bypass_active(settings):
	until = settings.get("bypass_until")
	return bool(until) and get_datetime(until) > now_datetime()


def in_scope(doc, settings):
	"""Rules apply only to timesheets touching enforce_from_date or later.

	A document with any row on or after the cutover is in scope, so a straddling
	timesheet is validated rather than waved through.
	"""
	cutover = settings.get("enforce_from_date")
	if not cutover:
		return True

	days = [getdate(row.custom_from_date) for row in (doc.time_logs or []) if row.custom_from_date]
	if not days:
		return True

	return max(days) >= getdate(cutover)

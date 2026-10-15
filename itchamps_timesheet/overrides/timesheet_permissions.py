"""Permission hook for Timesheet.

Frappe ANDs this with the normal role permissions, so returning False here can
only take access away. This is the layer that makes the Edit and Amend buttons
disappear in the UI instead of letting the user click through to an error.
"""

from itchamps_timesheet.overrides.timesheet_rules import (
	LOCKED_STATES,
	is_privileged,
	is_timesheet_manager,
)

MUTATING = ("write", "submit", "cancel", "amend", "delete")

#: Actions on a locked timesheet that the Manager role profile may still take.
#: Cancelling or deleting removes the timesheet without changing its contents.
MANAGER_OVERRIDES = ("cancel", "delete")


def has_permission(doc, ptype=None, user=None):
	if ptype not in MUTATING:
		return True

	# Corrections are made by raising a fresh timesheet, never by amending.
	if ptype == "amend":
		return is_privileged(user)

	if (doc.get("workflow_state") or "") in LOCKED_STATES:
		if is_privileged(user):
			return True
		return ptype in MANAGER_OVERRIDES and is_timesheet_manager(user)

	return True

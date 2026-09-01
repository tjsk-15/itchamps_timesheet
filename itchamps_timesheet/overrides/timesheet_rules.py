"""Timesheet guardrails for ITChamps.

Every Timesheet business rule lives in this one module so it can be reviewed,
tested and released as a unit. Wired up in hooks.py through doc_events.

Rules enforced:
  1. Approved and Rejected timesheets are frozen, and amendment is blocked.
  2. Approvers may move the workflow but may not edit the contents.
  3. A timesheet row covers exactly one day.
  4. An employee cannot have more than 12 submitted hours on any single day,
	 counted across all of that employee's timesheets.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import add_to_date, flt, get_datetime, getdate

MAX_DAILY_HOURS = 12.0
MAX_ROW_HOURS = 12.0
DAY_START = "09:00:00"

#: Terminal workflow states. Nothing is editable once one of these is reached.
LOCKED_STATES = ("Approved", "Rejected")

#: States that do not consume an employee's daily hour budget.
DEAD_STATES = ("Rejected", "Cancelled")

#: Roles allowed to bypass the guardrails for data fixes.
PRIVILEGED_ROLES = ("System Manager",)

#: Set to False if one timesheet is allowed to span several projects.
ENFORCE_SINGLE_PROJECT = True


# ---------------------------------------------------------------------------
# hook entry points
# ---------------------------------------------------------------------------


def before_validate(doc, method=None):
	"""Runs on save and on submit, before anything is derived."""
	block_amendment(doc)
	guard_locked_document(doc)
	guard_approver_edits(doc)
	normalise_rows(doc)


def validate(doc, method=None):
	"""Runs after the ERPNext Timesheet controller has done its own validate."""
	validate_single_project(doc)
	booked = validate_daily_limit(doc)
	assign_times(doc, booked)
	set_approver(doc)
	set_derived_fields(doc)


def before_update_after_submit(doc, method=None):
	"""Frappe skips before_validate and validate on update_after_submit."""
	guard_locked_document(doc)
	guard_approver_edits(doc)


def share_with_approver(doc, method=None):
	"""Give the routed approver access. Idempotent, safe to call repeatedly."""
	approver = doc.custom_project_manager
	if not approver or approver == doc.owner:
		return

	if frappe.db.exists(
		"DocShare",
		{"share_doctype": "Timesheet", "share_name": doc.name, "user": approver},
	):
		return

	share = frappe.new_doc("DocShare")
	share.update(
		{
			"user": approver,
			"share_doctype": "Timesheet",
			"share_name": doc.name,
			"read": 1,
			# write is needed for the workflow transition to save. The approver
			# is stopped from editing content by guard_approver_edits, not here.
			"write": 1,
			"submit": 1,
			"notify": 1,
		}
	)
	share.flags.ignore_share_permission = True
	share.insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


def is_privileged(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(set(frappe.get_roles(user)) & set(PRIVILEGED_ROLES))


def block_amendment(doc):
	if doc.amended_from and not is_privileged():
		frappe.throw(
			_(
				"This timesheet has already been approved or rejected and cannot "
				"be amended. Please raise a new timesheet for the corrected hours."
			),
			title=_("Amendment not allowed"),
		)


def guard_locked_document(doc):
	before = doc.get_doc_before_save()
	if not before or is_privileged():
		return

	state = before.workflow_state or ""
	if state in LOCKED_STATES:
		frappe.throw(
			_(
				"Timesheet {0} is already {1} and is locked. Please raise a new "
				"timesheet instead of editing this one."
			).format(doc.name, state),
			title=_("Timesheet locked"),
		)


def guard_approver_edits(doc):
	before = doc.get_doc_before_save()
	if not before or is_privileged() or is_timesheet_owner(doc):
		return

	if row_signature(before) != row_signature(doc) or before.employee != doc.employee:
		frappe.throw(
			_(
				"Approvers cannot change the contents of a timesheet. Approve it, "
				"or reject it so that {0} can submit a corrected one."
			).format(before.employee_name or before.employee),
			title=_("Read only for approvers"),
		)


def is_timesheet_owner(doc):
	if doc.owner == frappe.session.user:
		return True
	if not doc.employee:
		return False
	return frappe.db.get_value("Employee", doc.employee, "user_id") == frappe.session.user


def row_signature(doc):
	"""Content fingerprint used to detect edits. Derived time fields are left
	out on purpose because this app writes them itself."""
	return [
		(
			getdate(row.custom_from_date) if row.custom_from_date else None,
			getdate(row.custom_to_date) if row.custom_to_date else None,
			flt(row.hours, 2),
			row.project,
			row.task,
			row.activity_type,
			(row.description or "").strip(),
		)
		for row in (doc.time_logs or [])
	]


# ---------------------------------------------------------------------------
# row rules
# ---------------------------------------------------------------------------


def normalise_rows(doc):
	if not doc.time_logs:
		frappe.throw(_("Please add at least one time log entry."))

	for row in doc.time_logs:
		if not row.custom_from_date:
			frappe.throw(_("Row {0}: please set the date for this entry.").format(row.idx))

		if not row.custom_to_date:
			row.custom_to_date = row.custom_from_date

		from_day = getdate(row.custom_from_date)
		to_day = getdate(row.custom_to_date)

		if from_day != to_day:
			frappe.throw(
				_(
					"Row {0} runs from {1} to {2}. Each timesheet line must cover a "
					"single day. Please split it into one row per day so the {3} "
					"hour daily limit can be applied."
				).format(row.idx, from_day, to_day, MAX_DAILY_HOURS),
				title=_("One row, one day"),
			)

		hours = flt(row.hours, 2)
		if hours <= 0:
			frappe.throw(_("Row {0}: hours must be greater than zero.").format(row.idx))
		if hours > MAX_ROW_HOURS:
			frappe.throw(
				_("Row {0} has {1} hours. A single entry cannot exceed {2} hours.").format(
					row.idx, hours, MAX_ROW_HOURS
				)
			)


def validate_single_project(doc):
	projects = []
	for row in doc.time_logs:
		if row.project and row.project not in projects:
			projects.append(row.project)

	if ENFORCE_SINGLE_PROJECT and len(projects) > 1:
		frappe.throw(
			_(
				"A timesheet can only cover one project. Please raise a separate "
				"timesheet for each project worked on."
			),
			title=_("One project per timesheet"),
		)

	if projects and not doc.parent_project:
		doc.parent_project = projects[0]


# ---------------------------------------------------------------------------
# daily limit
# ---------------------------------------------------------------------------


def validate_daily_limit(doc):
	"""Reject the document if any day would go over MAX_DAILY_HOURS once this
	timesheet is counted alongside the employee's other submitted timesheets.

	Returns the hours already booked per day, which assign_times reuses.
	"""
	own = {}
	for row in doc.time_logs:
		day = getdate(row.custom_from_date)
		own[day] = own.get(day, 0.0) + flt(row.hours)

	if not own:
		return {}

	if doc.docstatus == 1 and doc.employee:
		# Serialise concurrent submissions for the same employee so two
		# timesheets cannot both pass the check and then both commit.
		frappe.db.get_value("Employee", doc.employee, "name", for_update=True)

	booked = hours_booked_elsewhere(doc, list(own))

	for day in sorted(own):
		already = flt(booked.get(day), 2)
		adding = flt(own[day], 2)
		total = flt(already + adding, 2)
		if total > MAX_DAILY_HOURS:
			frappe.throw(
				_(
					"{0} already has {1} hours submitted on {2}. This timesheet "
					"adds {3} more, taking the day to {4} hours against a limit "
					"of {5}. Please reduce the hours for that day."
				).format(
					doc.employee_name or doc.employee,
					already,
					day,
					adding,
					total,
					MAX_DAILY_HOURS,
				),
				title=_("Daily limit exceeded"),
			)

	return booked


def hours_booked_elsewhere(doc, days):
	"""Hours already submitted by this employee on the given days, excluding
	this document and excluding rejected or cancelled timesheets.

	Built with frappe.qb rather than frappe.get_all. Querying a child doctype
	through get_all needed a `parent` hint on v15 and that argument was dropped
	when v16 moved to qb_query, so the query builder is the portable option. It
	also does the join and the per day sum in one round trip.
	"""
	if not doc.employee or not days:
		return {}

	detail = frappe.qb.DocType("Timesheet Detail")
	sheet = frappe.qb.DocType("Timesheet")

	rows = (
		frappe.qb.from_(detail)
		.join(sheet)
		.on(detail.parent == sheet.name)
		.select(detail.custom_from_date, Sum(detail.hours).as_("hours"))
		.where(detail.parenttype == "Timesheet")
		.where(detail.custom_from_date.isin(days))
		.where(sheet.employee == doc.employee)
		.where(sheet.docstatus == 1)
		.where(sheet.name != (doc.name or ""))
		# Coalesce matters: NOT IN against a NULL workflow_state yields NULL and
		# would silently drop timesheets that predate the workflow.
		.where(Coalesce(sheet.workflow_state, "").notin(list(DEAD_STATES)))
		.groupby(detail.custom_from_date)
	).run(as_dict=True)

	booked = {}
	for row in rows:
		booked[getdate(row.custom_from_date)] = flt(row.hours)
	return booked


# ---------------------------------------------------------------------------
# derived fields
# ---------------------------------------------------------------------------


def assign_times(doc, booked):
	"""Lay each row end to end starting at 09:00, offset by whatever the
	employee already has booked that day. Two projects on the same day then
	never look like overlapping time logs to the ERPNext overlap check."""
	cursor = dict(booked)

	for row in doc.time_logs:
		day = getdate(row.custom_from_date)
		offset = flt(cursor.get(day))
		start = add_to_date(get_datetime(f"{day} {DAY_START}"), hours=offset)
		row.from_time = start
		row.to_time = add_to_date(start, hours=flt(row.hours))
		cursor[day] = offset + flt(row.hours)


def set_approver(doc):
	"""Project manager if there is one, otherwise the reporting manager. If the
	employee is themselves the project manager, escalate one level up."""
	approver = None
	project = doc.parent_project or doc.get("project")
	if project:
		approver = frappe.db.get_value("Project", project, "custom_project_manager")

	employee_user = frappe.db.get_value("Employee", doc.employee, "user_id") if doc.employee else None

	if not approver or (employee_user and approver == employee_user):
		approver = reporting_manager_user(doc.employee)

	doc.custom_project_manager = approver or ""
	doc.custom_project_manager_name = frappe.db.get_value("User", approver, "full_name") if approver else ""


def reporting_manager_user(employee):
	if not employee:
		return None

	reports_to = frappe.db.get_value("Employee", employee, "reports_to")
	if not reports_to:
		return None

	manager = frappe.db.get_value("Employee", reports_to, ["user_id", "employee_name"], as_dict=True)
	if not manager:
		return None

	if manager.user_id:
		return manager.user_id

	if manager.employee_name:
		# fallback for employees whose user_id was never filled in
		return frappe.db.get_value("User", {"full_name": manager.employee_name, "enabled": 1}, "name")

	return None


def set_derived_fields(doc):
	days = [getdate(row.custom_from_date) for row in doc.time_logs if row.custom_from_date]
	if days:
		doc.start_date = min(days)
		doc.end_date = max(days)

	# Total Hours is read only, so anything the client or API sends is ignored.
	# It has to be computed here.
	doc.total_hours = flt(sum(flt(row.hours) for row in doc.time_logs), 2)

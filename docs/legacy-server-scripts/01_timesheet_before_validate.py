# =============================================================================
# Server Script:  Timesheet Guardrails (Draft)
# DocType:        Timesheet
# Event:          Before Validate
# =============================================================================
# Replaces the old "Timesheet from-to date update" and "Timesheet PM Routing"
# scripts. Everything that runs while the document is still a draft lives here.
#
# safe_exec notes for Frappe Cloud:
#   * no imports, no str(), no int(), no float(), no sorted(), no set()
#   * use frappe.utils.flt / cint / cstr / getdate / get_datetime / add_to_date
#   * f-strings are allowed only without format specifiers
# =============================================================================

MAX_DAILY_HOURS = 12.0
MAX_ROW_HOURS = 12.0
LOCKED_STATES = ("Approved", "Rejected")
DEAD_STATES = ("Rejected", "Cancelled")
ENFORCE_SINGLE_PROJECT = True

roles = frappe.get_roles()
privileged = ("System Manager" in roles) or (frappe.session.user == "Administrator")

before = doc.get_doc_before_save()

# -----------------------------------------------------------------------------
# 1. No amendments. A finished timesheet stays finished.
# -----------------------------------------------------------------------------
if doc.amended_from and not privileged:
    frappe.throw(
        "This timesheet has already been approved or rejected and cannot be "
        "amended. Please raise a new timesheet for the corrected hours."
    )

# -----------------------------------------------------------------------------
# 2. Nothing changes once the workflow reaches Approved or Rejected.
# -----------------------------------------------------------------------------
if before and not privileged:
    old_state = before.workflow_state or ""
    if old_state in LOCKED_STATES:
        frappe.throw(
            f"Timesheet {doc.name} is already {old_state} and is locked. "
            "Please raise a new timesheet instead of editing this one."
        )

# -----------------------------------------------------------------------------
# 3. Approvers may move the workflow, never the contents.
# -----------------------------------------------------------------------------
if before and not privileged:
    employee_user = None
    if doc.employee:
        employee_user = frappe.db.get_value("Employee", doc.employee, "user_id")

    is_owner = (doc.owner == frappe.session.user) or (
        employee_user and employee_user == frappe.session.user
    )

    if not is_owner:
        old_rows = []
        for r in before.time_logs or []:
            old_rows.append((
                frappe.utils.getdate(r.custom_from_date) if r.custom_from_date else None,
                frappe.utils.flt(r.hours, 2),
                r.project,
                r.task,
                r.activity_type,
                frappe.utils.cstr(r.description).strip(),
            ))

        new_rows = []
        for r in doc.time_logs or []:
            new_rows.append((
                frappe.utils.getdate(r.custom_from_date) if r.custom_from_date else None,
                frappe.utils.flt(r.hours, 2),
                r.project,
                r.task,
                r.activity_type,
                frappe.utils.cstr(r.description).strip(),
            ))

        if old_rows != new_rows or before.employee != doc.employee:
            frappe.throw(
                "Approvers cannot change the contents of a timesheet. Approve "
                "it, or reject it so the employee can submit a corrected one."
            )

# -----------------------------------------------------------------------------
# 4. Row level rules. One row is one day.
# -----------------------------------------------------------------------------
if not doc.time_logs:
    frappe.throw("Please add at least one time log entry.")

days = []
own_hours = {}
projects = []

for row in doc.time_logs:
    if not row.custom_from_date:
        frappe.throw(f"Row {row.idx}: please set the date for this entry.")

    if not row.custom_to_date:
        row.custom_to_date = row.custom_from_date

    from_day = frappe.utils.getdate(row.custom_from_date)
    to_day = frappe.utils.getdate(row.custom_to_date)

    if from_day != to_day:
        frappe.throw(
            f"Row {row.idx} runs from {from_day} to {to_day}. Each timesheet "
            "line must cover a single day. Please split the week into one row "
            "per day so the 12 hour daily limit can be applied."
        )

    hours = frappe.utils.flt(row.hours, 2)
    if hours <= 0:
        frappe.throw(f"Row {row.idx}: hours must be greater than zero.")
    if hours > MAX_ROW_HOURS:
        frappe.throw(
            f"Row {row.idx} has {hours} hours. A single entry cannot exceed "
            f"{MAX_ROW_HOURS} hours."
        )

    if from_day not in own_hours:
        own_hours[from_day] = 0.0
        days.append(from_day)
    own_hours[from_day] = own_hours[from_day] + hours

    if row.project and row.project not in projects:
        projects.append(row.project)

# -----------------------------------------------------------------------------
# 5. One timesheet, one project. Keeps approver routing unambiguous.
# -----------------------------------------------------------------------------
if ENFORCE_SINGLE_PROJECT and len(projects) > 1:
    frappe.throw(
        "A timesheet can only cover one project. Please raise a separate "
        "timesheet for each project worked on."
    )

if projects and not doc.parent_project:
    doc.parent_project = projects[0]

# -----------------------------------------------------------------------------
# 6. Twelve hour daily cap across every submitted timesheet for this employee.
# -----------------------------------------------------------------------------
booked = {}

if doc.employee and days:
    other_rows = frappe.get_all(
        "Timesheet Detail",
        parent="Timesheet",
        filters={
            "parenttype": "Timesheet",
            "docstatus": 1,
            "custom_from_date": ["in", days],
        },
        fields=["parent", "custom_from_date", "hours"],
    )

    candidates = []
    for r in other_rows:
        if r.parent != doc.name and r.parent not in candidates:
            candidates.append(r.parent)

    live = []
    if candidates:
        for ts in frappe.get_all(
            "Timesheet",
            filters={"name": ["in", candidates], "employee": doc.employee},
            fields=["name", "workflow_state"],
        ):
            if (ts.workflow_state or "") not in DEAD_STATES:
                live.append(ts.name)

    for r in other_rows:
        if r.parent in live:
            day = frappe.utils.getdate(r.custom_from_date)
            booked[day] = frappe.utils.flt(booked.get(day)) + frappe.utils.flt(r.hours)

for day in days:
    already = frappe.utils.flt(booked.get(day))
    adding = frappe.utils.flt(own_hours.get(day))
    total = frappe.utils.flt(already + adding, 2)
    if total > MAX_DAILY_HOURS:
        frappe.throw(
            f"{doc.employee_name or doc.employee} already has {already} hours "
            f"submitted on {day}. This timesheet adds {adding} more, which "
            f"takes the day to {total} hours against a limit of "
            f"{MAX_DAILY_HOURS}. Please reduce the hours for that day."
        )

# -----------------------------------------------------------------------------
# 7. Derive from_time and to_time. Rows are laid end to end from 09:00 so that
#    two projects on the same day never look like overlapping time logs.
# -----------------------------------------------------------------------------
cursor = {}
for day in days:
    cursor[day] = frappe.utils.flt(booked.get(day))

for row in doc.time_logs:
    day = frappe.utils.getdate(row.custom_from_date)
    offset = frappe.utils.flt(cursor.get(day))
    start = frappe.utils.add_to_date(
        frappe.utils.get_datetime(f"{day} 09:00:00"), hours=offset
    )
    row.from_time = start
    row.to_time = frappe.utils.add_to_date(start, hours=frappe.utils.flt(row.hours))
    cursor[day] = offset + frappe.utils.flt(row.hours)

# -----------------------------------------------------------------------------
# 8. Approver routing. Project manager first, reporting manager as fallback.
# -----------------------------------------------------------------------------
approver = None
project = doc.parent_project or doc.get("project")

if project:
    approver = frappe.db.get_value("Project", project, "custom_project_manager")

employee_user = None
if doc.employee:
    employee_user = frappe.db.get_value("Employee", doc.employee, "user_id")

# no PM on the project, or the employee is the PM, so escalate one level up
if not approver or (employee_user and approver == employee_user):
    approver = None
    reports_to = None
    if doc.employee:
        reports_to = frappe.db.get_value("Employee", doc.employee, "reports_to")
    if reports_to:
        manager = frappe.db.get_value(
            "Employee", reports_to, ["user_id", "employee_name"], as_dict=True
        )
        if manager:
            approver = manager.get("user_id")
            if not approver and manager.get("employee_name"):
                approver = frappe.db.get_value(
                    "User", {"full_name": manager.get("employee_name"), "enabled": 1}, "name"
                )

doc.custom_project_manager = approver or ""
doc.custom_project_manager_name = (
    frappe.db.get_value("User", approver, "full_name") if approver else ""
)

# -----------------------------------------------------------------------------
# 9. Derived parent fields. Total Hours is read only, so it must be set here.
# -----------------------------------------------------------------------------
first_day = None
last_day = None
for day in days:
    if first_day is None or day < first_day:
        first_day = day
    if last_day is None or day > last_day:
        last_day = day

if first_day:
    doc.start_date = first_day
if last_day:
    doc.end_date = last_day

total = 0.0
for row in doc.time_logs:
    total = total + frappe.utils.flt(row.hours)
doc.total_hours = frappe.utils.flt(total, 2)

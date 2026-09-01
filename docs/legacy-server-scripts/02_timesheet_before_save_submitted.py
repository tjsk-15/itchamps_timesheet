# =============================================================================
# Server Script:  Timesheet Guardrails (Submitted)
# DocType:        Timesheet
# Event:          Before Save (Submitted Document)
# =============================================================================
# Frappe does NOT run before_validate or validate on update_after_submit, so the
# lock and the approver guard have to be repeated here. This is the single
# biggest reason the rules belong in an app rather than in server scripts.
# =============================================================================

LOCKED_STATES = ("Approved", "Rejected")

roles = frappe.get_roles()
privileged = ("System Manager" in roles) or (frappe.session.user == "Administrator")

before = doc.get_doc_before_save()

if before and not privileged:
    old_state = before.workflow_state or ""

    # 1. Approved and Rejected are terminal.
    if old_state in LOCKED_STATES:
        frappe.throw(
            f"Timesheet {doc.name} is already {old_state} and is locked. "
            "Please raise a new timesheet instead of editing this one."
        )

    # 2. Approvers may move the workflow, never the contents.
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

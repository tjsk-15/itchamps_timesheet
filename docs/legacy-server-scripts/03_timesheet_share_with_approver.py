# =============================================================================
# Server Script:  Timesheet Approver Share
# DocType:        Timesheet
# Event:          install this SAME body three times, once for each of:
#                   After Save                    (on_update)
#                   After Submit                  (on_submit)
#                   After Save (Submitted Document)  (on_update_after_submit)
# =============================================================================
# The write permission is deliberate. The approver needs write access for the
# workflow transition to save. What stops the approver from actually changing
# anything is the guard in scripts 01 and 02, not the share.
# =============================================================================

approver = doc.custom_project_manager

if approver and approver != doc.owner:
    already = frappe.db.exists("DocShare", {
        "share_doctype": "Timesheet",
        "share_name": doc.name,
        "user": approver,
    })

    if not already:
        share = frappe.new_doc("DocShare")
        share.user = approver
        share.share_doctype = "Timesheet"
        share.share_name = doc.name
        share.read = 1
        share.write = 1
        share.submit = 1
        share.notify = 1
        # required when the share is created inside the approver's own session
        share.flags.ignore_share_permission = True
        share.insert(ignore_permissions=True)

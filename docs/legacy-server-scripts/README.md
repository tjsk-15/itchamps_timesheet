# Legacy server scripts

These are the four original Timesheet server scripts consolidated down to three
bodies. They are kept here for two reasons: as a stopgap if the app cannot be
deployed yet, and as the record of what has to be disabled before the app goes
on a site.

| File | Server Script DocType Event |
| --- | --- |
| `01_timesheet_before_validate.py` | Before Validate |
| `02_timesheet_before_save_submitted.py` | Before Save (Submitted Document) |
| `03_timesheet_share_with_approver.py` | install the same body three times: After Save, After Submit, After Save (Submitted Document) |

They are written for the Frappe Cloud safe_exec sandbox, which means no imports,
no `str()`, no `int()`, no `float()`, no `sorted()`, no `set()`, no
`str.format()`, and no `frappe.share`. The app version under
`itchamps_timesheet/overrides/` has none of those restrictions and is the
supported path.

**Do not run these and the app at the same time.** Two copies of the routing
logic will fight over `custom_project_manager`.

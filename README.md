# ITChamps Timesheet

Timesheet guardrails for Frappe HRMS. Replaces four database resident server
scripts with one reviewable, testable app.

## What it enforces

1. **Approved and Rejected are terminal.** Once the workflow reaches either
   state the document is frozen, and amendment is blocked outright. Corrections
   are made by raising a new timesheet.
2. **Approvers approve, they do not edit.** An approver can move the workflow
   but cannot change hours, dates, projects or the employee. Any content change
   from a non owner is rejected.
3. **One row, one day.** A timesheet line whose from date and to date differ is
   rejected, so a week of work on one project has to be entered as one row per
   day.
4. **Twelve hours per employee per day.** Counted across every submitted
   timesheet for that employee on that date, not just within the document being
   saved.

It also routes each timesheet to an approver (project manager first, reporting
manager as fallback, escalating one level if the employee is themselves the
project manager) and shares the document with them.

## Requirements

Frappe v15 or v16, ERPNext, HRMS. Python 3.10 or newer.

## Install

```bash
cd ~/frappe-bench
bench get-app https://github.com/<org>/itchamps_timesheet.git
bench --site <site> install-app itchamps_timesheet
bench --site <site> migrate
bench restart
```

On Frappe Cloud, add the repository as a custom app to your bench group and
deploy. A private bench is required.

### Before you install on production

Disable the existing Timesheet server scripts first. Running both means two
copies of the routing logic fighting over `custom_project_manager`. The old
scripts are kept in `docs/legacy-server-scripts/` for reference.

## Configuration the code does not cover

The app cannot set these for you. Do them once per site.

1. **Role Permissions Manager, Timesheet.** Uncheck **Amend** for every role
   except System Manager. Uncheck **Cancel** for Employee and the approver role.
2. **Customize Form, Timesheet.** Turn off **Allow on Submit** for every field
   except `workflow_state`.
3. **Projects Settings.** Tick **Ignore Employee Time Overlap** and **Ignore
   User Time Overlap**. ERPNext's own overlap check will otherwise fight the
   staggering logic when a rejected timesheet leaves a gap in the day.
4. **Workflow, Timesheet.** On the Pending Approval state set **Allow Edit** to
   a role approvers do not hold. Give Approved and Rejected no outgoing
   transitions.
5. **Existing data.** Rows that span several days will fail validation the next
   time anyone touches them. Either split them with a one off script or gate the
   rule on `doc.creation` against a cutover date.

Item 5 in the previous version of this list, the search index on
`Timesheet Detail.custom_from_date`, is now handled by
`patches/v0_1/add_timesheet_detail_index.py` and runs on install and migrate.

## Layout

```
itchamps_timesheet/
├── hooks.py                            doc_events, has_permission, fixtures
├── install.py                          after_install
├── modules.txt
├── patches.txt
├── overrides/
│   ├── timesheet_rules.py              all four rules, one module
│   └── timesheet_permissions.py        has_permission hook
├── patches/v0_1/
│   └── add_timesheet_detail_index.py
├── public/js/timesheet.js              hides controls the server would reject
├── fixtures/                           populated by export-fixtures
└── tests/
    └── test_timesheet_rules.py
docs/
├── DECISION.md                         why an app and not server scripts
└── legacy-server-scripts/              the consolidated scripts, for reference
```

## Tuning

Both constants live at the top of `overrides/timesheet_rules.py`.

* `ENFORCE_SINGLE_PROJECT` defaults to `True`. A single
  `custom_project_manager` on the parent only makes sense if the whole document
  is one project. If documents can mix projects, set this to `False` and move
  routing to a per row approver.
* Drafts do not consume the daily budget. The cap counts `docstatus == 1` only.
  To make drafts reserve hours, change the filter in `hours_booked_elsewhere`
  to `("docstatus", "<", 2)`.
* `MAX_DAILY_HOURS`, `MAX_ROW_HOURS`, `LOCKED_STATES`, `DEAD_STATES` and
  `PRIVILEGED_ROLES` are all constants in the same place.

## Tests

```bash
bench --site <site> run-tests --app itchamps_timesheet
```

The suite covers the multi day row rejection, zero hours, the cap inside one
document, the cap across two submitted timesheets, non overlapping derived
times, blocked amendment, and server side computation of Total Hours.

Manual cycle before any production deploy: one employee submits, the manager
tries to edit, the manager rejects, the employee resubmits, the manager
approves, someone tries to amend.

## Development

```bash
pip install pre-commit
pre-commit install
```

Ruff is configured for tabs and a 110 column limit, matching Frappe house style.

## License

MIT

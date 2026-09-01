# Timesheet guardrails: consolidation and the app vs server script decision

## The recommendation

Move this into a custom app. Keep the consolidated server scripts only as a
stopgap while the app is being set up and reviewed.

The reason is not style. Three of the four problems you listed cannot be solved
properly inside a server script:

| Problem | Why server scripts fall short |
| --- | --- |
| Editing after Approved or Rejected | Frappe does not run `before_validate` or `validate` on `update_after_submit`. The guard has to be duplicated into a second server script, and the Amend and Edit buttons still render in the UI because there is no `has_permission` server script type. |
| Manager editing before approving | Needs a `has_permission` hook plus a client script to hide the controls. Neither can come from a server script. |
| 12 hour daily cap across timesheets | Needs a `SELECT ... FOR UPDATE` style lock so two simultaneous submissions do not both pass. `frappe.db.sql` is not in the safe_exec whitelist. |
| One day per row | This one is fine as a server script. |

The rest of the case:

* **Duplication.** Your two "Timesheet Permission" scripts are byte identical
  because Frappe needs one record per event. In the app, `share_with_approver`
  is one function registered on three events in `hooks.py`.
* **Version control.** Server scripts live in the database. There is no diff, no
  review, no rollback, and a restore of prod over dev silently reverts them.
  You have already been through several rounds of `on_update` vs
  `on_update_after_submit` and `doc.project` vs `doc.parent_project`. Those are
  exactly the bugs a git history and a test catch.
* **Testing.** `bench run-tests` can assert the 12 hour rule. A server script
  can only be tested by clicking.
* **Sandbox tax.** No imports, no `str()`, no `int()`, no `str.format()`, no
  `frappe.share`. You are writing worse Python than you need to, and every new
  rule costs another round of discovering what the sandbox blocks.
* **Reuse.** ITChamps runs Frappe implementations for multiple clients. A
  `itchamps_timesheet` app installs on the next one with `bench install-app`.
  Server scripts get copy pasted and drift.

The honest counterargument is speed. A server script is edited in the browser
and live in ten seconds. On Frappe Cloud an app means a private bench, a GitHub
repo, and a deploy for every change. That is a real cost, and it is why the
consolidated server scripts are included here. Use them if the app is more than
a week away. But the guardrails you are asking for are permission behaviour, not
just validation, and permission behaviour belongs in an app.

## What was consolidated

Four scripts became three, with a lot removed:

* The PM routing script had the same reporting manager fallback written out
  three times, about 90 lines. It is now one linear fallback chain of about 15.
* The two identical DocShare scripts became one body installed on three events.
* The from/to date script's daily total check only looked inside the current
  document. It now counts every submitted timesheet for that employee.
* The DocShare insert now sets `share.flags.ignore_share_permission = True`,
  which it needs when it fires inside the approver's own session.

## Files

Everything now lives in one repo, `itchamps_timesheet`. See the README for the
full layout. The short version:

* `itchamps_timesheet/overrides/timesheet_rules.py` holds all four rules.
* `itchamps_timesheet/overrides/timesheet_permissions.py` holds the
  `has_permission` hook.
* `itchamps_timesheet/hooks.py` wires one function across the six events Frappe
  uses for the draft path and the submitted path.
* `docs/legacy-server-scripts/` keeps the consolidated server scripts as a
  stopgap and as the list of what to disable before deploying.

## Configuration that the code does not cover

Code alone will not close these. Do them in the Desk.

1. **Role Permissions Manager, Timesheet.** Uncheck **Amend** for every role
   except System Manager. Uncheck **Cancel** for Employee and for the approver
   role. Corrections happen by raising a new timesheet.

2. **Customize Form, Timesheet.** Set **Allow on Submit** to off for every field
   except `workflow_state`. This is what stops post submission edits at the
   framework level rather than at the throw level.

3. **Projects Settings.** Tick **Ignore Employee Time Overlap** and **Ignore
   User Time Overlap**. ERPNext's own overlap check will otherwise fight the
   staggering logic if a timesheet is ever rejected and leaves a gap in the day.

4. **Workflow, Timesheet.** On the Pending Approval state, set **Allow Edit** to
   a role that approvers do not hold. This is a second line of defence behind
   `guard_approver_edits`. Add explicit Approved and Rejected states with no
   outgoing transitions.

5. **Search index.** Handled by `patches/v0_1/add_timesheet_detail_index.py`,
   which runs on install and on every migrate. Nothing to do by hand.

6. **Backfill.** Existing rows that span several days will fail validation the
   next time anyone touches them. Run a one off script to split them, or leave
   them alone and only enforce the rule on new documents by checking
   `doc.creation` against a cutover date.

## Rollout order

1. Install the app on a staging site, run `bench run-tests --app itchamps_timesheet`.
2. Do the six configuration items above on staging.
3. Have one employee and one manager run a full cycle: submit, try to edit as
   the manager, reject, resubmit, approve, try to amend.
4. On production, disable the four existing server scripts before installing the
   app. Do not run both. Two copies of the routing logic will fight over
   `custom_project_manager`.
5. Install, migrate, restart, repeat the manual cycle.

## Two things worth deciding

* **`ENFORCE_SINGLE_PROJECT`** is set to `True` in `rules.py`. You said
  timesheets are project based and an employee raises one per project per day,
  so a single `custom_project_manager` field on the parent only makes sense if
  the whole document is one project. If a document can genuinely mix projects,
  set this to `False`, but then routing has to move to a per row approver.
* **Drafts do not consume the daily budget.** The cap counts `docstatus == 1`
  only, matching your wording of "total submitted time". If you want drafts to
  reserve hours too, change the filter in `hours_booked_elsewhere` to
  `("docstatus", "<", 2)`.

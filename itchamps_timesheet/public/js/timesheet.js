// Cosmetic layer only. The server rules in rules.py are what actually enforce
// this. The point here is that the approver never sees a button that will fail.

frappe.ui.form.on("Timesheet", {
	refresh(frm) {
		const locked = ["Approved", "Rejected"].includes(frm.doc.workflow_state);

		if (locked) {
			frm.page.clear_primary_action();
			frm.page.remove_inner_button(__("Amend"));
			frm.disable_save();
			frm.dashboard.add_comment(
				__("This timesheet is {0} and is locked. Raise a new timesheet for any correction.", [
					frm.doc.workflow_state,
				]),
				"blue",
				true
			);
		}

		// Anyone who is not the person the timesheet belongs to gets a read only
		// grid. They can still use the workflow action button.
		const is_owner = frm.doc.owner === frappe.session.user;
		if (!is_owner && !frappe.user.has_role("System Manager")) {
			frm.set_df_property("time_logs", "read_only", 1);
			frm.set_df_property("employee", "read_only", 1);
			frm.set_df_property("parent_project", "read_only", 1);
		}
	},

	// keep the grid honest: one row is one day
	time_logs_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.custom_from_date && !row.custom_to_date) {
			frappe.model.set_value(cdt, cdn, "custom_to_date", row.custom_from_date);
		}
	},
});

frappe.ui.form.on("Timesheet Detail", {
	custom_from_date(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "custom_to_date", row.custom_from_date);
	},
});

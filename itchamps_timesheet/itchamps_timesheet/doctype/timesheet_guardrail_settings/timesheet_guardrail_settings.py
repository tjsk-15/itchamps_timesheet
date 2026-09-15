import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime, now_datetime

#: A bypass that outlives the reason for it is worse than no bypass at all.
MAX_BYPASS_HOURS = 24


class TimesheetGuardrailSettings(Document):
	def validate(self):
		self.validate_bypass()

	def validate_bypass(self):
		if not self.bypass_until:
			return

		until = get_datetime(self.bypass_until)
		now = now_datetime()

		if until <= now:
			frappe.throw(
				_("Bypass until has to be in the future. Clear the field to end the bypass now."),
				title=_("Bypass already expired"),
			)

		if until > add_to_date(now, hours=MAX_BYPASS_HOURS):
			frappe.throw(
				_(
					"A bypass can run for at most {0} hours. Set a shorter window and "
					"extend it if the backlog is not cleared."
				).format(MAX_BYPASS_HOURS),
				title=_("Bypass window too long"),
			)

		if not (self.bypass_reason or "").strip():
			frappe.throw(_("Please record why the guardrails are being bypassed."))

	def on_update(self):
		# The rules read this through frappe.get_cached_doc, so the cache has to
		# go or a bypass would not take effect until the next worker restart.
		frappe.clear_cache(doctype=self.doctype)

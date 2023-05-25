import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class MandateCancelReason(models.TransientModel):
    _name = "mandate.cancel.reason"
    _description = "Add Reason for select contract template"

    name = fields.Text(string="Reason for Cancellation")
    mandate_id = fields.Many2one("twikey.mandate.details")

    def action_cancel_confirm(self):
        if self.name:
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(
                company=self.env.company
            )
            if twikey_client:
                twikey_client.document.cancel(self.mandate_id.reference, self.name)
                self.mandate_id.update_feed()
        else:
            raise UserError(_("Add reason to cancel the mandate!"))

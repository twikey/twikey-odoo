import logging

from ..twikey.client import TwikeyError
from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class MandateCancelReason(models.TransientModel):
    _name = "mandate.cancel.reason"
    _description = "Cancel a specific mandate"

    name = fields.Text(string="Reason for Cancellation")
    mandate_id = fields.Many2one("twikey.mandate.details")

    def action_cancel_confirm(self):
        if self.name:
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
            if twikey_client:
                try:
                    twikey_client.document.cancel(self.mandate_id.reference, self.name)
                    self.mandate_id.update_feed()
                except TwikeyError as te:
                    raise UserError(_("This mandate could not be cancelled: %s") % te.get_error())
                except Exception as ex:
                    raise UserError(_("This mandate could not be cancelled: %s") % ex)
        else:
            raise UserError(_("Add reason to cancel the mandate!"))

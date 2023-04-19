from odoo import _, api, fields, models
from odoo.exceptions import UserError

class AccountJournal(models.Model):
    _inherit = "account.journal"

    use_with_twikey = fields.Boolean(
        "Use with Twikey", help="Journal to be used for incoming Twikey payments."
    )

    @api.constrains("use_with_twikey")
    def _check_use_with_twikey(self):
        journals = self.env["account.journal"].search_count([("use_with_twikey", "=", True)])

        if journals > 1:
            raise UserError(_("It's not allowed to use Twikey in multiple journals!"))

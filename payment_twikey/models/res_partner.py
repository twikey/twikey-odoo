from odoo import fields, models, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    twikey_mandate_ids = fields.One2many(
        "twikey.mandate.details", "partner_id", string="Mandates"
    )

    def action_invite_customer(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        if company.sudo().activate_twikey:
            wizard = self.env["twikey.contract.template.wizard"].create(
                {
                    "partner_ids": self.ids,
                }
            )
            action = self.env.ref(
                "payment_twikey.contract_template_wizard_action"
            ).read()[0]
            action["res_id"] = wizard.id
            return action
        else:
            raise UserError(_("Twikey is not activated for company %s") % company.name)

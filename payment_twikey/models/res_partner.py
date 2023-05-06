from odoo import exceptions, fields, models

class ResPartner(models.Model):
    _inherit = "res.partner"

    twikey_mandate_ids = fields.One2many("twikey.mandate.details", "partner_id", string="Mandates")

    def action_invite_customer(self):
        wizard = self.env["twikey.contract.template.wizard"].create({
                "partner_ids": self.ids,
        })
        action = self.env.ref("payment_twikey.contract_template_wizard_action").read()[0]
        action["res_id"] = wizard.id
        return action

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
            if len(self) == 1:
                return {
                    'name': _("Invite customer"),
                    'type': 'ir.actions.act_window',
                    'view_mode': 'form',
                    'res_model': 'twikey.contract.template.wizard',
                    'target': 'new',
                    'context': {
                        'active_id': self.id,
                        'active_model': 'res.partner',
                    },
                }
            else:
                return {
                    'name': _("Invite customers"),
                    'type': 'ir.actions.act_window',
                    'view_mode': 'tree',
                    'res_model': 'twikey.contract.template.batch.wizard',
                    'target': 'new',
                    'context': {
                        'active_model': 'res.partner',
                        'partner_ids': self.ids,
                    },
                }
        else:
            raise UserError(_("Twikey is not activated for company %s") % company.name)

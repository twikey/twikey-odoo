# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models

class PaymentToken(models.Model):
    _inherit = 'payment.token'
    expiry = fields.Date(string="Expiry", readonly=True)
    type = fields.Selection(
        [
            ("SDD", "SDD"),
            ("CC", "CC"),
        ]
        , readonly=True
    )

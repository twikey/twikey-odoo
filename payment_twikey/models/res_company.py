from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    twikey_base_url = fields.Char()
    twikey_api_key = fields.Char()

    mandate_feed_pos = fields.Integer(string="Twikey Mandate feed position", readonly=True)
    invoice_feed_pos = fields.Integer(string="Twikey Invoice feed position", readonly=True)

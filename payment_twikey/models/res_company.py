from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    twikey_base_url = fields.Char()
    twikey_api_key = fields.Char()

    twikey_auto_collect = fields.Boolean()
    twikey_send_pdf = fields.Boolean()
    twikey_send_invoice = fields.Boolean()
    twikey_include_purchase = fields.Boolean()

    mandate_feed_pos = fields.Integer(readonly=True)
    invoice_feed_pos = fields.Integer(readonly=True)

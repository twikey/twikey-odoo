from odoo import fields, models

class ResCompany(models.Model):
    _inherit = "res.company"

    twikey_base_url = fields.Char()
    twikey_api_key = fields.Char()

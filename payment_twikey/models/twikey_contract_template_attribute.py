from odoo import fields, models


class ContractTemplateAttribute(models.Model):
    _name = "twikey.contract.template.attribute"
    _description = "Attributes for Twikey Profile"

    name = fields.Char(string="Twikey Profile Attribute", readonly=True)
    contract_template_id = fields.Many2one(
        "twikey.contract.template", string="Twikey Profile", required=True, ondelete="cascade", readonly=True
    )
    type = fields.Selection(
        [
            ("char", "Text"),
            ("integer", "Number"),
            ("boolean", "Boolean"),
            ("float", "Amount"),
            ("selection", "Select"),
        ], readonly=True
    )

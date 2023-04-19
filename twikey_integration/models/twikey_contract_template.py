from odoo import fields, models


class TwikeyContractTemplate(models.Model):
    _name = "twikey.contract.template"
    _description = "Twikey Contract Template for Mandate"

    _sql_constraints = [("template_id_unique", "unique(template_id_twikey)", "Already Exist!")]

    name = fields.Char(string="Contract Template", required=True)
    template_id_twikey = fields.Integer(string="Template ID")
    active = fields.Boolean(default=True)
    mandate_number_required = fields.Boolean(default=True)
    type = fields.Selection(
        [
            ("CORE", "CORE"),
            ("B2B", "B2B"),
            ("CODA", "CODA"),
            ("CONTRACT", "CONTRACT"),
            ("CONSENT", "CONSENT"),
            ("IDENT", "IDENT"),
            ("CREDITCARD", "CREDITCARD"),
            ("WIK", "WIK"),
            ("PAYROLL", "PAYROLL"),
        ],
    )
    twikey_attribute_ids = fields.One2many(
        "twikey.contract.template.attribute", "contract_template_id", string="Attributes"
    )
    display_name = fields.Char(help="Can be used e.g. in checkout of the webshop", translate=True)


class ContractTemplateAttribute(models.Model):
    _name = "twikey.contract.template.attribute"
    _description = "Attributes for Contract Template"

    name = fields.Char(string="Contract Template Attribute")
    contract_template_id = fields.Many2one(
        "twikey.contract.template", string="Contract Template", required=True, ondelete="cascade"
    )
    type = fields.Selection(
        [
            ("char", "Text"),
            ("integer", "Number"),
            ("boolean", "Boolean"),
            ("float", "Amount"),
            ("selection", "Select"),
        ]
    )

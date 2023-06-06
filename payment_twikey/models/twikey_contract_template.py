from odoo import fields, models


class TwikeyContractTemplate(models.Model):
    _name = "twikey.contract.template"
    _description = "Twikey Profile"

    _sql_constraints = [("template_id_unique", "unique(template_id_twikey)", "Already Exist!")]

    name = fields.Char(string="Twikey Profile", required=True, readonly=True)
    template_id_twikey = fields.Integer(string="Template ID", readonly=True, index=True)
    active = fields.Boolean(default=True, readonly=True)
    mandate_number_required = fields.Boolean(default=True, readonly=True)
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
        ], readonly=True
    )
    twikey_attribute_ids = fields.One2many("twikey.contract.template.attribute", "contract_template_id", string="Attributes")

    def is_creditcard(self):
        return self.type == "CREDITCARD"

    def ct(self):
        return self.template_id_twikey


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

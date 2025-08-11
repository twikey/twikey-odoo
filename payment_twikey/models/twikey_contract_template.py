from odoo import fields, models


class TwikeyContractTemplate(models.Model):
    _name = "twikey.contract.template"
    _description = "Twikey Profile"

    _sql_constraints = [
        ("twikey_id_unique", "unique(twikey_id)", "Already Exist!")
    ]

    name = fields.Char(string="Twikey Profile", required=True, readonly=True)
    twikey_id = fields.Integer(string="Profile Id", readonly=True, index=True)
    twikey_prefix = fields.Integer(string="Profile Prefix", readonly=True, index=True)
    active = fields.Boolean(default=True, readonly=True)
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
        readonly=True,
    )
    twikey_attribute_ids = fields.One2many(
        "twikey.contract.template.attribute",
        "template_id",
        string="Attributes",
    )

    def is_creditcard(self):
        return self.type == "CREDITCARD"

    def ct(self):
        return self.twikey_id

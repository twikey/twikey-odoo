import requests

from odoo import _, exceptions, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    twikey_mandate_ids = fields.One2many("twikey.mandate.details", "partner_id", string="Mandates")
    twikey_inv_ids = fields.One2many(
        "account.move",
        "partner_id",
        readonly=True,
        domain=[("move_type", "=", "out_invoice"), ("twikey_invoice_identifier", "=", True)],
    )

    def action_invite_customer(self):
        self.env["res.config.settings"].twikey_sync_contract_template()
        wizard = self.env["twikey.contract.template.wizard"].create(
            {
                "partner_id": self.id,
            }
        )
        action = self.env.ref("twikey_integration.contract_template_wizard_action").read()[0]
        action["res_id"] = wizard.id
        return action

    def write(self, values):
        res = super(ResPartner, self).write(values)
        if self._context.get("update_feed"):
            return res

        twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
        if twikey_client:
            for rec in self:
                country_id = False
                if values.get("country_id"):
                    country_id = self.env["res.country"].browse(values.get("country_id"))

                data = {
                    "customerNumber": rec.id,
                    "address": values.get("street")
                    if values.get("street")
                    else rec.street
                    if rec.street
                    else "",
                    "city": values.get("city")
                    if values.get("city")
                    else rec.city
                    if rec.city
                    else "",
                    "zip": values.get("zip") if values.get("zip") else rec.zip if rec.zip else "",
                    "country": country_id.code
                    if country_id
                    else rec.country_id.code
                    if rec.country_id
                    else "",
                    "l": values.get("lang") if values.get("lang") else rec.lang,
                }
                if values.get("email") or rec.email:
                    data["email"] = (
                        values.get("email")
                        if values.get("email")
                        else rec.email
                        if rec.email
                        else ""
                    )
                if rec.company_type == "company" and values.get("name"):
                    data["companyName"] = values.get("name") if values.get("name") else ""
                    data["vatno"] = values.get("vat") if values.get("vat") else ""
                elif values.get("name"):  # 'person'
                    customer_name = values.get("name").split(" ")
                    if customer_name and len(customer_name) > 1:
                        data["firstname"] = customer_name[0]
                        data["lastname"] = " ".join(customer_name[1:])
                    else:
                        data["firstname"] = values.get("name")

                if rec.twikey_mandate_ids:
                    mandate_id = rec.twikey_mandate_ids[0]
                    data.update({"mndtId": mandate_id.reference})
                    try:
                        twikey_client.document.update(data)
                    except (ValueError, requests.exceptions.RequestException):
                        raise exceptions.AccessError(
                            _(
                                "The url that this service requested returned an error."
                                " Please check your connection or try after sometime."
                            )
                        )

        return res

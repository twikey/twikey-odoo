import requests

from odoo import exceptions, fields, models

language_dict = {
    "en_US": "en",
    "fr_FR": "fr",
    "nl_NL": "nl",
    "nl_BE": "nl",
    "de_DE": "de",
    "pt_PT": "pt",
    "es_ES": "es",
    "it_IT": "it",
}


class ResPartner(models.Model):
    _inherit = "res.partner"

    twikey_mandate_ids = fields.One2many("twikey.mandate.details", "partner_id", string="Mandates")
    twikey_inv_ids = fields.One2many(
        "account.move",
        "partner_id",
        readonly=True,
        domain=[("move_type", "=", "out_invoice"), ("twikey_invoice_identifier", "=", True)],
    )
    show_create_mandate_invite_button = fields.Boolean(
        compute="_compute_show_create_mandate_invite_button"
    )

    def _compute_show_create_mandate_invite_button(self):
        for record in self:
            record.show_create_mandate_invite_button = True

    def action_invite_customer(self):
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
                street = self.get_street(rec, values)
                city = self.get_city(rec, values)
                zip_code = self.get_zip(rec, values)
                country_code = self.get_country_code(rec, values)
                language = self.get_language(rec, values)

                mandate_data = {
                    "customerNumber": rec.id,
                    "address": street,
                    "city": city,
                    "zip": zip_code,
                    "country": country_code,
                    "l": language,
                }

                if values.get("email") or rec.email:
                    mandate_data["email"] = (
                        values.get("email")
                        if values.get("email")
                        else rec.email
                        if rec.email
                        else ""
                    )

                customer_data = mandate_data
                mobile = self.get_mobile(rec, values)
                if mobile:
                    customer_data["mobile"] = mobile

                if rec.company_type == "company" and values.get("name"):
                    mandate_data["companyName"] = values.get("name") if values.get("name") else ""
                    mandate_data["vatno"] = values.get("vat") if values.get("vat") else ""
                elif values.get("name"):  # 'person'
                    customer_name = values.get("name").split(" ")
                    if customer_name and len(customer_name) > 1:
                        mandate_data["firstname"] = customer_name[0]
                        mandate_data["lastname"] = " ".join(customer_name[1:])
                        customer_data["firstname"] = mandate_data["firstname"]
                        customer_data["lastname"] = mandate_data["lastname"]
                    else:
                        mandate_data["firstname"] = values.get("name")
                        customer_data["firstname"] = mandate_data["firstname"]

                # Update the customer
                if rec.twikey_mandate_ids:
                    twikey_client.document.update_customer(customer_id=rec.id, data=customer_data)

                # Update the mandates
                self.update_mandate(rec=rec, mandate_data=mandate_data, twikey_client=twikey_client)

        return res

    def get_language(self, rec, values):
        language = ""
        if rec.lang:
            language = language_dict.get(rec.lang)
        elif values.get("lang"):
            language = language_dict.get(values.get("lang"))

        return language

    def get_street(self, rec, values):
        street = ""
        if rec.street:
            street = rec.street
        elif values.get("street"):
            street = values.get("street")

        return street

    def get_city(self, rec, values):
        city = ""
        if rec.city:
            city = rec.city
        elif values.get("city"):
            city = values.get("city")

        return city

    def get_zip(self, rec, values):
        zip_code = ""
        if rec.zip:
            zip_code = rec.zip
        elif values.get("zip"):
            zip_code = values.get("zip")

        return zip_code

    def get_country_code(self, rec, values):
        country_code = ""
        if rec.country_id:
            country_code = rec.country_id.code
        elif values.get("country"):
            country_code = self.env["res.country"].browse(values.get("country_id")).code

        return country_code

    def get_mobile(self, rec, values):
        mobile = ""
        if rec.mobile:
            mobile = rec.mobile
        elif values.get("mobile"):
            mobile = values.get("mobile")

        return mobile

    def update_mandate(self, rec, mandate_data, twikey_client):
        if rec.twikey_mandate_ids:
            for mandate in rec.twikey_mandate_ids:
                if mandate.state == "pending":
                    try:
                        # Update mandate in Twikey
                        mandate_data.update({"mndtId": mandate.reference})
                        twikey_client.document.update(mandate_data)

                        # Update mandate in Odoo
                        mandate.zip = rec.zip if rec.zip else False
                        mandate.address = rec.street if rec.street else False
                        mandate.city = rec.city if rec.city else False
                        mandate.country_id = rec.country_id if rec.country_id else False

                    except (ValueError, requests.exceptions.RequestException) as e:
                        raise exceptions.AccessError from e

    def send_twikey_error(self):
        mail_template = self.env.ref("twikey_integration.error_message_mail_twikey_authentication")
        if mail_template:
            users = self.env["res.users"].search([])
            for user in users:
                if user.has_group("base.group_system"):
                    email_values = {"email_to": user.email}

                    mail_template.send_mail(user.id, force_send=True, email_values=email_values)

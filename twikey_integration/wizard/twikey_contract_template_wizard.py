import json
import logging

import requests

from odoo import _, exceptions, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

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


class TwikeyContractTemplateWizard(models.Model):
    _name = "twikey.contract.template.wizard"
    _description = "Wizard for Select Contract Template"

    name = fields.Char()
    template_id = fields.Many2one("twikey.contract.template", string="Contract Template")
    twikey_attribute_ids = fields.One2many(
        related="template_id.twikey_attribute_ids", readonly=False
    )
    partner_id = fields.Many2one(comodel_name="res.partner")

    def prepare_contract_date(self, template_id, current_id, customer):
        contract_data = {
            "ct": template_id.template_id_twikey,
            "l": language_dict.get(customer.lang),
            "customerNumber": current_id,
            "mandateNumber": customer.id if not template_id.mandate_number_required else "",
            "mobile": customer.mobile if customer.mobile else "",
            "address": customer.street if customer.street else "",
            "city": customer.city if customer.city else "",
            "zip": customer.zip if customer.zip else "",
            "country": customer.country_id.code if customer.country_id else "",
        }

        if customer.email:
            contract_data["email"] = customer.email
            contract_data["sendInvite"] = True
        if customer.company_type == "company" and customer.name:
            contract_data["companyName"] = customer.name
            contract_data["coc"] = customer.vat
        elif customer.name:  # 'person'
            customer_name = customer.name.split(" ")
            if customer_name and len(customer_name) > 1:
                contract_data["firstname"] = customer_name[0]
                contract_data["lastname"] = " ".join(customer_name[1:])
            else:
                contract_data["firstname"] = customer.name
        return contract_data

    def action_confirm(self):
        twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
        if twikey_client:
            customer = self.partner_id
            current_id = customer.id
            if customer.parent_id:
                current_id = customer.parent_id.id

            contract_data = self.prepare_contract_date(self.template_id, current_id, customer)

            sp_lst = [
                "x_" + attr.name + "_" + str(self.template_id.template_id_twikey)
                for attr in self.template_id.twikey_attribute_ids
            ]

            lst = []
            for name, _field in self._fields.items():
                if name in sp_lst or name == "template_id":
                    lst.append(name)

            get_fields = self.read(fields=lst, load="_classic_read")
            if get_fields:
                template_id = False
                if get_fields[0].get("template_id"):
                    template_id = get_fields[0].get("template_id")[0]
                get_template_id = self.env["twikey.contract.template"].browse(template_id)
                get_fields[0].pop("id")
                get_fields[0].pop("template_id")
                new_keys = []
                for key, value in get_fields[0].items():
                    model_id = self.env["ir.model"].search(
                        [("model", "=", "twikey.contract.template.wizard")]
                    )
                    field_id = self.env["ir.model.fields"].search(
                        [("name", "=", key), ("model_id", "=", model_id.id)]
                    )
                    if field_id.ttype != "boolean" and not value:
                        get_fields[0].update({key: ""})
                    key_split = key.split("_")
                    if len(key_split) > 0 and key_split[0] == "x":
                        new_keys.append(key_split[1])
                final_dict = dict(zip(new_keys, list(get_fields[0].values())))
                contract_data.update(final_dict)
            try:
                _logger.debug("New mandate creation data: {}".format(contract_data))

                twikey_client.refreshTokenIfRequired()
                response = requests.post(
                    twikey_client.api_base + "/invite",
                    data=contract_data,
                    headers=twikey_client.headers(),
                    timeout=15,
                )
                _logger.info("Creating new mandate with response: %s" % (response.content))
                resp_obj = response.json()
                response_text = json.loads(response.text)
                if "code" in response_text:
                    if "err" in response_text["code"]:
                        raise UserError(_("%s") % (resp_obj.get("message")))
                mandate_id = (
                    self.env["twikey.mandate.details"]
                    .sudo()
                    .create(
                        {
                            "contract_temp_id": get_template_id.id,
                            "lang": customer.lang,
                            "partner_id": current_id,
                            "reference": resp_obj.get("mndtId"),
                            "url": resp_obj.get("url"),
                            "zip": customer.zip if customer.zip else False,
                            "address": customer.street if customer.street else False,
                            "city": customer.city if customer.city else False,
                            "country_id": customer.country_id.id if customer.country_id else False,
                        }
                    )
                )
                mandate_id.with_context(update_feed=True).write(get_fields[0])
                view = self.env.ref("twikey_integration.success_message_wizard")
                context = dict(self._context or {})
                context["message"] = "Mandate Invitation Created Successfully."
                return self.succes_message(view, context)

            except (ValueError, requests.exceptions.RequestException) as e:
                _logger.error("Exception raised while creating a new Mandate %s" % (e))
                raise exceptions.AccessError from e

    def succes_message(self, view, context):
        return {
            "name": "Success",
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "success.message.wizard",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "context": context,
        }

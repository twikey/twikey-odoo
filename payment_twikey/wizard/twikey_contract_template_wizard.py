import logging

from odoo import _, exceptions, fields, models

from ..twikey.client import TwikeyError
from ..utils import get_error_msg, get_success_msg, get_twikey_customer

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
    reference = fields.Char(string="Mandate number")
    twikey_attribute_ids = fields.One2many(
        related="template_id.twikey_attribute_ids", readonly=False
    )
    partner_id = fields.Many2one(comodel_name="res.partner")

    def action_confirm(self):
        payload = get_twikey_customer(self.partner_id)
        payload["ct"] = self.template_id.template_id_twikey
        if self.template_id.mandate_number_required:
            payload["mandateNumber"] = self.reference
        if payload["email"]:
            payload["sendInvite"] = True

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
            payload.update(final_dict)
        try:
            _logger.debug("New mandate creation data: {}".format(payload))
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
            if twikey_client:
                twikey_client.refreshTokenIfRequired()
                resp_obj = twikey_client.document.create(payload)
                _logger.info("Creating new mandate with response: %s" % (resp_obj))
                mandate_id = (
                    self.env["twikey.mandate.details"]
                    .sudo()
                    .create(
                        {
                            "contract_temp_id": self.template_id.id,
                            "lang": self.partner_id.lang,
                            "partner_id": payload.get("customerNumber"),
                            "reference": resp_obj.get("mndtId"),
                            "url": resp_obj.get("url"),
                            "zip": self.partner_id.zip if self.partner_id.zip else False,
                            "address": self.partner_id.street if self.partner_id.street else False,
                            "city": self.partner_id.city if self.partner_id.city else False,
                            "country_id": self.partner_id.country_id.id if self.partner_id.country_id else False,
                        }
                    )
                )
                mandate_id.with_context(update_feed=True).write(get_fields[0])
                return get_success_msg("Mandate Invitation Created Successfully.")

        except TwikeyError as e:
            errmsg = "Exception raised while creating a new Mandate:\n%s" % (e)
            self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Configuration",body=errmsg,)
            _logger.error(errmsg)
            return get_error_msg(str(e), 'Exception raised while creating a new Mandate', sticky=True)
